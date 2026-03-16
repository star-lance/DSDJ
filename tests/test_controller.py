"""Unit tests for src/controller.py.

All tests use mocks — no hardware required.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.controller import normalize_stick, normalize_trigger, normalize_touchpad


# ---------------------------------------------------------------------------
# Mock factory
# ---------------------------------------------------------------------------


def _make_mock_ds():
    """Create a MagicMock pydualsense instance with neutral state values."""
    ds = MagicMock()

    # Sticks (center = 0 in pydualsense's signed -128..127 range)
    ds.state.LX = 0
    ds.state.LY = 0
    ds.state.RX = 0
    ds.state.RY = 0

    # Triggers
    ds.state.L2_value = 0
    ds.state.R2_value = 0

    # Bumpers / stick clicks
    ds.state.L1 = False
    ds.state.R1 = False
    ds.state.L3 = False
    ds.state.R3 = False

    # D-Pad
    ds.state.DpadUp = False
    ds.state.DpadRight = False
    ds.state.DpadDown = False
    ds.state.DpadLeft = False

    # Face buttons
    ds.state.triangle = False
    ds.state.circle = False
    ds.state.cross = False
    ds.state.square = False

    # Center buttons
    ds.state.share = False
    ds.state.options = False
    ds.state.micBtn = False
    ds.state.ps = False

    # Touchpad finger 1
    ds.state.trackPadTouch0.isActive = False
    ds.state.trackPadTouch0.X = 0
    ds.state.trackPadTouch0.Y = 0

    # Touchpad finger 2
    ds.state.trackPadTouch1.isActive = False
    ds.state.trackPadTouch1.X = 0
    ds.state.trackPadTouch1.Y = 0

    # Touchpad click
    ds.state.touchBtn = False

    # Gyro
    ds.state.gyro.Pitch = 0
    ds.state.gyro.Yaw = 0
    ds.state.gyro.Roll = 0

    # Accelerometer
    ds.state.accelerometer.X = 0
    ds.state.accelerometer.Y = 0
    ds.state.accelerometer.Z = 1

    return ds


# ---------------------------------------------------------------------------
# normalize_stick tests
# ---------------------------------------------------------------------------


def test_normalize_stick_center():
    """Center raw value 0 should return approximately 0.0."""
    assert normalize_stick(0, 0.08) == pytest.approx(0.0, abs=0.01)


def test_normalize_stick_max():
    """Maximum raw value 127 should return approximately 1.0."""
    assert normalize_stick(127, 0.08) == pytest.approx(1.0, abs=0.02)


def test_normalize_stick_min():
    """Minimum raw value -128 should return approximately -1.0."""
    assert normalize_stick(-128, 0.08) == pytest.approx(-1.0, abs=0.01)


def test_normalize_stick_deadzone():
    """A small value within the deadzone should return exactly 0.0."""
    # raw=5 → value = 5/128 ≈ 0.039, which is < 0.08 deadzone
    assert normalize_stick(5, 0.08) == 0.0


# ---------------------------------------------------------------------------
# normalize_trigger tests
# ---------------------------------------------------------------------------


def test_normalize_trigger_zero():
    """Raw 0 should return exactly 0.0."""
    assert normalize_trigger(0) == 0.0


def test_normalize_trigger_max():
    """Raw 255 should return approximately 1.0."""
    assert normalize_trigger(255) == pytest.approx(1.0, abs=0.01)


def test_normalize_trigger_mid():
    assert normalize_trigger(128) == pytest.approx(0.502, abs=0.01)


# ---------------------------------------------------------------------------
# normalize_touchpad tests
# ---------------------------------------------------------------------------


def test_normalize_touchpad_left():
    """Raw 0 with max 1919 should return approximately 0.0."""
    assert normalize_touchpad(0, 1919) == pytest.approx(0.0, abs=0.01)


def test_normalize_touchpad_right():
    """Raw 1919 with max 1919 should return approximately 1.0."""
    assert normalize_touchpad(1919, 1919) == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# DualSenseController.read_state() tests
# ---------------------------------------------------------------------------


def test_read_state_center_sticks():
    """Neutral stick positions should produce left_stick_x ≈ 0.0."""
    with patch("src.controller.pydualsense") as mock_pds:
        mock_pds.pydualsense.return_value = _make_mock_ds()
        from src.controller import DualSenseController
        ctrl = DualSenseController({"deadzone": 0.08})
        state = ctrl.read_state()
    assert state.left_stick_x == pytest.approx(0.0, abs=0.01)


def test_read_state_full_trigger():
    """L2=255 should produce l2_analog ≈ 1.0."""
    with patch("src.controller.pydualsense") as mock_pds:
        ds = _make_mock_ds()
        ds.state.L2_value = 255
        mock_pds.pydualsense.return_value = ds
        from src.controller import DualSenseController
        ctrl = DualSenseController({"deadzone": 0.08})
        state = ctrl.read_state()
    assert state.l2_analog == pytest.approx(1.0, abs=0.01)


def test_read_state_touchpad_normalized():
    """trackPadTouch0.X=960 should produce touchpad_finger1_x ≈ 0.5."""
    with patch("src.controller.pydualsense") as mock_pds:
        ds = _make_mock_ds()
        ds.state.trackPadTouch0.X = 960
        mock_pds.pydualsense.return_value = ds
        from src.controller import DualSenseController
        ctrl = DualSenseController({"deadzone": 0.08})
        state = ctrl.read_state()
    assert state.touchpad_finger1_x == pytest.approx(0.5, abs=0.01)


def test_read_state_buttons():
    """triangle=True in mock state should produce state.triangle is True."""
    with patch("src.controller.pydualsense") as mock_pds:
        ds = _make_mock_ds()
        ds.state.triangle = True
        mock_pds.pydualsense.return_value = ds
        from src.controller import DualSenseController
        ctrl = DualSenseController({"deadzone": 0.08})
        state = ctrl.read_state()
    assert state.triangle is True
