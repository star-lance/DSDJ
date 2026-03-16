"""Hardware interface layer for the DualSense PS5 gamepad.

This module is the lowest layer in the stack.  It owns the physical USB/BT
connection to the DualSense controller and translates raw HID report values
into a clean, normalised ``ControllerState`` dataclass consumed by the
mapping layer.

Key responsibilities:
    - Wrap ``pydualsense`` (a third-party HID library) behind a stable API.
    - Apply deadzone filtering and axis normalisation so higher layers receive
      values in predictable ranges (−1.0..1.0 for sticks, 0.0..1.0 for
      triggers and touchpad coordinates).
    - Expose ``set_led_color`` / ``close`` for lifecycle management.

Note on naming:
    The ``pydualsense`` package uses the same name for both the Python module
    and its main class (``pydualsense.pydualsense``).  The constructor comment
    ``# outer pydualsense = module, inner pydualsense = class name`` clarifies
    this intentional-looking redundancy.
"""

import time
from dataclasses import dataclass

import pydualsense


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def normalize_stick(raw: int, deadzone: float) -> float:
    """Convert a raw 0-255 stick byte to a deadzone-filtered −1.0..1.0 float.

    The pydualsense library exposes stick axes as signed integers in the range
    −128..127 where 0 is the mechanical centre.  This function performs three
    steps:

    1. **Scale**: ``value = raw / 128.0``
       Maps the range [−128, 127] to approximately [−1.0, 1.0].
    2. **Deadzone gate**: if ``|value| < deadzone`` return 0.0.
       Eliminates the natural mechanical drift around the centre position.
    3. **Deadzone rescale**: ``sign * (|value| - deadzone) / (1.0 - deadzone)``
       Linearly remaps the live zone [deadzone, 1.0] back to [0.0, 1.0] so
       that the output range is still a full [−1.0, 1.0] after the dead band
       is removed.  Without this step a non-zero deadzone would cause a
       discontinuity at the deadzone boundary.

    Args:
        raw: Signed integer from pydualsense (−128..127, centre = 0).
        deadzone: Fraction of the full range to treat as zero (e.g. 0.08).

    Returns:
        Normalised stick value in the range −1.0..1.0, or exactly 0.0 when
        inside the deadzone.
    """
    value = raw / 128.0
    if abs(value) < deadzone:
        return 0.0
    # >= (not >) intentional: correctly handles zero-deadzone edge case
    sign = 1.0 if value >= 0.0 else -1.0
    return sign * (abs(value) - deadzone) / (1.0 - deadzone)


def normalize_trigger(raw: int) -> float:
    """Convert a raw 0-255 trigger byte to a 0.0..1.0 float.

    The DualSense L2/R2 triggers report their analog depth as an unsigned byte
    (0 = fully released, 255 = fully pressed).

    Args:
        raw: Raw unsigned byte from the HID report (0-255).

    Returns:
        Trigger depth in the range 0.0 (released) to 1.0 (fully pressed).
    """
    return raw / 255.0


def normalize_touchpad(raw: int, max_val: int) -> float:
    """Normalize a touchpad coordinate to a 0.0..1.0 fraction.

    The DualSense touchpad reports absolute finger positions in a fixed pixel
    grid: 1920 wide (0-1919) × 943 tall (0-942).  Dividing by the axis
    maximum converts to a device-independent [0.0, 1.0] range that the mapping
    layer can use without knowing the hardware resolution.

    Args:
        raw: Raw pixel coordinate from the HID report.
        max_val: Maximum pixel value for this axis (1919 for X, 942 for Y).

    Returns:
        Normalised position in the range 0.0..1.0.
    """
    return raw / max_val


# ---------------------------------------------------------------------------
# ControllerState dataclass
# ---------------------------------------------------------------------------


@dataclass
class ControllerState:
    """Normalised snapshot of every input on the DualSense controller.

    All values are already normalised by the time they reach this dataclass —
    no further scaling should be needed by consumers.

    Grouping of the 36 fields:

    **Analog sticks** (−1.0 to 1.0, deadzone applied):
        ``left_stick_x``, ``left_stick_y``, ``right_stick_x``,
        ``right_stick_y``.
        Positive X = right, positive Y = down (raw HID convention).

    **Stick clicks** (bool):
        ``l3`` (left stick pressed), ``r3`` (right stick pressed).

    **Triggers** (0.0 = released → 1.0 = fully pressed):
        ``l2_analog``, ``r2_analog``.

    **Bumpers** (bool):
        ``l1``, ``r1``.

    **D-Pad** (bool, one per direction):
        ``dpad_up``, ``dpad_right``, ``dpad_down``, ``dpad_left``.

    **Face buttons** (bool):
        ``triangle``, ``circle``, ``cross``, ``square``.

    **Center / system buttons** (bool):
        ``create`` (formerly "Share"), ``options``, ``mute`` (microphone
        button with LED), ``ps`` (PlayStation logo).

    **Touchpad** — finger 1:
        ``touchpad_active`` (bool): True when at least one finger is present.
        ``touchpad_finger1_x`` (0.0 = left edge → 1.0 = right edge).
        ``touchpad_finger1_y`` (0.0 = top edge → 1.0 = bottom edge).

    **Touchpad** — finger 2:
        ``touchpad_finger2_active`` (bool).
        ``touchpad_finger2_x``, ``touchpad_finger2_y`` (same range as finger 1).

    **Touchpad click** (bool):
        ``touchpad_click``: physical click of the touchpad surface.

    **Gyroscope** (degrees per second, hardware units):
        ``gyro_x``, ``gyro_y``, ``gyro_z``.
        The mapping layer uses only the accelerometer for tilt; gyro data is
        captured here for completeness and future use.

    **Accelerometer** (G-force units):
        ``accel_x``, ``accel_y``, ``accel_z``.
        Used by the mapping layer to compute relative tilt angles via atan2.

    **Timestamp**:
        ``timestamp``: ``time.monotonic()`` value at the moment the HID
        report was read, used by the track-browse throttle logic.
    """

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
    """Thin wrapper around pydualsense exposing a clean read_state() API.

    ``pydualsense`` (the module) provides ``pydualsense.pydualsense`` (the
    class) — both the package and its primary class share the same name.
    This class hides that quirk and presents a minimal surface: initialise,
    poll, set LED, close.

    Attributes:
        _deadzone: Stick deadzone fraction loaded from config (default 0.08).
        _ds: The underlying ``pydualsense.pydualsense`` instance that manages
            the HID connection.
    """

    def __init__(self, config: dict):
        """Initialize pydualsense and open the HID connection.

        Reads the ``deadzone`` key from ``config`` (defaults to 0.08 if
        absent) and calls ``pydualsense.init()`` which opens the USB/BT HID
        device.

        Args:
            config: Controller configuration sub-dict (the ``controller``
                section of ``config.yaml``).

        Raises:
            Exception: Propagates any error from ``pydualsense.init()`` —
                typically ``OSError`` if no DualSense is connected.
        """
        self._deadzone = config.get("deadzone", 0.08)
        # outer pydualsense = module, inner pydualsense = class name (both happen to be the same)
        self._ds = pydualsense.pydualsense()
        self._ds.init()
        # Wait for the HID thread to deliver the first real report.
        # pydualsense initializes stick axes to 128 (unsigned) before any HID
        # data arrives; the first real report switches to signed values (0=center).
        # Without this sleep the first read_state() call returns stale 128 values,
        # which normalize_stick would map to 1.0 instead of 0.0.
        time.sleep(0.15)

    def read_state(self) -> ControllerState:
        """Read pydualsense state and return a normalized ControllerState.

        This is a blocking call that reads the latest HID report from the
        ``pydualsense`` internal state object.  It is designed to be called
        from a ``ThreadPoolExecutor`` thread via ``loop.run_in_executor`` so
        that it does not stall the asyncio event loop.

        Returns:
            A fully normalised ``ControllerState`` snapshot with a
            ``time.monotonic()`` timestamp.
        """
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
            l2_analog=normalize_trigger(s.L2_value),
            r2_analog=normalize_trigger(s.R2_value),
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
            create=bool(s.share),
            options=bool(s.options),
            mute=bool(s.micBtn),
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
            touchpad_click=bool(s.touchBtn),
            # Gyro
            gyro_x=float(s.gyro.Pitch),
            gyro_y=float(s.gyro.Yaw),
            gyro_z=float(s.gyro.Roll),
            # Accelerometer
            accel_x=float(s.accelerometer.X),
            accel_y=float(s.accelerometer.Y),
            accel_z=float(s.accelerometer.Z),
            # Timestamp
            timestamp=time.monotonic(),
        )

    @property
    def is_connected(self) -> bool:
        """Return False if pydualsense's read thread has died (USB disconnect)."""
        return bool(getattr(self._ds, "connected", True))

    def reconnect(self):
        """Close the current pydualsense instance and open a fresh one.

        Called by the controller loop when a disconnect is detected.
        Raises the same exceptions as __init__ if no device is found.
        """
        try:
            self._ds.close()
        except Exception:
            pass
        self._ds = pydualsense.pydualsense()
        self._ds.init()
        time.sleep(0.15)

    def set_led_color(self, r: int, g: int, b: int):
        """Set the DualSense lightbar color.

        Args:
            r: Red component (0-255).
            g: Green component (0-255).
            b: Blue component (0-255).
        """
        self._ds.light.setColorI(r, g, b)

    def close(self):
        """Release the DualSense HID device.

        Should be called on shutdown to cleanly close the USB/BT connection
        and allow the OS to reclaim the device handle.
        """
        self._ds.close()
