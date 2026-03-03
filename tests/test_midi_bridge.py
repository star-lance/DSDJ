from unittest.mock import MagicMock, patch
from src.midi_bridge import MIDIBridge


# ---------------------------------------------------------------------------
# Task 1: MIDIBridge opens a virtual port
# ---------------------------------------------------------------------------


def test_midi_bridge_opens_virtual_port():
    with patch("src.midi_bridge.rtmidi") as mock_rtmidi:
        mock_out = MagicMock()
        mock_rtmidi.MidiOut.return_value = mock_out
        bridge = MIDIBridge("TestPort")
        mock_out.open_virtual_port.assert_called_once_with("TestPort")


# ---------------------------------------------------------------------------
# Task 2: send_cc, send_note_on, send_note_off
# ---------------------------------------------------------------------------


def _bridge_with_mock():
    with patch("src.midi_bridge.rtmidi") as mock_rtmidi:
        mock_out = MagicMock()
        mock_rtmidi.MidiOut.return_value = mock_out
        bridge = MIDIBridge("TestPort")
        return bridge, mock_out


def test_send_cc_correct_bytes():
    bridge, mock_out = _bridge_with_mock()
    bridge.send_cc(channel=0, cc=0x07, value=100)
    mock_out.send_message.assert_called_once_with([0xB0, 0x07, 100])


def test_send_cc_channel_1():
    bridge, mock_out = _bridge_with_mock()
    bridge.send_cc(channel=1, cc=0x07, value=64)
    mock_out.send_message.assert_called_once_with([0xB1, 0x07, 64])


def test_send_note_on():
    bridge, mock_out = _bridge_with_mock()
    bridge.send_note_on(channel=0, note=0x01, velocity=127)
    mock_out.send_message.assert_called_once_with([0x90, 0x01, 127])


def test_send_note_off():
    bridge, mock_out = _bridge_with_mock()
    bridge.send_note_off(channel=0, note=0x01)
    mock_out.send_message.assert_called_once_with([0x80, 0x01, 0])


def test_cc_value_clamped_to_127():
    bridge, mock_out = _bridge_with_mock()
    bridge.send_cc(channel=0, cc=0x07, value=200)  # out of range
    args = mock_out.send_message.call_args[0][0]
    assert args[2] <= 127


# ---------------------------------------------------------------------------
# Task 3: send_action dispatch
# ---------------------------------------------------------------------------


def _action(type_, deck, value, extra=None):
    a = MagicMock()
    a.action_type = type_
    a.deck = deck
    a.value = value
    a.extra = extra or {}
    return a


def test_send_action_volume_deck_a():
    bridge, mock_out = _bridge_with_mock()
    bridge.send_action(_action("volume", "A", 0.5))
    args = mock_out.send_message.call_args[0][0]
    assert args == [0xB0, 0x07, 63]


def test_send_action_play_pause_deck_b():
    bridge, mock_out = _bridge_with_mock()
    bridge.send_action(_action("play_pause", "B", 1.0))
    args = mock_out.send_message.call_args[0][0]
    assert args == [0x91, 0x01, 127]


def test_send_action_hot_cue_3_deck_a():
    bridge, mock_out = _bridge_with_mock()
    bridge.send_action(_action("hot_cue", "A", 1.0, {"cue_index": 3}))
    args = mock_out.send_message.call_args[0][0]
    assert args == [0x90, 0x12, 127]


def test_send_action_effect_uses_gyro_binding():
    bridge, mock_out = _bridge_with_mock()
    from src.state import GyroBinding
    binding = GyroBinding(unit=2, target="mix")
    bridge.send_action(_action("effect_wet_dry", "master", 0.75), binding=binding)
    args = mock_out.send_message.call_args[0][0]
    assert args[0] == 0xB0
    assert args[1] == 0x40
