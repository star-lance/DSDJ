import { useWebSocket } from './hooks/useWebSocket'
import { DeckDisplay } from './components/DeckDisplay'
import { Crossfader } from './components/Crossfader'
import { EffectsPanel } from './components/EffectsPanel'
import { ControllerMap } from './components/ControllerMap'
import { Library } from './components/Library'
import { MacroEditor } from './components/MacroEditor'

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
        <DeckDisplay deck={state.deck_b} label="B" color="fuchsia" />
      </div>

      <Crossfader value={state.crossfader} />

      <EffectsPanel
        gyroEnabled={state.gyro_enabled}
        wetDry={state.effect_wet_dry}
        parameter={state.effect_parameter}
        rollBinding={state.gyro_roll_binding}
        pitchBinding={state.gyro_pitch_binding}
      />

      <MacroEditor macroA={state.macro_a ?? []} macroB={state.macro_b ?? []} />

      <div className="grid grid-cols-2 gap-3">
        <ControllerMap eqMode={state.eq_mode} gyroEnabled={state.gyro_enabled} />
        <Library deckA={state.deck_a} deckB={state.deck_b} />
      </div>
    </div>
  )
}
