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
