"""MIDI bridge: creates a virtual MIDI output port and dispatches CC/Note messages.

This module is the output layer of the stack.  It receives ``DJAction``
objects from the mapping layer and translates them into standard MIDI messages
delivered through a virtual port that Mixxx (or any DAW) can subscribe to.

Virtual MIDI port concept:
    A virtual MIDI port is a software-only port that appears in the operating
    system's MIDI device list without any physical hardware.  Other
    applications — here, Mixxx — can connect to it as if it were a real MIDI
    device.  ``python-rtmidi`` (the ``rtmidi`` package) creates this port via
    ``MidiOut.open_virtual_port()``.  The port lives for as long as the
    ``MidiOut`` object is open; closing it removes the port from the OS list.

MIDI message encoding summary:
    - **Control Change (CC)**: three bytes — ``[0xB0 | ch, cc_number, value]``
      Used for continuous analog controls (faders, knobs).  Value range 0-127.
    - **Note On**: three bytes — ``[0x90 | ch, note_number, velocity]``
      Used for momentary button actions.  Velocity is always 127 here.
    - **Note Off**: three bytes — ``[0x80 | ch, note_number, 0]``
      Sent to indicate button release (currently only via ``send_note_off``
      directly; high-level dispatch does not auto-send Note Off).

Channel mapping:
    Deck A and "master" actions → MIDI channel 0 (displayed as channel 1 in
    most software).  Deck B actions → MIDI channel 1 (displayed as channel 2).
    This lets a single Mixxx MIDI mapping script distinguish deck-A from deck-B
    messages purely by channel number.
"""

import rtmidi


class MIDIBridge:
    """Opens a virtual MIDI output port and sends CC/Note messages to Mixxx.

    Maintains a mapping from ``DJAction.action_type`` strings to MIDI CC or
    Note numbers, and handles the channel-per-deck convention (channel 0 for
    Deck A/master, channel 1 for Deck B).

    Attributes:
        _CC_MAP: Maps continuous action types to their MIDI CC numbers.
        _NOTE_MAP: Maps momentary action types to their MIDI Note numbers.
        _HOT_CUE_BASE: Base note number for hot-cue actions; cue index is
            added to this base (e.g. cue 1 → note 0x10, cue 2 → note 0x11).
        _out: The ``rtmidi.MidiOut`` instance; ``None`` after ``close()``.
    """

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
        """Create a virtual MIDI output port with the given name.

        The port appears in the OS MIDI device list immediately after this
        call.  Mixxx should be configured to use this port name in its MIDI
        preferences.

        Args:
            port_name: Human-readable name for the virtual port as it will
                appear in Mixxx's MIDI controller list.
        """
        self._out = None
        self._out = rtmidi.MidiOut()
        self._out.open_virtual_port(port_name)

    def close(self):
        """Close the virtual MIDI port and release the rtmidi object.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        if self._out is None:
            return
        self._out.close_port()
        self._out = None

    # ------------------------------------------------------------------
    # Low-level send helpers
    # ------------------------------------------------------------------

    def send_cc(self, channel: int, cc: int, value: int):
        """Send a MIDI Control Change message.

        Encodes the three-byte CC message ``[status, cc, value]`` where
        ``status = 0xB0 | (channel & 0x0F)``.

        Args:
            channel: MIDI channel (0-15).
            cc: CC number (0-127); the high bit is masked off for safety.
            value: CC value (0-127); clamped to [0, 127] before sending.
        """
        status = 0xB0 | (channel & 0x0F)
        self._out.send_message([status, cc & 0x7F, max(0, min(127, value))])

    def send_note_on(self, channel: int, note: int, velocity: int = 127):
        """Send a MIDI Note On message.

        Args:
            channel: MIDI channel (0-15).
            note: MIDI note number (0-127); the high bit is masked off.
            velocity: Note velocity (0-127); clamped to [0, 127]. Defaults to
                127 (full velocity) for button-press actions.
        """
        status = 0x90 | (channel & 0x0F)
        self._out.send_message([status, note & 0x7F, max(0, min(127, velocity))])

    def send_note_off(self, channel: int, note: int):
        """Send a MIDI Note Off message with zero velocity.

        Args:
            channel: MIDI channel (0-15).
            note: MIDI note number (0-127); the high bit is masked off.
        """
        status = 0x80 | (channel & 0x0F)
        self._out.send_message([status, note & 0x7F, 0])

    # ------------------------------------------------------------------
    # High-level action dispatch
    # ------------------------------------------------------------------

    def send_action(self, action, binding=None):
        """Translate a DJAction into one or more MIDI messages.

        Dispatch logic (evaluated in order):

        1. **track_browse** — handled *before* the general ``_CC_MAP`` check
           even though ``"track_browse"`` is also in ``_CC_MAP``.  Uses
           *relative encoder* encoding: value 65 means "increment" (scroll
           down / next track) and 63 means "decrement" (scroll up / previous
           track).  This matches Mixxx's relative-mode encoder expectation and
           avoids the value-jumping artefact you would get from absolute
           position encoding.

        2. **_CC_MAP** — all other continuous controls.  The 0.0-1.0 float
           value is linearly scaled to 0-127 via ``int(value * 127)``.

        3. **_NOTE_MAP** — momentary button actions.  A Note On at velocity 127
           is sent; no automatic Note Off is generated (Mixxx treats Note On as
           a toggle trigger).

        4. **hot_cue** — dynamic Note On at ``_HOT_CUE_BASE + (cue_index - 1)``
           where ``cue_index`` comes from ``action.extra["cue_index"]`` (1-based,
           clamped to 1-4).

        Channel assignment:
            Deck "A" or "master" → channel 0; Deck "B" → channel 1.

        Args:
            action: ``DJAction`` with attributes ``action_type`` (str),
                ``deck`` (``"A"``, ``"B"``, or ``"master"``),
                ``value`` (float 0.0-1.0), and ``extra`` (dict).
            binding: Optional ``GyroBinding``; reserved for future
                gyro-to-effect routing.  Currently unused in dispatch logic
                (``effect_wet_dry`` and ``effect_parameter`` travel through
                ``_CC_MAP`` as regular CC messages).
        """
        t = action.action_type
        deck = action.deck
        value = action.value
        channel = 0 if deck in ("A", "master") else 1

        # track_browse: use relative encoding — must come BEFORE the general
        # _CC_MAP check because track_browse is also in _CC_MAP.
        if t == "track_browse":
            # Relative encoder protocol: 65 = step forward, 63 = step back.
            # Mixxx interprets any value > 64 as clockwise and < 64 as
            # counter-clockwise, regardless of the magnitude.
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
