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
