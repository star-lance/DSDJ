"""
Integration test — requires DualSense connected via USB.
Run with: pytest tests/integration/test_controller_live.py -v -s -m integration
"""
import pytest
import time
from src.controller import DualSenseController

@pytest.mark.integration
def test_live_reads_state():
    ctrl = DualSenseController({"deadzone": 0.08})
    state = ctrl.read_state()
    print(f"\nLeft stick: ({state.left_stick_x:.3f}, {state.left_stick_y:.3f})")
    print(f"Triggers: L2={state.l2_analog:.3f} R2={state.r2_analog:.3f}")
    print(f"Touchpad: active={state.touchpad_active} x={state.touchpad_finger1_x:.3f}")
    print(f"Gyro: x={state.gyro_x:.1f} y={state.gyro_y:.1f} z={state.gyro_z:.1f}")
    ctrl.close()
    assert True
