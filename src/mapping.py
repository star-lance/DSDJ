"""Mapping layer: converts ControllerState snapshots into DJAction lists.

This is the core DJ logic layer.  It takes a ``ControllerState`` (from the
DualSense controller hardware interface) and emits a list of ``DJAction``
objects that get forwarded to the MIDI bridge and UI state manager.

Processing pipeline (``InputMapper.process``):

    a) Volume        — L2/R2 analog triggers → deck A/B volume
    b) Play/Pause    — L1/R1 bumpers (edge-triggered) → play_pause A/B
    c) Sticks        — normal mode: filter + pitch_nudge;
                       eq_mode (Options held): eq_low + eq_high per deck
    d) L3/R3 clicks  — normal: sync_toggle; gyro active: cycle EffectUnit
    e) D-Pad         — edge-triggered hot cues 1-4 on Deck A
    f) Face buttons  — edge-triggered hot cues 1-4 on Deck B
    g) Create button — loop_toggle on Deck A
    h) Options held  — activates eq_mode for sticks and touchpad verticals
    i) Mute button   — gyro_toggle; captures accelerometer reference on enable
    j) Touchpad      — direction-locked: horizontal→crossfader, vertical→track
                       browse (throttled) or EQ (when eq_mode)
    k) Gyro          — accelerometer relative tilt → effect_wet_dry / effect_parameter
    l) State update  — save current state as previous for next call
"""

import math
from dataclasses import dataclass, field

from src.state import GyroBinding


# ---------------------------------------------------------------------------
# Task 1: DJAction dataclass
# ---------------------------------------------------------------------------


@dataclass
class DJAction:
    """A single normalised DJ control action emitted by the mapping layer.

    Attributes:
        action_type: String identifier matching one of the keys in
            ``MIDIBridge._CC_MAP`` / ``_NOTE_MAP``, or ``"hot_cue"`` /
            ``"gyro_toggle"``.
        deck: Target deck for the action: ``"A"``, ``"B"``, or ``"master"``
            for controls that apply to the whole mix (crossfader, effects).
        value: Normalised control value.  0.0-1.0 for analog controls;
            1.0 for momentary button presses; signed float for
            ``"pitch_nudge"`` and ``"track_browse"`` (direction matters).
        extra: Optional payload for action types that need additional data.
            Currently only used by ``"hot_cue"`` which carries
            ``{"cue_index": 1-4}``.
    """

    action_type: str   # matches ActionType strings
    deck: str          # "A", "B", or "master"
    value: float       # 0.0-1.0 for analog, 1.0 for button press
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Task 2: Helper functions
# ---------------------------------------------------------------------------


def detect_edge(current: bool, previous: bool) -> str:
    """Detect button press/release edges.

    Returns ``"pressed"`` on False→True transition, ``"released"`` on
    True→False, or ``"none"`` if the state is unchanged.

    Args:
        current: Button state in the current controller frame.
        previous: Button state in the previous controller frame.

    Returns:
        One of ``"pressed"``, ``"released"``, or ``"none"``.
    """
    if current and not previous:
        return "pressed"
    if not current and previous:
        return "released"
    return "none"


def apply_smoothing(current: float, previous: float, factor: float) -> float:
    """Exponential moving average (EMA) filter.

    Blends the new sample toward the previous value to reduce jitter.
    A factor of 1.0 disables smoothing (output = current); 0.0 freezes the
    output at the previous value.

    Args:
        current: Latest raw sample.
        previous: Previous smoothed value.
        factor: Smoothing weight in [0.0, 1.0].  Higher = faster response,
            lower = more smoothing.

    Returns:
        ``previous + factor * (current - previous)``
    """
    return previous + factor * (current - previous)


def apply_stick_curve(value: float, curve: str, exponent: float) -> float:
    """Apply a response curve to a stick/analog value.

    Curves:
        ``"linear"``      -- pass through unchanged; output == input.
        ``"exponential"`` -- raise ``|value|`` to ``exponent`` power,
            preserving the original sign.  Exponents > 1 create a slow
            centre with snappy edges; exponents < 1 do the opposite.

    Args:
        value: Normalised stick value in the range −1.0..1.0.
        curve: Curve type — ``"linear"`` or ``"exponential"``.
        exponent: Power applied when ``curve == "exponential"``.

    Returns:
        Curved value in the same −1.0..1.0 range as the input.
    """
    if curve == "linear":
        return value
    sign = 1.0 if value >= 0 else -1.0
    return sign * (abs(value) ** exponent)


# ---------------------------------------------------------------------------
# Task 3: TouchpadDirectionLock
# ---------------------------------------------------------------------------


class TouchpadDirectionLock:
    """Lock a touchpad gesture to a single axis (horizontal or vertical).

    Direction-lock algorithm:
        On the first touchpad frame with an active finger, the starting
        position ``(x, y)`` is recorded.  On each subsequent frame the
        Euclidean distance from the start is compared to ``_threshold``.
        Once that distance is exceeded the direction is determined by which
        axis has the larger absolute displacement:

        * ``|dx| >= |dy|`` → lock to ``"horizontal"`` (crossfader control)
        * ``|dx|  < |dy|`` → lock to ``"vertical"`` (track browse / EQ)

        Once a direction is locked, all further ``update()`` calls for the
        same touch are ignored — the direction cannot change mid-gesture.

    EQ zone assignment (vertical gestures only):
        When the lock direction is ``"vertical"``, the horizontal start
        position determines which EQ band the gesture controls.  The
        touchpad is divided into three equal thirds:

        * ``start_x < 0.333`` → ``"low"``   (low-frequency EQ)
        * ``start_x < 0.667`` → ``"mid"``   (mid-frequency EQ)
        * otherwise           → ``"high"``  (high-frequency EQ)

        This mapping is only used when ``eq_mode`` is active.

    Attributes:
        _threshold: Minimum Euclidean displacement (in normalised units)
            required before the direction is committed.
        direction: Current locked direction: ``None``, ``"horizontal"``, or
            ``"vertical"``.
        start: ``(x, y)`` tuple of the first touch position, or ``None``.
        eq_zone: EQ band for vertical gestures: ``None``, ``"low"``,
            ``"mid"``, or ``"high"``.
    """

    def __init__(self, threshold: float = 0.04):
        """Initialise with an unlocked state.

        Args:
            threshold: Minimum finger displacement (in normalised 0-1 space)
                before the gesture direction is committed.
        """
        self._threshold = threshold
        self.direction = None   # None | "horizontal" | "vertical"
        self.start = None       # (x, y) of first contact
        self.eq_zone = None     # None | "low" | "mid" | "high"

    def update(self, x: float, y: float):
        """Feed the current finger position and update direction lock state.

        Should be called on every controller frame while the finger is
        touching the pad.  Once ``direction`` is set it will not change
        until ``reset()`` is called.

        Args:
            x: Current normalised X position (0.0 = left, 1.0 = right).
            y: Current normalised Y position (0.0 = top, 1.0 = bottom).
        """
        if self.start is None:
            # First contact — record anchor position and wait for movement.
            self.start = (x, y)
            return
        if self.direction is not None:
            return  # already locked -- ignore subsequent updates
        dx = x - self.start[0]
        dy = y - self.start[1]
        magnitude = math.sqrt(dx ** 2 + dy ** 2)
        if magnitude < self._threshold:
            return  # not enough movement yet
        # Commit to the axis with the larger displacement.
        if abs(dx) >= abs(dy):
            self.direction = "horizontal"
        else:
            self.direction = "vertical"
            # Determine EQ zone from horizontal start position (thirds of pad).
            sx = self.start[0]
            if sx < 0.333:
                self.eq_zone = "low"
            elif sx < 0.667:
                self.eq_zone = "mid"
            else:
                self.eq_zone = "high"

    def reset(self):
        """Clear all lock state.

        Must be called when the finger lifts off the touchpad so that the
        next touch starts a fresh gesture.
        """
        self.direction = None
        self.start = None
        self.eq_zone = None


# ---------------------------------------------------------------------------
# Task 4: InputMapper -- the core processing class
# ---------------------------------------------------------------------------


class InputMapper:
    """Converts ControllerState snapshots into lists of DJAction objects.

    Maintains internal state across frames for:
        - Previous controller frame (for button edge detection).
        - Smoothed crossfader value (EMA filter for touchpad horizontal drag).
        - Gyro enable flag and reference accelerometer snapshot.
        - EQ mode flag (held Options button).
        - Touchpad direction lock instance.
        - Gyro axis EffectUnit bindings (mutable at runtime via L3/R3).

    Attributes:
        prev_state: The ``ControllerState`` from the previous ``process()``
            call, used to detect button edges.  ``None`` on first call.
        smoothed_crossfader: EMA-filtered crossfader value (0.5 at startup).
        gyro_enabled: True when the gyro-to-effect mapping is active.
        eq_mode: True while the Options button is physically held.
        gyro_reference: Accelerometer reading ``(accel_x, accel_y, accel_z)``
            captured at the moment gyro was enabled; used as the tilt origin
            so that any current controller angle is the neutral position.
        gyro_roll_binding: ``GyroBinding`` for the roll (left/right tilt) axis.
        gyro_pitch_binding: ``GyroBinding`` for the pitch (forward/back) axis.
    """

    def __init__(self, config: dict):
        """Construct an InputMapper from the application config dict.

        Args:
            config: Full ``config.yaml`` dict.  Reads the following keys:
                ``config["controller"]["direction_lock_threshold"]`` — touchpad
                gesture commit distance.
                ``config["controller"]["touchpad_crossfader_smoothing"]`` —
                EMA factor for crossfader dragging.
                ``config["filter"]["stick_curve"]`` and
                ``config["filter"]["stick_exponent"]`` — response curve.
                ``config["gyro"]["tilt_range_degrees"]`` — ±degrees mapped
                to the 0.0-1.0 effect range.
                ``config["gyro"]["roll_unit/target"]`` and
                ``config["gyro"]["pitch_unit/target"]`` — initial EffectUnit
                bindings for the two tilt axes.
        """
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

        This is the main per-frame entry point.  It is called at 250 Hz from
        the controller loop and must complete quickly (no I/O, no blocking).

        On the very first call ``prev_state`` is ``None``; the current state
        is used as the previous state so that no spurious edge events fire
        (all buttons appear as if they were already in their current position
        on "frame zero").

        The 12 processing steps (a-l) are described in the module docstring.

        Args:
            state: ``ControllerState`` snapshot from the current HID poll.

        Returns:
            A list of ``DJAction`` objects (may be empty if no controls moved).
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
        # Apply the configured curve before using the values.
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
        # eq_mode is level-sensitive (not edge-triggered): it is True for
        # every frame the button is physically depressed.
        # ------------------------------------------------------------------
        self.eq_mode = state.options

        # ------------------------------------------------------------------
        # i) Mute button -- gyro toggle
        # On enable, the current accelerometer reading becomes the "neutral"
        # tilt reference so the player can hold the controller in any
        # comfortable position and have that be the zero point.
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
        # The direction lock (see TouchpadDirectionLock) commits the gesture
        # to exactly one axis.  Horizontal → crossfader.  Vertical →
        # track_browse (throttled) or EQ (when eq_mode + eq_zone set).
        # ------------------------------------------------------------------
        if state.touchpad_active:
            self._touchpad_lock.update(state.touchpad_finger1_x, state.touchpad_finger1_y)
            if self._touchpad_lock.direction == "horizontal":
                # EMA smooth the raw X position to prevent jumpy crossfader.
                self.smoothed_crossfader = apply_smoothing(
                    state.touchpad_finger1_x,
                    self.smoothed_crossfader,
                    self._smoothing,
                )
                actions.append(DJAction("crossfader", "master", self.smoothed_crossfader))
            elif self._touchpad_lock.direction == "vertical":
                if self.eq_mode and self._touchpad_lock.eq_zone:
                    # Map EQ zone to the correct action type.
                    zone_map = {"low": "eq_low", "mid": "eq_mid", "high": "eq_high"}
                    eq_type = zone_map[self._touchpad_lock.eq_zone]
                    actions.append(DJAction(eq_type, "A", state.touchpad_finger1_y))
                else:
                    # Track browse: positive dy = scroll down, negative = scroll up.
                    # Throttle to at most one event per 50 ms (20 Hz) to prevent
                    # the library from receiving hundreds of track-skip events per
                    # second at 250 Hz polling.
                    dy = state.touchpad_finger1_y - self._touchpad_lock.start[1]
                    now = state.timestamp
                    if abs(dy) > 0.02 and (now - self._last_browse_time) >= 0.05:
                        self._last_browse_time = now
                        actions.append(DJAction("track_browse", "master", dy))
        else:
            # Finger lifted — reset direction lock so next touch is a fresh gesture.
            self._touchpad_lock.reset()

        # ------------------------------------------------------------------
        # k) Gyro processing (accelerometer-based relative tilt, no drift)
        #
        # Rather than integrating gyroscope angular velocity (which drifts),
        # we use the accelerometer to measure the static gravity vector.
        # The angle is computed *relative* to the reference snapshot taken
        # when gyro was enabled, so the neutral position is wherever the
        # controller was at that moment.
        #
        # roll_angle  = atan2(accel_x - ref_x, ref_z)
        # pitch_angle = atan2(accel_y - ref_y, ref_z)
        #
        # atan2(delta_lateral, vertical) gives the tilt angle in radians
        # away from vertical.  Dividing by tilt_range_rad and rescaling to
        # [0, 1] maps ±tilt_range_degrees of physical tilt to the full
        # MIDI CC range.  Values outside ±tilt_range are clamped.
        # ------------------------------------------------------------------
        if self.gyro_enabled and self.gyro_reference is not None:
            ref_x, ref_y, ref_z = self.gyro_reference
            # Compute tilt angles relative to the reference position.
            # atan2 returns values in [-π, π]; we expect small angles here.
            roll_angle = math.atan2(state.accel_x - ref_x, ref_z)
            pitch_angle = math.atan2(state.accel_y - ref_y, ref_z)
            tilt_range_rad = math.radians(self._tilt_range)
            # Rescale from [-tilt_range_rad, +tilt_range_rad] → [0.0, 1.0].
            roll_val = max(0.0, min(1.0, (roll_angle / tilt_range_rad + 1.0) / 2.0))
            pitch_val = max(0.0, min(1.0, (pitch_angle / tilt_range_rad + 1.0) / 2.0))
            actions.append(DJAction("effect_wet_dry", "master", roll_val))
            actions.append(DJAction("effect_parameter", "master", pitch_val))

        # ------------------------------------------------------------------
        # l) Update previous state for next call
        # ------------------------------------------------------------------
        self.prev_state = state
        return actions
