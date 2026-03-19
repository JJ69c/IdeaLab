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
    <div className="mx-2 mt-2 bg-white border border-gray-200 rounded-lg px-4 py-2.5 shadow-sm">
      <p className="text-sm font-medium text-gray-800">{summary.headline}</p>
      <div className="flex items-center gap-4 mt-1.5 text-xs text-gray-500 flex-wrap">
        {summary.newAware > 0 && <span>{summary.newAware} newly aware</span>}
        {summary.discussions > 0 && <span>{summary.discussions} discussion{summary.discussions !== 1 ? 's' : ''}</span>}
        {summary.positiveShifts > 0 && (
          <span className="text-green-600">+{summary.positiveShifts} positive shift{summary.positiveShifts !== 1 ? 's' : ''}</span>
        )}
        {summary.negativeShifts > 0 && (
          <span className="text-red-500">+{summary.negativeShifts} negative shift{summary.negativeShifts !== 1 ? 's' : ''}</span>
        )}
        {summary.avgDelta !== 0 && (
          <span className={summary.avgDelta > 0 ? 'text-green-600' : 'text-red-500'}>
            avg {summary.avgDelta > 0 ? '+' : ''}{(summary.avgDelta * 100).toFixed(0)}% per discussion
          </span>
        )}
      </div>
      {summary.keyPoints.length > 0 && (
        <div className="flex gap-2 mt-2 flex-wrap">
          {summary.keyPoints.map((kp, i) => (
            <span key={i} className="text-[10px] bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
              "{kp}"
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
