"""main.py — asyncio entry point for the DualSense DJ Controller.

This module is the top-level wiring layer.  It instantiates every subsystem,
connects them together, and manages the lifecycle of three concurrent tasks
under a simple supervisor:

Tasks:
    ``controller_loop`` — polls the DualSense HID device at 250 Hz, maps
        inputs to ``DJAction`` objects, sends MIDI, and updates internal state.
    ``broadcast_loop``  — consumes state snapshots from the channel and
        broadcasts them to connected WebSocket clients at up to 60 fps.
    ``ws_server.serve`` — runs the FastAPI/uvicorn WebSocket server that the
        React UI connects to.

Concurrency model:
    The asyncio event loop runs on the main thread.  The only blocking I/O
    (HID reads from ``pydualsense``) is offloaded to the default
    ``ThreadPoolExecutor`` via ``loop.run_in_executor``.  All other work
    (mapping, MIDI, state updates) is fast enough to run directly on the loop.

Signal handling:
    ``SIGINT`` (Ctrl-C) and ``SIGTERM`` are caught via
    ``loop.add_signal_handler`` and set a shared ``asyncio.Event``
    (``stop_event``).  Once set, the main coroutine cancels all tasks and
    performs a clean shutdown.
"""

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time

import yaml

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task 1: LatestValueChannel
# ---------------------------------------------------------------------------


class LatestValueChannel:
    """Async single-producer single-consumer channel that keeps only the newest value.

    Unlike ``asyncio.Queue``, this channel does not accumulate a backlog.
    When the consumer is slower than the producer (which it can be — the
    controller runs at 250 Hz but broadcasts are capped at 60 fps) old state
    snapshots are silently overwritten by newer ones.

    This is intentional: the UI only ever needs the *latest* state to render
    an accurate view.  Queuing every intermediate state would just waste
    memory and cause the UI to lag behind reality.

    The channel uses an ``asyncio.Event`` as its signalling primitive.  The
    event is set by ``put()`` (possibly overwriting a value that hasn't been
    consumed yet) and cleared by ``get()`` after reading the stored value.
    """

    def __init__(self):
        self._value = None
        self._event = asyncio.Event()

    def put(self, value):
        """Store the latest value and signal any waiting consumer.

        If the previous value has not yet been consumed it is silently
        discarded — only the newest value matters.

        Args:
            value: The new value to store (any object).
        """
        self._value = value
        self._event.set()

    async def get(self):
        """Wait for the next value and return it.

        Suspends the caller until ``put()`` is called, then clears the event
        and returns the stored value.  If ``put()`` is called again before
        the next ``get()``, the intermediate value is lost.

        Returns:
            The most recently ``put`` value.
        """
        await self._event.wait()
        self._event.clear()
        return self._value


# ---------------------------------------------------------------------------
# Task 2: controller_loop
# ---------------------------------------------------------------------------


async def controller_loop(controller, mapper_ref, midi_bridge, state_manager, state_channel, loop):
    """Poll the DualSense at 250 Hz, map inputs, send MIDI, and push state.

    Runs as a long-lived coroutine under ``supervised_task``.  Each iteration:

    1. Offloads the blocking HID read to a thread-pool executor so the event
       loop is not stalled waiting for USB I/O.
    2. Calls ``mapper.process()`` — pure computation, no I/O.
    3. Sends MIDI CC/Note messages for each produced action.  MIDI writes are
       microsecond-latency operations and are called directly (not via
       executor) since they do not cause measurable event-loop jitter.
    4. Applies each action to the ``StateManager`` (updates the in-memory
       state snapshot used by the WebSocket broadcast loop).
    5. Pushes the serialised state dict to ``state_channel``; the channel
       drops it if a newer value arrives before the broadcast loop consumes it.
    6. Sleeps for the remainder of the 4 ms (250 Hz) budget.

    Args:
        controller: ``DualSenseController`` instance — owns the HID handle.
        mapper: ``InputMapper`` instance — stateful, must not be shared.
        midi_bridge: ``MIDIBridge`` instance — owns the virtual MIDI port.
        state_manager: ``StateManager`` instance — thread-safe state store.
        state_channel: ``LatestValueChannel`` — delivers state to broadcast loop.
        loop: The running asyncio event loop (obtained from
            ``asyncio.get_running_loop()`` in ``main``).
    """
    INTERVAL = 0.004  # 250Hz

    while True:
        t_start = loop.time()

        # Check for USB disconnect (pydualsense sets connected=False when IOError)
        if not controller.is_connected:
            log.warning("DualSense disconnected. Attempting reconnect...")
            state_manager.update(connected=False)
            while True:
                try:
                    await loop.run_in_executor(None, controller.reconnect)
                    controller.set_led_color(0, 200, 200)
                    state_manager.update(connected=True)
                    log.info("DualSense reconnected.")
                    break
                except Exception as e:
                    log.warning(f"Reconnect failed: {e}. Retrying in 2s...")
                    await asyncio.sleep(2.0)

        # Blocking HID read — run in thread pool
        ctrl_state = await loop.run_in_executor(None, controller.read_state)

        # Map to actions (pure computation — no I/O)
        mapper = mapper_ref[0]
        actions = mapper.process(ctrl_state)

        # Send MIDI and handle side-effects (microsecond blocking calls — acceptable)
        for action in actions:
            if action.action_type == "deck_switch":
                # Update controller LED to reflect active deck
                if action.deck == "A":
                    controller.set_led_color(0, 200, 200)    # cyan
                elif action.deck == "B":
                    controller.set_led_color(200, 0, 200)    # magenta
                else:
                    controller.set_led_color(200, 200, 200)  # white (mirror)
            else:
                midi_bridge.send_action(
                    action,
                    binding=(
                        mapper.gyro_roll_binding if action.action_type == "effect_wet_dry"
                        else mapper.gyro_pitch_binding if action.action_type == "effect_parameter"
                        else None
                    )
                )

        # Update internal state
        for action in actions:
            state_manager.update_from_action(action)

        # Push latest state (non-blocking, drops stale)
        state_channel.put(state_manager.to_dict())

        # Maintain 250Hz
        elapsed = loop.time() - t_start
        await asyncio.sleep(max(0.0, INTERVAL - elapsed))


# ---------------------------------------------------------------------------
# Task 3: broadcast_loop
# ---------------------------------------------------------------------------


async def broadcast_loop(state_channel, ws_server):
    """Consume state from the channel and broadcast to WebSocket clients.

    Caps the broadcast rate at 60 fps (``MIN_INTERVAL = 1/60`` s) so that
    connected browser clients are not overwhelmed by the full 250 Hz rate of
    the controller loop.  Because ``LatestValueChannel`` silently drops stale
    values, the state delivered here is always the most recent one available
    at the time the channel was consumed.

    Args:
        state_channel: ``LatestValueChannel`` — source of state snapshots.
        ws_server: ``WebSocketServer`` — destination for JSON broadcasts.
    """
    MIN_INTERVAL = 1 / 60

    while True:
        state_dict = await state_channel.get()
        await ws_server.broadcast(state_dict)
        await asyncio.sleep(MIN_INTERVAL)


# ---------------------------------------------------------------------------
# Task 4: supervised_task
# ---------------------------------------------------------------------------


async def supervised_task(coro_factory, name: str):
    """Run a coroutine indefinitely, restarting it after recoverable crashes.

    ``asyncio.CancelledError`` is intentionally NOT caught here.  In Python
    3.8+, ``CancelledError`` is a subclass of ``BaseException``, not
    ``Exception``, so the ``except Exception`` clause below does not intercept
    it.  This is correct by design: when the main shutdown sequence calls
    ``task.cancel()``, the ``CancelledError`` propagates up immediately and
    terminates the supervised task cleanly without an unwanted restart.

    Any other exception (e.g. ``OSError`` from a momentary USB disconnect,
    ``RuntimeError`` from a pydualsense state hiccup) is logged and the
    coroutine is restarted after a 2-second back-off.

    Args:
        coro_factory: Zero-argument callable that returns a fresh coroutine
            object each time it is called.  Passed as a lambda in ``main``.
        name: Human-readable task name used in log messages.
    """
    while True:
        try:
            await coro_factory()
        except Exception as e:
            log.error(f"Task '{name}' crashed: {e}. Restarting in 2s...")
            await asyncio.sleep(2.0)


# ---------------------------------------------------------------------------
# Task 5: main() entry point
# ---------------------------------------------------------------------------


def load_config(path="config.yaml") -> dict:
    """Load and parse the YAML configuration file.

    Args:
        path: Path to the YAML config file, relative to the working directory.

    Returns:
        Parsed configuration as a nested ``dict``.
    """
    with open(path) as f:
        return yaml.safe_load(f)


async def main():
    """Async entry point: initialise all subsystems and run until a signal.

    Start-up sequence:
        1. Load ``config.yaml``.
        2. Instantiate ``StateManager`` and ``LatestValueChannel``.
        3. Open the DualSense HID device (exit with error if unavailable).
        4. Open the virtual MIDI port.
        5. Build the ``InputMapper`` and ``WebSocketServer``.
        6. Install ``SIGINT``/``SIGTERM`` handlers that set ``stop_event``.
        7. Set the controller LED to dim blue (ready indicator).
        8. Launch the three asyncio tasks under supervision.
        9. Await ``stop_event`` (blocks until Ctrl-C or ``SIGTERM``).

    Shutdown sequence (after stop_event fires):
        - Cancel all three tasks; gather to allow their ``finally`` blocks to
          run (``return_exceptions=True`` prevents a second exception from
          masking the first).
        - Close the DualSense HID handle.
        - Close the virtual MIDI port (removes it from the OS device list).
    """
    config = load_config()

    from .state import StateManager
    from .controller import DualSenseController
    from .midi_bridge import MIDIBridge
    from .mapping import InputMapper
    from .server import WebSocketServer

    state_manager = StateManager()
    state_channel = LatestValueChannel()

    controller = None
    while controller is None:
        try:
            controller = DualSenseController(config["controller"])
        except Exception as e:
            print(f"DualSense not found ({e}). Retrying in 2s...")
            await asyncio.sleep(2.0)

    state_manager.update(connected=True)

    # Seed macro state from config so UI reflects initial bindings on first connect
    from .state import MacroBinding as _MacroBinding

    def _bindings_from_config(raw):
        return [_MacroBinding(control=b["control"], deck=b["deck"],
                              base=float(b.get("base", 0.5)),
                              min_val=float(b.get("min_val", 0.0)),
                              max_val=float(b.get("max_val", 1.0)))
                for b in raw]

    macro_cfg = config.get("macros", {})
    state_manager.update(
        macro_a=_bindings_from_config(macro_cfg.get("left_stick", [])),
        macro_b=_bindings_from_config(macro_cfg.get("right_stick", [])),
    )

    midi_bridge = MIDIBridge(config["midi"]["port_name"])
    mapper_ref = [InputMapper(config)]
    ws_server = WebSocketServer(state_manager, state_channel, config["server"], mapper_ref=mapper_ref)

    loop = asyncio.get_running_loop()

    # Signal handler for clean shutdown
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    async def reload_mapper():
        import importlib
        import shutil
        import src.mapping as mapping_module
        importlib.reload(mapping_module)
        new_config = load_config()
        mapper_ref[0] = mapping_module.InputMapper(new_config)
        state_manager.update(
            macro_a=mapper_ref[0]._macro_a,
            macro_b=mapper_ref[0]._macro_b,
        )
        # Keep Mixxx's copy of the XML in sync with the project file
        xml_src = os.path.join(os.path.dirname(__file__), "mixxx", "midi_mapping.xml")
        xml_dst = os.path.expanduser("~/.mixxx/controllers/DualSense-DJ.midi.xml")
        if os.path.exists(xml_src):
            shutil.copy2(xml_src, xml_dst)
        print("\n  \033[1;32mMapper reloaded.\033[0m\n")

    loop.add_signal_handler(signal.SIGUSR1, lambda: asyncio.create_task(reload_mapper()))

    controller.set_led_color(0, 200, 200)  # cyan = Deck A active
    host = config["server"]["host"]
    port = config["server"]["port"]
    url = f"http://{host}:{port}"
    midi_port = config["midi"]["port_name"]
    print()
    print("  \033[1;36mDualSense DJ\033[0m  ready")
    print(f"  MIDI  →  \033[1m{midi_port}\033[0m")
    print(f"  UI    →  \033[1;4;34m{url}\033[0m  \033[2m(O = open browser, R = reload mapper)\033[0m")
    print()

    def _open_browser():
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    import atexit, select
    _stdin_is_tty = sys.stdin.isatty()

    if _stdin_is_tty:
        import tty, termios
        old_term = termios.tcgetattr(sys.stdin)
        atexit.register(termios.tcsetattr, sys.stdin, termios.TCSADRAIN, old_term)
        tty.setcbreak(sys.stdin.fileno())

    def _check_keypress():
        """Non-blocking stdin check; returns pressed char or None."""
        if not _stdin_is_tty:
            return None
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None

    try:
        tasks = [
            asyncio.create_task(
                supervised_task(
                    lambda: controller_loop(controller, mapper_ref, midi_bridge,
                                            state_manager, state_channel, loop),
                    "controller"
                )
            ),
            asyncio.create_task(
                supervised_task(lambda: broadcast_loop(state_channel, ws_server), "broadcast")
            ),
            asyncio.create_task(
                supervised_task(lambda: ws_server.serve(), "server")
            ),
        ]

        while not stop_event.is_set():
            key = _check_keypress()
            if key and key.lower() == "o":
                _open_browser()
            elif key and key.lower() == "r":
                await reload_mapper()
            await asyncio.sleep(0.1)
    finally:
        if _stdin_is_tty:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_term)

    print("\nShutting down...")
    for t in tasks:
        t.cancel()
    # return_exceptions=True ensures a CancelledError from one task does not
    # prevent the others from being awaited and cleaned up.
    await asyncio.gather(*tasks, return_exceptions=True)
    controller.close()
    midi_bridge.close()


if __name__ == "__main__":
    asyncio.run(main())
