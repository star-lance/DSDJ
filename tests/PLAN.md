# Tests Implementation Plan

> **For Claude:** Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Ensure all unit tests pass before integration testing begins. This plan is executed *after* each `src/plan-*.md` is complete — the test files already exist as stubs; each src plan writes its own tests inline.

**Directory:** `tests/`
**Run all tests:** `pytest -v`

---

## Test file ownership

Each plan owns its test file. This plan covers cross-cutting concerns only.

| Test file | Written by |
|---|---|
| `tests/test_state.py` | `src/plan-state.md` |
| `tests/test_controller.py` | `src/plan-controller.md` |
| `tests/test_midi_bridge.py` | `src/plan-midi-bridge.md` |
| `tests/test_mapping.py` | `src/plan-mapping.md` |
| `tests/test_main.py` | `src/plan-main.md` |
| `tests/integration/` | Integration plans below |

---

## Task 1: Confirm all unit tests pass after each src module is complete

After implementing each module per its plan, run:

```bash
pytest tests/ -v --ignore=tests/integration
```

Expected: all PASSED. No errors. Fix any failures in the corresponding source file before proceeding to the next module.

---

## Task 2: Integration test checklist

Run these **only with DualSense connected and python src/main.py running**.

### Controller hardware test
```bash
pytest tests/integration/test_controller_live.py -v -s -m integration
```
Confirm:
- [ ] All stick values read (move sticks, see output)
- [ ] Triggers read 0.0 at rest, 1.0 at full press
- [ ] Touchpad coordinates change when finger moves
- [ ] Gyro values change when controller is tilted

### MIDI port test
```bash
pytest tests/integration/test_midi_live.py -v -s -m integration
# In another terminal:
aconnect -l | grep DualSense
```
Confirm:
- [ ] "DualSense DJ" port appears in ALSA
- [ ] No errors on test messages

### Mixxx integration (manual — see `src/mixxx/PLAN.md` Task 4)
Confirm each mapping works in Mixxx.

---

## Task 3: WebSocket end-to-end test

With `python src/main.py` running, run the quick client:

```bash
python -c "
import asyncio, json, websockets

async def main():
    async with websockets.connect('ws://127.0.0.1:8765/ws') as ws:
        for _ in range(5):
            msg = json.loads(await ws.recv())
            print('crossfader:', msg['data']['crossfader'])

asyncio.run(main())
"
```

Move the touchpad while this runs. Confirm crossfader value changes appear.

---

## Task 4: Full system smoke test

Run everything together:
1. `python src/main.py` in terminal 1
2. Open Mixxx, connect to "DualSense DJ" controller, load the preset
3. Open `http://127.0.0.1:8765` in a browser (or `http://localhost:5173` for Vite dev server)
4. Verify:
   - [ ] UI shows CONNECTED badge
   - [ ] Moving L2 trigger changes Deck A volume bar in UI
   - [ ] Moving touchpad left/right moves crossfader in Mixxx and UI
   - [ ] L1 toggles play/pause in Mixxx and UI
   - [ ] Holding Options changes ControllerMap overlay to EQ MODE
   - [ ] Mute button changes gyro indicator in UI
