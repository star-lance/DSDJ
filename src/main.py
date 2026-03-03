"""main.py — asyncio entry point for the DualSense DJ Controller.

Wires together all modules under a task supervisor at 250Hz controller loop,
a 60fps broadcast loop, and a WebSocket server.
"""

import asyncio
import logging
import signal
import sys
import time

import yaml

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task 1: LatestValueChannel
# ---------------------------------------------------------------------------


class LatestValueChannel:
    """Async channel that always delivers the latest value, dropping stale ones."""

    def __init__(self):
        self._value = None
        self._event = asyncio.Event()

    def put(self, value):
        self._value = value
        self._event.set()

    async def get(self):
        await self._event.wait()
        self._event.clear()
        return self._value


# ---------------------------------------------------------------------------
# Task 2: controller_loop
# ---------------------------------------------------------------------------


async def controller_loop(controller, mapper, midi_bridge, state_manager, state_channel, loop):
    """Read controller at 250Hz, map inputs, send MIDI, push state."""
    INTERVAL = 0.004  # 250Hz

    while True:
        t_start = loop.time()

        # Blocking HID read — run in thread pool
        ctrl_state = await loop.run_in_executor(None, controller.read_state)

        # Map to actions (pure computation — no I/O)
        actions = mapper.process(ctrl_state)

        # Send MIDI (microsecond blocking calls — acceptable direct call)
        for action in actions:
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
    """Consume state channel and broadcast to WebSocket clients at up to 60fps."""
    MIN_INTERVAL = 1 / 60

    while True:
        state_dict = await state_channel.get()
        await ws_server.broadcast(state_dict)
        await asyncio.sleep(MIN_INTERVAL)


# ---------------------------------------------------------------------------
# Task 4: supervised_task
# ---------------------------------------------------------------------------


async def supervised_task(coro_factory, name: str):
    """Run a coroutine, restarting it on recoverable errors.

    asyncio.CancelledError is NOT a subclass of Exception in Python 3.8+,
    so task cancellation propagates correctly and does NOT restart.
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
    with open(path) as f:
        return yaml.safe_load(f)


async def main():
    config = load_config()

    from src.state import StateManager
    from src.controller import DualSenseController
    from src.midi_bridge import MIDIBridge
    from src.mapping import InputMapper
    from src.server import WebSocketServer

    state_manager = StateManager()
    state_channel = LatestValueChannel()

    try:
        controller = DualSenseController(config["controller"])
    except Exception as e:
        print(f"ERROR: Could not connect to DualSense controller: {e}")
        sys.exit(1)

    midi_bridge = MIDIBridge(config["midi"]["port_name"])
    mapper = InputMapper(config)
    ws_server = WebSocketServer(state_manager, state_channel, config["server"])

    loop = asyncio.get_running_loop()

    # Signal handler for clean shutdown
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    controller.set_led_color(0, 0, 80)  # dim blue = ready
    print(f"DualSense DJ ready. Connect Mixxx to '{config['midi']['port_name']}' MIDI device.")

    tasks = [
        asyncio.create_task(
            supervised_task(
                lambda: controller_loop(controller, mapper, midi_bridge,
                                        state_manager, state_channel, loop),
                "controller"
            )
        ),
        asyncio.create_task(
            supervised_task(lambda: broadcast_loop(state_channel, ws_server), "broadcast")
        ),
        asyncio.create_task(ws_server.serve()),
    ]

    await stop_event.wait()

    print("\nShutting down...")
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    controller.close()
    midi_bridge.close()


if __name__ == "__main__":
    asyncio.run(main())
