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
