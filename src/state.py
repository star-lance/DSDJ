"""Central state container for the DualSense DJ Controller.

This module defines the data model for the entire application and provides a
thread-safe wrapper (StateManager) that bridges the controller-input thread
with the asyncio event loop.

Responsibilities:
    - ``GyroBinding``  -- maps a gyro axis to a specific Mixxx EffectUnit knob.
    - ``DeckState``    -- snapshot of a single DJ deck's playback and mixer state.
    - ``AppState``     -- top-level container that holds both decks plus global state.
    - ``StateManager`` -- thread-safe read/write with an optional change callback.

Threading model:
    ``StateManager`` uses a single ``threading.Lock`` to protect ``AppState``
    mutations.  The controller loop runs in a ``ThreadPoolExecutor`` thread
    (via ``loop.run_in_executor``), so every write must hold the lock.  The
    asyncio broadcast loop reads state only through ``to_dict()``, which also
    acquires the lock, ensuring a consistent serialized snapshot.
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
    """Describes which Mixxx EffectUnit knob a gyro axis controls.

    Mixxx exposes effects through numbered EffectUnits (1-4 in the UI,
    indexed 0-3 here).  Each unit has a wet/dry mix knob and up to three
    parameter knobs.  A ``GyroBinding`` records which unit and which knob
    the user has mapped to a physical tilt axis.

    Attributes:
        unit: Zero-based EffectUnit index (0 → EffectUnit1 … 3 → EffectUnit4
            in Mixxx).
        target: Which knob on the chosen unit to modulate.  One of ``"mix"``,
            ``"parameter1"``, ``"parameter2"``, or ``"parameter3"``.
    """

    unit: int = 0          # Which EffectUnit (0-3 → EffectUnit1-4 in Mixxx)
    target: GyroTarget = "mix"  # Which knob on that unit to modulate

    def cycle_unit(self):
        """Cycle unit index 0→1→2→3→0.

        Called when the user presses L3/R3 while gyro is active, allowing
        real-time reassignment of the tilt axis to the next EffectUnit without
        leaving the DJ session.
        """
        self.unit = (self.unit + 1) % 4


@dataclass
class DeckState:
    """Snapshot of a single DJ deck's playback and mixer state.

    All values are kept in a normalised range where possible so that the UI
    can render them directly without further scaling.

    Attributes:
        playing: True if the deck is currently playing (transport running).
        bpm: Current track tempo in beats-per-minute as reported by Mixxx.
        position: Playback position as a fraction of the track (0.0 = start,
            1.0 = end).
        volume: Channel fader level (0.0 = silent, 1.0 = unity gain).
        filter_value: High-pass / low-pass filter position (0.0 = full LP,
            0.5 = flat/off, 1.0 = full HP).
        eq_low: Low-frequency EQ gain (0.0 = cut, 0.5 = flat, 1.0 = boost).
        eq_mid: Mid-frequency EQ gain (same scale as eq_low).
        eq_high: High-frequency EQ gain (same scale as eq_low).
        sync_enabled: True when Mixxx sync (master/follower BPM sync) is on.
        loop_active: True when a loop is currently engaged on this deck.
        hot_cues: List of four booleans indicating which hot-cue slots are
            set (index 0 = cue 1 … index 3 = cue 4).
        track_title: Title of the currently loaded track (empty if none).
        track_artist: Artist of the currently loaded track (empty if none).
    """

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
    hot_cues: list[bool] = field(default_factory=lambda: [False, False, False, False])
    track_title: str = ""
    track_artist: str = ""


@dataclass
class AppState:
    """Full application state container.

    Holds both deck states plus global controls that are not deck-specific.

    Attributes:
        deck_a: State of the left/A deck.
        deck_b: State of the right/B deck.
        crossfader: Master crossfader position (0.0 = full Deck A,
            0.5 = centre, 1.0 = full Deck B).
        gyro_enabled: True when the controller's tilt-to-effect mapping is
            active.  Toggled by the Mute button.
        eq_mode: True while the Options button is held; redirects sticks and
            touchpad vertical gestures to EQ controls.
        effect_wet_dry: Current wet/dry value sent to the bound EffectUnit
            (driven by roll axis when gyro is enabled).
        effect_parameter: Current parameter value sent to the bound EffectUnit
            (driven by pitch axis when gyro is enabled).
        gyro_roll_binding: Which EffectUnit/knob the roll axis controls.
        gyro_pitch_binding: Which EffectUnit/knob the pitch axis controls.
        ui_view: Current view name displayed in the React UI (e.g. ``"decks"``).
        connected: True once the DualSense has been successfully opened.
    """

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

    All public methods acquire ``self._lock`` before touching ``_state``,
    making them safe to call from both the thread-pool controller loop and
    the asyncio event loop simultaneously.

    The optional ``on_change`` callback is invoked *outside* the lock (after
    releasing it) to avoid holding the lock during potentially slow I/O such
    as WebSocket serialisation.  The callback receives a plain ``dict``
    (``dataclasses.asdict`` output) rather than an ``AppState`` object so
    that it is safe to serialise to JSON without further conversion.

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
        # Protects all reads and writes to _state from concurrent threads.
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

        Supports dot-notation for nested fields::

            update(**{"deck_a.volume": 0.8})

        The lock is held only for the mutation phase; the on_change callback
        is called afterwards without the lock so that callback I/O cannot
        block the controller thread.

        Args:
            **kwargs: Field names (with optional ``parent.child`` dot notation)
                mapped to their new values.
        """
        with self._lock:
            for key, value in kwargs.items():
                if "." in key:
                    parent, child = key.split(".", 1)
                    setattr(getattr(self._state, parent), child, value)
                else:
                    setattr(self._state, key, value)
        cb = self._on_change
        if cb:
            cb(dataclasses.asdict(self._state))

    def update_from_action(self, action) -> None:
        """Translate a DJAction into state mutations.

        Dispatch table — ``action.action_type`` → state change:

        * ``"volume"``          → ``deck_state().volume = v``
        * ``"crossfader"``      → ``_state.crossfader = v``
        * ``"filter"``          → ``deck_state().filter_value = v``
        * ``"eq_low"``          → ``deck_state().eq_low = v``
        * ``"eq_mid"``          → ``deck_state().eq_mid = v``
        * ``"eq_high"``         → ``deck_state().eq_high = v``
        * ``"play_pause"``      → toggles ``deck_state().playing``
        * ``"sync_toggle"``     → toggles ``deck_state().sync_enabled``
        * ``"loop_toggle"``     → toggles ``deck_state().loop_active``
        * ``"hot_cue"``         → sets ``deck_state().hot_cues[idx] = True``
          where ``idx = clamp(action.extra["cue_index"] - 1, 0, 3)``
        * ``"gyro_toggle"``     → ``_state.gyro_enabled = bool(v)``
        * ``"effect_wet_dry"``  → ``_state.effect_wet_dry = v``
        * ``"effect_parameter"``→ ``_state.effect_parameter = v``
        * ``"pitch_nudge"``, ``"track_browse"``, ``"track_load"`` →
          transient actions with no persistent state; silently ignored here.

        Args:
            action: Object with attributes ``action_type`` (str), ``deck``
                (``"A"``, ``"B"``, or ``"master"``), ``value`` (float), and
                ``extra`` (dict).
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
                ds = deck_state()
                ds.playing = not ds.playing
            elif t == "sync_toggle":
                ds = deck_state()
                ds.sync_enabled = not ds.sync_enabled
            elif t == "loop_toggle":
                ds = deck_state()
                ds.loop_active = not ds.loop_active
            elif t == "hot_cue":
                idx = max(0, min(3, action.extra.get("cue_index", 1) - 1))
                deck_state().hot_cues[idx] = True
            elif t == "gyro_toggle":
                self._state.gyro_enabled = bool(v)
            elif t == "effect_wet_dry":
                self._state.effect_wet_dry = v
            elif t == "effect_parameter":
                self._state.effect_parameter = v
            # "pitch_nudge", "track_browse", "track_load" — transient, no state change

        cb = self._on_change
        if cb:
            cb(dataclasses.asdict(self._state))

    def set_on_change(self, callback) -> None:
        """Register a callback invoked after every state mutation.

        The callback receives a ``dict`` (the result of
        ``dataclasses.asdict(state)``) as its sole argument, not an
        ``AppState`` object.

        Args:
            callback: Callable that accepts a single ``dict`` argument.
                Pass ``None`` to deregister an existing callback.
        """
        self._on_change = callback

    def to_dict(self) -> dict:
        """Serialize the full state to a plain dictionary (JSON-safe).

        Returns:
            A nested ``dict`` produced by ``dataclasses.asdict``.  All values
            are Python primitives (bool, int, float, str, list) suitable for
            direct ``json.dumps`` serialisation.
        """
        with self._lock:
            return dataclasses.asdict(self._state)
