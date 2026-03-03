"""Mapping layer: converts ControllerState snapshots into DJAction lists.

This is the core DJ logic layer. It takes a ControllerState (from the
DualSense controller hardware interface) and emits a list of DJAction
objects that get forwarded to the MIDI bridge and UI state manager.
"""

import math
from dataclasses import dataclass, field

from src.state import GyroBinding


# ---------------------------------------------------------------------------
# Task 1: DJAction dataclass
# ---------------------------------------------------------------------------


@dataclass
class DJAction:
    action_type: str   # matches ActionType strings
    deck: str          # "A", "B", or "master"
    value: float       # 0.0-1.0 for analog, 1.0 for button press
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Task 2: Helper functions
# ---------------------------------------------------------------------------


def detect_edge(current: bool, previous: bool) -> str:
    """Detect button press/release edges.

    Returns "pressed" on False->True transition,
    "released" on True->False, or "none" if unchanged.
    """
    if current and not previous:
        return "pressed"
    if not current and previous:
        return "released"
    return "none"


def apply_smoothing(current: float, previous: float, factor: float) -> float:
    """Exponential moving average: previous + factor * (current - previous)."""
    return previous + factor * (current - previous)


def apply_stick_curve(value: float, curve: str, exponent: float) -> float:
    """Apply a response curve to a stick/analog value.

    Curves:
        "linear"      -- pass through unchanged
        "exponential" -- apply power curve, preserving sign
    """
    if curve == "linear":
        return value
    sign = 1.0 if value >= 0 else -1.0
    return sign * (abs(value) ** exponent)


# ---------------------------------------------------------------------------
# Task 3: TouchpadDirectionLock
# ---------------------------------------------------------------------------


class TouchpadDirectionLock:
    """Lock touchpad gesture to a single axis (horizontal or vertical).

    On first contact, records the start position. Once movement exceeds
    the threshold, locks to whichever axis had greater displacement.
    Vertical locks also record which EQ zone the gesture started in
    (based on horizontal start position: low/mid/high thirds).
    """

    def __init__(self, threshold: float = 0.04):
        self._threshold = threshold
        self.direction = None   # None | "horizontal" | "vertical"
        self.start = None       # (x, y) of first contact
        self.eq_zone = None     # None | "low" | "mid" | "high"

    def update(self, x: float, y: float):
        """Feed the current finger position. Call on every touchpad frame."""
        if self.start is None:
            self.start = (x, y)
            return
        if self.direction is not None:
            return  # already locked -- ignore subsequent updates
        dx = x - self.start[0]
        dy = y - self.start[1]
        magnitude = math.sqrt(dx ** 2 + dy ** 2)
        if magnitude < self._threshold:
            return  # not enough movement yet
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
        """Clear lock state (call when finger lifts off touchpad)."""
        self.direction = None
        self.start = None
        self.eq_zone = None


# ---------------------------------------------------------------------------
# Task 4: InputMapper -- the core processing class
# ---------------------------------------------------------------------------


class InputMapper:
    """Converts ControllerState snapshots into lists of DJAction objects.

    Maintains internal state for:
    - Previous controller state (for edge detection)
    - Smoothed crossfader value
    - Gyro enable/disable toggle
    - EQ mode (held Options button)
    - Touchpad direction lock
    - Gyro axis bindings
    """

    def __init__(self, config: dict):
        self.prev_state = None
        self.smoothed_crossfader = 0.5
        self.gyro_enabled = False
        self.eq_mode = False
        self._touchpad_lock = TouchpadDirectionLock(
            threshold=config["controller"]["direction_lock_threshold"]
        )
        self._smoothing = config["controller"]["touchpad_crossfader_smoothing"]
        self._stick_curve = config["filter"]["stick_curve"]
        self._stick_exponent = config["filter"]["stick_exponent"]
        self._tilt_range = config["gyro"]["tilt_range_degrees"]
        self.gyro_reference = None  # (accel_x, accel_y, accel_z) at gyro enable
        self._last_browse_time = 0.0
        self.gyro_roll_binding = GyroBinding(
            unit=config["gyro"]["roll_unit"],
            target=config["gyro"]["roll_target"],
        )
        self.gyro_pitch_binding = GyroBinding(
            unit=config["gyro"]["pitch_unit"],
            target=config["gyro"]["pitch_target"],
        )

    def process(self, state) -> list:
        """Process a ControllerState and return a list of DJAction objects.

        On the very first call prev_state is None; we use the current state
        as previous so no spurious edge events fire on first poll.
        """
        actions = []
        prev = self.prev_state if self.prev_state is not None else state

        # ------------------------------------------------------------------
        # a) Volume -- L2/R2 analog, always emitted when depressed
        # ------------------------------------------------------------------
        if state.l2_analog > 0.005:
            actions.append(DJAction("volume", "A", state.l2_analog))
        if state.r2_analog > 0.005:
            actions.append(DJAction("volume", "B", state.r2_analog))

        # ------------------------------------------------------------------
        # b) Play/Pause -- L1/R1 bumpers, edge detection
        # ------------------------------------------------------------------
        if detect_edge(state.l1, prev.l1) == "pressed":
            actions.append(DJAction("play_pause", "A", 1.0))
        if detect_edge(state.r1, prev.r1) == "pressed":
            actions.append(DJAction("play_pause", "B", 1.0))

        # ------------------------------------------------------------------
        # c) Sticks -- filter/nudge in normal mode, EQ in eq_mode
        # ------------------------------------------------------------------
        lsy = apply_stick_curve(state.left_stick_y, self._stick_curve, self._stick_exponent)
        lsx = apply_stick_curve(state.left_stick_x, self._stick_curve, self._stick_exponent)
        rsy = apply_stick_curve(state.right_stick_y, self._stick_curve, self._stick_exponent)
        rsx = apply_stick_curve(state.right_stick_x, self._stick_curve, self._stick_exponent)

        if self.eq_mode:
            if abs(lsy) > 0.005:
                actions.append(DJAction("eq_low", "A", (lsy + 1) / 2))
            if abs(lsx) > 0.005:
                actions.append(DJAction("eq_high", "A", (lsx + 1) / 2))
            if abs(rsy) > 0.005:
                actions.append(DJAction("eq_low", "B", (rsy + 1) / 2))
            if abs(rsx) > 0.005:
                actions.append(DJAction("eq_high", "B", (rsx + 1) / 2))
        else:
            if abs(lsy) > 0.005:
                actions.append(DJAction("filter", "A", (lsy + 1) / 2))
            if abs(lsx) > 0.15:
                actions.append(DJAction("pitch_nudge", "A", lsx))
            if abs(rsy) > 0.005:
                actions.append(DJAction("filter", "B", (rsy + 1) / 2))
            if abs(rsx) > 0.15:
                actions.append(DJAction("pitch_nudge", "B", rsx))

        # ------------------------------------------------------------------
        # d) L3/R3 -- sync toggle normal mode, gyro binding cycle when gyro enabled
        # ------------------------------------------------------------------
        if detect_edge(state.l3, prev.l3) == "pressed":
            if self.gyro_enabled:
                # cycle_unit() mutates the GyroBinding in place, returns None
                self.gyro_roll_binding.cycle_unit()
            else:
                actions.append(DJAction("sync_toggle", "A", 1.0))

        if detect_edge(state.r3, prev.r3) == "pressed":
            if self.gyro_enabled:
                self.gyro_pitch_binding.cycle_unit()
            else:
                actions.append(DJAction("sync_toggle", "B", 1.0))

        # ------------------------------------------------------------------
        # e) D-Pad hot cues (deck A): up=1, right=2, down=3, left=4
        # ------------------------------------------------------------------
        dpad_attrs = ["dpad_up", "dpad_right", "dpad_down", "dpad_left"]
        for cue_index, attr in enumerate(dpad_attrs, start=1):
            pressed = getattr(state, attr)
            prev_val = getattr(prev, attr)
            if detect_edge(pressed, prev_val) == "pressed":
                actions.append(DJAction("hot_cue", "A", 1.0, {"cue_index": cue_index}))

        # ------------------------------------------------------------------
        # f) Face buttons hot cues (deck B): triangle=1, circle=2, cross=3, square=4
        # ------------------------------------------------------------------
        face_buttons = [
            (state.triangle, prev.triangle, 1),
            (state.circle,   prev.circle,   2),
            (state.cross,    prev.cross,    3),
            (state.square,   prev.square,   4),
        ]
        for btn, prev_btn, cue_index in face_buttons:
            if detect_edge(btn, prev_btn) == "pressed":
                actions.append(DJAction("hot_cue", "B", 1.0, {"cue_index": cue_index}))

        # ------------------------------------------------------------------
        # g) Create button -- loop toggle (deck A)
        # ------------------------------------------------------------------
        if detect_edge(state.create, prev.create) == "pressed":
            actions.append(DJAction("loop_toggle", "A", 1.0))

        # ------------------------------------------------------------------
        # h) Options button -- eq_mode while held
        # ------------------------------------------------------------------
        self.eq_mode = state.options

        # ------------------------------------------------------------------
        # i) Mute button -- gyro toggle
        # ------------------------------------------------------------------
        if detect_edge(state.mute, prev.mute) == "pressed":
            self.gyro_enabled = not self.gyro_enabled
            if self.gyro_enabled:
                self.gyro_reference = (state.accel_x, state.accel_y, state.accel_z)
            else:
                self.gyro_reference = None
            actions.append(DJAction("gyro_toggle", "master", 1.0 if self.gyro_enabled else 0.0))

        # ------------------------------------------------------------------
        # j) Touchpad processing
        # ------------------------------------------------------------------
        if state.touchpad_active:
            self._touchpad_lock.update(state.touchpad_finger1_x, state.touchpad_finger1_y)
            if self._touchpad_lock.direction == "horizontal":
                self.smoothed_crossfader = apply_smoothing(
                    state.touchpad_finger1_x,
                    self.smoothed_crossfader,
                    self._smoothing,
                )
                actions.append(DJAction("crossfader", "master", self.smoothed_crossfader))
            elif self._touchpad_lock.direction == "vertical":
                if self.eq_mode and self._touchpad_lock.eq_zone:
                    zone_map = {"low": "eq_low", "mid": "eq_mid", "high": "eq_high"}
                    eq_type = zone_map[self._touchpad_lock.eq_zone]
                    actions.append(DJAction(eq_type, "A", state.touchpad_finger1_y))
                else:
                    # Track browse: positive dy = scroll down, negative = scroll up
                    dy = state.touchpad_finger1_y - self._touchpad_lock.start[1]
                    now = state.timestamp
                    if abs(dy) > 0.02 and (now - self._last_browse_time) >= 0.05:
                        self._last_browse_time = now
                        actions.append(DJAction("track_browse", "master", dy))
        else:
            self._touchpad_lock.reset()

        # ------------------------------------------------------------------
        # k) Gyro processing (accelerometer-based relative tilt, no drift)
        # ------------------------------------------------------------------
        if self.gyro_enabled and self.gyro_reference is not None:
            ref_x, ref_y, ref_z = self.gyro_reference
            # Tilt relative to reference position
            roll_angle = math.atan2(state.accel_x - ref_x, ref_z)
            pitch_angle = math.atan2(state.accel_y - ref_y, ref_z)
            tilt_range_rad = math.radians(self._tilt_range)
            roll_val = max(0.0, min(1.0, (roll_angle / tilt_range_rad + 1.0) / 2.0))
            pitch_val = max(0.0, min(1.0, (pitch_angle / tilt_range_rad + 1.0) / 2.0))
            actions.append(DJAction("effect_wet_dry", "master", roll_val))
            actions.append(DJAction("effect_parameter", "master", pitch_val))

        # ------------------------------------------------------------------
        # l) Update previous state for next call
        # ------------------------------------------------------------------
        self.prev_state = state
        return actions
