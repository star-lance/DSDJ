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
