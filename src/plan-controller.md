# `controller.py` Implementation Plan

> **For Claude:** Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Wrap pydualsense into a clean `DualSenseController` that exposes a single `read_state()` returning a normalized `ControllerState`. All unit tests use mocks; hardware tests are in `tests/integration/`.

**File:** `src/controller.py`
**Tests:** `tests/test_controller.py`, `tests/integration/test_controller_live.py`
**Dependencies:** `pydualsense`, `src/state.py` must exist (not imported — just consistent naming)

---

## Task 1: `ControllerState` dataclass

**Step 1:** Write failing test in `tests/test_controller.py`

```python
from src.controller import ControllerState
import time

def test_controller_state_fields():
    s = ControllerState(
        left_stick_x=0.0, left_stick_y=0.0,
        right_stick_x=0.0, right_stick_y=0.0,
        l3=False, r3=False,
        l2_analog=0.0, r2_analog=0.0,
        l1=False, r1=False,
        dpad_up=False, dpad_right=False, dpad_down=False, dpad_left=False,
        triangle=False, circle=False, cross=False, square=False,
        create=False, options=False, mute=False, ps=False,
        touchpad_active=False, touchpad_finger1_x=0.0, touchpad_finger1_y=0.0,
        touchpad_finger2_active=False, touchpad_finger2_x=0.0, touchpad_finger2_y=0.0,
        touchpad_click=False,
        gyro_x=0.0, gyro_y=0.0, gyro_z=0.0,
        accel_x=0.0, accel_y=0.0, accel_z=1.0,
        timestamp=time.monotonic()
    )
    assert s.left_stick_x == 0.0
    assert s.accel_z == 1.0
```

**Step 2:** Run to confirm failure
```bash
pytest tests/test_controller.py::test_controller_state_fields -v
```

**Step 3:** Implement `ControllerState` in `src/controller.py`

```python
from dataclasses import dataclass
import time

@dataclass
class ControllerState:
    left_stick_x: float
    left_stick_y: float
    right_stick_x: float
    right_stick_y: float
    l3: bool
    r3: bool
    l2_analog: float
    r2_analog: float
    l1: bool
    r1: bool
    dpad_up: bool
    dpad_right: bool
    dpad_down: bool
    dpad_left: bool
    triangle: bool
    circle: bool
    cross: bool
    square: bool
    create: bool
    options: bool
    mute: bool
    ps: bool
    touchpad_active: bool
    touchpad_finger1_x: float
    touchpad_finger1_y: float
    touchpad_finger2_active: bool
    touchpad_finger2_x: float
    touchpad_finger2_y: float
    touchpad_click: bool
    gyro_x: float
    gyro_y: float
    gyro_z: float
    accel_x: float
    accel_y: float
    accel_z: float
    timestamp: float
```

**Step 4:** Run test
```bash
pytest tests/test_controller.py::test_controller_state_fields -v
```
Expected: PASSED

---

## Task 2: Normalization helpers

**Step 1:** Add tests

```python
from src.controller import normalize_stick, normalize_trigger, normalize_touchpad

def test_normalize_stick_center():
    assert normalize_stick(128, deadzone=0.08) == pytest.approx(0.0, abs=0.01)

def test_normalize_stick_max():
    assert normalize_stick(255, deadzone=0.08) == pytest.approx(1.0, abs=0.01)

def test_normalize_stick_min():
    assert normalize_stick(0, deadzone=0.08) == pytest.approx(-1.0, abs=0.01)

def test_normalize_stick_deadzone():
    # A small deflection within the deadzone should return 0.0
    assert normalize_stick(133, deadzone=0.08) == 0.0

def test_normalize_trigger():
    assert normalize_trigger(0) == 0.0
    assert normalize_trigger(255) == pytest.approx(1.0, abs=0.01)
    assert normalize_trigger(128) == pytest.approx(0.502, abs=0.01)

def test_normalize_touchpad():
    assert normalize_touchpad(0, 1919) == pytest.approx(0.0, abs=0.001)
    assert normalize_touchpad(1919, 1919) == pytest.approx(1.0, abs=0.001)
    assert normalize_touchpad(960, 1919) == pytest.approx(0.5, abs=0.01)
```

Add `import pytest` at top of test file.

**Step 2:** Run to confirm failure
```bash
pytest tests/test_controller.py -k "normalize" -v
```

**Step 3:** Implement helpers in `src/controller.py`

```python
def normalize_stick(raw: int, deadzone: float) -> float:
    """Convert raw 0-255 stick value to -1.0..1.0 with deadzone."""
    value = (raw - 128) / 128.0
    if abs(value) < deadzone:
        return 0.0
    sign = 1.0 if value > 0 else -1.0
    return sign * (abs(value) - deadzone) / (1.0 - deadzone)

def normalize_trigger(raw: int) -> float:
    """Convert raw 0-255 trigger to 0.0..1.0."""
    return raw / 255.0

def normalize_touchpad(raw: int, max_val: int) -> float:
    """Normalize touchpad coordinate."""
    return raw / max_val
```

**Step 4:** Run tests
```bash
pytest tests/test_controller.py -v
```
Expected: all PASSED

---

## Task 3: `DualSenseController` with mocked pydualsense

**Step 1:** Add tests using mock

```python
from unittest.mock import MagicMock, patch
from src.controller import DualSenseController

def _make_mock_ds():
    ds = MagicMock()
    ds.state.LX = 128
    ds.state.LY = 128
    ds.state.RX = 128
    ds.state.RY = 128
    ds.state.L2 = 0
    ds.state.R2 = 0
    ds.state.L1 = False
    ds.state.R1 = False
    ds.state.L3 = False
    ds.state.R3 = False
    ds.state.DpadUp = False
    ds.state.DpadRight = False
    ds.state.DpadDown = False
    ds.state.DpadLeft = False
    ds.state.triangle = False
    ds.state.circle = False
    ds.state.cross = False
    ds.state.square = False
    ds.state.create = False
    ds.state.options = False
    ds.state.mute = False
    ds.state.ps = False
    ds.state.trackPadTouch0.isActive = False
    ds.state.trackPadTouch0.X = 0
    ds.state.trackPadTouch0.Y = 0
    ds.state.trackPadTouch1.isActive = False
    ds.state.trackPadTouch1.X = 0
    ds.state.trackPadTouch1.Y = 0
    ds.state.touchpad = False
    ds.state.gyro.X = 0
    ds.state.gyro.Y = 0
    ds.state.gyro.Z = 0
    ds.state.accelerometer.X = 0
    ds.state.accelerometer.Y = 0
    ds.state.accelerometer.Z = 1
    return ds

def test_read_state_returns_controller_state():
    config = {"deadzone": 0.08}
    with patch("src.controller.pydualsense") as mock_pds:
        mock_pds.pydualsense.return_value = _make_mock_ds()
        ctrl = DualSenseController(config)
        state = ctrl.read_state()
    assert state.left_stick_x == pytest.approx(0.0, abs=0.01)
    assert state.l2_analog == 0.0

def test_read_state_trigger_normalized():
    config = {"deadzone": 0.08}
    with patch("src.controller.pydualsense") as mock_pds:
        mock_ds = _make_mock_ds()
        mock_ds.state.L2 = 255
        mock_pds.pydualsense.return_value = mock_ds
        ctrl = DualSenseController(config)
        state = ctrl.read_state()
    assert state.l2_analog == pytest.approx(1.0, abs=0.01)
```

**Step 2:** Run to confirm failure
```bash
pytest tests/test_controller.py -k "read_state" -v
```

**Step 3:** Implement `DualSenseController`

```python
import pydualsense as pydualsense_module
import time

class DualSenseController:
    def __init__(self, config: dict):
        self._deadzone = config.get("deadzone", 0.08)
        self._ds = pydualsense_module.pydualsense()
        self._ds.init()

    def read_state(self) -> ControllerState:
        s = self._ds.state
        return ControllerState(
            left_stick_x=normalize_stick(s.LX, self._deadzone),
            left_stick_y=normalize_stick(s.LY, self._deadzone),
            right_stick_x=normalize_stick(s.RX, self._deadzone),
            right_stick_y=normalize_stick(s.RY, self._deadzone),
            l3=bool(s.L3),
            r3=bool(s.R3),
            l2_analog=normalize_trigger(s.L2),
            r2_analog=normalize_trigger(s.R2),
            l1=bool(s.L1),
            r1=bool(s.R1),
            dpad_up=bool(s.DpadUp),
            dpad_right=bool(s.DpadRight),
            dpad_down=bool(s.DpadDown),
            dpad_left=bool(s.DpadLeft),
            triangle=bool(s.triangle),
            circle=bool(s.circle),
            cross=bool(s.cross),
            square=bool(s.square),
            create=bool(s.create),
            options=bool(s.options),
            mute=bool(s.mute),
            ps=bool(s.ps),
            touchpad_active=bool(s.trackPadTouch0.isActive),
            touchpad_finger1_x=normalize_touchpad(s.trackPadTouch0.X, 1919),
            touchpad_finger1_y=normalize_touchpad(s.trackPadTouch0.Y, 942),
            touchpad_finger2_active=bool(s.trackPadTouch1.isActive),
            touchpad_finger2_x=normalize_touchpad(s.trackPadTouch1.X, 1919),
            touchpad_finger2_y=normalize_touchpad(s.trackPadTouch1.Y, 942),
            touchpad_click=bool(s.touchpad),
            gyro_x=s.gyro.X,
            gyro_y=s.gyro.Y,
            gyro_z=s.gyro.Z,
            accel_x=s.accelerometer.X,
            accel_y=s.accelerometer.Y,
            accel_z=s.accelerometer.Z,
            timestamp=time.monotonic(),
        )

    def set_led_color(self, r: int, g: int, b: int):
        self._ds.light.setColorI(r, g, b)

    def close(self):
        self._ds.close()
```

**Step 4:** Run all controller unit tests
```bash
pytest tests/test_controller.py -v
```
Expected: all PASSED

---

## Task 4: Integration test (requires hardware)

File: `tests/integration/test_controller_live.py`

```python
"""Run with: pytest tests/integration/test_controller_live.py -v -s
Requires DualSense connected via USB."""
import pytest, time
from src.controller import DualSenseController

@pytest.mark.integration
def test_live_reads_state():
    ctrl = DualSenseController({"deadzone": 0.08})
    state = ctrl.read_state()
    print(f"\nStick L: ({state.left_stick_x:.3f}, {state.left_stick_y:.3f})")
    print(f"Triggers: L2={state.l2_analog:.3f} R2={state.r2_analog:.3f}")
    print(f"Touchpad: active={state.touchpad_active} x={state.touchpad_finger1_x:.3f}")
    print(f"Gyro: x={state.gyro_x:.1f} y={state.gyro_y:.1f} z={state.gyro_z:.1f}")
    ctrl.close()
    # If we get here without exception, hardware is working
    assert True
```

Run manually with controller connected:
```bash
pytest tests/integration/test_controller_live.py -v -s -m integration
```
