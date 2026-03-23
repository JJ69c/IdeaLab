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
    <div className="flex items-center gap-4">
      <h2 className="font-semibold text-on-surface truncate max-w-xs tracking-tight">
        {ideaTitle || 'Simulation'}
      </h2>
      <div className="flex items-center gap-3 flex-1">
        <span className="text-xs text-outline whitespace-nowrap font-medium">
          Round {currentTick}/{maxTicks}
        </span>
        <div className="flex-1 bg-surface-container-high rounded-full h-2 max-w-xs overflow-hidden">
          <div
            className="bg-gradient-to-r from-primary to-primary-container h-2 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        {narrative && (
          <span className="text-xs text-on-surface-variant truncate max-w-md" title={narrative}>
            {narrative}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <span className={`inline-block w-2 h-2 rounded-full ${
          isComplete ? 'bg-green-500' : isRunning ? 'bg-primary animate-pulse' : 'bg-outline-variant'
        }`} />
        <span className="text-xs text-on-surface-variant font-medium">
          {isComplete ? 'Complete' : isRunning ? 'Live' : 'Waiting'}
        </span>
      </div>
    </div>
  )
}
