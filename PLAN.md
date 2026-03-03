# DualSense DJ — Project Setup Plan

> **For Claude:** Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Bootstrap the Python environment, config file, and test runner so every subsequent plan can run immediately.

**Execution order for the full project:**

| Phase | Plans | Can parallelize? |
|---|---|---|
| A | This file (scaffolding) | — |
| B | `src/plan-state.md`, `src/mixxx/PLAN.md` | Yes |
| C | `src/plan-controller.md`, `src/plan-midi-bridge.md`, `src/plan-server.md` | Yes |
| D | `src/plan-mapping.md` | After B + C |
| E | `src/plan-main.md`, `ui/PLAN.md` | Yes, after D |
| F | `tests/PLAN.md` | After E |

---

## Task 1: Create the virtual environment

**Step 1:** Create venv
```bash
cd /home/star/STARDUST/projects/DJCONTROLLER
python -m venv .venv
```

**Step 2:** Verify it exists
```bash
ls .venv/bin/python
```
Expected: path printed with no error.

**Step 3:** Activate (all subsequent commands assume this is active)
```bash
source .venv/bin/activate
```

---

## Task 2: Install Python dependencies

**Step 1:** Write `requirements.txt`

```
pydualsense
python-rtmidi
fastapi
uvicorn[standard]
websockets
PyYAML
pytest
pytest-asyncio
```

**Step 2:** Install
```bash
pip install -r requirements.txt
```

**Step 3:** Verify key packages
```bash
python -c "import rtmidi; import fastapi; import yaml; print('OK')"
```
Expected: `OK`

---

## Task 3: Write `config.yaml`

Create this file at the project root:

```yaml
controller:
  connection: "usb"
  deadzone: 0.08
  touchpad_crossfader_smoothing: 0.15
  direction_lock_threshold: 0.04   # normalized units before axis is locked

midi:
  port_name: "DualSense DJ"
  channel: 0

haptics:
  enabled: false   # Phase 2

adaptive_triggers:
  enabled: false   # Phase 2

gyro:
  roll_unit: 0        # EffectUnit index (0-3) for roll axis
  roll_target: "mix"  # "mix" | "parameter1" | "parameter2" | "parameter3"
  pitch_unit: 1
  pitch_target: "parameter1"
  tilt_range_degrees: 45.0

filter:
  stick_curve: "exponential"
  stick_exponent: 2.0

server:
  host: "127.0.0.1"
  port: 8765
  ui_port: 5173
```

---

## Task 4: Configure pytest

Write `pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

**Step 1:** Verify pytest finds tests (all empty for now)
```bash
pytest --collect-only
```
Expected: `no tests ran` (zero tests collected, no errors)

---

## Task 5: Verify project tree

```bash
find . -not -path './.venv/*' -not -path './docs/*' | sort
```

Expected output should include all directories and stub files created. If anything is missing, create it with `touch`.
