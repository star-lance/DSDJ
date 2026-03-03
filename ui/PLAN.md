# React UI Implementation Plan

> **For Claude:** Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Build a React 18 + Vite + Tailwind web UI that connects to the Python WebSocket server and displays real-time DJ state.

**Directory:** `ui/`
**Dependencies:** `src/server.py` must be running. Python backend WebSocket at `ws://127.0.0.1:8765/ws`.

---

## Task 1: Initialize Vite + React project

**Step 1:** Scaffold

```bash
cd ui
npm create vite@latest . -- --template react
```

When prompted: confirm overwrite (files exist as stubs) → Yes.

**Step 2:** Install dependencies

```bash
npm install
npm install -D tailwindcss @tailwindcss/vite
```

**Step 3:** Configure Tailwind — update `vite.config.js`:

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/ws': { target: 'ws://127.0.0.1:8765', ws: true }
    }
  }
})
```

**Step 4:** Add Tailwind to `ui/src/index.css`:

```css
@import "tailwindcss";
```

**Step 5:** Verify dev server starts

```bash
npm run dev
```

Open `http://localhost:5173` — Vite default page appears. No errors in console.

---

## Task 2: `useWebSocket` hook

File: `ui/src/hooks/useWebSocket.js`

```javascript
import { useState, useEffect, useRef } from 'react'

const DEFAULT_STATE = {
  deck_a: { playing: false, bpm: 0, volume: 0, filter_value: 0.5,
            eq_low: 0.5, eq_mid: 0.5, eq_high: 0.5, sync_enabled: false,
            loop_active: false, hot_cues: [false,false,false,false],
            track_title: '', track_artist: '' },
  deck_b: { playing: false, bpm: 0, volume: 0, filter_value: 0.5,
            eq_low: 0.5, eq_mid: 0.5, eq_high: 0.5, sync_enabled: false,
            loop_active: false, hot_cues: [false,false,false,false],
            track_title: '', track_artist: '' },
  crossfader: 0.5,
  gyro_enabled: false,
  eq_mode: false,
  effect_wet_dry: 0.0,
  effect_parameter: 0.5,
  gyro_roll_binding: { unit: 0, target: 'mix' },
  gyro_pitch_binding: { unit: 1, target: 'parameter1' },
  ui_view: 'decks',
  connected: false,
}

export function useWebSocket(url) {
  const [state, setState] = useState(DEFAULT_STATE)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)

  useEffect(() => {
    let retryTimer = null

    function connect() {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'state_update') setState(msg.data)
        } catch {}
      }

      ws.onclose = () => {
        setConnected(false)
        retryTimer = setTimeout(connect, 2000)
      }

      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      clearTimeout(retryTimer)
      wsRef.current?.close()
    }
  }, [url])

  return { state, connected }
}
```

---

## Task 3: `DeckDisplay` component

File: `ui/src/components/DeckDisplay.jsx`

Props: `{ deck, label, color }` where `color` is `"cyan"` or `"magenta"`.

Shows: track title/artist, BPM, play state badge, volume bar, filter slider position, EQ Low/Mid/High bars, hot cue buttons (lit when set), loop indicator, sync badge.

```jsx
export function DeckDisplay({ deck, label, color }) {
  const accent = color === 'cyan' ? 'text-cyan-400' : 'text-fuchsia-400'
  const bar = color === 'cyan' ? 'bg-cyan-500' : 'bg-fuchsia-500'

  return (
    <div className="flex flex-col gap-2 p-4 bg-zinc-900 rounded-xl">
      <div className={`text-xs font-bold tracking-widest ${accent}`}>DECK {label}</div>

      <div className="text-sm font-semibold truncate">{deck.track_title || '—'}</div>
      <div className="text-xs text-zinc-400 truncate">{deck.track_artist}</div>

      <div className="flex gap-2 items-center">
        <span className={`text-xs px-2 py-0.5 rounded ${deck.playing ? 'bg-green-700' : 'bg-zinc-700'}`}>
          {deck.playing ? '▶ PLAY' : '■ STOP'}
        </span>
        {deck.sync_enabled && <span className="text-xs px-2 py-0.5 rounded bg-blue-700">SYNC</span>}
        {deck.loop_active && <span className="text-xs px-2 py-0.5 rounded bg-yellow-700">LOOP</span>}
        <span className="text-xs text-zinc-400 ml-auto">{deck.bpm.toFixed(1)} BPM</span>
      </div>

      {/* Volume */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-zinc-500 w-6">VOL</span>
        <div className="flex-1 h-2 bg-zinc-700 rounded">
          <div className={`h-full rounded ${bar}`} style={{ width: `${deck.volume * 100}%` }} />
        </div>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-zinc-500 w-6">FLT</span>
        <div className="flex-1 h-2 bg-zinc-700 rounded relative">
          <div className="absolute top-0 w-2 h-full bg-white rounded"
               style={{ left: `calc(${deck.filter_value * 100}% - 4px)` }} />
        </div>
      </div>

      {/* EQ */}
      <div className="flex gap-1">
        {[['L', deck.eq_low], ['M', deck.eq_mid], ['H', deck.eq_high]].map(([k, v]) => (
          <div key={k} className="flex flex-col items-center gap-1 flex-1">
            <div className="h-12 w-full bg-zinc-700 rounded relative">
              <div className={`absolute bottom-0 w-full rounded ${bar}`}
                   style={{ height: `${v * 100}%` }} />
            </div>
            <span className="text-xs text-zinc-500">{k}</span>
          </div>
        ))}
      </div>

      {/* Hot cues */}
      <div className="flex gap-1">
        {deck.hot_cues.map((set, i) => (
          <div key={i}
               className={`flex-1 h-6 rounded text-xs flex items-center justify-center font-bold
                          ${set ? bar + ' text-black' : 'bg-zinc-700 text-zinc-500'}`}>
            {i + 1}
          </div>
        ))}
      </div>
    </div>
  )
}
```

---

## Task 4: `Crossfader` component

File: `ui/src/components/Crossfader.jsx`

```jsx
export function Crossfader({ value }) {
  const pct = value * 100
  return (
    <div className="px-4 py-2 bg-zinc-900 rounded-xl">
      <div className="text-xs text-zinc-500 mb-1">CROSSFADER</div>
      <div className="relative h-4 bg-zinc-700 rounded">
        {/* Center zone highlight */}
        <div className="absolute h-full bg-zinc-600 rounded" style={{ left: '45%', width: '10%' }} />
        {/* Fader knob */}
        <div className="absolute top-0 w-4 h-full bg-white rounded"
             style={{ left: `calc(${pct}% - 8px)` }} />
      </div>
      <div className="flex justify-between text-xs text-zinc-600 mt-1">
        <span>A</span><span>B</span>
      </div>
    </div>
  )
}
```

---

## Task 5: `EffectsPanel` component

File: `ui/src/components/EffectsPanel.jsx`

```jsx
export function EffectsPanel({ gyroEnabled, wetDry, parameter, rollBinding, pitchBinding }) {
  return (
    <div className="px-4 py-2 bg-zinc-900 rounded-xl flex gap-6 items-center">
      <div className={`text-xs font-bold px-2 py-1 rounded ${gyroEnabled ? 'bg-green-700' : 'bg-zinc-700'}`}>
        GYRO {gyroEnabled ? 'ON' : 'OFF'}
      </div>
      <div className="flex flex-col gap-1 flex-1">
        <div className="text-xs text-zinc-500">
          Roll → Unit {rollBinding.unit + 1} / {rollBinding.target}
        </div>
        <div className="h-2 bg-zinc-700 rounded">
          <div className="h-full bg-green-500 rounded" style={{ width: `${wetDry * 100}%` }} />
        </div>
      </div>
      <div className="flex flex-col gap-1 flex-1">
        <div className="text-xs text-zinc-500">
          Pitch → Unit {pitchBinding.unit + 1} / {pitchBinding.target}
        </div>
        <div className="h-2 bg-zinc-700 rounded">
          <div className="h-full bg-purple-500 rounded" style={{ width: `${parameter * 100}%` }} />
        </div>
      </div>
    </div>
  )
}
```

---

## Task 6: `Library` component

File: `ui/src/components/Library.jsx`

Shows the two currently loaded tracks, one per deck.

```jsx
export function Library({ deckA, deckB }) {
  return (
    <div className="px-4 py-2 bg-zinc-900 rounded-xl">
      <div className="text-xs text-zinc-500 mb-2">LOADED TRACKS</div>
      <div className="flex flex-col gap-1">
        <div className="flex gap-2 text-xs">
          <span className="text-cyan-400 w-8">DECK A</span>
          <span className="text-white">{deckA.track_title || 'Empty'}</span>
          <span className="text-zinc-400 ml-auto">{deckA.track_artist}</span>
        </div>
        <div className="flex gap-2 text-xs">
          <span className="text-fuchsia-400 w-8">DECK B</span>
          <span className="text-white">{deckB.track_title || 'Empty'}</span>
          <span className="text-zinc-400 ml-auto">{deckB.track_artist}</span>
        </div>
      </div>
    </div>
  )
}
```

---

## Task 7: `ControllerMap` component

File: `ui/src/components/ControllerMap.jsx`

Shows current mode labels. No SVG silhouette needed for v1 — a clean text legend is sufficient.

```jsx
export function ControllerMap({ eqMode, gyroEnabled }) {
  const stickLabel = eqMode ? 'EQ Low / High' : 'Filter / Nudge'
  return (
    <div className="px-4 py-2 bg-zinc-900 rounded-xl text-xs">
      <div className="flex justify-between mb-1">
        <span className={`font-bold px-2 py-0.5 rounded ${eqMode ? 'bg-orange-700' : 'bg-zinc-700'}`}>
          {eqMode ? 'EQ MODE' : 'NORMAL MODE'}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-zinc-400">
        <span>L2/R2</span><span className="text-white">Volume A/B</span>
        <span>L1/R1</span><span className="text-white">Play/Pause A/B</span>
        <span>Sticks</span><span className="text-white">{stickLabel}</span>
        <span>D-Pad</span><span className="text-white">Hot Cues A 1-4</span>
        <span>△○✕□</span><span className="text-white">Hot Cues B 1-4</span>
        <span>Touchpad H</span><span className="text-white">Crossfader</span>
        <span>Touchpad V</span><span className="text-white">{eqMode ? 'EQ Band (zone)' : 'Browse'}</span>
        <span>Mute</span><span className={gyroEnabled ? 'text-green-400' : 'text-white'}>
          Gyro {gyroEnabled ? 'ON' : 'OFF'}
        </span>
        <span>Options</span><span className="text-white">EQ Mode (hold)</span>
        <span>Create</span><span className="text-white">Loop Toggle</span>
      </div>
    </div>
  )
}
```

---

## Task 8: `App.jsx` — wire everything together

File: `ui/src/App.jsx`

```jsx
import { useWebSocket } from './hooks/useWebSocket'
import { DeckDisplay } from './components/DeckDisplay'
import { Crossfader } from './components/Crossfader'
import { EffectsPanel } from './components/EffectsPanel'
import { ControllerMap } from './components/ControllerMap'
import { Library } from './components/Library'

const WS_URL = `ws://${window.location.hostname}:8765/ws`

export default function App() {
  const { state, connected } = useWebSocket(WS_URL)

  return (
    <div className="min-h-screen bg-zinc-950 text-white p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold tracking-widest">DUALSENSE DJ</h1>
        <span className={`text-xs px-2 py-1 rounded ${connected ? 'bg-green-800' : 'bg-red-900'}`}>
          {connected ? 'CONNECTED' : 'DISCONNECTED'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <DeckDisplay deck={state.deck_a} label="A" color="cyan" />
        <DeckDisplay deck={state.deck_b} label="B" color="magenta" />
      </div>

      <Crossfader value={state.crossfader} />

      <EffectsPanel
        gyroEnabled={state.gyro_enabled}
        wetDry={state.effect_wet_dry}
        parameter={state.effect_parameter}
        rollBinding={state.gyro_roll_binding}
        pitchBinding={state.gyro_pitch_binding}
      />

      <div className="grid grid-cols-2 gap-3">
        <ControllerMap eqMode={state.eq_mode} gyroEnabled={state.gyro_enabled} />
        <Library deckA={state.deck_a} deckB={state.deck_b} />
      </div>
    </div>
  )
}
```

---

## Task 9: Build for production

```bash
cd ui
npm run build
```

Expected: `ui/dist/` created with `index.html` and assets.

Then test the production build is served by the Python server:
```bash
cd ..
python src/main.py
```

Open `http://127.0.0.1:8765` — the UI should load and connect to the WebSocket.
