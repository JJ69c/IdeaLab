import { useMemo } from 'react'
import type { SimEvent } from '../types'
import { computeRoundNarrative } from '../types'

interface Props {
  currentTick: number
  maxTicks: number
  isRunning: boolean
  isComplete: boolean
  ideaTitle: string
  events: SimEvent[]
}

export default function TickProgress({ currentTick, maxTicks, isRunning, isComplete, ideaTitle, events }: Props) {
  const pct = maxTicks > 0 ? (currentTick / maxTicks) * 100 : 0

  const narrative = useMemo(
    () => currentTick > 0 ? computeRoundNarrative(events, currentTick) : '',
    [events, currentTick],
  )

  return (
    <div className="flex items-center gap-4 bg-white border-b border-gray-200 px-4 py-2">
      <h2 className="font-semibold text-gray-800 truncate max-w-xs">
        {ideaTitle || 'Simulation'}
      </h2>
      <div className="flex items-center gap-2 flex-1">
        <span className="text-xs text-gray-400 whitespace-nowrap">
          Round {currentTick}/{maxTicks}
        </span>
        <div className="flex-1 bg-gray-100 rounded-full h-2 max-w-xs">
          <div
            className="bg-indigo-500 h-2 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        {narrative && (
          <span className="text-xs text-gray-500 truncate max-w-md" title={narrative}>
            {narrative}
          </span>
        )}
      </div>
      <div className="flex items-center gap-1.5">
        <span className={`inline-block w-2 h-2 rounded-full ${
          isComplete ? 'bg-green-500' : isRunning ? 'bg-indigo-500 animate-pulse' : 'bg-gray-300'
        }`} />
        <span className="text-xs text-gray-500">
          {isComplete ? 'Complete' : isRunning ? 'Live' : 'Waiting'}
        </span>
      </div>
    </div>
  )
}
