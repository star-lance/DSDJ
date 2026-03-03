"""Tests for src/state.py — GyroBinding, DeckState, AppState, StateManager."""

from unittest.mock import MagicMock

from src.state import AppState, DeckState, GyroBinding, StateManager


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_action(action_type, deck, value, extra=None):
    a = MagicMock()
    a.action_type = action_type
    a.deck = deck
    a.value = value
    a.extra = extra or {}
    return a


# ---------------------------------------------------------------------------
# GyroBinding
# ---------------------------------------------------------------------------


def test_gyro_binding_defaults():
    b = GyroBinding()
    assert b.unit == 0
    assert b.target == "mix"


def test_gyro_binding_cycle_unit_increments():
    b = GyroBinding(unit=1)
    b.cycle_unit()
    assert b.unit == 2


def test_gyro_binding_cycle_unit_wraps():
    b = GyroBinding(unit=3)
    b.cycle_unit()
    assert b.unit == 0


# ---------------------------------------------------------------------------
# DeckState
# ---------------------------------------------------------------------------


def test_deck_state_defaults():
    d = DeckState()
    assert d.playing is False
    assert d.volume == 0.0
    assert d.eq_low == 0.5
    assert len(d.hot_cues) == 4


# ---------------------------------------------------------------------------
# AppState
# ---------------------------------------------------------------------------


def test_app_state_defaults():
    a = AppState()
    assert a.crossfader == 0.5
    assert a.gyro_enabled is False
    assert isinstance(a.gyro_roll_binding, GyroBinding)
    assert isinstance(a.gyro_pitch_binding, GyroBinding)
    assert a.gyro_roll_binding.unit == 0
    assert a.gyro_pitch_binding.unit == 1


# ---------------------------------------------------------------------------
# StateManager — basic get / update
# ---------------------------------------------------------------------------


def test_state_manager_get_returns_appstate():
    sm = StateManager()
    s = sm.get_state()
    assert isinstance(s, AppState)
    assert s.crossfader == 0.5


def test_state_manager_update_top_level():
    sm = StateManager()
    sm.update(crossfader=0.8)
    assert sm.get_state().crossfader == 0.8


def test_state_manager_update_nested():
    sm = StateManager()
    sm.update(**{"deck_a.volume": 0.7})
    assert sm.get_state().deck_a.volume == 0.7


# ---------------------------------------------------------------------------
# StateManager — update_from_action
# ---------------------------------------------------------------------------


def test_update_volume_deck_a():
    sm = StateManager()
    sm.update_from_action(_make_action("volume", "A", 0.9))
    assert sm.get_state().deck_a.volume == 0.9


def test_update_play_pause_toggles():
    sm = StateManager()
    assert sm.get_state().deck_a.playing is False
    sm.update_from_action(_make_action("play_pause", "A", 1.0))
    assert sm.get_state().deck_a.playing is True
    sm.update_from_action(_make_action("play_pause", "A", 1.0))
    assert sm.get_state().deck_a.playing is False


def test_update_crossfader():
    sm = StateManager()
    sm.update_from_action(_make_action("crossfader", "master", 0.25))
    assert sm.get_state().crossfader == 0.25


def test_update_hot_cue_deck_b():
    sm = StateManager()
    sm.update_from_action(_make_action("hot_cue", "B", 1.0, {"cue_index": 2}))
    assert sm.get_state().deck_b.hot_cues[1] is True


# ---------------------------------------------------------------------------
# StateManager — on_change callback
# ---------------------------------------------------------------------------


def test_on_change_callback_called_after_update():
    sm = StateManager()
    cb = MagicMock()
    sm.set_on_change(cb)
    sm.update(crossfader=0.3)
    cb.assert_called_once()
    # Callback receives the state object
    called_with = cb.call_args[0][0]
    assert isinstance(called_with, AppState)


# ---------------------------------------------------------------------------
# StateManager — serialization
# ---------------------------------------------------------------------------


def test_to_dict_returns_plain_dict():
    sm = StateManager()
    result = sm.to_dict()
    assert isinstance(result, dict)
    # Spot-check that nested values are also plain types, not dataclasses
    assert isinstance(result["deck_a"], dict)
    assert isinstance(result["gyro_roll_binding"], dict)
