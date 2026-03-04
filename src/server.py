"""WebSocket server for the DualSense DJ Controller browser UI.

This module exposes real-time controller state to a React-based browser UI
over a WebSocket connection.  It uses FastAPI as the ASGI framework and
uvicorn as the ASGI server, both running inside the same asyncio event loop
as the rest of the application.

Architecture:
    - ``WebSocketServer`` wraps a ``FastAPI`` app with a single ``/ws``
      WebSocket endpoint and optional static file serving for the compiled UI.
    - A shared ``_connections`` list acts as a broadcast registry.  Every
      connected WebSocket is kept in this list; ``broadcast`` iterates it and
      removes dead connections as they are discovered.
    - State is pushed *server → client* only.  The client never sends messages;
      ``receive_text()`` is used purely as a blocking keep-alive so that the
      server can detect when the browser tab closes or the network drops.

Broadcast pattern:
    The ``broadcast_loop`` in ``main.py`` calls ``broadcast()`` at up to
    60 fps.  ``broadcast`` serialises the state dict to JSON once and fans
    it out to all connections.  Failed sends are collected in a ``dead``
    list and removed after the loop, avoiding mutation of the list while
    iterating over it.
"""

import asyncio
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import uvicorn

log = logging.getLogger(__name__)


class WebSocketServer:
    """FastAPI-based WebSocket server that broadcasts DJ state to browser clients.

    Manages a list of active WebSocket connections and provides a ``broadcast``
    method for pushing state updates to all of them simultaneously.

    Attributes:
        _state_manager: ``StateManager`` instance — used to get the current
            full state on initial client connection.
        _state_channel: ``LatestValueChannel`` — not used directly by the
            server, but stored for potential future use.
        _host: Bind address for the uvicorn HTTP server.
        _port: TCP port for the uvicorn HTTP server.
        _connections: List of currently active ``WebSocket`` objects.
            Entries are added in ``_handle_connection`` and removed either
            there (in the ``finally`` block) or in ``broadcast`` when a send
            fails.
        _app: The ``FastAPI`` application instance with routes attached.
    """

    def __init__(self, state_manager, state_channel, config: dict):
        """Initialise the server and register FastAPI routes.

        Args:
            state_manager: ``StateManager`` — provides ``to_dict()`` for the
                initial state snapshot sent to newly connected clients.
            state_channel: ``LatestValueChannel`` — stored but not actively
                polled by the server itself.
            config: Server configuration sub-dict (the ``server`` section of
                ``config.yaml``).  Expected keys: ``host`` (default
                ``"127.0.0.1"``) and ``port`` (default ``8765``).
        """
        self._state_manager = state_manager
        self._state_channel = state_channel
        self._host = config.get("host", "127.0.0.1")
        self._port = config.get("port", 8765)
        self._connections: list[WebSocket] = []
        self._app = FastAPI()
        self._setup_routes()

    def _setup_routes(self):
        """Register the WebSocket endpoint and optional static file mount.

        The ``/ws`` endpoint delegates to ``_handle_connection``.

        The compiled React UI (``ui/dist/``) is mounted at ``/`` only if the
        directory exists, so the server starts successfully even in development
        environments where the UI has not been built yet.
        """
        @self._app.websocket("/ws")
        async def ws_endpoint(websocket: WebSocket):
            await self._handle_connection(websocket)

        # Serve built React UI — only if the dist folder exists
        import os
        ui_dist = os.path.join(os.path.dirname(__file__), "..", "ui", "dist")
        if os.path.isdir(ui_dist):
            self._app.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")

    async def _handle_connection(self, websocket: WebSocket):
        """Accept a new WebSocket client and manage its full lifecycle.

        On connection:
            1. Accept the WebSocket handshake.
            2. Add the socket to ``_connections`` (enables it to receive
               subsequent ``broadcast`` calls).
            3. Send the current full state immediately so the client has
               something to render before the first broadcast arrives.

        Keep-alive loop:
            The server only sends to clients; it never expects the client to
            send anything meaningful.  ``receive_text()`` is called in a loop
            solely to detect client disconnection: when the browser tab closes
            or the network drops, ``receive_text()`` raises an exception
            (typically ``WebSocketDisconnect`` or a starlette ``RuntimeError``)
            which breaks the loop.  Without this loop the coroutine would
            return immediately and the connection handle would be lost.

        Cleanup (``finally``):
            The socket is removed from ``_connections`` so that future
            ``broadcast`` calls no longer attempt to write to it.

        Args:
            websocket: The FastAPI ``WebSocket`` instance for this connection.
        """
        await websocket.accept()
        self._connections.append(websocket)
        log.info(f"UI client connected. Total: {len(self._connections)}")

        # Send current state immediately on connect
        try:
            await websocket.send_text(json.dumps({
                "type": "state_update",
                "data": self._state_manager.to_dict()
            }))
        except Exception:
            self._connections.remove(websocket)
            return

        try:
            while True:
                # Keep alive — we only send to clients, not receive
                await websocket.receive_text()
        except Exception:
            pass
        finally:
            if websocket in self._connections:
                self._connections.remove(websocket)
            log.info(f"UI client disconnected. Total: {len(self._connections)}")

    async def broadcast(self, state_dict: dict):
        """Serialise state and send it to all connected clients.

        Serialises ``state_dict`` to a JSON string once, then iterates over
        all connections.  Any connection that raises an exception during
        ``send_text`` is assumed dead and added to a ``dead`` list.  After the
        iteration, dead connections are removed from ``_connections``.

        Collecting failures in a separate list and removing them after the
        loop avoids the classic "mutate list while iterating" bug.

        Does nothing if there are no connected clients.

        Args:
            state_dict: Serialisable state snapshot from
                ``StateManager.to_dict()``.
        """
        if not self._connections:
            return
        message = json.dumps({"type": "state_update", "data": state_dict})
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                # Mark as dead — do not remove here to avoid mutating _connections mid-loop.
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)

    async def serve(self):
        """Start the uvicorn ASGI server and run until cancelled.

        Creates a ``uvicorn.Server`` with ``install_signal_handlers=False`` so
        that uvicorn does not register its own ``SIGINT``/``SIGTERM`` handlers
        (the application's ``main`` function owns those).  Runs until the
        asyncio task is cancelled, which causes ``server.serve()`` to return.

        Raises:
            asyncio.CancelledError: Propagated when the task is cancelled
                during application shutdown.
        """
        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="warning",
            install_signal_handlers=False,
        )
        server = uvicorn.Server(config)
        await server.serve()
