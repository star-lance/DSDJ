# `midi_bridge.py` Implementation Plan

> **For Claude:** Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Create a virtual MIDI output port and send CC/Note messages. All unit tests mock rtmidi; the integration test uses a live port.

**File:** `src/midi_bridge.py`
**Tests:** `tests/test_midi_bridge.py`, `tests/integration/test_midi_live.py`
**Dependencies:** `python-rtmidi`

---

## Task 1: `MIDIBridge` opens a virtual port

**Step 1:** Write failing test in `tests/test_midi_bridge.py`

```python
from unittest.mock import MagicMock, patch
from src.midi_bridge import MIDIBridge

def test_midi_bridge_opens_virtual_port():
    with patch("src.midi_bridge.rtmidi") as mock_rtmidi:
        mock_out = MagicMock()
        mock_rtmidi.MidiOut.return_value = mock_out
        bridge = MIDIBridge("TestPort")
        mock_out.open_virtual_port.assert_called_once_with("TestPort")
```

**Step 2:** Run to confirm failure
```bash
pytest tests/test_midi_bridge.py::test_midi_bridge_opens_virtual_port -v
```

**Step 3:** Implement in `src/midi_bridge.py`

```python
import rtmidi

class MIDIBridge:
    def __init__(self, port_name: str = "DualSense DJ"):
        self._out = rtmidi.MidiOut()
        self._out.open_virtual_port(port_name)

    def close(self):
        self._out.close_port()
        del self._out
```

**Step 4:** Run test
```bash
pytest tests/test_midi_bridge.py::test_midi_bridge_opens_virtual_port -v
```
Expected: PASSED

---

## Task 2: `send_cc` and `send_note_on`

**Step 1:** Add tests

```python
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
```

**Step 2:** Run to confirm failure
```bash
pytest tests/test_midi_bridge.py -k "send" -v
```

**Step 3:** Implement

```python
    def send_cc(self, channel: int, cc: int, value: int):
        status = 0xB0 | (channel & 0x0F)
        self._out.send_message([status, cc & 0x7F, min(value, 127) & 0x7F])

    def send_note_on(self, channel: int, note: int, velocity: int = 127):
        status = 0x90 | (channel & 0x0F)
        self._out.send_message([status, note & 0x7F, velocity & 0x7F])

    def send_note_off(self, channel: int, note: int):
        status = 0x80 | (channel & 0x0F)
        self._out.send_message([status, note & 0x7F, 0])
```

**Step 4:** Run tests
```bash
pytest tests/test_midi_bridge.py -v
```
Expected: all PASSED

---

## Task 3: `send_action` dispatch

**Step 1:** Add tests

```python
from unittest.mock import MagicMock
from src.midi_bridge import MIDIBridge

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
    # CC 0x07, channel 0, value ~63
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
    # CC 0x40, channel 0, value ~95
    args = mock_out.send_message.call_args[0][0]
    assert args[0] == 0xB0
    assert args[1] == 0x40
```

**Step 2:** Run to confirm failure
```bash
pytest tests/test_midi_bridge.py -k "send_action" -v
```

**Step 3:** Implement `send_action`

```python
    # MIDI CC map: action_type -> cc number
    _CC_MAP = {
        "volume":           0x07,
        "crossfader":       0x08,
        "filter":           0x1A,
        "pitch_nudge":      0x1B,
        "eq_low":           0x20,
        "eq_mid":           0x21,
        "eq_high":          0x22,
        "track_browse":     0x30,
        "effect_wet_dry":   0x40,
        "effect_parameter": 0x41,
    }

    # MIDI Note map: action_type -> note number
    _NOTE_MAP = {
        "play_pause":   0x01,
        "sync_toggle":  0x03,
        "track_load":   0x04,
        "loop_toggle":  0x20,
    }

    _HOT_CUE_BASE = 0x10  # notes 0x10-0x13

    def send_action(self, action, binding=None):
        t = action.action_type
        deck = action.deck
        value = action.value
        channel = 0 if deck in ("A", "master") else 1

        if t in self._CC_MAP:
            midi_val = int(value * 127)
            self.send_cc(channel, self._CC_MAP[t], midi_val)

        elif t == "track_browse":
            midi_val = 65 if value > 0 else 63  # relative
            self.send_cc(channel, self._CC_MAP[t], midi_val)

        elif t in self._NOTE_MAP:
            self.send_note_on(channel, self._NOTE_MAP[t])

        elif t == "hot_cue":
            idx = action.extra.get("cue_index", 1) - 1
            self.send_note_on(channel, self._HOT_CUE_BASE + idx)

        elif t in ("effect_wet_dry", "effect_parameter"):
            midi_val = int(value * 127)
            self.send_cc(channel, self._CC_MAP[t], midi_val)
```

**Step 4:** Run all tests
```bash
pytest tests/test_midi_bridge.py -v
```
Expected: all PASSED

---

## Task 4: Integration test (no hardware needed — just verifies port creation)

File: `tests/integration/test_midi_live.py`

```python
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
```

Run:
```bash
pytest tests/integration/test_midi_live.py -v -s -m integration
# In another terminal: aconnect -l | grep DualSense
```
