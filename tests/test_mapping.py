"""Tests for src/mapping.py — DJAction, helpers, TouchpadDirectionLock, InputMapper."""

import time
import pytest

from src.state import MacroBinding
from src.mapping import (
    DJAction,
    detect_edge,
    apply_smoothing,
    apply_stick_curve,
    TouchpadDirectionLock,
    InputMapper,
)
from src.controller import ControllerState


# ---------------------------------------------------------------------------
# Task 1: DJAction dataclass
# ---------------------------------------------------------------------------


def test_dj_action_fields():
    a = DJAction(action_type="volume", deck="A", value=0.8)
    assert a.deck == "A"
    assert a.extra == {}


def test_dj_action_with_extra():
    a = DJAction(action_type="hot_cue", deck="A", value=1.0, extra={"cue_index": 2})
    assert a.extra["cue_index"] == 2


# ---------------------------------------------------------------------------
# Task 2: Helper functions
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Task 3: TouchpadDirectionLock
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Task 4: InputMapper
# ---------------------------------------------------------------------------


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
                       "direction_lock_threshold": 0.04, "volume_sensitivity": 0.004},
        "filter": {"stick_curve": "linear", "stick_exponent": 2.0},
        "gyro": {"roll_unit": 0, "roll_target": "mix",
                 "pitch_unit": 1, "pitch_target": "parameter1",
                 "tilt_range_degrees": 45.0},
    }


def _macro_config():
    cfg = _config()
    cfg["macros"] = {
        "left_stick": [
            {"control": "filter", "deck": "A", "base": 0.5, "min_val": 0.0, "max_val": 1.0}
        ],
        "right_stick": [
            {"control": "filter", "deck": "B", "base": 0.5, "min_val": 0.0, "max_val": 1.0}
        ],
    }
    return cfg


def test_macro_center_emits_base_on_change():
    """Moving stick from non-center to center should emit base value."""
    mapper = InputMapper(_macro_config())
    # Prime with stick pushed right
    mapper.process(_blank_state(left_stick_x=0.9))
    # Return to center — should emit base
    actions = mapper.process(_blank_state(left_stick_x=0.0))
    f = next((a for a in actions if a.action_type == "filter" and a.deck == "A"), None)
    assert f is not None
    assert f.value == pytest.approx(0.5, abs=0.02)


def test_macro_full_right_emits_max():
    mapper = InputMapper(_macro_config())
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(left_stick_x=1.0))
    f = next((a for a in actions if a.action_type == "filter" and a.deck == "A"), None)
    assert f is not None
    assert f.value == pytest.approx(1.0, abs=0.02)


def test_macro_full_left_emits_min():
    mapper = InputMapper(_macro_config())
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(left_stick_x=-1.0))
    f = next((a for a in actions if a.action_type == "filter" and a.deck == "A"), None)
    assert f is not None
    assert f.value == pytest.approx(0.0, abs=0.02)


def test_macro_no_emit_when_value_unchanged():
    """If stick doesn't move enough to change interpolated value, no action emitted."""
    mapper = InputMapper(_macro_config())
    mapper.process(_blank_state())
    mapper.process(_blank_state(left_stick_x=0.5))
    # Same stick position again — value hasn't changed, no emit
    actions = mapper.process(_blank_state(left_stick_x=0.5))
    f = [a for a in actions if a.action_type == "filter" and a.deck == "A"]
    assert len(f) == 0


def test_macro_deck_both_emits_two_actions():
    cfg = _macro_config()
    cfg["macros"]["left_stick"][0]["deck"] = "both"
    mapper = InputMapper(cfg)
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(left_stick_x=1.0))
    filters = [a for a in actions if a.action_type == "filter"]
    assert len(filters) == 2
    assert {a.deck for a in filters} == {"A", "B"}


def test_macro_update_replaces_bindings():
    mapper = InputMapper(_macro_config())
    new_bindings_a = [MacroBinding(control="eq_high", deck="A", base=0.5, min_val=0.0, max_val=1.0)]
    mapper.update_macros(new_bindings_a, mapper._macro_b)
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(left_stick_x=1.0))
    assert any(a.action_type == "eq_high" for a in actions)
    assert not any(a.action_type == "filter" for a in actions)


def test_l1_press_emits_play_pause_deck_a():
    mapper = InputMapper(_config())
    mapper.process(_blank_state())  # prime prev_state
    actions = mapper.process(_blank_state(l1=True))
    types = [a.action_type for a in actions]
    assert "play_pause" in types
    play = next(a for a in actions if a.action_type == "play_pause")
    assert play.deck == "A"


def test_l2_kills_deck_a_eq_low():
    """L2 fully squeezed should cut Deck A LOW EQ to zero."""
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(l2_analog=1.0))
    eq = next((a for a in actions if a.action_type == "eq_low" and a.deck == "A"), None)
    assert eq is not None
    assert eq.value == pytest.approx(0.0, abs=0.01)


def test_l2_release_restores_deck_a_eq_low():
    """Releasing L2 after a kill should emit eq_low=0.5 (flat) for Deck A."""
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    mapper.process(_blank_state(l2_analog=1.0))   # squeeze
    actions = mapper.process(_blank_state(l2_analog=0.0))  # release
    eq = next((a for a in actions if a.action_type == "eq_low" and a.deck == "A"), None)
    assert eq is not None
    assert eq.value == pytest.approx(0.5, abs=0.01)


def test_left_stick_y_accumulates_deck_a_volume():
    """Pushing left stick up should increase Deck A volume."""
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    vol_before = mapper._deck_a_volume
    mapper.process(_blank_state(left_stick_y=-1.0))
    assert mapper._deck_a_volume > vol_before


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


def test_options_press_switches_to_deck_a():
    mapper = InputMapper(_config())
    mapper.active_deck = "B"
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(options=True))
    assert mapper.active_deck == "A"
    assert any(a.action_type == "deck_switch" and a.deck == "A" for a in actions)


def test_l3_in_gyro_mode_cycles_roll_binding():
    mapper = InputMapper(_config())
    mapper.gyro_enabled = True
    mapper.process(_blank_state())
    initial_unit = mapper.gyro_roll_binding.unit
    mapper.process(_blank_state(l3=True))
    assert mapper.gyro_roll_binding.unit == (initial_unit + 1) % 4


def test_gyro_reference_captured_on_enable():
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    # Enable gyro with specific accel values
    actions = mapper.process(_blank_state(mute=True, accel_x=0.1, accel_y=0.2, accel_z=0.9))
    assert mapper.gyro_enabled is True
    assert mapper.gyro_reference == (pytest.approx(0.1), pytest.approx(0.2), pytest.approx(0.9))


def test_gyro_reference_cleared_on_disable():
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    # Enable
    mapper.process(_blank_state(mute=True))
    assert mapper.gyro_enabled is True
    # Disable
    mapper.process(_blank_state())
    mapper.process(_blank_state(mute=True))
    assert mapper.gyro_enabled is False
    assert mapper.gyro_reference is None


def test_r1_press_emits_play_pause_deck_b():
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(r1=True))
    play = next((a for a in actions if a.action_type == "play_pause" and a.deck == "B"), None)
    assert play is not None


def test_face_buttons_emit_hot_cue_deck_b():
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(triangle=True))
    cue = next((a for a in actions if a.action_type == "hot_cue" and a.deck == "B"), None)
    assert cue is not None
    assert cue.extra["cue_index"] == 1


def test_create_press_switches_to_deck_b():
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(create=True))
    assert mapper.active_deck == "B"
    assert any(a.action_type == "deck_switch" and a.deck == "B" for a in actions)


def test_ps_press_switches_to_mirror():
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(ps=True))
    assert mapper.active_deck == "both"
    assert any(a.action_type == "deck_switch" and a.deck == "both" for a in actions)


def test_mirror_mode_hot_cues_emit_for_both_decks():
    """In mirror mode, D-pad hot cues should fire on both decks."""
    mapper = InputMapper(_config())
    mapper.active_deck = "both"
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(dpad_up=True))
    cue_actions = [a for a in actions if a.action_type == "hot_cue"]
    assert len(cue_actions) == 2
    assert {a.deck for a in cue_actions} == {"A", "B"}


def test_l1_always_targets_deck_a_regardless_of_active_deck():
    """L1 should always emit play_pause for Deck A even when active deck is B."""
    mapper = InputMapper(_config())
    mapper.active_deck = "B"
    mapper.process(_blank_state())
    actions = mapper.process(_blank_state(l1=True))
    play = next((a for a in actions if a.action_type == "play_pause"), None)
    assert play is not None
    assert play.deck == "A"


def test_touchpad_horizontal_emits_crossfader():
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    # First touch to set start
    mapper.process(_blank_state(touchpad_active=True, touchpad_finger1_x=0.5, touchpad_finger1_y=0.5))
    # Move clearly horizontal
    actions = mapper.process(_blank_state(touchpad_active=True, touchpad_finger1_x=0.56, touchpad_finger1_y=0.5))
    cf = next((a for a in actions if a.action_type == "crossfader"), None)
    assert cf is not None


def test_crossfader_relative_no_jump():
    """Placing finger at an extreme X should not jump the crossfader."""
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    # Crossfader starts at 0.5. Place finger at far right (0.9) — should not jump.
    mapper.process(_blank_state(touchpad_active=True, touchpad_finger1_x=0.9, touchpad_finger1_y=0.5))
    actions = mapper.process(_blank_state(touchpad_active=True, touchpad_finger1_x=0.96, touchpad_finger1_y=0.5))
    cf = next((a for a in actions if a.action_type == "crossfader"), None)
    # Value should be near 0.5 + delta (0.06), not 0.96
    assert cf is not None
    assert cf.value < 0.7


def test_track_browse_throttled():
    import time
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    # Start a vertical swipe
    t0 = time.monotonic()
    mapper.process(_blank_state(touchpad_active=True, touchpad_finger1_x=0.5, touchpad_finger1_y=0.1, timestamp=t0))
    # First browse event — should fire
    t1 = t0 + 0.001  # 1ms later (< 50ms throttle)
    actions1 = mapper.process(_blank_state(touchpad_active=True, touchpad_finger1_x=0.5, touchpad_finger1_y=0.16, timestamp=t1))
    browse_count_1 = sum(1 for a in actions1 if a.action_type == "track_browse")
    # Second call < 50ms later — should NOT fire again
    t2 = t0 + 0.01  # 10ms later (< 50ms throttle)
    actions2 = mapper.process(_blank_state(touchpad_active=True, touchpad_finger1_x=0.5, touchpad_finger1_y=0.22, timestamp=t2))
    browse_count_2 = sum(1 for a in actions2 if a.action_type == "track_browse")
    # Third call > 50ms later — should fire again
    t3 = t0 + 0.1  # 100ms later (> 50ms throttle)
    actions3 = mapper.process(_blank_state(touchpad_active=True, touchpad_finger1_x=0.5, touchpad_finger1_y=0.28, timestamp=t3))
    browse_count_3 = sum(1 for a in actions3 if a.action_type == "track_browse")
    assert browse_count_1 == 1   # first fires
    assert browse_count_2 == 0   # throttled
    assert browse_count_3 == 1   # unthrottled after interval


def test_gyro_produces_effect_actions():
    mapper = InputMapper(_config())
    mapper.process(_blank_state())
    # Enable gyro with reference at flat position
    mapper.process(_blank_state(mute=True, accel_x=0.0, accel_y=0.0, accel_z=1.0))
    # Process with gyro tilted
    actions = mapper.process(_blank_state(accel_x=0.3, accel_y=0.2, accel_z=0.9))
    wet_dry = next((a for a in actions if a.action_type == "effect_wet_dry"), None)
    param = next((a for a in actions if a.action_type == "effect_parameter"), None)
    assert wet_dry is not None
    assert param is not None
    assert 0.0 <= wet_dry.value <= 1.0
    assert 0.0 <= param.value <= 1.0
