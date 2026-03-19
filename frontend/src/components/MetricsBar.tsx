import type { SimMetrics } from '../types'

interface Props {
  metrics: SimMetrics | null
  previousMetrics: SimMetrics | null
}

interface MetricDef {
  key: keyof SimMetrics
  label: string
  format: (v: number) => string
}

const METRIC_DEFS: MetricDef[] = [
  { key: 'awareness_rate', label: 'Awareness', format: v => `${(v * 100).toFixed(0)}%` },
  { key: 'interest_rate', label: 'Interest', format: v => `${(v * 100).toFixed(0)}%` },
  { key: 'rejection_rate', label: 'Rejection', format: v => `${(v * 100).toFixed(0)}%` },
  { key: 'viral_coefficient', label: 'Viral Coeff', format: v => v.toFixed(2) },
  { key: 'net_sentiment', label: 'Sentiment', format: v => (v >= 0 ? '+' : '') + v.toFixed(2) },
  { key: 'would_pay_rate', label: 'Would Pay', format: v => `${(v * 100).toFixed(0)}%` },
  { key: 'adoption_likelihood', label: 'Adoption', format: v => `${(v * 100).toFixed(0)}%` },
]

function Delta({ current, previous, isPercent }: { current: number; previous: number; isPercent: boolean }) {
  const diff = current - previous
  if (Math.abs(diff) < 0.001) return null

  const formatted = isPercent
    ? `${diff > 0 ? '+' : ''}${(diff * 100).toFixed(0)}%`
    : `${diff > 0 ? '+' : ''}${diff.toFixed(2)}`

  return (
    <span className={`text-[10px] font-medium ml-1 ${diff > 0 ? 'text-green-500' : 'text-red-400'}`}>
      {formatted}
    </span>
  )
}

export default function MetricsBar({ metrics, previousMetrics }: Props) {
  if (!metrics) {
    return (
      <div className="flex gap-4 px-4 py-2.5 bg-gray-900 text-xs text-gray-500">
        Waiting for first round...
      </div>
    )
  }

  const percentKeys = new Set(['awareness_rate', 'interest_rate', 'rejection_rate', 'would_pay_rate', 'adoption_likelihood'])

  return (
    <div className="flex items-center gap-6 px-4 py-2.5 bg-gray-900 border-t border-gray-800">
      {METRIC_DEFS.map(({ key, label, format }) => {
        const val = metrics[key] ?? 0
        const prevVal = previousMetrics?.[key] ?? 0
        const hasPrev = previousMetrics !== null
        return (
          <div key={key} className="text-center">
            <div className="text-[10px] text-gray-500 uppercase tracking-wide">{label}</div>
            <div className="text-sm font-semibold text-gray-100">
              {format(val)}
              {hasPrev && <Delta current={val} previous={prevVal} isPercent={percentKeys.has(key as string)} />}
            </div>
          </div>
        )
      })}
      <div className="text-center ml-auto">
        <div className="text-[10px] text-gray-500 uppercase tracking-wide">Aware</div>
        <div className="text-sm font-semibold text-gray-100">
          {metrics.aware_count ?? 0}/{metrics.total_npcs ?? 0}
        </div>
      </div>
    </div>
  )
}
