import { useMemo } from 'react'
import type { SimEvent } from '../types'
import { computeRoundSummaryData } from '../types'

interface Props {
  events: SimEvent[]
  currentTick: number
}

export default function RoundSummaryCard({ events, currentTick }: Props) {
  const summary = useMemo(
    () => computeRoundSummaryData(events, currentTick),
    [events, currentTick],
  )

  if (currentTick === 0) return null

  return (
    <div className="mx-3 mt-2 glass-panel border border-white/40 rounded-2xl px-5 py-3 shadow-sm">
      <p className="text-sm font-semibold text-on-surface">{summary.headline}</p>
      <div className="flex items-center gap-4 mt-1.5 text-xs text-on-surface-variant flex-wrap">
        {summary.newAware > 0 && (
          <span className="flex items-center gap-1">
            <span className="material-symbols-outlined text-[14px] text-primary">visibility</span>
            {summary.newAware} newly aware
          </span>
        )}
        {summary.discussions > 0 && (
          <span className="flex items-center gap-1">
            <span className="material-symbols-outlined text-[14px] text-secondary">forum</span>
            {summary.discussions} discussion{summary.discussions !== 1 ? 's' : ''}
          </span>
        )}
        {summary.positiveShifts > 0 && (
          <span className="text-green-600 font-medium">+{summary.positiveShifts} positive shift{summary.positiveShifts !== 1 ? 's' : ''}</span>
        )}
        {summary.negativeShifts > 0 && (
          <span className="text-error font-medium">+{summary.negativeShifts} negative shift{summary.negativeShifts !== 1 ? 's' : ''}</span>
        )}
        {summary.avgDelta !== 0 && (
          <span className={summary.avgDelta > 0 ? 'text-green-600 font-medium' : 'text-error font-medium'}>
            avg {summary.avgDelta > 0 ? '+' : ''}{(summary.avgDelta * 100).toFixed(0)}% per discussion
          </span>
        )}
      </div>
      {summary.keyPoints.length > 0 && (
        <div className="flex gap-2 mt-2.5 flex-wrap">
          {summary.keyPoints.map((kp, i) => (
            <span key={i} className="text-[10px] bg-surface-container-low text-on-surface-variant px-2.5 py-1 rounded-lg border border-outline-variant/20">
              "{kp}"
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
