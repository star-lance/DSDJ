# DualSense DJ Controller — Implementation Guide

## Project Overview

Build a DJ controller system that uses a PlayStation 5 DualSense controller as the hardware interface, wrapping around **Mixxx** (open-source DJ software) as the audio engine. A Python middleware layer reads DualSense inputs via `pydualsense`, translates them to MIDI messages sent to Mixxx via a virtual MIDI port, and writes haptic/adaptive trigger feedback back to the controller. A web-based UI (React + FastAPI + WebSocket) displays deck state, waveforms, and the current input mapping.

---

## Architecture

```
┌─────────────────┐      USB/BT       ┌──────────────────────┐
│  DualSense      │◄──────────────────►│  Controller Layer    │
│  Controller     │   pydualsense      │  (Python)            │
└─────────────────┘   read inputs +    │                      │
                      write haptics    │  Reads all inputs,   │
                                       │  normalizes values,  │
                                       │  manages deck state  │
                                       └──────────┬───────────┘
                                                  │
                                                  ▼
                                       ┌──────────────────────┐
                                       │  Translation Layer   │
                                       │  (Python)            │
                                       │                      │
                                       │  Maps normalized     │
                                       │  inputs to DJ        │
                                       │  actions + MIDI CCs  │
                                       └──────┬───────┬───────┘
                                              │       │
                              ┌───────────────┘       └────────────┐
                              ▼                                    ▼
                   ┌─────────────────────┐            ┌────────────────────┐
                   │  Virtual MIDI Port  │            │  WebSocket Server  │
                   │  (python-rtmidi)    │            │  (FastAPI)         │
                   │                     │            │                    │
                   │  Sends MIDI CC/     │            │  Broadcasts state  │
                   │  Note messages      │            │  to UI clients     │
                   └──────────┬──────────┘            └─────────┬──────────┘
                              │                                 │
                              ▼                                 ▼
                   ┌─────────────────────┐            ┌────────────────────┐
                   │  Mixxx              │            │  Web UI (React)    │
                   │  DJ Engine          │            │                    │
                   │                     │            │  Deck display,     │
                   │  Audio playback,    │            │  waveforms,        │
                   │  mixing, effects,   │            │  input mapping     │
                   │  library            │            │  overlay           │
                   └─────────────────────┘            └────────────────────┘
```

### Why This Architecture

- **Mixxx as engine**: Open-source, Linux-native, mature audio engine with full MIDI support. No need to build audio playback, beatgrid detection, library management, or effects processing from scratch.
- **Virtual MIDI bridge**: Mixxx already understands MIDI natively. Using python-rtmidi to create a virtual MIDI port means Mixxx sees the DualSense as a standard MIDI controller. This avoids any custom Mixxx plugin development.
- **Separate UI**: Mixxx has its own UI, but we want a custom display optimized for the DualSense mapping. The web UI runs alongside Mixxx and shows what each button is currently mapped to, current deck states, and a visual crossfader/EQ display.

---

## Dependencies

### System Packages (Arch Linux)

```bash
# DJ Engine
sudo pacman -S mixxx

# Audio (should already be present on an audio production system)
# Ensure JACK or PipeWire is running — Mixxx needs a proper audio backend

# MIDI
sudo pacman -S alsa-utils   # for aconnect to verify virtual MIDI ports

# Python
sudo pacman -S python python-pip

# HID access (DualSense)
sudo pacman -S hidapi

# Node.js (for React UI build)
sudo pacman -S nodejs npm
```

### Python Packages

```bash
pip install pydualsense          # DualSense HID communication
pip install python-rtmidi        # Virtual MIDI port creation
pip install fastapi              # WebSocket + HTTP server
pip install uvicorn              # ASGI server for FastAPI
pip install websockets           # WebSocket support (FastAPI dependency)
```

### udev Rule for DualSense Access Without Root

Create `/etc/udev/rules.d/70-dualsense.rules`:

```
# Sony DualSense (USB)
KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0ce6", MODE="0666"
# Sony DualSense (Bluetooth)
KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0ce6", MODE="0666"
# Sony DualSense Edge (USB)
KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0df2", MODE="0666"
```

Then reload:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Unplug and replug the controller after this.

---

## Project Structure

```
dualsense-dj/
├── README.md
├── requirements.txt              # Python dependencies
├── config.yaml                   # User-configurable settings
├── src/
│   ├── __init__.py
│   ├── main.py                   # Entry point — starts all subsystems
│   ├── controller.py             # DualSense input reader + haptic writer
│   ├── mapping.py                # Input-to-action mapping logic
│   ├── midi_bridge.py            # Virtual MIDI port + message sender
│   ├── state.py                  # Global application state manager
│   ├── haptics.py                # Haptic feedback engine
│   ├── server.py                 # FastAPI WebSocket server
│   └── mixxx/
│       ├── __init__.py
│       ├── midi_mapping.xml      # Mixxx MIDI mapping file
│       └── midi_mapping.js       # Mixxx MIDI scripting (if needed)
├── ui/
│   ├── package.json
│   ├── index.html
│   ├── src/
│   │   ├── App.jsx               # Main React app
│   │   ├── components/
│   │   │   ├── DeckDisplay.jsx   # Single deck state display
│   │   │   ├── Crossfader.jsx    # Visual crossfader
│   │   │   ├── EQDisplay.jsx     # EQ knob visualization
│   │   │   ├── ControllerMap.jsx # Shows current button mapping overlay
│   │   │   ├── EffectsPanel.jsx  # Gyro-mapped effects display
│   │   │   └── Library.jsx       # Track browser
│   │   └── hooks/
│   │       └── useWebSocket.js   # WebSocket connection hook
│   └── vite.config.js
└── docs/
    └── mapping-reference.md      # Visual mapping reference card
```

---

## Configuration File: `config.yaml`

```yaml
# DualSense DJ Controller Configuration

controller:
  connection: "usb"                # "usb" or "bluetooth"
  deadzone: 0.08                   # Stick deadzone (0.0 - 1.0), values below this are treated as 0
  touchpad_crossfader_smoothing: 0.15  # Smoothing factor for touchpad crossfader (0 = none, 1 = max)

midi:
  port_name: "DualSense DJ"       # Name of the virtual MIDI port
  channel: 0                       # MIDI channel (0-15)

haptics:
  enabled: true
  beat_pulse_intensity: 80         # 0-255, strength of downbeat haptic pulse
  sync_drift_vibration: true       # Vibrate when tracks drift out of sync
  crossfader_center_click: true    # Haptic click when crossfader passes center

adaptive_triggers:
  enabled: true
  volume_fader:
    mode: "section"                # "section" mode allows defining resistance zones
    start_resistance: 20           # Light resistance at start of throw (0-255)
    unity_position: 0.75           # Position of the tactile notch (0.0-1.0)
    unity_resistance: 180          # Resistance at unity gain notch (0-255)
    end_resistance: 255            # Hard wall at end (0-255)

filter:
  stick_curve: "exponential"       # "linear" or "exponential" — exponential gives more control near center
  stick_exponent: 2.0              # Exponent for exponential curve

server:
  host: "127.0.0.1"
  port: 8765                       # WebSocket server port
  ui_port: 5173                    # Vite dev server port (development only)
```

---

## Module Specifications

### 1. `src/controller.py` — DualSense Controller Interface

**Purpose**: Read all DualSense inputs, normalize values, and provide a clean API. Write haptic feedback and adaptive trigger settings back to the controller.

**Class: `DualSenseController`**

```python
class DualSenseController:
    """
    Manages the DualSense controller connection and provides
    normalized input state.

    All analog values are normalized to 0.0-1.0 or -1.0 to 1.0 ranges.
    """

    def __init__(self, config: dict):
        """
        Initialize pydualsense connection.

        Args:
            config: Controller section from config.yaml

        Setup:
            - Initialize pydualsense DSController instance
            - Call ds.init() to connect
            - Set initial adaptive trigger profiles (see haptics section)
            - Set initial LED color (dim blue = standby)
        """

    def read_state(self) -> ControllerState:
        """
        Read current controller state and return a normalized ControllerState.

        Returns a ControllerState dataclass (defined below).

        Normalization rules:
            - Sticks: Raw 0-255 → normalized -1.0 to 1.0, with deadzone applied
            - Triggers: Raw 0-255 → normalized 0.0 to 1.0
            - Touchpad: Raw coordinates → normalized 0.0 to 1.0 for both X and Y
            - Gyro: Raw values → degrees per second (pydualsense handles this)
            - Buttons: boolean True/False

        Deadzone application for sticks:
            1. Convert raw 0-255 to -1.0 to 1.0
            2. If abs(value) < deadzone threshold: return 0.0
            3. Otherwise: rescale remaining range to 0.0-1.0
               formula: sign(value) * (abs(value) - deadzone) / (1.0 - deadzone)
        """

    def set_adaptive_trigger(self, trigger: str, mode: str, params: list[int]):
        """
        Set adaptive trigger effect.

        Args:
            trigger: "left" or "right"
            mode: One of the pydualsense TriggerModes:
                  - "off": No resistance
                  - "rigid": Constant resistance
                  - "pulse": Vibrate at a position
                  - "section": Resistance in a defined section (USED FOR VOLUME FADERS)
            params: Mode-specific parameters (list of up to 7 ints, 0-255)

        For volume fader "section" mode, params are:
            [start_position, end_position, resistance]
            - Use multiple calls or the "rigid_gradient" approach
              to create the unity-gain notch effect

        pydualsense API:
            ds.triggerL.setMode(TriggerModes.Rigid)
            ds.triggerL.setForce(0, force)  # position 0, with force value
        """

    def set_haptic(self, motor: str, intensity: int):
        """
        Set haptic motor intensity.

        Args:
            motor: "left" or "right"
            intensity: 0-255

        pydualsense API:
            ds.setLeftMotor(intensity)
            ds.setRightMotor(intensity)
        """

    def set_led_color(self, r: int, g: int, b: int):
        """
        Set the LED bar color.

        Args:
            r, g, b: 0-255

        Use for deck state indication:
            - Dim blue: standby
            - Left-weighted color (e.g., cyan): Deck A active
            - Right-weighted color (e.g., magenta): Deck B active
            - Pulsing: beat sync indicator (optional)

        pydualsense API:
            ds.light.setColorI(r, g, b)
        """

    def close(self):
        """
        Clean shutdown. Reset triggers to off, stop motors, close connection.
        ds.close()
        """
```

**Dataclass: `ControllerState`**

```python
from dataclasses import dataclass

@dataclass
class ControllerState:
    """Snapshot of all DualSense inputs at a single point in time."""

    # Sticks (normalized -1.0 to 1.0, deadzone applied)
    left_stick_x: float     # Left/right
    left_stick_y: float     # Up(negative) / Down(positive)
    right_stick_x: float
    right_stick_y: float

    # Stick clicks
    l3: bool
    r3: bool

    # Triggers (normalized 0.0 to 1.0)
    l2_analog: float        # Left trigger analog value
    r2_analog: float        # Right trigger analog value

    # Bumpers
    l1: bool
    r1: bool

    # D-Pad
    dpad_up: bool
    dpad_right: bool
    dpad_down: bool
    dpad_left: bool

    # Face buttons
    triangle: bool
    circle: bool
    cross: bool
    square: bool

    # Center buttons
    create: bool            # Left of touchpad
    options: bool           # Right of touchpad
    mute: bool              # Below touchpad (mic mute)
    ps: bool                # PS button

    # Touchpad
    touchpad_active: bool           # Is a finger on the touchpad?
    touchpad_finger1_x: float       # Normalized 0.0 (left) to 1.0 (right)
    touchpad_finger1_y: float       # Normalized 0.0 (top) to 1.0 (bottom)
    touchpad_finger2_active: bool   # Is a second finger present?
    touchpad_finger2_x: float
    touchpad_finger2_y: float
    touchpad_click: bool            # Touchpad pressed down

    # Motion sensors (degrees per second for gyro, G-force for accel)
    gyro_x: float           # Pitch (tilt forward/back)
    gyro_y: float           # Yaw (rotate left/right)
    gyro_z: float           # Roll (tilt left/right)
    accel_x: float
    accel_y: float
    accel_z: float

    # Timestamp
    timestamp: float        # time.monotonic() when this state was captured
```

**Important pydualsense Notes**:

- `pydualsense` uses a background thread for reading. Access `.state` properties directly.
- Touchpad: `ds.state.trackPadTouch0.X`, `ds.state.trackPadTouch0.Y`, `ds.state.trackPadTouch0.isActive`
- Gyro: `ds.state.gyro.X`, `.Y`, `.Z`
- Accelerometer: `ds.state.accelerometer.X`, `.Y`, `.Z`
- The touchpad X range is 0-1919, Y range is 0-942. Normalize by dividing by these max values.
- Trigger values: `ds.state.L2`, `ds.state.R2` (0-255 range)
- Button states: `ds.state.triangle`, `ds.state.circle`, etc. (boolean or 0/1)
- D-Pad may be reported as `ds.state.DpadUp`, `ds.state.DpadDown`, etc.

**Polling Strategy**:

Run a polling loop at **250 Hz** (4ms interval). This is fast enough for responsive DJ control while not saturating CPU. Use `time.monotonic()` for timing and `time.sleep()` for the interval. The main loop in `main.py` handles this — `controller.py` just provides `read_state()`.

---

### 2. `src/mapping.py` — Input Mapping Engine

**Purpose**: Take a `ControllerState`, compute DJ actions, and emit both MIDI messages and state updates.

**Class: `InputMapper`**

```python
class InputMapper:
    """
    Maps DualSense inputs to DJ control actions.

    Maintains internal state for:
        - Which mode is active (normal vs EQ mode via Options hold)
        - Gyro enable/disable toggle state
        - Previous frame's state (for edge detection on buttons)
        - Smoothed values for analog inputs
    """

    def __init__(self, config: dict):
        """
        Args:
            config: Full config dict

        Internal state:
            self.gyro_enabled: bool = False
            self.prev_state: ControllerState | None = None
            self.smoothed_crossfader: float = 0.5
            self.active_effect_index: int = 0  # Which effect is selected
        """

    def process(self, state: ControllerState) -> list[DJAction]:
        """
        Process a controller state snapshot and return a list of DJ actions.

        Args:
            state: Current ControllerState

        Returns:
            List of DJAction objects representing all changes since last frame.
            Only emit actions for values that have CHANGED beyond a threshold
            (for analog) or changed state (for buttons). This prevents flooding
            MIDI with redundant messages.

        Processing order:
            1. Detect button edges (pressed this frame, not last frame)
            2. Process mode toggles (mute → gyro toggle, options held → EQ mode)
            3. Process transport (L1/R1 for play/pause)
            4. Process triggers (L2/R2 for volume)
            5. Process sticks (filter or EQ depending on mode)
            6. Process touchpad (crossfader + track management)
            7. Process gyro (effects, only if gyro enabled)
            8. Process hot cues (d-pad for Deck A, face buttons for Deck B)
            9. Process utility (create → loop toggle)
            10. Store current state as prev_state
        """

    def _detect_button_edge(self, current: bool, previous: bool) -> str:
        """
        Returns "pressed", "released", or "none".
        Used for buttons that trigger on press, not hold.
        """

    def _apply_smoothing(self, current: float, previous: float, factor: float) -> float:
        """
        Exponential smoothing: output = previous + factor * (current - previous)
        Used for crossfader and other analog inputs to prevent jitter.
        """

    def _apply_stick_curve(self, value: float, curve: str, exponent: float) -> float:
        """
        Apply response curve to stick input.

        For "linear": return value as-is
        For "exponential": return sign(value) * abs(value) ** exponent

        Exponential curve gives more precision near center (where fine
        filter adjustments happen) and faster movement at extremes.
        """
```

**Dataclass: `DJAction`**

```python
from dataclasses import dataclass
from enum import Enum

class ActionType(Enum):
    # Transport
    PLAY_PAUSE = "play_pause"
    SYNC_TOGGLE = "sync_toggle"

    # Mix
    VOLUME = "volume"
    CROSSFADER = "crossfader"

    # EQ
    EQ_LOW = "eq_low"
    EQ_MID = "eq_mid"
    EQ_HIGH = "eq_high"

    # Filter
    FILTER = "filter"              # Combined hi-pass/lo-pass

    # Navigation
    TRACK_BROWSE = "track_browse"  # Scroll direction
    TRACK_LOAD = "track_load"      # Load to deck

    # Performance
    HOT_CUE = "hot_cue"
    LOOP_TOGGLE = "loop_toggle"
    PITCH_NUDGE = "pitch_nudge"

    # Effects
    EFFECT_WET_DRY = "effect_wet_dry"
    EFFECT_PARAMETER = "effect_parameter"
    GYRO_TOGGLE = "gyro_toggle"

class Deck(Enum):
    A = "A"
    B = "B"
    MASTER = "master"    # For crossfader and other global controls

@dataclass
class DJAction:
    action_type: ActionType
    deck: Deck
    value: float            # 0.0-1.0 for analog, 1.0 for button press, 0.0 for release
    extra: dict = None      # Optional metadata, e.g. {"cue_index": 2}
```

**Detailed Mapping Logic — Every Input Documented**:

#### Triggers → Volume (Analog, Continuous)

```
L2 analog (0.0-1.0) → DJAction(VOLUME, Deck.A, value)
R2 analog (0.0-1.0) → DJAction(VOLUME, Deck.B, value)

Emit when: abs(current - previous) > 0.005 (tiny threshold to catch all movement)
MIDI: CC 0x07 (volume) on channels 0 (Deck A) and 1 (Deck B)
MIDI value: int(value * 127)
```

#### Bumpers → Play/Pause (Button, Edge-triggered)

```
L1 pressed edge → DJAction(PLAY_PAUSE, Deck.A, 1.0)
R1 pressed edge → DJAction(PLAY_PAUSE, Deck.B, 1.0)

Emit when: button transitions from False → True (press edge only)
MIDI: Note On, note 0x01 (Deck A) / 0x02 (Deck B), velocity 127
```

#### Left Stick → Deck A Filter + Pitch Nudge (Analog, Continuous)

**Normal mode (Options NOT held):**

```
Left stick Y:
    Center (0.0) → no filter
    Negative (up, toward -1.0) → hi-pass filter sweep
    Positive (down, toward 1.0) → lo-pass filter sweep

    Mapping: value 0.0 maps to MIDI 64 (center/bypass)
             value -1.0 maps to MIDI 0 (full hi-pass)
             value 1.0 maps to MIDI 127 (full lo-pass)
    Formula: midi_value = int((value + 1.0) / 2.0 * 127)

    → DJAction(FILTER, Deck.A, normalized_value)
    MIDI: CC 0x1A on channel 0

Left stick X:
    Left/right → pitch nudge for Deck A
    Only emit when abs(value) > 0.15 (larger deadzone for nudge to prevent accidental triggers)
    → DJAction(PITCH_NUDGE, Deck.A, value)
    MIDI: CC 0x1B on channel 0, centered at 64
```

**EQ mode (Options IS held):**

```
Left stick Y:
    Up/down → Deck A bass cut/boost
    Center = unity (MIDI 64), up = cut (MIDI 0), down = boost (MIDI 127)
    → DJAction(EQ_LOW, Deck.A, value)
    MIDI: CC 0x20 on channel 0

Left stick X:
    Left/right → Deck A treble cut/boost
    Center = unity (MIDI 64), left = cut (MIDI 0), right = boost (MIDI 127)
    → DJAction(EQ_HIGH, Deck.A, value)
    MIDI: CC 0x22 on channel 0

(EQ mid remains at unity — controlled separately if needed in a future version)
```

#### Right Stick → Deck B Filter + Pitch Nudge (same logic, different deck)

**Normal mode:**

```
Right stick Y → DJAction(FILTER, Deck.B, value)       MIDI: CC 0x1A on channel 1
Right stick X → DJAction(PITCH_NUDGE, Deck.B, value)   MIDI: CC 0x1B on channel 1
```

**EQ mode:**

```
Right stick Y → DJAction(EQ_LOW, Deck.B, value)        MIDI: CC 0x20 on channel 1
Right stick X → DJAction(EQ_HIGH, Deck.B, value)       MIDI: CC 0x22 on channel 1
```

#### Stick Clicks → Sync Toggle (Button, Edge-triggered)

```
L3 pressed edge → DJAction(SYNC_TOGGLE, Deck.A, 1.0)  MIDI: Note On 0x03 ch0
R3 pressed edge → DJAction(SYNC_TOGGLE, Deck.B, 1.0)  MIDI: Note On 0x03 ch1
```

#### Touchpad → Crossfader + Library Navigation

```
Touchpad finger1 X position (0.0 to 1.0):
    → DJAction(CROSSFADER, Deck.MASTER, x_position)
    Apply smoothing: smoothed = prev + smoothing_factor * (current - prev)
    MIDI: CC 0x08 on channel 0, value = int(smoothed * 127)
    Emit when: touchpad_active is True AND abs(current_smoothed - last_sent) > 0.008

    When touchpad_active becomes False: do NOT reset crossfader.
    The crossfader stays at its last position when finger is lifted.

Touchpad finger1 Y swipe (vertical movement):
    Calculate delta_y = current_y - previous_y each frame
    If abs(delta_y) > 0.03: interpret as scroll
    delta_y < -0.03 (swipe up) → DJAction(TRACK_BROWSE, Deck.MASTER, -1.0)  # scroll up
    delta_y > 0.03 (swipe down) → DJAction(TRACK_BROWSE, Deck.MASTER, 1.0)  # scroll down
    MIDI: CC 0x30 on channel 0, value 65 (scroll down) or 63 (scroll up)
    Throttle: max 20 scroll events per second to prevent over-scrolling

Touchpad click (pressed down):
    Determine which half was clicked based on finger1 X position:
    If finger1_x < 0.5: → DJAction(TRACK_LOAD, Deck.A, 1.0)  MIDI: Note On 0x04 ch0
    If finger1_x >= 0.5: → DJAction(TRACK_LOAD, Deck.B, 1.0)  MIDI: Note On 0x04 ch1
    Edge-triggered (press only, not hold).

Two-finger tap (touchpad_finger2_active becomes True):
    → This is a UI-layer toggle only (switch between library view and waveform view).
       Emit as a WebSocket event, no MIDI needed.
       Edge-triggered.
```

#### D-Pad → Deck A Hot Cues (Button, Edge-triggered)

```
D-pad Up    pressed → DJAction(HOT_CUE, Deck.A, 1.0, {"cue_index": 1})  MIDI: Note On 0x10 ch0
D-pad Right pressed → DJAction(HOT_CUE, Deck.A, 1.0, {"cue_index": 2})  MIDI: Note On 0x11 ch0
D-pad Down  pressed → DJAction(HOT_CUE, Deck.A, 1.0, {"cue_index": 3})  MIDI: Note On 0x12 ch0
D-pad Left  pressed → DJAction(HOT_CUE, Deck.A, 1.0, {"cue_index": 4})  MIDI: Note On 0x13 ch0
```

#### Face Buttons → Deck B Hot Cues (Button, Edge-triggered)

```
Triangle pressed → DJAction(HOT_CUE, Deck.B, 1.0, {"cue_index": 1})  MIDI: Note On 0x10 ch1
Circle   pressed → DJAction(HOT_CUE, Deck.B, 1.0, {"cue_index": 2})  MIDI: Note On 0x11 ch1
Cross    pressed → DJAction(HOT_CUE, Deck.B, 1.0, {"cue_index": 3})  MIDI: Note On 0x12 ch1
Square   pressed → DJAction(HOT_CUE, Deck.B, 1.0, {"cue_index": 4})  MIDI: Note On 0x13 ch1
```

#### Create Button → Loop Toggle (Button, Edge-triggered)

```
Create pressed → DJAction(LOOP_TOGGLE, <current_active_deck>, 1.0)
    MIDI: Note On 0x20 on the relevant channel

"Current active deck" determination:
    - If crossfader < 0.4: active deck = A
    - If crossfader > 0.6: active deck = B
    - If 0.4 <= crossfader <= 0.6: active deck = whichever was last explicitly interacted with
      (last deck that had a play/pause, hot cue, or volume change)

    This is a sensible default — looping the track you're currently focused on.
```

#### Mute Button → Gyro Toggle (Button, Edge-triggered)

```
Mute pressed → toggle self.gyro_enabled
    → DJAction(GYRO_TOGGLE, Deck.MASTER, 1.0 if gyro_enabled else 0.0)
    No MIDI. Broadcast to UI via WebSocket for visual indicator.
    Change LED color to indicate gyro state:
        gyro enabled: pulsing green
        gyro disabled: steady dim blue
```

#### Options Button → Mode Shift (Button, Hold)

```
Options held (not edge, continuous hold):
    Sets EQ mode flag. While held, sticks map to EQ instead of filter.
    No MIDI or action emitted for the mode change itself.
    The stick processing reads this flag and routes accordingly.
    Broadcast mode state to UI via WebSocket for visual overlay.
```

#### Gyro → Effects (Analog, Continuous, Only When Enabled)

```
ONLY process gyro when self.gyro_enabled is True.

Gyro Z (roll, tilt left/right):
    → DJAction(EFFECT_WET_DRY, Deck.MASTER, normalized_value)
    Normalize: Map gyro Z degrees/sec to 0.0-1.0 range
        - At rest (controller level): 0.0 (fully dry)
        - Tilted 45° left or right: 1.0 (fully wet)
        - Use absolute value of roll — tilt either direction increases wet
        - Clamp to 0.0-1.0
        - Apply smoothing factor of 0.3 to prevent jitter
    MIDI: CC 0x40 on channel 0, value = int(value * 127)

Gyro X (pitch, tilt forward/back):
    → DJAction(EFFECT_PARAMETER, Deck.MASTER, normalized_value)
    Normalize: Map gyro X to 0.0-1.0
        - Level = 0.5 (center)
        - Tilted forward = 0.0
        - Tilted back = 1.0
        - Apply smoothing factor of 0.3
    MIDI: CC 0x41 on channel 0, value = int(value * 127)

Gyro normalization approach:
    The raw gyro values are angular velocity (degrees/sec), not absolute angle.
    To get a usable "current tilt" value:
        1. Integrate gyro readings over time: angle += gyro_value * dt
        2. Apply a complementary filter with the accelerometer to prevent drift:
           angle = 0.98 * (angle + gyro * dt) + 0.02 * accel_angle
        3. Where accel_angle = atan2(accel_x, accel_z) for roll
        4. Normalize the resulting angle: map ±45° to 0.0-1.0 range, clamp

    Alternatively, for simpler implementation:
        - Use accelerometer directly for tilt angle (less responsive but no drift)
        - accel_roll = atan2(accel_y, accel_z)
        - Normalize to 0.0-1.0 and smooth
```

#### PS Button → Reserved

```
Do not map. The PS button triggers system-level actions on the controller.
```

---

### 3. `src/midi_bridge.py` — Virtual MIDI Port

**Purpose**: Create a virtual MIDI output port and send MIDI messages that Mixxx will receive.

**Class: `MIDIBridge`**

```python
import rtmidi

class MIDIBridge:
    """
    Creates a virtual MIDI output port using python-rtmidi.
    Mixxx connects to this port as a MIDI input.
    """

    def __init__(self, port_name: str = "DualSense DJ"):
        """
        Create and open a virtual MIDI output port.

        Implementation:
            self.midi_out = rtmidi.MidiOut()
            self.midi_out.open_virtual_port(port_name)

        The port will appear in ALSA MIDI and Mixxx's controller preferences
        as a connectable MIDI device.
        """

    def send_cc(self, channel: int, cc: int, value: int):
        """
        Send a MIDI Control Change message.

        Args:
            channel: 0-15
            cc: Controller number 0-127
            value: 0-127

        Implementation:
            status = 0xB0 | (channel & 0x0F)
            self.midi_out.send_message([status, cc & 0x7F, value & 0x7F])
        """

    def send_note_on(self, channel: int, note: int, velocity: int = 127):
        """
        Send a MIDI Note On message.

        Args:
            channel: 0-15
            note: Note number 0-127
            velocity: 0-127 (127 = button press)

        Implementation:
            status = 0x90 | (channel & 0x0F)
            self.midi_out.send_message([status, note & 0x7F, velocity & 0x7F])
        """

    def send_note_off(self, channel: int, note: int):
        """
        Send a MIDI Note Off message.

        Implementation:
            status = 0x80 | (channel & 0x0F)
            self.midi_out.send_message([status, note & 0x7F, 0])
        """

    def send_action(self, action: DJAction):
        """
        Convert a DJAction to the appropriate MIDI message and send it.

        Use the MIDI CC/Note mappings defined in the mapping section above.

        MIDI CC mapping table:
            VOLUME:           CC 0x07, channel = 0 (A) or 1 (B)
            CROSSFADER:       CC 0x08, channel 0
            FILTER:           CC 0x1A, channel = 0 (A) or 1 (B)
            PITCH_NUDGE:      CC 0x1B, channel = 0 (A) or 1 (B)
            EQ_LOW:           CC 0x20, channel = 0 (A) or 1 (B)
            EQ_MID:           CC 0x21, channel = 0 (A) or 1 (B)
            EQ_HIGH:          CC 0x22, channel = 0 (A) or 1 (B)
            TRACK_BROWSE:     CC 0x30, channel 0
            EFFECT_WET_DRY:   CC 0x40, channel 0
            EFFECT_PARAMETER: CC 0x41, channel 0

        MIDI Note mapping table:
            PLAY_PAUSE:       Note 0x01, channel = 0 (A) or 1 (B)
            SYNC_TOGGLE:      Note 0x03, channel = 0 (A) or 1 (B)
            TRACK_LOAD:       Note 0x04, channel = 0 (A) or 1 (B)
            HOT_CUE 1-4:     Notes 0x10-0x13, channel = 0 (A) or 1 (B)
            LOOP_TOGGLE:      Note 0x20, channel = 0 (A) or 1 (B)

        Channel mapping:
            Deck.A → channel 0
            Deck.B → channel 1
            Deck.MASTER → channel 0 (Mixxx master controls are on ch0)
        """

    def close(self):
        """
        Close the virtual MIDI port.
        self.midi_out.close_port()
        del self.midi_out
        """
```

---

### 4. `src/haptics.py` — Haptic Feedback Engine

**Purpose**: Drive DualSense haptic motors and adaptive triggers in response to DJ state.

**Class: `HapticEngine`**

```python
class HapticEngine:
    """
    Manages haptic feedback on the DualSense controller based on
    DJ playback state.

    Runs in a separate thread, receiving state updates via a queue.
    """

    def __init__(self, controller: DualSenseController, config: dict):
        """
        Args:
            controller: DualSenseController instance (for writing haptics)
            config: Haptics section from config.yaml

        Internal state:
            self.deck_a_bpm: float = 0.0
            self.deck_b_bpm: float = 0.0
            self.deck_a_playing: bool = False
            self.deck_b_playing: bool = False
            self.last_beat_time: float = 0.0
        """

    def setup_adaptive_triggers(self):
        """
        Configure adaptive trigger resistance profiles for volume faders.

        Called once on startup and whenever config changes.

        Left trigger (Deck A volume) and Right trigger (Deck B volume):
            - Use "section" mode from pydualsense
            - Light resistance from 0% to 70% of travel
            - Strong resistance "notch" at 75% (unity gain marker)
            - Hard stop at 100%

        pydualsense trigger modes:
            TriggerModes.Off = 0
            TriggerModes.Rigid = 1
            TriggerModes.Pulse = 2
            TriggerModes.Rigid_A = 3
            TriggerModes.Rigid_B = 4
            TriggerModes.Rigid_AB = 5
            TriggerModes.Pulse_A = 6
            TriggerModes.Pulse_B = 7
            TriggerModes.Pulse_AB = 8

        For the volume notch effect, use Rigid_AB or Section mode:
            ds.triggerL.setMode(TriggerModes.Rigid_AB)
            ds.triggerL.setForce(zone1_start, zone1_force, zone2_start, zone2_force)

        Experiment with exact values — the goal is:
            - Smooth light resistance through most of the throw
            - A noticeable bump at ~75% so you can feel unity gain
            - This lets the DJ set volume to unity without looking at the screen
        """

    def beat_pulse(self, deck: str, bpm: float):
        """
        Trigger a brief haptic pulse on the downbeat.

        Implementation:
            - Calculate beat interval: 60.0 / bpm seconds
            - On each beat: set motor to beat_pulse_intensity for 30ms, then off
            - Use left motor for Deck A, right motor for Deck B
            - If both decks playing, alternate or layer pulses

        Timing approach:
            - Run a timer coroutine per active deck
            - Each tick: motor on, sleep 30ms, motor off, sleep (beat_interval - 30ms)
            - Phase-align to Mixxx's beat clock if possible (via OSC feedback)
        """

    def sync_drift_warning(self, drift_amount: float):
        """
        Vibrate when two playing tracks drift out of sync.

        Args:
            drift_amount: 0.0 (perfect sync) to 1.0 (completely out of phase)

        If drift_amount > 0.05: start a low-frequency rumble
        Intensity scales with drift amount.

        Implementation:
            intensity = int(min(drift_amount * 3, 1.0) * 200)
            controller.set_haptic("left", intensity)
            controller.set_haptic("right", intensity)
        """

    def crossfader_center_click(self, position: float, previous_position: float):
        """
        Emit a brief haptic click when the crossfader crosses the center point.

        If previous_position < 0.5 and position >= 0.5, or vice versa:
            Quick pulse: both motors at 150 for 20ms, then off
        """

    def update_state(self, state_update: dict):
        """
        Receive state updates from the main loop.

        Expected keys:
            "deck_a_bpm": float
            "deck_b_bpm": float
            "deck_a_playing": bool
            "deck_b_playing": bool
            "crossfader": float
        """
```

---

### 5. `src/state.py` — Application State Manager

**Purpose**: Central state that all modules read/write. Thread-safe.

```python
import threading
from dataclasses import dataclass, field

@dataclass
class DeckState:
    playing: bool = False
    bpm: float = 0.0
    position: float = 0.0          # Track position 0.0-1.0
    volume: float = 0.0
    filter_value: float = 0.5      # 0.0 = full hi-pass, 0.5 = bypass, 1.0 = full lo-pass
    eq_low: float = 0.5            # 0.0 = full cut, 0.5 = unity, 1.0 = full boost
    eq_mid: float = 0.5
    eq_high: float = 0.5
    sync_enabled: bool = False
    loop_active: bool = False
    hot_cues: list = field(default_factory=lambda: [False, False, False, False])
    track_title: str = ""
    track_artist: str = ""

@dataclass
class AppState:
    deck_a: DeckState = field(default_factory=DeckState)
    deck_b: DeckState = field(default_factory=DeckState)
    crossfader: float = 0.5
    gyro_enabled: bool = False
    eq_mode: bool = False           # True when Options is held
    effect_wet_dry: float = 0.0
    effect_parameter: float = 0.5
    ui_view: str = "decks"          # "decks" or "library"
    connected: bool = False

class StateManager:
    """
    Thread-safe state container.

    All reads and writes go through this class.
    Uses a threading.Lock internally.
    Notifies WebSocket server on changes via a callback.
    """

    def __init__(self):
        self._state = AppState()
        self._lock = threading.Lock()
        self._on_change_callback = None

    def get_state(self) -> AppState:
        """Return a copy of the current state."""
        with self._lock:
            # Return a deep copy or the dataclass itself if reads are safe
            return self._state

    def update(self, **kwargs):
        """
        Update state fields.

        Supports dot-notation keys for nested updates:
            state_manager.update(**{"deck_a.volume": 0.8, "crossfader": 0.5})

        After update, call self._on_change_callback(self._state) if set.
        """

    def set_on_change(self, callback):
        """Register a callback for state changes (used by WebSocket server)."""
        self._on_change_callback = callback

    def to_dict(self) -> dict:
        """Serialize state to dict for JSON WebSocket broadcast."""
```

---

### 6. `src/server.py` — WebSocket Server

**Purpose**: Serve the React UI and broadcast real-time state updates via WebSocket.

```python
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
import json, asyncio

app = FastAPI()

class WebSocketServer:
    """
    Manages WebSocket connections to the React UI.
    Broadcasts state updates whenever the StateManager changes.
    """

    def __init__(self, state_manager: StateManager, config: dict):
        """
        Args:
            state_manager: StateManager instance
            config: Server section from config.yaml

        Sets up:
            - FastAPI app with WebSocket endpoint at /ws
            - Static file serving for the built React UI at /
            - state_manager.set_on_change(self.broadcast)
        """
        self.connections: list[WebSocket] = []

    async def websocket_endpoint(self, websocket: WebSocket):
        """
        Handle a WebSocket connection.

        1. Accept connection
        2. Add to self.connections
        3. Send full current state immediately
        4. Keep connection alive, remove on disconnect
        """

    async def broadcast(self, state: AppState):
        """
        Send state to all connected clients as JSON.

        Message format:
        {
            "type": "state_update",
            "data": {
                "deck_a": { ... },
                "deck_b": { ... },
                "crossfader": 0.5,
                "gyro_enabled": false,
                "eq_mode": false,
                "effect_wet_dry": 0.0,
                "effect_parameter": 0.5,
                "ui_view": "decks"
            }
        }

        Throttle broadcasts to max 60 per second (every ~16ms).
        Batch multiple state changes within a frame into a single broadcast.
        """

    def start(self):
        """
        Start the uvicorn server in a background thread.

        uvicorn.run(app, host=config["host"], port=config["port"])
        """
```

**FastAPI Route Setup**:

```python
# In server.py module level:

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await server_instance.websocket_endpoint(websocket)

# Serve built React UI
app.mount("/", StaticFiles(directory="ui/dist", html=True), name="ui")
```

---

### 7. `src/main.py` — Entry Point

**Purpose**: Initialize all subsystems and run the main polling loop.

```python
import time, threading, signal, sys, yaml

def main():
    """
    1. Load config.yaml
    2. Initialize StateManager
    3. Initialize DualSenseController(config["controller"])
    4. Initialize MIDIBridge(config["midi"]["port_name"])
    5. Initialize HapticEngine(controller, config["haptics"])
    6. Initialize InputMapper(config)
    7. Initialize WebSocketServer(state_manager, config["server"])
    8. Start WebSocket server in background thread
    9. Setup adaptive triggers via HapticEngine
    10. Set LED color to indicate ready state

    Main loop (250Hz):
        while running:
            t_start = time.monotonic()

            # Read controller
            controller_state = controller.read_state()

            # Map inputs to actions
            actions = mapper.process(controller_state)

            # Send MIDI and update state
            for action in actions:
                midi_bridge.send_action(action)
                state_manager.update_from_action(action)

            # Update haptics
            haptic_engine.update_state(state_manager.get_state())

            # Maintain 250Hz
            elapsed = time.monotonic() - t_start
            sleep_time = max(0, 0.004 - elapsed)
            time.sleep(sleep_time)

    Signal handlers:
        SIGINT/SIGTERM → set running = False
        Cleanup: controller.close(), midi_bridge.close()
    """

if __name__ == "__main__":
    main()
```

---

## Mixxx MIDI Mapping Configuration

Mixxx uses XML files to define MIDI mappings. This file tells Mixxx how to interpret the MIDI messages from the virtual "DualSense DJ" port.

### File: `src/mixxx/midi_mapping.xml`

This must be placed in `~/.mixxx/controllers/` (or the equivalent Mixxx controllers directory).

```xml
<?xml version="1.0" encoding="utf-8"?>
<MixxxControllerPreset mixxxVersion="2.3" schemaVersion="1">
    <info>
        <name>DualSense DJ</name>
        <author>DualSense DJ Project</author>
        <description>PS5 DualSense controller mapping for DJ use</description>
    </info>
    <controller id="DualSense DJ">
        <scriptfiles>
            <file filename="DualSense-DJ-scripts.js" functionprefix="DualSenseDJ"/>
        </scriptfiles>
        <controls>
            <!-- ==================== DECK A (Channel 0) ==================== -->

            <!-- Volume: CC 0x07 Ch1 (status 0xB0) -->
            <control>
                <group>[Channel1]</group>
                <key>volume</key>
                <status>0xB0</status>
                <midino>0x07</midino>
                <options><normal/></options>
            </control>

            <!-- Filter: CC 0x1A Ch1 -->
            <control>
                <group>[QuickEffectRack1_[Channel1]]</group>
                <key>super1</key>
                <status>0xB0</status>
                <midino>0x1A</midino>
                <options><normal/></options>
            </control>

            <!-- Pitch Nudge: CC 0x1B Ch1 -->
            <control>
                <group>[Channel1]</group>
                <key>jog</key>
                <status>0xB0</status>
                <midino>0x1B</midino>
                <options><normal/></options>
            </control>

            <!-- EQ Low: CC 0x20 Ch1 -->
            <control>
                <group>[EqualizerRack1_[Channel1]_Effect1]</group>
                <key>parameter1</key>
                <status>0xB0</status>
                <midino>0x20</midino>
                <options><normal/></options>
            </control>

            <!-- EQ Mid: CC 0x21 Ch1 -->
            <control>
                <group>[EqualizerRack1_[Channel1]_Effect1]</group>
                <key>parameter2</key>
                <status>0xB0</status>
                <midino>0x21</midino>
                <options><normal/></options>
            </control>

            <!-- EQ High: CC 0x22 Ch1 -->
            <control>
                <group>[EqualizerRack1_[Channel1]_Effect1]</group>
                <key>parameter3</key>
                <status>0xB0</status>
                <midino>0x22</midino>
                <options><normal/></options>
            </control>

            <!-- Play/Pause: Note 0x01 Ch1 (status 0x90) -->
            <control>
                <group>[Channel1]</group>
                <key>play</key>
                <status>0x90</status>
                <midino>0x01</midino>
                <options><toggle/></options>
            </control>

            <!-- Sync: Note 0x03 Ch1 -->
            <control>
                <group>[Channel1]</group>
                <key>sync_enabled</key>
                <status>0x90</status>
                <midino>0x03</midino>
                <options><toggle/></options>
            </control>

            <!-- Load Track: Note 0x04 Ch1 -->
            <control>
                <group>[Channel1]</group>
                <key>LoadSelectedTrack</key>
                <status>0x90</status>
                <midino>0x04</midino>
                <options><normal/></options>
            </control>

            <!-- Hot Cues 1-4: Notes 0x10-0x13 Ch1 -->
            <control>
                <group>[Channel1]</group>
                <key>hotcue_1_activate</key>
                <status>0x90</status>
                <midino>0x10</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel1]</group>
                <key>hotcue_2_activate</key>
                <status>0x90</status>
                <midino>0x11</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel1]</group>
                <key>hotcue_3_activate</key>
                <status>0x90</status>
                <midino>0x12</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel1]</group>
                <key>hotcue_4_activate</key>
                <status>0x90</status>
                <midino>0x13</midino>
                <options><normal/></options>
            </control>

            <!-- Loop Toggle: Note 0x20 Ch1 -->
            <control>
                <group>[Channel1]</group>
                <key>beatloop_4_toggle</key>
                <status>0x90</status>
                <midino>0x20</midino>
                <options><normal/></options>
            </control>

            <!-- ==================== DECK B (Channel 1, status 0xB1/0x91) ==================== -->

            <!-- Volume: CC 0x07 Ch2 -->
            <control>
                <group>[Channel2]</group>
                <key>volume</key>
                <status>0xB1</status>
                <midino>0x07</midino>
                <options><normal/></options>
            </control>

            <!-- Filter: CC 0x1A Ch2 -->
            <control>
                <group>[QuickEffectRack1_[Channel2]]</group>
                <key>super1</key>
                <status>0xB1</status>
                <midino>0x1A</midino>
                <options><normal/></options>
            </control>

            <!-- Pitch Nudge: CC 0x1B Ch2 -->
            <control>
                <group>[Channel2]</group>
                <key>jog</key>
                <status>0xB1</status>
                <midino>0x1B</midino>
                <options><normal/></options>
            </control>

            <!-- EQ Low: CC 0x20 Ch2 -->
            <control>
                <group>[EqualizerRack1_[Channel2]_Effect1]</group>
                <key>parameter1</key>
                <status>0xB1</status>
                <midino>0x20</midino>
                <options><normal/></options>
            </control>

            <!-- EQ Mid: CC 0x21 Ch2 -->
            <control>
                <group>[EqualizerRack1_[Channel2]_Effect1]</group>
                <key>parameter2</key>
                <status>0xB1</status>
                <midino>0x21</midino>
                <options><normal/></options>
            </control>

            <!-- EQ High: CC 0x22 Ch2 -->
            <control>
                <group>[EqualizerRack1_[Channel2]_Effect1]</group>
                <key>parameter3</key>
                <status>0xB1</status>
                <midino>0x22</midino>
                <options><normal/></options>
            </control>

            <!-- Play/Pause: Note 0x01 Ch2 -->
            <control>
                <group>[Channel2]</group>
                <key>play</key>
                <status>0x91</status>
                <midino>0x01</midino>
                <options><toggle/></options>
            </control>

            <!-- Sync: Note 0x03 Ch2 -->
            <control>
                <group>[Channel2]</group>
                <key>sync_enabled</key>
                <status>0x91</status>
                <midino>0x03</midino>
                <options><toggle/></options>
            </control>

            <!-- Load Track: Note 0x04 Ch2 -->
            <control>
                <group>[Channel2]</group>
                <key>LoadSelectedTrack</key>
                <status>0x91</status>
                <midino>0x04</midino>
                <options><normal/></options>
            </control>

            <!-- Hot Cues 1-4: Notes 0x10-0x13 Ch2 -->
            <control>
                <group>[Channel2]</group>
                <key>hotcue_1_activate</key>
                <status>0x91</status>
                <midino>0x10</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel2]</group>
                <key>hotcue_2_activate</key>
                <status>0x91</status>
                <midino>0x11</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel2]</group>
                <key>hotcue_3_activate</key>
                <status>0x91</status>
                <midino>0x12</midino>
                <options><normal/></options>
            </control>
            <control>
                <group>[Channel2]</group>
                <key>hotcue_4_activate</key>
                <status>0x91</status>
                <midino>0x13</midino>
                <options><normal/></options>
            </control>

            <!-- Loop Toggle: Note 0x20 Ch2 -->
            <control>
                <group>[Channel2]</group>
                <key>beatloop_4_toggle</key>
                <status>0x91</status>
                <midino>0x20</midino>
                <options><normal/></options>
            </control>

            <!-- ==================== MASTER (Channel 0) ==================== -->

            <!-- Crossfader: CC 0x08 Ch1 -->
            <control>
                <group>[Master]</group>
                <key>crossfader</key>
                <status>0xB0</status>
                <midino>0x08</midino>
                <options><normal/></options>
            </control>

            <!-- Track Browse: CC 0x30 Ch1 -->
            <control>
                <group>[Library]</group>
                <key>MoveVertical</key>
                <status>0xB0</status>
                <midino>0x30</midino>
                <options><relative/></options>
            </control>

            <!-- Effect Wet/Dry: CC 0x40 Ch1 -->
            <control>
                <group>[EffectRack1_EffectUnit1]</group>
                <key>mix</key>
                <status>0xB0</status>
                <midino>0x40</midino>
                <options><normal/></options>
            </control>

            <!-- Effect Parameter: CC 0x41 Ch1 -->
            <control>
                <group>[EffectRack1_EffectUnit1_Effect1]</group>
                <key>parameter1</key>
                <status>0xB0</status>
                <midino>0x41</midino>
                <options><normal/></options>
            </control>
        </controls>
    </controller>
</MixxxControllerPreset>
```

### Installing the Mapping in Mixxx

1. Copy `midi_mapping.xml` to `~/.mixxx/controllers/DualSense-DJ.midi.xml`
2. Copy `midi_mapping.js` to `~/.mixxx/controllers/DualSense-DJ-scripts.js` (even if empty initially)
3. Open Mixxx → Preferences → Controllers
4. Select "DualSense DJ" from the MIDI device list
5. Load the "DualSense DJ" preset
6. Enable the controller

---

## React UI Specification

### Technology

- **Vite** for bundling
- **React 18** with hooks
- **Tailwind CSS** for styling
- **WebSocket** for real-time state

### `ui/src/App.jsx` — Main Layout

```
┌─────────────────────────────────────────────────────┐
│                   DualSense DJ                       │
├──────────────────────┬──────────────────────────────┤
│      DECK A          │         DECK B               │
│                      │                              │
│  Track: title        │  Track: title                │
│  Artist: artist      │  Artist: artist              │
│  BPM: 128.0          │  BPM: 126.5                  │
│                      │                              │
│  [▶ PLAYING] [SYNC]  │  [■ STOPPED] [SYNC]          │
│                      │                              │
│  Volume: ████████░░  │  Volume: ██████░░░░          │
│  Filter: ──────●───  │  Filter: ────●─────          │
│                      │                              │
│  EQ:  H[■] M[■] L[■]│  EQ:  H[■] M[■] L[■]       │
│                      │                              │
│  Cues: [1][2][3][4]  │  Cues: [1][2][3][4]         │
│  Loop: OFF           │  Loop: OFF                   │
│                      │                              │
├──────────────────────┴──────────────────────────────┤
│  Crossfader: ─────────────●──────────────────       │
├─────────────────────────────────────────────────────┤
│  Effects: [GYRO OFF]  Wet/Dry: ░░░░░░░░░░          │
│  Tilt:    ─────●─────                               │
├─────────────────────────────────────────────────────┤
│  Mode: NORMAL          [EQ MODE when Options held]  │
│                                                      │
│  Controller Input Monitor (debug overlay):           │
│  L2: 0.75  R2: 0.50  LX: 0.00  LY: -0.23          │
│  Touchpad: 0.50, 0.30  Gyro: 0.0, 0.0, 0.0        │
└─────────────────────────────────────────────────────┘
```

### `ui/src/hooks/useWebSocket.js`

```javascript
/**
 * Custom hook that connects to the Python backend WebSocket.
 *
 * Returns:
 *   { state, connected }
 *
 * Implementation:
 *   - Connect to ws://${config.host}:${config.port}/ws
 *   - On message: parse JSON, update state via setState
 *   - On disconnect: attempt reconnect every 2 seconds
 *   - On connect: set connected = true
 *
 * The state object matches the AppState structure from state.py.
 */
```

### Component Specs

**`DeckDisplay.jsx`**: Receives a deck state object. Shows track info, play state, volume bar, filter position, EQ sliders, hot cue buttons (highlighted when set), loop indicator. Use color coding: Deck A = cyan tones, Deck B = magenta tones.

**`Crossfader.jsx`**: Horizontal slider showing current crossfader position. Animated smoothly. Highlight center zone (0.45-0.55) to indicate the blend zone.

**`ControllerMap.jsx`**: Visual overlay showing a DualSense controller silhouette with current mappings labeled on each input. When EQ mode is active, the stick labels change from "Filter" to "EQ Lo/Hi". When gyro is enabled, highlight the gyro section. This is the "at a glance" reference for the performer.

**`EffectsPanel.jsx`**: Shows gyro enable state, current effect wet/dry level, and effect parameter. Visual indicator of controller tilt angle.

**`Library.jsx`**: Simple track list that scrolls based on TRACK_BROWSE actions. Highlights the currently selected track. Shows which deck each loaded track is on.

---

## Startup Sequence

1. User runs `python src/main.py`
2. Python loads `config.yaml`
3. DualSenseController connects to the controller (fails with clear error if not found)
4. MIDIBridge creates virtual MIDI port "DualSense DJ"
5. HapticEngine configures adaptive triggers
6. WebSocket server starts on configured port
7. Console prints: "DualSense DJ ready. Connect Mixxx to 'DualSense DJ' MIDI device."
8. LED turns solid blue
9. Main polling loop begins
10. User opens Mixxx separately, goes to Preferences → Controllers, selects "DualSense DJ", loads the mapping preset, and enables it
11. User opens `http://localhost:5173` (dev) or `http://localhost:8765` (production) for the UI
12. Mixing begins

---

## Error Handling

### Controller Disconnection

- `pydualsense` will raise an exception or return stale data if the controller disconnects
- Wrap `read_state()` in try/except
- On disconnect: pause main loop, set LED state to "disconnected" in UI via WebSocket, attempt reconnection every 2 seconds
- On reconnect: re-initialize adaptive triggers, resume loop

### MIDI Port Issues

- If Mixxx is not connected to the virtual port, MIDI messages are simply dropped (this is normal MIDI behavior — no error)
- If `python-rtmidi` fails to create the port (rare on Linux with ALSA), print a clear error directing the user to check ALSA configuration

### Haptic Failures

- Haptic writes should never crash the main loop
- Wrap all haptic calls in try/except, log warnings, continue

---

## Testing Plan

### Phase 1: Controller Input Verification

Create `test_controller.py`:
- Connect to DualSense
- Print all input values in real time (like evtest but using pydualsense)
- Verify every input in `ControllerState` is reading correctly
- Verify touchpad X/Y ranges and normalization
- Verify gyro/accelerometer values and orientation

### Phase 2: MIDI Output Verification

Create `test_midi.py`:
- Create virtual MIDI port
- Map a few test inputs (one stick, one trigger, one button)
- Use `amidi` or `aseqdump` to verify correct MIDI messages are being sent
- Verify CC values are in 0-127 range
- Verify Note On/Off messages fire correctly

### Phase 3: Mixxx Integration

- Start `main.py` and Mixxx
- Connect Mixxx to the virtual MIDI port
- Verify each mapping one by one:
  - Triggers control volume
  - Bumpers toggle play/pause
  - Touchpad moves crossfader
  - Sticks control filter sweep
  - D-pad/face buttons trigger hot cues
  - Create button toggles loop
  - Stick clicks toggle sync
  - Options hold switches to EQ mode

### Phase 4: Haptic Feedback

- Verify adaptive trigger resistance is felt on volume faders
- Verify beat pulse haptics fire in time with playing tracks
- Verify crossfader center click fires at the right position

### Phase 5: UI Verification

- Verify WebSocket connects and receives state updates
- Verify all UI elements update in real time
- Verify EQ mode overlay toggles when Options is held
- Verify gyro enable indicator responds to Mute button

---

## Known Challenges and Solutions

### Challenge: Gyro Drift

**Problem**: Integrating gyro data over time accumulates error, causing the "zero" point to drift.

**Solution**: Use a complementary filter combining gyro and accelerometer. When gyro is first enabled (mute button toggle), capture the current accelerometer reading as the "zero" reference orientation. All subsequent readings are relative to this reference. Add a "recalibrate" option (e.g., hold mute for 2 seconds instead of tapping) that resets the zero point.

### Challenge: Touchpad Crossfader Precision

**Problem**: The touchpad is small and finger position isn't as precise as a physical fader.

**Solution**: Apply configurable smoothing (exponential moving average). The `touchpad_crossfader_smoothing` config value controls this. Higher values = smoother but laggier. Start with 0.15 and let the user tune it. Also implement a "crossfader cut" zone — the outermost 5% on each side snaps to 0.0/1.0 for clean cuts.

### Challenge: MIDI Value Resolution

**Problem**: MIDI CC is 7-bit (0-127), which means volume jumps in steps of ~0.8%.

**Solution**: For most DJ use this is fine. If higher resolution is needed later, implement 14-bit MIDI CC using CC pairs (MSB + LSB). Mixxx supports this but it adds complexity — defer unless needed.

### Challenge: Mixxx State Feedback

**Problem**: The architecture sends control TO Mixxx but doesn't read state FROM Mixxx. Track info, BPM, play state shown in the UI will only reflect what the controller sent, not what Mixxx actually did.

**Solution (Phase 2)**: Mixxx supports OSC output and has a REST-like control interface. In a future iteration, add a Mixxx state reader that polls Mixxx's current state and feeds it back to the StateManager. For v1, the UI shows controller-side state only, which is accurate enough for basic use. Alternatively, Mixxx's MIDI scripting can send MIDI feedback messages back through the virtual port — `python-rtmidi` can open a virtual input port to receive these.

---

## MIDI CC and Note Reference Table

| Function          | Type    | CC/Note | Ch 0 (Deck A) | Ch 1 (Deck B) | Value Range   |
|-------------------|---------|---------|----------------|----------------|---------------|
| Volume            | CC      | 0x07    | 0xB0 0x07      | 0xB1 0x07      | 0-127         |
| Crossfader        | CC      | 0x08    | 0xB0 0x08      | —              | 0-127         |
| Filter            | CC      | 0x1A    | 0xB0 0x1A      | 0xB1 0x1A      | 0=HP, 64=off, 127=LP |
| Pitch Nudge       | CC      | 0x1B    | 0xB0 0x1B      | 0xB1 0x1B      | 64=center     |
| EQ Low            | CC      | 0x20    | 0xB0 0x20      | 0xB1 0x20      | 0=cut, 64=unity, 127=boost |
| EQ Mid            | CC      | 0x21    | 0xB0 0x21      | 0xB1 0x21      | same          |
| EQ High           | CC      | 0x22    | 0xB0 0x22      | 0xB1 0x22      | same          |
| Track Browse      | CC      | 0x30    | 0xB0 0x30      | —              | 63=up, 65=down (relative) |
| Effect Wet/Dry    | CC      | 0x40    | 0xB0 0x40      | —              | 0-127         |
| Effect Parameter  | CC      | 0x41    | 0xB0 0x41      | —              | 0-127         |
| Play/Pause        | Note On | 0x01    | 0x90 0x01      | 0x91 0x01      | Toggle        |
| Sync              | Note On | 0x03    | 0x90 0x03      | 0x91 0x03      | Toggle        |
| Load Track        | Note On | 0x04    | 0x90 0x04      | 0x91 0x04      | Trigger       |
| Hot Cue 1         | Note On | 0x10    | 0x90 0x10      | 0x91 0x10      | Trigger       |
| Hot Cue 2         | Note On | 0x11    | 0x90 0x11      | 0x91 0x11      | Trigger       |
| Hot Cue 3         | Note On | 0x12    | 0x90 0x12      | 0x91 0x12      | Trigger       |
| Hot Cue 4         | Note On | 0x13    | 0x90 0x13      | 0x91 0x13      | Trigger       |
| Loop Toggle       | Note On | 0x20    | 0x90 0x20      | 0x91 0x20      | Trigger       |

---

## DualSense Input → DJ Action Quick Reference

| DualSense Input         | Normal Mode                    | EQ Mode (Options held)        |
|-------------------------|--------------------------------|-------------------------------|
| L2 (analog)             | Deck A Volume                  | Deck A Volume                 |
| R2 (analog)             | Deck B Volume                  | Deck B Volume                 |
| L1                      | Deck A Play/Pause              | Deck A Play/Pause             |
| R1                      | Deck B Play/Pause              | Deck B Play/Pause             |
| Left Stick Y            | Deck A Filter (HP↑ / LP↓)     | Deck A EQ Low (cut↑ / boost↓)|
| Left Stick X            | Deck A Pitch Nudge             | Deck A EQ High (cut← / boost→)|
| Right Stick Y           | Deck B Filter (HP↑ / LP↓)     | Deck B EQ Low                 |
| Right Stick X           | Deck B Pitch Nudge             | Deck B EQ High                |
| L3 (stick click)        | Deck A Sync Toggle             | Deck A Sync Toggle            |
| R3 (stick click)        | Deck B Sync Toggle             | Deck B Sync Toggle            |
| D-Pad Up/Right/Down/Left| Deck A Hot Cues 1/2/3/4       | same                          |
| △ ○ ✕ □                 | Deck B Hot Cues 1/2/3/4       | same                          |
| Touchpad X (slide)      | Crossfader                     | Crossfader                    |
| Touchpad Y (swipe)      | Track Browse                   | Track Browse                  |
| Touchpad Click Left     | Load Track → Deck A            | Load Track → Deck A           |
| Touchpad Click Right    | Load Track → Deck B            | Load Track → Deck B           |
| Two-finger Tap          | Toggle UI View                 | Toggle UI View                |
| Gyro Roll (when enabled)| Effect Wet/Dry                 | Effect Wet/Dry                |
| Gyro Pitch (when enabled)| Effect Parameter              | Effect Parameter              |
| Create                  | Loop Toggle (active deck)      | Loop Toggle (active deck)     |
| Options                 | — (activates EQ mode)          | — (deactivates on release)    |
| Mute                    | Gyro Enable/Disable Toggle     | Gyro Enable/Disable Toggle    |
| PS                      | Reserved (system)              | Reserved (system)             |

---

## Implementation Order

Implement in this exact order. Each step should be testable independently before moving to the next.

1. **`controller.py`** + `test_controller.py` — Get all inputs reading and printing correctly
2. **`midi_bridge.py`** + `test_midi.py` — Get virtual MIDI port working, send test messages
3. **`state.py`** — Implement the state manager (simple, no external dependencies)
4. **`mapping.py`** — Implement input mapping, connect controller → mapping → MIDI bridge
5. **`main.py`** — Wire everything together, get basic two-deck control of Mixxx working
6. **Mixxx MIDI mapping XML** — Install and test in Mixxx
7. **`haptics.py`** — Add adaptive triggers and haptic feedback
8. **`server.py`** — Add WebSocket server
9. **React UI** — Build the web interface
10. **Polish** — Tuning, smoothing values, haptic timing, UX refinement
