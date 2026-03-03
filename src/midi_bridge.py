"""MIDI bridge: creates a virtual MIDI output port and dispatches CC/Note messages.

Bridges a PS5 DualSense controller (via DJAction objects) to Mixxx DJ software
through a virtual MIDI port created with python-rtmidi.
"""

import rtmidi


class MIDIBridge:
    """Opens a virtual MIDI output port and sends CC/Note messages to Mixxx."""

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

    def __init__(self, port_name: str = "DualSense DJ"):
        self._out = None
        self._out = rtmidi.MidiOut()
        self._out.open_virtual_port(port_name)

    def close(self):
        if self._out is None:
            return
        self._out.close_port()
        self._out = None

    # ------------------------------------------------------------------
    # Low-level send helpers
    # ------------------------------------------------------------------

    def send_cc(self, channel: int, cc: int, value: int):
        """Send a Control Change message."""
        status = 0xB0 | (channel & 0x0F)
        self._out.send_message([status, cc & 0x7F, max(0, min(127, value))])

    def send_note_on(self, channel: int, note: int, velocity: int = 127):
        """Send a Note On message."""
        status = 0x90 | (channel & 0x0F)
        self._out.send_message([status, note & 0x7F, max(0, min(127, velocity))])

    def send_note_off(self, channel: int, note: int):
        """Send a Note Off message."""
        status = 0x80 | (channel & 0x0F)
        self._out.send_message([status, note & 0x7F, 0])

    # ------------------------------------------------------------------
    # High-level action dispatch
    # ------------------------------------------------------------------

    def send_action(self, action, binding=None):
        """Translate a DJAction into MIDI CC or Note messages.

        Parameters
        ----------
        action:
            Object with attributes: action_type (str), deck (str),
            value (float 0.0–1.0), extra (dict).
        binding:
            Optional GyroBinding; reserved for future gyro-to-effect routing.
            Currently unused in dispatch logic (effect_wet_dry uses _CC_MAP).
        """
        t = action.action_type
        deck = action.deck
        value = action.value
        channel = 0 if deck in ("A", "master") else 1

        # track_browse: use relative encoding — must come BEFORE the general
        # _CC_MAP check because track_browse is also in _CC_MAP.
        if t == "track_browse":
            midi_val = 65 if value > 0 else 63  # relative encoder
            self.send_cc(channel, self._CC_MAP[t], midi_val)

        elif t in self._CC_MAP:
            midi_val = int(value * 127)
            self.send_cc(channel, self._CC_MAP[t], midi_val)

        elif t in self._NOTE_MAP:
            self.send_note_on(channel, self._NOTE_MAP[t])

        elif t == "hot_cue":
            idx = max(0, min(3, action.extra.get("cue_index", 1) - 1))
            self.send_note_on(channel, self._HOT_CUE_BASE + idx)
