"""Run with: pytest tests/integration/test_midi_live.py -v -s
Verifies a virtual MIDI port can be created and sends a test message.
Check with: aconnect -l (the port should appear)"""
import pytest
from src.midi_bridge import MIDIBridge


@pytest.mark.integration
def test_virtual_port_creation():
    bridge = MIDIBridge("DualSense DJ Test")
    bridge.send_cc(0, 0x07, 64)  # Volume center
    bridge.send_note_on(0, 0x01)  # Play
    bridge.close()
    assert True  # No exception = port worked
