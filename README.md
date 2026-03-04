# DSDJ

**Use a PS5 DualSense controller as a full DJ interface — MIDI bridge to Mixxx, real-time React web UI**

![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Overview

DSDJ turns a PS5 DualSense controller into a capable two-deck DJ controller. Every physical input — analog triggers, thumbsticks, touchpad swipes, the gyroscope, buttons, and the D-pad — is mapped to a meaningful DJ action and translated in real time into MIDI messages that Mixxx understands. No custom drivers, no firmware flashing: the DualSense is read as a standard HID device over USB, and Mixxx receives a standard virtual MIDI port.

The bridge is a Python asyncio application that sits between the hardware and the audio engine. It reads raw controller state via `pydualsense`, normalizes every value (deadzones, exponential stick curves, touchpad direction locking, gyro tilt angles), maps normalized inputs to DJ actions through a stateful `InputMapper`, and forwards those actions to Mixxx over a virtual ALSA MIDI port created by `python-rtmidi`. A parallel broadcast loop pushes a 60fps JSON state snapshot to any connected WebSocket clients.

The React web UI connects over WebSocket and renders a live dashboard: deck A and B state with BPM, volume, EQ, and hot cue indicators; an animated crossfader; an effects panel showing gyro axis bindings and wet/dry levels; and a DualSense silhouette that relabels itself dynamically when EQ mode or gyro mode is active. The UI is served from the same FastAPI process that hosts the WebSocket endpoint, so one port does everything.

---

## Architecture

```
DualSense (HID/USB)
    |  pydualsense  [run_in_executor]
    v
controller_loop()  -->  action_queue  (asyncio.Queue)
                                |
                   +------------+------------+
                   v                         v
           midi_loop()              state_broadcast_loop()
           (python-rtmidi)          (asyncio.Queue maxsize=1)
                   |                         |
                   v                         v
                Mixxx                 WebSocket clients
             (MIDI input)              (React UI)
```

Key design decisions:

- **Full asyncio**: one event loop, all subsystems are coroutine tasks running under a supervisor that restarts individual tasks on recoverable failures.
- **Blocking I/O isolation**: pydualsense HID reads run via `loop.run_in_executor(None, ...)` so they never stall the event loop. python-rtmidi sends are microsecond-duration synchronous calls made directly from async context.
- **Latest-value queue**: the state broadcast queue has `maxsize=1`. A new snapshot overwrites any unread old snapshot. The UI always receives the current state, never a stale backlog.
- **Fire and forget**: `controller_loop` emits actions and immediately loops back. It never awaits downstream results.

---

## Hardware and Software Requirements

### Hardware

- PS5 DualSense controller connected via **USB** (Bluetooth is not supported)

### Software

| Requirement | Version | Notes |
|---|---|---|
| Linux | any modern kernel | udev rules required for HID access without root |
| Python | 3.12+ | `pydualsense`, `python-rtmidi`, `fastapi`, `uvicorn` |
| Node.js | 18+ | only needed to rebuild the React UI |
| Mixxx | 2.4+ | open-source DJ software, available on Arch as `mixxx` |
| ALSA | system package | provides virtual MIDI port infrastructure |

### udev rule (one-time setup)

Without this, pydualsense requires root. Create `/etc/udev/rules.d/70-dualsense.rules`:

```
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0ce6", MODE="0660", GROUP="input"
```

Then reload: `sudo udevadm control --reload-rules && sudo udevadm trigger`

Add your user to the `input` group: `sudo usermod -aG input $USER` (log out and back in).

---

## Quick Start

### 1. Clone and set up Python environment

```bash
git clone https://github.com/star-lance/DSDJ.git
cd DSDJ
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Build the React UI

```bash
cd ui && npm install && npm run build && cd ..
```

A pre-built `ui/dist/` is included in the repository, so this step is only required if you modify the UI source.

### 3. Install the Mixxx mapping

```bash
cp src/mixxx/midi_mapping.xml ~/.mixxx/controllers/DualSense-DJ.midi.xml
cp src/mixxx/midi_mapping.js ~/.mixxx/controllers/DualSense-DJ-scripts.js
```

### 4. Run

```bash
python src/main.py
```

The MIDI port named **DualSense DJ** will appear in ALSA. Open Mixxx, connect the controller (see [Mixxx Setup](#mixxx-setup)), then open `http://127.0.0.1:8765` in a browser.

---

## Configuration (`config.yaml`)

All tuneable parameters live in `config.yaml` at the project root. The file is loaded once at startup; restart the process to apply changes.

```yaml
controller:
  connection: "usb"               # Connection mode. Only "usb" is supported.
  deadzone: 0.08                  # Stick deadzone radius (0.0–1.0 normalized).
                                  # Values within this distance from center are
                                  # treated as zero and the remaining range is
                                  # rescaled to fill 0.0–1.0.
  touchpad_crossfader_smoothing: 0.15
                                  # Exponential moving average factor for the
                                  # touchpad crossfader (0 = frozen, 1 = raw).
                                  # Lower values reduce jitter at the cost of
                                  # slightly increased latency.
  direction_lock_threshold: 0.04  # Normalized touchpad distance that must be
                                  # exceeded before the direction (horizontal /
                                  # vertical) is committed. Prevents accidental
                                  # axis switching on diagonal touches.

midi:
  port_name: "DualSense DJ"       # Name of the virtual ALSA MIDI output port.
                                  # Must match the device name Mixxx is
                                  # configured to listen on.
  channel: 0                      # MIDI channel (0-indexed). 0 = MIDI channel 1
                                  # for Deck A; channel 1 = MIDI channel 2 for
                                  # Deck B. Used directly in the status byte.

haptics:
  enabled: false                  # Phase 2. Has no effect in the current release.

adaptive_triggers:
  enabled: false                  # Phase 2. Has no effect in the current release.

gyro:
  roll_unit: 0                    # EffectRack1 unit index (0-indexed) that gyro
                                  # roll (Z-axis) controls by default. Cycled
                                  # at runtime with L3 while gyro is active.
  roll_target: "mix"              # Mixxx effect parameter key for roll axis.
  pitch_unit: 1                   # EffectRack1 unit index for gyro pitch (X-axis).
  pitch_target: "parameter1"      # Mixxx effect parameter key for pitch axis.
  tilt_range_degrees: 45.0        # Controller tilt angle (degrees from reference)
                                  # that maps to full-scale (1.0) effect output.

filter:
  stick_curve: "exponential"      # Response curve applied to stick filter/EQ
                                  # values. "linear" passes values unchanged;
                                  # "exponential" applies a power curve for
                                  # finer control near center.
  stick_exponent: 2.0             # Exponent used when stick_curve is
                                  # "exponential". Higher values give more
                                  # resolution near center.

server:
  host: "127.0.0.1"              # Host the FastAPI/WebSocket server binds to.
  port: 8765                      # HTTP and WebSocket port (production build).
  ui_port: 5173                   # Vite dev server port (development only).
```

---

## Controller Mapping

The DualSense is mapped to two decks (A and B) plus master controls. Holding **Options** activates EQ mode, which re-purposes the thumbsticks and touchpad vertical swipe. All other controls are unaffected by EQ mode.

| Input | Normal Mode | Options Held (EQ Mode) |
|---|---|---|
| L2 analog | Deck A Volume | Deck A Volume |
| R2 analog | Deck B Volume | Deck B Volume |
| L1 | Deck A Play/Pause | Deck A Play/Pause |
| R1 | Deck B Play/Pause | Deck B Play/Pause |
| Left Stick Y | Deck A Filter | Deck A EQ Low |
| Left Stick X | Deck A Pitch Nudge | Deck A EQ High |
| Right Stick Y | Deck B Filter | Deck B EQ Low |
| Right Stick X | Deck B Pitch Nudge | Deck B EQ High |
| L3 (stick click) | Deck A Sync toggle | Cycle gyro roll binding unit (if gyro on) |
| R3 (stick click) | Deck B Sync toggle | Cycle gyro pitch binding unit (if gyro on) |
| D-Pad Up/Right/Down/Left | Deck A Hot Cues 1–4 | same |
| Triangle/Circle/Cross/Square | Deck B Hot Cues 1–4 | same |
| Touchpad horizontal swipe | Crossfader | Crossfader |
| Touchpad vertical swipe | Track Browse | EQ Low / Mid / High (by touch zone) |
| Touchpad click left half | Load track to Deck A | Load track to Deck A |
| Touchpad click right half | Load track to Deck B | Load track to Deck B |
| Touchpad two-finger tap | Toggle UI view | Toggle UI view |
| Create | Loop toggle (active deck) | Loop toggle (active deck) |
| Options | — (mode shift, no action) | — |
| Mute | Gyro enable/disable toggle | Gyro enable/disable toggle |
| Gyro roll (Z-axis) | — (gyro off) | — (gyro off) |
| Gyro pitch (X-axis) | — (gyro off) | — (gyro off) |
| Gyro roll (Z-axis) | Effect wet/dry (gyro on) | Effect wet/dry (gyro on) |
| Gyro pitch (X-axis) | Effect parameter1 (gyro on) | Effect parameter1 (gyro on) |
| PS | Reserved | Reserved |

---

## Mixxx Setup

### 1. Copy the mapping files

```bash
cp src/mixxx/midi_mapping.xml ~/.mixxx/controllers/DualSense-DJ.midi.xml
cp src/mixxx/midi_mapping.js ~/.mixxx/controllers/DualSense-DJ-scripts.js
```

### 2. Connect in Mixxx

1. Start Mixxx.
2. Open **Preferences** (Ctrl+P) → **Controllers**.
3. Select **DualSense DJ** from the device list on the left.
4. In the preset dropdown, choose **DualSense DJ**.
5. Click **Enable**.
6. Click **Apply**.

### 3. Verify the mapping

With `python src/main.py` running in a terminal:

| Action | Expected Mixxx response |
|---|---|
| Press L1 | Deck 1 play/pause toggles |
| Press R1 | Deck 2 play/pause toggles |
| Hold L2 trigger | Deck 1 volume rises |
| Slide touchpad left to right | Crossfader moves |
| Press D-pad Up | Deck 1 hot cue 1 set/jump |
| Press Triangle | Deck 2 hot cue 1 set/jump |
| Press Create | Deck 1 beat loop toggles |
| Press L3 | Deck 1 sync toggles |

---

## React UI

The web UI is a React 18 application styled with Tailwind CSS and bundled with Vite. It connects to the Python backend over WebSocket and renders the full system state at up to 60fps.

### URLs

| Mode | URL |
|---|---|
| Production (served by FastAPI) | http://127.0.0.1:8765 |
| Development (Vite hot-reload) | http://localhost:5173 |

### What the UI shows

- **Connected badge**: green when the WebSocket is live, red when disconnected (auto-reconnects every 2 seconds).
- **Deck A / Deck B panels**: play state, BPM, volume level, filter position, EQ low/mid/high, hot cue indicators (1–4), loop active state. Deck A uses cyan tones, Deck B uses magenta tones.
- **Crossfader**: animated horizontal slider with center-zone highlight.
- **Effects panel**: gyro enabled state, roll and pitch axis bindings (unit index + target parameter), wet/dry level, parameter level.
- **Controller map**: DualSense silhouette with button labels that update dynamically to reflect the current mode (normal, EQ mode, gyro on).
- **Library**: currently loaded track name per deck. Full Mixxx library browsing is planned for Phase 2.

### Running the dev server

```bash
cd ui && npm run dev
```

The Vite dev server proxies WebSocket connections to the Python backend on port 8765. Changes to `ui/src/` hot-reload instantly.

---

## Running Tests

### Unit tests (no hardware required)

```bash
pytest tests/ -v --ignore=tests/integration
```

All unit tests mock hardware dependencies and can run in any environment with the Python venv active.

### Integration tests (DualSense and ALSA required)

```bash
pytest tests/integration/ -v -s -m integration
```

These tests require a connected DualSense and `python src/main.py` running. They verify that:

- The controller's sticks, triggers, touchpad, and gyro all produce readings.
- The **DualSense DJ** virtual MIDI port appears in ALSA (`aconnect -l | grep DualSense`).

### WebSocket end-to-end check

With `python src/main.py` running, move the touchpad and watch crossfader values stream live:

```bash
python -c "
import asyncio, json, websockets

async def main():
    async with websockets.connect('ws://127.0.0.1:8765/ws') as ws:
        for _ in range(5):
            msg = json.loads(await ws.recv())
            print('crossfader:', msg['data']['crossfader'])

asyncio.run(main())
"
```

---

## Project Structure

```
DSDJ/
|
|-- config.yaml                          # All runtime configuration (see Configuration section)
|-- requirements.txt                     # Python dependencies
|-- pytest.ini                           # pytest configuration (asyncio mode, markers)
|
|-- src/
|   |-- main.py                          # Entry point: asyncio event loop, task supervisor, shutdown
|   |-- controller.py                    # DualSense HID wrapper; normalizes all inputs to ControllerState
|   |-- mapping.py                       # InputMapper: ControllerState -> list[DJAction]; all mode logic
|   |-- state.py                         # Thread-safe AppState/DeckState; update_from_action(); to_dict()
|   |-- midi_bridge.py                   # Virtual ALSA MIDI port; send_cc/note_on/note_off/send_action
|   |-- server.py                        # FastAPI app: serves ui/dist/, hosts /ws WebSocket endpoint
|   |-- haptics.py                       # HapticEngine stub (Phase 2, currently empty)
|   |-- mixxx/
|   |   |-- midi_mapping.xml             # Mixxx 2.4 MIDI preset (all CC and Note mappings)
|   |   |-- midi_mapping.js              # Required Mixxx scripting stub (init/shutdown hooks)
|
|-- ui/
|   |-- src/
|   |   |-- App.jsx                      # Root component: layout, WebSocket state, view routing
|   |   |-- main.jsx                     # React 18 entry point
|   |   |-- index.css                    # Tailwind base styles
|   |   |-- components/
|   |   |   |-- DeckDisplay.jsx          # Per-deck state panel (BPM, play, volume, EQ, hot cues, loop)
|   |   |   |-- Crossfader.jsx           # Animated crossfader slider
|   |   |   |-- EffectsPanel.jsx         # Gyro bindings, wet/dry and parameter levels
|   |   |   |-- ControllerMap.jsx        # DualSense silhouette with dynamic mode labels
|   |   |   |-- Library.jsx              # Currently loaded track display (Phase 2: full library)
|   |   |-- hooks/
|   |       |-- useWebSocket.js          # Connect, parse, auto-reconnect (2s), expose {state, connected}
|   |-- dist/                            # Pre-built production bundle (served by FastAPI)
|   |-- vite.config.js                   # Vite build configuration
|   |-- package.json                     # Node dependencies (React, Tailwind, Vite)
|
|-- tests/
|   |-- test_state.py                    # Unit tests for StateManager and DeckState
|   |-- test_controller.py               # Unit tests for ControllerState normalization
|   |-- test_midi_bridge.py              # Unit tests for MIDI message construction
|   |-- test_mapping.py                  # Unit tests for InputMapper, edge detection, direction lock
|   |-- test_main.py                     # Unit tests for supervisor and startup logic
|   |-- integration/
|       |-- test_controller_live.py      # Hardware test: reads live DualSense inputs
|       |-- test_midi_live.py            # Hardware test: verifies ALSA port creation
|
|-- docs/
    |-- plans/
    |   |-- 2026-03-03-dualsense-dj-design.md  # Full architecture and module design document
    |-- dualsense-dj-implementation-guide.md    # Step-by-step implementation reference
```

---

## Gyro Effects

The DualSense gyroscope drives two Mixxx effect parameters simultaneously when gyro mode is active.

**Enabling gyro**: press **Mute**. The gyro indicator in the UI lights up and `AppState.gyro_enabled` flips to `true`. Press Mute again to disable.

**What the axes do**:

- **Roll (Z-axis)**: tilting the controller left or right controls the **wet/dry mix** of the target effect unit. The reference tilt is captured at the moment gyro is enabled, so the neutral position is wherever you hold the controller when you press Mute.
- **Pitch (X-axis)**: tilting the controller forward or backward controls **effect parameter 1** of its target effect unit.

**Tilt range**: `gyro.tilt_range_degrees` (default `45.0`) defines the angle from the reference that maps to full-scale (1.0) MIDI output. Tilting beyond 45 degrees clips to 1.0.

**Cycling effect targets**: while gyro is active:
- **L3** cycles the roll axis through EffectRack1 units 0–3. The current binding is shown in the Effects panel.
- **R3** cycles the pitch axis through EffectRack1 units 0–3 independently.

When gyro is disabled, L3 and R3 revert to their normal function (Deck A / Deck B sync toggle).

Default bindings from `config.yaml`:

| Axis | Default unit | Default parameter |
|---|---|---|
| Roll (Z) | EffectRack1_EffectUnit1 | mix (wet/dry) |
| Pitch (X) | EffectRack1_EffectUnit2 | parameter1 |

---

## EQ Mode

Holding **Options** shifts the controller into EQ mode. Options itself emits no action — it is a pure mode modifier. Release Options to return to normal mode.

**Thumbsticks in EQ mode**:

| Stick | Axis | Normal mode | EQ mode |
|---|---|---|---|
| Left stick | Y-axis | Deck A Filter | Deck A EQ Low |
| Left stick | X-axis | Deck A Pitch Nudge | Deck A EQ High |
| Right stick | Y-axis | Deck B Filter | Deck B EQ Low |
| Right stick | X-axis | Deck B Pitch Nudge | Deck B EQ High |

Mid EQ for each deck is not on the sticks. It is on the touchpad.

**Touchpad vertical swipe in EQ mode**:

The touchpad is divided into three horizontal zones. When you touch the touchpad in EQ mode and swipe vertically, the zone where the swipe started determines which EQ band is controlled:

| Touch start X position | Zone | EQ band controlled |
|---|---|---|
| 0.0 – 0.33 (left third) | Low zone | EQ Low |
| 0.33 – 0.67 (center third) | Mid zone | EQ Mid |
| 0.67 – 1.0 (right third) | High zone | EQ High |

The direction lock mechanism prevents accidental cross-axis interference: once a swipe commits to vertical, it stays vertical for the duration of the touch, and the EQ zone is fixed at the start position.

The ControllerMap component in the UI displays an EQ MODE overlay when Options is held, relabelling the stick and touchpad zones to reflect the current bindings.

---

## Phase 2 / Roadmap

The following features are designed but intentionally deferred to Phase 2:

- **Haptic feedback**: `src/haptics.py` is scaffolded with an empty `HapticEngine` class. Phase 2 will implement beat-pulse haptics synchronized to Mixxx's beat clock.
- **Adaptive trigger resistance**: the DualSense adaptive triggers will provide physical resistance feedback (e.g., increasing resistance as volume approaches clip level).
- **Beat sync haptics**: rumble pulses locked to the BPM of the active deck.
- **Mixxx state feedback**: read Mixxx's internal state via OSC or the SQLite library database so the UI displays accurate track position, waveform, and BPM rather than relying solely on MIDI echo.
- **Full Mixxx library view**: the `Library.jsx` component currently shows only the loaded track per deck. Phase 2 will add full library browsing, search, and playlist navigation from the UI.
- **14-bit MIDI CC**: higher resolution volume and EQ control using 14-bit MIDI CC pairs for finer mixing precision.

---

## License

MIT — see [LICENSE](LICENSE) for full text.
