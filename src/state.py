"""Central state container for the DualSense DJ Controller.

Provides:
    GyroBinding  — which Mixxx EffectUnit + parameter a gyro axis controls.
    DeckState    — per-deck playback/mixer state snapshot.
    AppState     — full application state.
    StateManager — thread-safe read/write with optional change callback.
"""

import dataclasses
import threading
from dataclasses import dataclass, field
from typing import Literal

GyroTarget = Literal["mix", "parameter1", "parameter2", "parameter3"]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class GyroBinding:
    unit: int = 0          # Which EffectUnit (0-3 → EffectUnit1-4 in Mixxx)
    target: GyroTarget = "mix"  # Which knob on that unit to modulate

    def cycle_unit(self):
        """Cycle unit index 0→1→2→3→0."""
        self.unit = (self.unit + 1) % 4


@dataclass
class DeckState:
    playing: bool = False
    bpm: float = 0.0
    position: float = 0.0
    volume: float = 0.0
    filter_value: float = 0.5
    eq_low: float = 0.5
    eq_mid: float = 0.5
    eq_high: float = 0.5
    sync_enabled: bool = False
    loop_active: bool = False
    hot_cues: list = field(default_factory=lambda: [False, False, False, False])
    track_title: str = ""
    track_artist: str = ""


@dataclass
class AppState:
    deck_a: DeckState = field(default_factory=DeckState)
    deck_b: DeckState = field(default_factory=DeckState)
    crossfader: float = 0.5
    gyro_enabled: bool = False
    eq_mode: bool = False
    effect_wet_dry: float = 0.0
    effect_parameter: float = 0.5
    gyro_roll_binding: GyroBinding = field(
        default_factory=lambda: GyroBinding(unit=0, target="mix")
    )
    gyro_pitch_binding: GyroBinding = field(
        default_factory=lambda: GyroBinding(unit=1, target="parameter1")
    )
    ui_view: str = "decks"
    connected: bool = False


# ---------------------------------------------------------------------------
# StateManager
# ---------------------------------------------------------------------------


class StateManager:
    """Thread-safe wrapper around AppState.

    Usage::

        sm = StateManager()
        sm.set_on_change(lambda s: print(s))
        sm.update(crossfader=0.8)
        sm.update(**{"deck_a.volume": 0.7})
        sm.update_from_action(action)
        d = sm.to_dict()
    """

    def __init__(self):
        self._state = AppState()
        self._lock = threading.Lock()
        self._on_change = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_state(self) -> AppState:
        """Return the current AppState (lock-protected read)."""
        with self._lock:
            return self._state

    def update(self, **kwargs):
        """Update one or more state fields.

        Supports dot-notation for nested fields:
            ``update(**{"deck_a.volume": 0.8})``
        """
        with self._lock:
            for key, value in kwargs.items():
                if "." in key:
                    parent, child = key.split(".", 1)
                    setattr(getattr(self._state, parent), child, value)
                else:
                    setattr(self._state, key, value)
        if self._on_change:
            self._on_change(self._state)

    def update_from_action(self, action) -> None:
        """Translate a DJAction into state mutations.

        Parameters
        ----------
        action:
            Object with attributes: ``action_type`` (str), ``deck`` (str),
            ``value`` (float), ``extra`` (dict).
        """
        t = action.action_type
        d = action.deck
        v = action.value

        def deck_state():
            return self._state.deck_a if d == "A" else self._state.deck_b

        with self._lock:
            if t == "volume":
                deck_state().volume = v
            elif t == "crossfader":
                self._state.crossfader = v
            elif t == "filter":
                deck_state().filter_value = v
            elif t == "eq_low":
                deck_state().eq_low = v
            elif t == "eq_mid":
                deck_state().eq_mid = v
            elif t == "eq_high":
                deck_state().eq_high = v
            elif t == "play_pause":
                deck_state().playing = not deck_state().playing
            elif t == "sync_toggle":
                deck_state().sync_enabled = not deck_state().sync_enabled
            elif t == "loop_toggle":
                deck_state().loop_active = not deck_state().loop_active
            elif t == "hot_cue":
                idx = action.extra.get("cue_index", 1) - 1
                deck_state().hot_cues[idx] = True
            elif t == "gyro_toggle":
                self._state.gyro_enabled = bool(v)
            elif t == "effect_wet_dry":
                self._state.effect_wet_dry = v
            elif t == "effect_parameter":
                self._state.effect_parameter = v
            # "pitch_nudge", "track_browse", "track_load" — transient, no state change

        if self._on_change:
            self._on_change(self._state)

    def set_on_change(self, callback) -> None:
        """Register a callback invoked after every state mutation.

        The callback receives the AppState object as its sole argument.
        """
        self._on_change = callback

    def to_dict(self) -> dict:
        """Serialize the full state to a plain dictionary (JSON-safe)."""
        with self._lock:
            return dataclasses.asdict(self._state)
