# `server.py` Implementation Plan

> **For Claude:** Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** FastAPI app with a WebSocket endpoint that broadcasts state updates to all connected React UI clients, and serves the built UI as static files.

**File:** `src/server.py`
**Tests:** No isolated unit test (FastAPI WS testing requires an async test client — out of scope for now). Verify manually after UI is built.
**Dependencies:** `src/state.py` (for `StateManager`), `src/main.py` (for `LatestValueChannel`)

---

## Task 1: `WebSocketServer` class

Implement in `src/server.py`:

```python
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
            pass

        try:
            while True:
                # Keep alive — we only send to clients, not receive
                await websocket.receive_text()
        except WebSocketDisconnect:
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
            log_level="warning"
        )
        server = uvicorn.Server(config)
        await server.serve()
```

---

## Task 2: Manual verification

**Step 1:** Start the full system
```bash
python src/main.py
```

**Step 2:** Test WebSocket connection with a simple Python client in another terminal

```python
# quick_ws_test.py (run in project root)
import asyncio, json, websockets

async def test():
    async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
        msg = await ws.recv()
        data = json.loads(msg)
        print("Type:", data["type"])
        print("Crossfader:", data["data"]["crossfader"])
        print("Connected!")

asyncio.run(test())
```

```bash
python quick_ws_test.py
```

Expected:
```
Type: state_update
Crossfader: 0.5
Connected!
```

**Step 3:** Verify state updates flow in real time

Move a trigger on the controller while the test client is running. Modify `quick_ws_test.py` to receive 10 messages and print them. Verify crossfader/volume values change.

---

## Task 3: Static file serving

Once the React UI is built (see `ui/PLAN.md`):

```bash
cd ui && npm run build && cd ..
python src/main.py
```

Open `http://127.0.0.1:8765` in a browser. The React UI should load.

If the `ui/dist` folder doesn't exist yet, the server starts without the static mount (no error — the `os.path.isdir` guard handles this).
