import type { SimMetrics } from '../types'

interface Props {
  metrics: SimMetrics | null
  previousMetrics: SimMetrics | null
}

interface MetricDef {
  key: keyof SimMetrics
  label: string
  icon: string
  format: (v: number) => string
}

const METRIC_DEFS: MetricDef[] = [
  { key: 'awareness_rate', label: 'Awareness', icon: 'visibility', format: v => `${(v * 100).toFixed(0)}%` },
  { key: 'interest_rate', label: 'Interest', icon: 'favorite', format: v => `${(v * 100).toFixed(0)}%` },
  { key: 'rejection_rate', label: 'Rejection', icon: 'thumb_down', format: v => `${(v * 100).toFixed(0)}%` },
  { key: 'viral_coefficient', label: 'Viral Coeff', icon: 'share', format: v => v.toFixed(2) },
  { key: 'net_sentiment', label: 'Sentiment', icon: 'sentiment_satisfied', format: v => (v >= 0 ? '+' : '') + v.toFixed(2) },
  { key: 'would_pay_rate', label: 'Would Pay', icon: 'payments', format: v => `${(v * 100).toFixed(0)}%` },
  { key: 'adoption_rate', label: 'Adoption', icon: 'trending_up', format: v => `${(v * 100).toFixed(0)}%` },
]

function Delta({ current, previous, isPercent }: { current: number; previous: number; isPercent: boolean }) {
  const diff = current - previous
  if (Math.abs(diff) < 0.001) return null

  const formatted = isPercent
    ? `${diff > 0 ? '+' : ''}${(diff * 100).toFixed(0)}%`
    : `${diff > 0 ? '+' : ''}${diff.toFixed(2)}`

  return (
    <span className={`text-[10px] font-semibold ml-1 ${diff > 0 ? 'text-green-600' : 'text-error'}`}>
      {formatted}
    </span>
  )
}

export default function MetricsBar({ metrics, previousMetrics }: Props) {
  if (!metrics) {
    return (
      <div className="flex gap-4 px-5 py-3 glass-panel border-t border-outline-variant/30 text-xs text-outline">
        <span className="material-symbols-outlined text-[16px] animate-pulse">hourglass_empty</span>
        Waiting for first round...
      </div>
    )
  }

  const percentKeys = new Set(['awareness_rate', 'interest_rate', 'rejection_rate', 'would_pay_rate', 'adoption_rate'])

  return (
    <div className="flex items-center gap-1 px-4 py-2.5 glass-panel border-t border-outline-variant/30">
      {METRIC_DEFS.map(({ key, label, icon, format }) => {
        const val = metrics[key] ?? 0
        const prevVal = previousMetrics?.[key] ?? 0
        const hasPrev = previousMetrics !== null
        return (
          <div key={key} className="flex-1 text-center px-2 py-1.5 rounded-xl hover:bg-surface-container-low/50 transition-colors">
            <div className="flex items-center justify-center gap-1 mb-0.5">
              <span className="material-symbols-outlined text-[12px] text-outline">{icon}</span>
              <span className="text-[10px] text-outline uppercase tracking-widest font-semibold">{label}</span>
            </div>
            <div className="text-sm font-bold text-on-surface">
              {format(val)}
              {hasPrev && <Delta current={val} previous={prevVal} isPercent={percentKeys.has(key as string)} />}
            </div>
          </div>
        )
      })}
      <div className="text-center px-3 py-1.5 ml-auto border-l border-outline-variant/20">
        <div className="flex items-center justify-center gap-1 mb-0.5">
          <span className="material-symbols-outlined text-[12px] text-outline">group</span>
          <span className="text-[10px] text-outline uppercase tracking-widest font-semibold">Aware</span>
        </div>
        <div className="text-sm font-bold text-on-surface">
          {metrics.aware_count ?? 0}/{metrics.total_npcs ?? 0}
        </div>
      </div>
    </div>
  )
}
