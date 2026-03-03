# `mapping.py` Implementation Plan

> **For Claude:** Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Implement `InputMapper` — the core logic that converts `ControllerState` snapshots into `DJAction` lists. Covers button edge detection, analog smoothing, touchpad direction lock, gyro binding cycling, and EQ mode.

**File:** `src/mapping.py`
**Tests:** `tests/test_mapping.py`
**Dependencies:** `src/state.py` (for `GyroBinding`), `src/controller.py` (for `ControllerState`)

---

## Task 1: `DJAction` dataclass and `ActionType`

**Step 1:** Write failing test in `tests/test_mapping.py`

```python
from src.mapping import DJAction

def test_dj_action_fields():
    a = DJAction(action_type="volume", deck="A", value=0.8)
    assert a.deck == "A"
    assert a.extra == {}

def test_dj_action_with_extra():
    a = DJAction(action_type="hot_cue", deck="A", value=1.0, extra={"cue_index": 2})
    assert a.extra["cue_index"] == 2
```

**Step 2:** Run to confirm failure
```bash
pytest tests/test_mapping.py -k "dj_action" -v
```

**Step 3:** Implement in `src/mapping.py`

```python
from dataclasses import dataclass, field

@dataclass
class DJAction:
    action_type: str   # matches ActionType strings
    deck: str          # "A", "B", or "master"
    value: float       # 0.0-1.0 for analog, 1.0 for button press
    extra: dict = field(default_factory=dict)
```

**Step 4:** Run tests
```bash
pytest tests/test_mapping.py -k "dj_action" -v
```
Expected: PASSED

---

## Task 2: Button edge detection and analog smoothing helpers

**Step 1:** Add tests

```python
from src.mapping import detect_edge, apply_smoothing, apply_stick_curve

def test_detect_edge_pressed():
    assert detect_edge(current=True, previous=False) == "pressed"

def test_detect_edge_released():
    assert detect_edge(current=False, previous=True) == "released"

def test_detect_edge_none():
    assert detect_edge(current=True, previous=True) == "none"
    assert detect_edge(current=False, previous=False) == "none"

def test_apply_smoothing():
    result = apply_smoothing(current=1.0, previous=0.0, factor=0.5)
    assert result == pytest.approx(0.5)

def test_apply_smoothing_no_factor():
    result = apply_smoothing(current=0.8, previous=0.2, factor=1.0)
    assert result == pytest.approx(0.8)

def test_stick_curve_linear():
    assert apply_stick_curve(0.5, "linear", 2.0) == pytest.approx(0.5)

def test_stick_curve_exponential():
    # At 0.5, exponent 2: 0.5^2 = 0.25
    assert apply_stick_curve(0.5, "exponential", 2.0) == pytest.approx(0.25)

def test_stick_curve_negative_exponential():
    # Sign is preserved
    assert apply_stick_curve(-0.5, "exponential", 2.0) == pytest.approx(-0.25)
```

**Step 2:** Run to confirm failure
```bash
pytest tests/test_mapping.py -k "edge or smoothing or curve" -v
```

**Step 3:** Implement helpers

```python
import math

def detect_edge(current: bool, previous: bool) -> str:
    if current and not previous:
        return "pressed"
    if not current and previous:
        return "released"
    return "none"

def apply_smoothing(current: float, previous: float, factor: float) -> float:
    return previous + factor * (current - previous)

def apply_stick_curve(value: float, curve: str, exponent: float) -> float:
    if curve == "linear":
        return value
    sign = 1.0 if value >= 0 else -1.0
    return sign * (abs(value) ** exponent)
```

**Step 4:** Run tests
```bash
pytest tests/test_mapping.py -k "edge or smoothing or curve" -v
```
Expected: all PASSED

---

## Task 3: Touchpad direction lock logic

**Step 1:** Add tests

```python
from src.mapping import TouchpadDirectionLock

def test_lock_starts_as_none():
    lock = TouchpadDirectionLock(threshold=0.04)
    assert lock.direction is None

def test_lock_resolves_horizontal():
    lock = TouchpadDirectionLock(threshold=0.04)
    lock.update(0.0, 0.0)       # touch start
    lock.update(0.06, 0.01)     # clear horizontal motion
    assert lock.direction == "horizontal"

def test_lock_resolves_vertical():
    lock = TouchpadDirectionLock(threshold=0.04)
    lock.update(0.0, 0.0)
    lock.update(0.01, 0.06)
    assert lock.direction == "vertical"

def test_lock_stays_locked_once_set():
    lock = TouchpadDirectionLock(threshold=0.04)
    lock.update(0.0, 0.0)
    lock.update(0.06, 0.01)
    assert lock.direction == "horizontal"
    lock.update(0.01, 0.06)    # now moving vertically — should stay horizontal
    assert lock.direction == "horizontal"

def test_lock_resets():
    lock = TouchpadDirectionLock(threshold=0.04)
    lock.update(0.0, 0.0)
    lock.update(0.06, 0.01)
    lock.reset()
    assert lock.direction is None
    assert lock.start is None

def test_eq_zone_from_start_x():
    lock = TouchpadDirectionLock(threshold=0.04)
    lock.update(0.1, 0.0)      # start in left third
    lock.update(0.11, 0.06)    # vertical lock
    assert lock.eq_zone == "low"

def test_eq_zone_mid():
    lock = TouchpadDirectionLock(threshold=0.04)
    lock.update(0.5, 0.0)
    lock.update(0.5, 0.06)
    assert lock.eq_zone == "mid"

def test_eq_zone_high():
    lock = TouchpadDirectionLock(threshold=0.04)
    lock.update(0.8, 0.0)
    lock.update(0.8, 0.06)
    assert lock.eq_zone == "high"
```

**Step 2:** Run to confirm failure
```bash
pytest tests/test_mapping.py -k "lock" -v
```

**Step 3:** Implement `TouchpadDirectionLock`

```python
import math

class TouchpadDirectionLock:
    def __init__(self, threshold: float = 0.04):
        self._threshold = threshold
        self.direction = None
        self.start = None
        self.eq_zone = None

    def update(self, x: float, y: float):
        if self.start is None:
            self.start = (x, y)
            return
        if self.direction is not None:
            return  # already locked
        dx = x - self.start[0]
        dy = y - self.start[1]
        magnitude = math.sqrt(dx ** 2 + dy ** 2)
        if magnitude < self._threshold:
            return
        if abs(dx) >= abs(dy):
            self.direction = "horizontal"
        else:
            self.direction = "vertical"
            sx = self.start[0]
            if sx < 0.333:
                self.eq_zone = "low"
            elif sx < 0.667:
                self.eq_zone = "mid"
            else:
                self.eq_zone = "high"

    def reset(self):
        self.direction = None
        self.start = None
        self.eq_zone = None
```

**Step 4:** Run tests
```bash
pytest tests/test_mapping.py -k "lock" -v
```
Expected: all PASSED

---

## Task 4: `InputMapper` — core process loop

**Step 1:** Add tests for key mappings

```python
from src.mapping import InputMapper
from src.controller import ControllerState
import time

def _blank_state(**overrides) -> ControllerState:
    defaults = dict(
        left_stick_x=0.0, left_stick_y=0.0,
        right_stick_x=0.0, right_stick_y=0.0,
        l3=False, r3=False,
        l2_analog=0.0, r2_analog=0.0,
        l1=False, r1=False,
        dpad_up=False, dpad_right=False, dpad_down=False, dpad_left=False,
        triangle=False, circle=False, cross=False, square=False,
        create=False, options=False, mute=False, ps=False,
        touchpad_active=False, touchpad_finger1_x=0.5, touchpad_finger1_y=0.5,
        touchpad_finger2_active=False, touchpad_finger2_x=0.0, touchpad_finger2_y=0.0,
        touchpad_click=False,
        gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
        accel_x=0.0, accel_y=0.0, accel_z=1.0,
        timestamp=time.monotonic(),
    )
    defaults.update(overrides)
    return ControllerState(**defaults)

def _config():
    return {
        "controller": {"deadzone": 0.08, "touchpad_crossfader_smoothing": 0.15,
                       "direction_lock_threshold": 0.04},
        "filter": {"stick_curve": "linear", "stick_exponent": 2.0},
        "gyro": {"roll_unit": 0, "roll_target": "mix",
                 "pitch_unit": 1, "pitch_target": "parameter1",
                 "tilt_range_degrees": 45.0},
    }

def test_l1_press_emits_play_pause_deck_a():
    mapper = InputMapper(_config())
    mapper.process(_blank_state())  # prime prev_state
    actions = mapper.process(_blank_state(l1=True))
    types = [a.action_type for a in actions]
    assert "play_pause" in types
    play = next(a for a in actions if a.action_type == "play_pause")
    assert play.deck == "A"

def test_l2_analog_emits_volume_deck_a():
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(l2_analog=0.8))
    vol = next((a for a in actions if a.action_type == "volume" and a.deck == "A"), None)
    assert vol is not None
    assert vol.value == pytest.approx(0.8, abs=0.01)

def test_dpad_up_emits_hot_cue_1_deck_a():
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(dpad_up=True))
    cue = next((a for a in actions if a.action_type == "hot_cue" and a.deck == "A"), None)
    assert cue is not None
    assert cue.extra["cue_index"] == 1

def test_mute_toggles_gyro():
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(mute=True))
    gyro = next((a for a in actions if a.action_type == "gyro_toggle"), None)
    assert gyro is not None

def test_options_held_sets_eq_mode():
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    mapper.process(_blank_state(options=True))
    assert mapper.eq_mode is True

def test_l3_in_gyro_mode_cycles_roll_binding():
    mapper = InputMapper(_config())
    mapper.gyro_enabled = True
    mapper.process(_blank_state())
    initial_unit = mapper.gyro_roll_binding.unit
    mapper.process(_blank_state(l3=True))
    assert mapper.gyro_roll_binding.unit == (initial_unit + 1) % 4
```

**Step 2:** Run to confirm failure
```bash
pytest tests/test_mapping.py -k "mapper" -v
```

**Step 3:** Implement `InputMapper` — this is the largest module. Write it in full in `src/mapping.py`. Key points:

- Constructor sets `prev_state = None`, `smoothed_crossfader = 0.5`, `gyro_enabled = False`, `eq_mode = False`, `_touchpad_lock = TouchpadDirectionLock(threshold)`, `gyro_roll_binding = GyroBinding(...)`, `gyro_pitch_binding = GyroBinding(...)`
- `process()` runs the 10-step sequence from the design doc, checking `prev_state` before accessing it (first call primes it)
- Button edges always compare to `prev_state`; if `prev_state` is `None`, treat all buttons as unpressed
- Analog thresholds: volume/filter/eq > 0.005, pitch nudge > 0.15
- Gyro integration: use accelerometer for tilt angle (`math.atan2`) rather than integrating angular velocity (simpler, no drift)

Refer to design doc Section 4.3 for the complete mapping table.

**Step 4:** Run all mapping tests
```bash
pytest tests/test_mapping.py -v
```
Expected: all PASSED
