"""Hardware interface layer for the DualSense PS5 gamepad.

Wraps pydualsense and exposes a clean read_state() API that returns a
normalized ControllerState dataclass.
"""

import time
from dataclasses import dataclass

import pydualsense


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def normalize_stick(raw: int, deadzone: float) -> float:
    """Convert raw 0-255 stick value to -1.0..1.0 with deadzone.

    Steps:
    1. Convert raw to -1.0..1.0: value = (raw - 128) / 128.0
    2. If abs(value) < deadzone: return 0.0
    3. Otherwise: sign * (abs(value) - deadzone) / (1.0 - deadzone)
    """
    value = (raw - 128) / 128.0
    if abs(value) < deadzone:
        return 0.0
    sign = 1.0 if value >= 0.0 else -1.0
    return sign * (abs(value) - deadzone) / (1.0 - deadzone)


def normalize_trigger(raw: int) -> float:
    """Convert raw 0-255 to 0.0..1.0: return raw / 255.0"""
    return raw / 255.0


def normalize_touchpad(raw: int, max_val: int) -> float:
    """Normalize touchpad coordinate: return raw / max_val"""
    return raw / max_val


# ---------------------------------------------------------------------------
# ControllerState dataclass
# ---------------------------------------------------------------------------


@dataclass
class ControllerState:
    # Sticks (-1.0 to 1.0, deadzone applied)
    left_stick_x: float
    left_stick_y: float
    right_stick_x: float
    right_stick_y: float
    # Stick clicks
    l3: bool
    r3: bool
    # Triggers (0.0 to 1.0)
    l2_analog: float
    r2_analog: float
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
    create: bool
    options: bool
    mute: bool
    ps: bool
    # Touchpad
    touchpad_active: bool
    touchpad_finger1_x: float   # 0.0 (left) to 1.0 (right)
    touchpad_finger1_y: float   # 0.0 (top) to 1.0 (bottom)
    touchpad_finger2_active: bool
    touchpad_finger2_x: float
    touchpad_finger2_y: float
    touchpad_click: bool
    # Motion (degrees/sec for gyro, G for accel)
    gyro_x: float
    gyro_y: float
    gyro_z: float
    accel_x: float
    accel_y: float
    accel_z: float
    # Timestamp
    timestamp: float


# ---------------------------------------------------------------------------
# DualSenseController
# ---------------------------------------------------------------------------

_TOUCHPAD_MAX_X = 1919
_TOUCHPAD_MAX_Y = 942


class DualSenseController:
    """Thin wrapper around pydualsense exposing a clean read_state() API."""

    def __init__(self, config: dict):
        """Initialize pydualsense with the given config dict.

        Reads ``deadzone`` from config (default 0.08).
        """
        self._deadzone = config.get("deadzone", 0.08)
        self._ds = pydualsense.pydualsense()
        self._ds.init()

    def read_state(self) -> ControllerState:
        """Read pydualsense state and return a normalized ControllerState."""
        ds = self._ds
        s = ds.state
        dz = self._deadzone

        touch0 = s.trackPadTouch0
        touch1 = s.trackPadTouch1

        return ControllerState(
            # Sticks
            left_stick_x=normalize_stick(s.LX, dz),
            left_stick_y=normalize_stick(s.LY, dz),
            right_stick_x=normalize_stick(s.RX, dz),
            right_stick_y=normalize_stick(s.RY, dz),
            # Stick clicks
            l3=bool(s.L3),
            r3=bool(s.R3),
            # Triggers
            l2_analog=normalize_trigger(s.L2),
            r2_analog=normalize_trigger(s.R2),
            # Bumpers
            l1=bool(s.L1),
            r1=bool(s.R1),
            # D-Pad
            dpad_up=bool(s.DpadUp),
            dpad_right=bool(s.DpadRight),
            dpad_down=bool(s.DpadDown),
            dpad_left=bool(s.DpadLeft),
            # Face buttons
            triangle=bool(s.triangle),
            circle=bool(s.circle),
            cross=bool(s.cross),
            square=bool(s.square),
            # Center buttons
            create=bool(s.create),
            options=bool(s.options),
            mute=bool(s.mute),
            ps=bool(s.ps),
            # Touchpad finger 1
            touchpad_active=bool(touch0.isActive),
            touchpad_finger1_x=normalize_touchpad(touch0.X, _TOUCHPAD_MAX_X),
            touchpad_finger1_y=normalize_touchpad(touch0.Y, _TOUCHPAD_MAX_Y),
            # Touchpad finger 2
            touchpad_finger2_active=bool(touch1.isActive),
            touchpad_finger2_x=normalize_touchpad(touch1.X, _TOUCHPAD_MAX_X),
            touchpad_finger2_y=normalize_touchpad(touch1.Y, _TOUCHPAD_MAX_Y),
            # Touchpad click
            touchpad_click=bool(s.touchpad),
            # Gyro
            gyro_x=float(s.gyro.X),
            gyro_y=float(s.gyro.Y),
            gyro_z=float(s.gyro.Z),
            # Accelerometer
            accel_x=float(s.accelerometer.X),
            accel_y=float(s.accelerometer.Y),
            accel_z=float(s.accelerometer.Z),
            # Timestamp
            timestamp=time.monotonic(),
        )

    def set_led_color(self, r: int, g: int, b: int):
        """Set the lightbar color."""
        self._ds.light.setColorI(r, g, b)

    def close(self):
        """Release the DualSense device."""
        self._ds.close()
