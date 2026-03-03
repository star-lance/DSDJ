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
        <span className="text-xs text-zinc-400 ml-auto">{(deck.bpm ?? 0).toFixed(1)} BPM</span>
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
