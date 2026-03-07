import { useState } from 'react'

const CONTROLS = ['filter', 'eq_low', 'eq_mid', 'eq_high', 'effect_wet_dry', 'effect_parameter', 'volume', 'crossfader']
const DECKS = ['A', 'B', 'both']

function BindingRow({ binding, onChange, onRemove }) {
  return (
    <div className="flex flex-col gap-1 p-2 bg-zinc-800 rounded-lg">
      <div className="flex gap-2 items-center">
        <select
          className="bg-zinc-700 text-xs rounded px-1 py-0.5 flex-1"
          value={binding.control}
          onChange={e => onChange({ ...binding, control: e.target.value })}
        >
          {CONTROLS.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select
          className="bg-zinc-700 text-xs rounded px-1 py-0.5 w-16"
          value={binding.deck}
          onChange={e => onChange({ ...binding, deck: e.target.value })}
        >
          {DECKS.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        <button
          className="text-zinc-500 hover:text-red-400 text-xs px-1"
          onClick={onRemove}
        >✕</button>
      </div>
      {[['min_val', 'MIN ←'], ['base', 'BASE ○'], ['max_val', '→ MAX']].map(([key, label]) => (
        <div key={key} className="flex items-center gap-2">
          <span className="text-xs text-zinc-500 w-14">{label}</span>
          <input
            type="range" min="0" max="1" step="0.01"
            className="flex-1 accent-cyan-400"
            value={binding[key]}
            onChange={e => onChange({ ...binding, [key]: parseFloat(e.target.value) })}
          />
          <span className="text-xs text-zinc-400 w-8 text-right">{binding[key].toFixed(2)}</span>
        </div>
      ))}
    </div>
  )
}

function MacroSlot({ label, bindings, onChange }) {
  function addBinding() {
    onChange([...bindings, { control: 'filter', deck: 'A', base: 0.5, min_val: 0.0, max_val: 1.0 }])
  }
  function updateBinding(i, updated) {
    onChange(bindings.map((b, idx) => idx === i ? updated : b))
  }
  function removeBinding(i) {
    onChange(bindings.filter((_, idx) => idx !== i))
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-zinc-400 tracking-widest">{label}</span>
        <button
          className="text-xs px-2 py-0.5 rounded bg-zinc-700 hover:bg-zinc-600"
          onClick={addBinding}
        >+ Add</button>
      </div>
      {bindings.length === 0 && (
        <div className="text-xs text-zinc-600 italic">No bindings — stick X has no effect</div>
      )}
      {bindings.map((b, i) => (
        <BindingRow
          key={i}
          binding={b}
          onChange={updated => updateBinding(i, updated)}
          onRemove={() => removeBinding(i)}
        />
      ))}
    </div>
  )
}

export function MacroEditor({ macroA, macroB }) {
  const [a, setA] = useState(macroA)
  const [b, setB] = useState(macroB)
  const [saved, setSaved] = useState(false)

  async function save() {
    await fetch('/macros', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ macro_a: a, macro_b: b }),
    })
    setSaved(true)
    setTimeout(() => setSaved(false), 1500)
  }

  return (
    <div className="px-4 py-3 bg-zinc-900 rounded-xl flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold tracking-widest text-zinc-300">STICK MACROS</span>
        <button
          className={`text-xs px-3 py-1 rounded font-bold transition-colors ${saved ? 'bg-green-700' : 'bg-cyan-700 hover:bg-cyan-600'}`}
          onClick={save}
        >
          {saved ? 'Saved ✓' : 'Apply'}
        </button>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <MacroSlot label="LEFT STICK X" bindings={a} onChange={setA} />
        <MacroSlot label="RIGHT STICK X" bindings={b} onChange={setB} />
      </div>
    </div>
  )
}
