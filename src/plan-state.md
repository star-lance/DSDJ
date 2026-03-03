# `state.py` Implementation Plan

> **For Claude:** Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Implement the central state container — `GyroBinding`, `DeckState`, `AppState`, and `StateManager` — with thread-safe read/write and JSON serialization.

**File:** `src/state.py`
**Tests:** `tests/test_state.py`
**Dependencies:** none (pure Python)

---

## Task 1: `GyroBinding` dataclass

**Step 1:** Write the failing test in `tests/test_state.py`

```python
from src.state import GyroBinding

def test_gyro_binding_defaults():
    b = GyroBinding()
    assert b.unit == 0
    assert b.target == "mix"

def test_gyro_binding_cycle_unit():
    b = GyroBinding(unit=3)
    b.cycle_unit()
    assert b.unit == 0  # wraps around

def test_gyro_binding_cycle_unit_increments():
    b = GyroBinding(unit=1)
    b.cycle_unit()
    assert b.unit == 2
```

**Step 2:** Run to confirm failure
```bash
pytest tests/test_state.py -v
```
Expected: `FAILED` — `cannot import name 'GyroBinding'`

**Step 3:** Implement in `src/state.py`

```python
from dataclasses import dataclass, field
from typing import Literal

GyroTarget = Literal["mix", "parameter1", "parameter2", "parameter3"]

@dataclass
class GyroBinding:
    unit: int = 0
    target: GyroTarget = "mix"

    def cycle_unit(self):
        self.unit = (self.unit + 1) % 4
```

**Step 4:** Run tests
```bash
pytest tests/test_state.py::test_gyro_binding_defaults tests/test_state.py::test_gyro_binding_cycle_unit tests/test_state.py::test_gyro_binding_cycle_unit_increments -v
```
Expected: all PASSED

---

## Task 2: `DeckState` and `AppState` dataclasses

**Step 1:** Add tests

```python
from src.state import DeckState, AppState

def test_deck_state_defaults():
    d = DeckState()
    assert d.playing == False
    assert d.volume == 0.0
    assert d.eq_low == 0.5
    assert len(d.hot_cues) == 4

def test_app_state_defaults():
    a = AppState()
    assert a.crossfader == 0.5
    assert a.gyro_enabled == False
    assert isinstance(a.gyro_roll_binding, GyroBinding)
    assert isinstance(a.gyro_pitch_binding, GyroBinding)
    assert a.gyro_pitch_binding.unit == 1  # default differs from roll
```

**Step 2:** Run to confirm failure
```bash
pytest tests/test_state.py -k "deck_state or app_state" -v
```

**Step 3:** Implement

```python
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
    gyro_roll_binding: GyroBinding = field(default_factory=lambda: GyroBinding(unit=0, target="mix"))
    gyro_pitch_binding: GyroBinding = field(default_factory=lambda: GyroBinding(unit=1, target="parameter1"))
    ui_view: str = "decks"
    connected: bool = False
```

**Step 4:** Run tests
```bash
pytest tests/test_state.py -v
```
Expected: all PASSED

---

## Task 3: `StateManager` — basic get/update

**Step 1:** Add tests

```python
from src.state import StateManager

def test_state_manager_get_returns_state():
    sm = StateManager()
    s = sm.get_state()
    assert s.crossfader == 0.5

def test_state_manager_update_top_level():
    sm = StateManager()
    sm.update(crossfader=0.8)
    assert sm.get_state().crossfader == 0.8

def test_state_manager_update_nested():
    sm = StateManager()
    sm.update(**{"deck_a.volume": 0.7})
    assert sm.get_state().deck_a.volume == 0.7
```

**Step 2:** Run to confirm failure
```bash
pytest tests/test_state.py -k "state_manager" -v
```

**Step 3:** Implement

```python
import threading
import dataclasses

class StateManager:
    def __init__(self):
        self._state = AppState()
        self._lock = threading.Lock()
        self._on_change = None

    def get_state(self) -> AppState:
        with self._lock:
            return self._state

    def update(self, **kwargs):
        with self._lock:
            for key, value in kwargs.items():
                if "." in key:
                    parent, child = key.split(".", 1)
                    setattr(getattr(self._state, parent), child, value)
                else:
                    setattr(self._state, key, value)
        if self._on_change:
            self._on_change(self._state)

    def set_on_change(self, callback):
        self._on_change = callback

    def to_dict(self) -> dict:
        return dataclasses.asdict(self._state)
```

**Step 4:** Run tests
```bash
pytest tests/test_state.py -v
```
Expected: all PASSED

---

## Task 4: `update_from_action`

**Step 1:** Add tests (import DJAction stubs — use strings for now, refine after mapping.py is written)

```python
from unittest.mock import MagicMock
from src.state import StateManager, AppState

def _make_action(action_type, deck, value, extra=None):
    a = MagicMock()
    a.action_type = action_type
    a.deck = deck
    a.value = value
    a.extra = extra or {}
    return a

def test_update_volume_deck_a():
    sm = StateManager()
    sm.update_from_action(_make_action("volume", "A", 0.9))
    assert sm.get_state().deck_a.volume == 0.9

def test_update_play_pause_toggles():
    sm = StateManager()
    assert sm.get_state().deck_a.playing == False
    sm.update_from_action(_make_action("play_pause", "A", 1.0))
    assert sm.get_state().deck_a.playing == True
    sm.update_from_action(_make_action("play_pause", "A", 1.0))
    assert sm.get_state().deck_a.playing == False

def test_update_crossfader():
    sm = StateManager()
    sm.update_from_action(_make_action("crossfader", "master", 0.25))
    assert sm.get_state().crossfader == 0.25

def test_update_hot_cue():
    sm = StateManager()
    sm.update_from_action(_make_action("hot_cue", "B", 1.0, {"cue_index": 2}))
    assert sm.get_state().deck_b.hot_cues[1] == True
```

**Step 2:** Run to confirm failure
```bash
pytest tests/test_state.py -k "update_" -v
```

**Step 3:** Implement `update_from_action` on `StateManager`

```python
def update_from_action(self, action):
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

    if self._on_change:
        self._on_change(self._state)
```

**Step 4:** Run all state tests
```bash
pytest tests/test_state.py -v
```
Expected: all PASSED
