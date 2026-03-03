# DualSense DJ Controller — Design Document

**Date**: 2026-03-03
**Status**: Approved

---

## 1. Project Purpose

Build a DJ controller system using a PS5 DualSense controller as the hardware interface, wrapping Mixxx (open-source DJ software) as the audio engine. A Python middleware layer reads DualSense inputs, translates them to MIDI messages sent to Mixxx via a virtual MIDI port, and broadcasts real-time state to a React web UI. Haptic/adaptive trigger feedback is deferred to Phase 2.

---

## 2. Architecture

```
DualSense (HID/USB)
    │  pydualsense (run_in_executor)
    ▼
controller_loop() ──► action_queue (asyncio.Queue)
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
            midi_loop()           state_broadcast_loop()
            (python-rtmidi)           (asyncio.Queue maxsize=1)
                    │                       │
                    ▼                       ▼
                 Mixxx               WebSocket clients
              (MIDI input)            (React UI)
```

### Key architectural decisions

- **Full asyncio**: One event loop, all subsystems are coroutine tasks.
- **Blocking I/O isolation**: pydualsense HID reads run via `loop.run_in_executor(None, ...)`. python-rtmidi sends are synchronous but microsecond-duration; called directly from async context.
- **Latest-value queue**: State broadcast queue has `maxsize=1`. New state overwrites unread old state. The UI always gets the current snapshot, never a backlog.
- **Fire and forget**: `controller_loop` emits actions into the pipeline and immediately loops. It never awaits downstream results.
- **Task supervisor**: All tasks launched under a supervisor that restarts individual tasks on recoverable crashes (logged as warnings). Controller disconnection is fatal and surfaces to the user explicitly.
- **Haptics**: Deferred to Phase 2. `haptics.py` scaffolded but empty.

---

## 3. Tech Stack

| Component | Choice | Version |
|---|---|---|
| Python env | venv | system Python 3.12+ |
| Controller | pydualsense | latest PyPI |
| MIDI | python-rtmidi | latest PyPI |
| Web server | FastAPI + uvicorn | latest PyPI |
| Config | PyYAML | latest PyPI |
| DJ engine | Mixxx | 2.4+ (Arch package) |
| UI bundler | Vite | latest |
| UI framework | React 18 | latest |
| UI styling | Tailwind CSS | latest |

---

## 4. Module Design

### 4.1 `src/controller.py`

Wraps pydualsense. Exposes a single synchronous `read_state() -> ControllerState` method that normalizes all inputs. Called from `controller_loop` via `run_in_executor`.

**Normalization:**
- Sticks: raw 0–255 → -1.0 to 1.0, deadzone applied and range rescaled
- Triggers: raw 0–255 → 0.0 to 1.0
- Touchpad: raw (0–1919, 0–942) → (0.0–1.0, 0.0–1.0)
- Gyro: degrees/second as provided by pydualsense
- Buttons: boolean

### 4.2 `src/state.py`

Thread-safe central state container. Two dataclasses: `DeckState` and `AppState`. `StateManager` wraps `AppState` with a `threading.Lock`.

**`update_from_action(action: DJAction)`**: Inline translation table mapping each `ActionType` to the correct `AppState` field. `PLAY_PAUSE` is a toggle (read-then-write). After any update, puts a state snapshot on the broadcast queue.

**`to_dict()`**: Uses `dataclasses.asdict()` for JSON serialization.

### 4.3 `src/mapping.py`

Processes `ControllerState` → `list[DJAction]`. Maintains internal state:
- `prev_state`: for button edge detection
- `smoothed_crossfader`: exponential moving average
- `gyro_enabled`: bool, toggled by Mute button tap
- `gyro_reference`: accelerometer snapshot captured when gyro is enabled (for tilt reference)
- `gyro_roll_binding`: `GyroBinding(unit=0, target="mix")`
- `gyro_pitch_binding`: `GyroBinding(unit=1, target="parameter1")`
- `touchpad_direction_lock`: `None | "horizontal" | "vertical"`
- `touchpad_start`: `(x, y)` of current touch, reset on lift

**Gyro binding cycling**: While gyro is enabled, L3 press cycles `gyro_roll_binding.unit` through 0–3. R3 press cycles `gyro_pitch_binding.unit` through 0–3. When gyro is disabled, L3/R3 are sync toggles as normal.

#### Touchpad directional lock

On touch start: record `touchpad_start`, set `touchpad_direction_lock = None`.

Each frame while touching:
1. Compute `dx = current_x - start_x`, `dy = current_y - start_y`
2. If lock is `None` and `sqrt(dx²+dy²) > 0.04` (normalized):
   - `abs(dx) > abs(dy)` → lock `HORIZONTAL`
   - `abs(dy) > abs(dx)` → lock `VERTICAL`, record `eq_zone` from `start_x`:
     - 0.0–0.33 → Low, 0.33–0.67 → Mid, 0.67–1.0 → High
3. If lock is `HORIZONTAL`: drive crossfader from `current_x`
4. If lock is `VERTICAL`:
   - **Normal mode**: emit `TRACK_BROWSE` from `dy` delta (throttled to 20/sec)
   - **Options held**: emit EQ action for `eq_zone` from `current_y` absolute value

On touch end: reset `touchpad_direction_lock = None`, `touchpad_start = None`.

#### Full input mapping summary

| Input | Normal mode | Options held |
|---|---|---|
| L2 analog | Deck A Volume | Deck A Volume |
| R2 analog | Deck B Volume | Deck B Volume |
| L1 | Deck A Play/Pause | Deck A Play/Pause |
| R1 | Deck B Play/Pause | Deck B Play/Pause |
| Left Stick Y | Deck A Filter | Deck A EQ Low |
| Left Stick X | Deck A Pitch Nudge | Deck A EQ High |
| Right Stick Y | Deck B Filter | Deck B EQ Low |
| Right Stick X | Deck B Pitch Nudge | Deck B EQ High |
| L3 | Deck A Sync | Cycle gyro_roll_binding.unit (if gyro on) |
| R3 | Deck B Sync | Cycle gyro_pitch_binding.unit (if gyro on) |
| D-Pad | Deck A Hot Cues 1–4 | same |
| △ ○ ✕ □ | Deck B Hot Cues 1–4 | same |
| Touchpad H-swipe | Crossfader | Crossfader |
| Touchpad V-swipe | Track Browse | EQ Low/Mid/High (by zone) |
| Touchpad Click L | Load → Deck A | Load → Deck A |
| Touchpad Click R | Load → Deck B | Load → Deck B |
| Two-finger tap | Toggle UI view | Toggle UI view |
| Gyro Roll (Z) | — | — |
| Gyro Pitch (X) | — | — |
| (Gyro enabled) Roll Z | gyro_roll_binding target | same |
| (Gyro enabled) Pitch X | gyro_pitch_binding target | same |
| Create | Loop (active deck) | Loop (active deck) |
| Options | — (mode shift) | — |
| Mute | Gyro toggle | Gyro toggle |
| PS | Reserved | Reserved |

### 4.4 `src/midi_bridge.py`

Creates a virtual MIDI output port ("DualSense DJ") via python-rtmidi. Mixxx connects to this port. Exposes `send_cc`, `send_note_on`, `send_note_off`, and `send_action(action, binding=None)`. `send_action` builds Mixxx group strings dynamically using `GyroBinding.unit` for effect actions.

### 4.5 `src/server.py`

FastAPI app with:
- `GET /` → serves built React UI from `ui/dist/`
- `WS /ws` → WebSocket endpoint

`broadcast_loop` consumes the state queue and sends JSON to all connected clients. Throttled to 60fps. Disconnected clients removed silently.

Message format:
```json
{
  "type": "state_update",
  "data": { ...AppState as dict... }
}
```

### 4.6 `src/haptics.py`

Scaffolded with empty `HapticEngine` class. Phase 2 implementation. Adaptive trigger setup deferred.

### 4.7 `src/main.py`

Entry point. Creates event loop, launches all tasks under supervisor, handles SIGINT/SIGTERM for clean shutdown.

```python
async def main():
    config = load_config()
    state_manager = StateManager()
    controller = DualSenseController(config)
    midi_bridge = MIDIBridge(config)
    mapper = InputMapper(config)
    server = WebSocketServer(state_manager, config)

    await asyncio.gather(
        controller_loop(controller, mapper, midi_bridge, state_manager),
        broadcast_loop(server, state_manager),
        server.serve(),
        return_exceptions=False
    )
```

### 4.8 `src/mixxx/midi_mapping.xml`

Targets Mixxx 2.4. Covers all CC and Note mappings for both decks plus master. Effect groups use `[EffectRack1_EffectUnit{N}]` with N determined dynamically — the XML covers Unit1 and Unit2 for the default gyro bindings. Additional units can be added.

### 4.9 `src/mixxx/midi_mapping.js`

Minimal valid Mixxx scripting stub:
```javascript
var DualSenseDJ = {};
DualSenseDJ.init = function(id, debugging) {};
DualSenseDJ.shutdown = function(id) {};
```

---

## 5. React UI

**Components:**
- `App.jsx`: Layout, WebSocket state, view routing
- `DeckDisplay.jsx`: Per-deck state (track info, BPM, play, volume, filter, EQ, hot cues, loop)
- `Crossfader.jsx`: Animated horizontal slider, center zone highlight
- `EffectsPanel.jsx`: Gyro state, both axis bindings displayed, wet/dry + parameter levels
- `ControllerMap.jsx`: DualSense silhouette with current mode labels
- `Library.jsx`: Shows currently loaded track per deck only (Phase 2: full Mixxx library)
- `hooks/useWebSocket.js`: Connect, parse, reconnect (2s), expose `{ state, connected }`

**Color scheme**: Deck A = cyan tones, Deck B = magenta tones.

---

## 6. State `update_from_action` translation table

| ActionType | State field updated |
|---|---|
| VOLUME | `deck_a.volume` or `deck_b.volume` |
| CROSSFADER | `crossfader` |
| FILTER | `deck_a.filter_value` or `deck_b.filter_value` |
| PITCH_NUDGE | no persistent state (transient) |
| EQ_LOW | `deck_a.eq_low` or `deck_b.eq_low` |
| EQ_MID | `deck_a.eq_mid` or `deck_b.eq_mid` |
| EQ_HIGH | `deck_a.eq_high` or `deck_b.eq_high` |
| PLAY_PAUSE | toggle `deck_a.playing` or `deck_b.playing` |
| SYNC_TOGGLE | toggle `deck_a.sync_enabled` or `deck_b.sync_enabled` |
| TRACK_LOAD | no state change (Mixxx handles it) |
| TRACK_BROWSE | no persistent state (transient) |
| HOT_CUE | `deck_a.hot_cues[index]` or `deck_b.hot_cues[index]` |
| LOOP_TOGGLE | toggle `deck_a.loop_active` or `deck_b.loop_active` |
| GYRO_TOGGLE | `gyro_enabled` |
| EFFECT_WET_DRY | `effect_wet_dry` |
| EFFECT_PARAMETER | `effect_parameter` |

---

## 7. Error Handling

- **Controller disconnect**: `controller_loop` catches exception, logs, broadcasts `connected: false` to UI, retries every 2s.
- **MIDI port failure**: Fatal on startup if port can't be created. Non-fatal if Mixxx isn't listening (messages silently dropped).
- **WebSocket client disconnect**: Removed from connection list silently.
- **Task crash**: Supervisor logs and restarts individual tasks. Controller disconnect is the only exception that triggers full shutdown.

---

## 8. Implementation Order

1. Project scaffolding (venv, directory structure, config.yaml, requirements.txt)
2. `state.py` — no external dependencies
3. `controller.py` + `test_controller.py`
4. `midi_bridge.py` + `test_midi.py`
5. `mapping.py` (depends on state, controller types, midi types)
6. `main.py` (wires everything, asyncio supervisor)
7. Mixxx XML + JS stub
8. `server.py` + WebSocket broadcast loop
9. React UI
10. Integration testing and tuning

---

## 9. Out of Scope (Phase 2)

- Haptic feedback (`haptics.py` scaffolded only)
- Adaptive trigger resistance
- Beat pulse haptics
- Mixxx state feedback (OSC/SQLite) for accurate UI state
- Full Mixxx library in React UI
- 14-bit MIDI CC for higher volume resolution
