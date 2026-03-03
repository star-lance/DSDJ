import asyncio
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import uvicorn

log = logging.getLogger(__name__)

class WebSocketServer:
    def __init__(self, state_manager, state_channel, config: dict):
        self._state_manager = state_manager
        self._state_channel = state_channel
        self._host = config.get("host", "127.0.0.1")
        self._port = config.get("port", 8765)
        self._connections: list[WebSocket] = []
        self._app = FastAPI()
        self._setup_routes()

    def _setup_routes(self):
        @self._app.websocket("/ws")
        async def ws_endpoint(websocket: WebSocket):
            await self._handle_connection(websocket)

        # Serve built React UI — only if the dist folder exists
        import os
        ui_dist = os.path.join(os.path.dirname(__file__), "..", "ui", "dist")
        if os.path.isdir(ui_dist):
            self._app.mount("/", StaticFiles(directory=ui_dist, html=True), name="ui")

    async def _handle_connection(self, websocket: WebSocket):
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
        if not self._connections:
            return
        message = json.dumps({"type": "state_update", "data": state_dict})
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)

    async def serve(self):
        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="warning",
            install_signal_handlers=False,
        )
        server = uvicorn.Server(config)
        await server.serve()
