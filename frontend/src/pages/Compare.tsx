import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ChangedFieldDetail {
  field: string
  label: string
  old_value: string
  new_value: string
}

interface AdoptionBreakdown {
  adoption_rate: number
  adopted_count: number
  aware_count: number
  top_blockers: { blocker: string; count: number }[]
}

interface ConvergenceData {
  final_state: {
    interest_stable: boolean
    polarization_score: number
    polarized: boolean
    result_class: string
    converged: boolean
    stability_streak: number
  }
  per_tick: unknown[]
}

interface ArchetypeEntry {
  archetype: string
  count: number
  mean_interest_parent: number
  mean_interest_variant: number
  interest_delta: number
  adoption_rate_parent?: number
  adoption_rate_variant?: number
  dominant_stance_parent?: string
  dominant_stance_variant?: string
}

interface CompareData {
  parent: {
    id: string
    idea_title: string
    metrics: Record<string, number>
    idea_metadata: Record<string, string>
    config: Record<string, number>
  }
  variant: {
    id: string
    idea_title: string
    metrics: Record<string, number>
    idea_metadata: Record<string, string>
    config: Record<string, number>
    variant_name: string | null
    changed_fields: string[]
  }
  diff: {
    changed_fields: string[]
    changed_fields_detail: ChangedFieldDetail[]
    metrics_delta: Record<string, number>
    parent_top_objections: { objection: string; frequency: number; severity: string }[]
    variant_top_objections: { objection: string; frequency: number; severity: string }[]
    parent_segments: { name: string; size: number; typical_reaction: string }[]
    variant_segments: { name: string; size: number; typical_reaction: string }[]
    parent_adoption_likelihood: string | null
    variant_adoption_likelihood: string | null
    parent_adoption_breakdown: AdoptionBreakdown | null
    variant_adoption_breakdown: AdoptionBreakdown | null
    parent_convergence: ConvergenceData | null
    variant_convergence: ConvergenceData | null
    archetype_comparison: ArchetypeEntry[]
  }
}

interface Explanation {
  verdict: string
  key_drivers: string[]
  segment_shifts: { segment: string; change: string; reason: string }[]
  recommendation: string
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const METRIC_LABELS: Record<string, string> = {
  awareness_rate: 'Awareness',
  interest_rate: 'Interest',
  rejection_rate: 'Rejection',
  viral_coefficient: 'Viral Coeff.',
  net_sentiment: 'Net Sentiment',
  would_pay_rate: 'Would Pay',
  adoption_rate: 'Adoption',
}

const RESULT_CLASS_STYLES: Record<string, { label: string; color: string }> = {
  stable_convergence: { label: 'Stable Convergence', color: 'text-green-700 bg-green-50' },
  stable_polarization: { label: 'Stable Polarization', color: 'text-amber-700 bg-amber-50' },
  unstable: { label: 'Unstable', color: 'text-red-700 bg-red-50' },
  noisy: { label: 'Noisy', color: 'text-purple-700 bg-purple-50' },
  unknown: { label: 'Unknown', color: 'text-outline bg-surface-container' },
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function DeltaArrow({ value, isRate }: { value: number; isRate: boolean }) {
  if (Math.abs(value) < 0.001) {
    return <span className="text-outline text-xs">no change</span>
  }
  const positive = value > 0
  const display = isRate
    ? `${positive ? '+' : ''}${(value * 100).toFixed(1)}pp`
    : `${positive ? '+' : ''}${value.toFixed(2)}`
  return (
    <span className={`text-sm font-semibold ${positive ? 'text-green-600' : 'text-red-500'}`}>
      {positive ? '\u2191' : '\u2193'} {display}
    </span>
  )
}

function SectionHeader({ icon, title }: { icon: string; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-5">
      <span className="material-symbols-outlined text-[20px] text-primary">{icon}</span>
      <h2 className="text-lg font-bold text-on-surface tracking-tight">{title}</h2>
    </div>
  )
}

function SideBySideHeader() {
  return (
    <div className="grid grid-cols-2 gap-6 mb-3">
      <h3 className="text-[10px] font-bold text-outline uppercase tracking-widest">Original</h3>
      <h3 className="text-[10px] font-bold text-outline uppercase tracking-widest">Variant</h3>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function Compare() {
  const { variantId } = useParams<{ variantId: string }>()
  const [data, setData] = useState<CompareData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [explanation, setExplanation] = useState<Explanation | null>(null)
  const [explaining, setExplaining] = useState(false)
  const [parentSimId, setParentSimId] = useState<string | null>(null)

  useEffect(() => {
    if (!variantId) return

    fetch(`/api/simulations/${variantId}`)
      .then(r => r.json())
      .then(variant => {
        if (!variant.parent_simulation_id) {
          setError('This simulation is not a variant')
          setLoading(false)
          return
        }
        setParentSimId(variant.parent_simulation_id)
        return fetch(
          `/api/simulations/${variant.parent_simulation_id}/compare/${variantId}`
        )
          .then(r => {
            if (!r.ok) throw new Error(`Failed to load comparison: ${r.status}`)
            return r.json()
          })
          .then(compareData => {
            setData(compareData)
            setLoading(false)
          })
      })
      .catch(err => {
        setError(err instanceof Error ? err.message : 'Failed to load')
        setLoading(false)
      })
  }, [variantId])

  const handleExplain = () => {
    if (!parentSimId || !variantId || explaining) return
    setExplaining(true)
    fetch(`/api/simulations/${parentSimId}/compare/${variantId}/explain`, {
      method: 'POST',
    })
      .then(r => {
        if (!r.ok) throw new Error(`Failed: ${r.status}`)
        return r.json()
      })
      .then(result => {
        setExplanation(result)
        setExplaining(false)
      })
      .catch(() => setExplaining(false))
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-outline gap-3">
        <span className="material-symbols-outlined text-[32px] animate-pulse">compare_arrows</span>
        <span className="text-sm font-medium">Loading comparison...</span>
      </div>
    )
  }
  if (error) return <p className="text-error">{error}</p>
  if (!data) return <p className="text-error">No comparison data available</p>

  const rateMetrics = ['awareness_rate', 'interest_rate', 'rejection_rate', 'would_pay_rate', 'adoption_rate']

  // Generate a verdict
  const interestDelta = data.diff.metrics_delta.interest_rate ?? 0
  const adoptionDelta = data.diff.metrics_delta.adoption_rate ?? 0
  const changedLabels = data.diff.changed_fields_detail
    .map(cf => cf.label)
    .join(', ')
  let verdict = ''
  if (interestDelta > 0.05) {
    verdict = `Changing ${changedLabels} improved interest by ${(interestDelta * 100).toFixed(0)} percentage points.`
  } else if (interestDelta < -0.05) {
    verdict = `Changing ${changedLabels} decreased interest by ${(Math.abs(interestDelta) * 100).toFixed(0)} percentage points.`
  } else if (adoptionDelta > 0.05) {
    verdict = `Changing ${changedLabels} improved adoption by ${(adoptionDelta * 100).toFixed(0)} percentage points.`
  } else if (adoptionDelta < -0.05) {
    verdict = `Changing ${changedLabels} decreased adoption by ${(Math.abs(adoptionDelta) * 100).toFixed(0)} percentage points.`
  } else {
    verdict = `Changing ${changedLabels || 'parameters'} had minimal impact on key metrics.`
  }

  const pAdoption = data.diff.parent_adoption_breakdown
  const vAdoption = data.diff.variant_adoption_breakdown
  const pConvergence = data.diff.parent_convergence?.final_state
  const vConvergence = data.diff.variant_convergence?.final_state

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="glass-panel rounded-3xl border border-white/40 p-6">
        <Link to={`/report/${variantId}`} className="inline-flex items-center gap-1 text-sm text-primary hover:underline mb-3">
          <span className="material-symbols-outlined text-[16px]">arrow_back</span>
          Back to Report
        </Link>
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold text-on-surface tracking-tight">Comparison</h1>
          {data.variant.variant_name && (
            <span className="text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-lg bg-orange-50 text-orange-700">
              {data.variant.variant_name}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-2 text-sm text-on-surface-variant">
          <Link to={`/report/${data.parent.id}`} className="text-primary hover:underline font-medium">
            {data.parent.idea_title}
          </Link>
          <span className="material-symbols-outlined text-[16px] text-outline">arrow_forward</span>
          <Link to={`/report/${data.variant.id}`} className="text-primary hover:underline font-medium">
            {data.variant.idea_title}
          </Link>
        </div>
      </div>

      {/* What Changed */}
      {data.diff.changed_fields_detail.length > 0 && (
        <section className="glass-panel rounded-3xl border border-white/40 p-6">
          <SectionHeader icon="difference" title="What Changed" />
          <div className="space-y-3">
            {data.diff.changed_fields_detail.map(cf => (
              <div key={cf.field} className="bg-surface-container-lowest border border-outline-variant/20 rounded-2xl p-4">
                <div className="text-[10px] font-bold text-outline uppercase tracking-widest mb-2">
                  {cf.label}
                </div>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-[10px] text-outline uppercase tracking-wider">Before</span>
                    <p className="text-on-surface-variant line-through mt-0.5">{cf.old_value || '(empty)'}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-outline uppercase tracking-wider">After</span>
                    <p className="text-on-surface font-medium mt-0.5">{cf.new_value || '(empty)'}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Metrics Comparison */}
      <section className="glass-panel rounded-3xl border border-white/40 p-6">
        <SectionHeader icon="monitoring" title="Metrics Comparison" />
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {Object.entries(METRIC_LABELS).map(([key, label]) => {
            const pVal = data.parent.metrics[key]
            const vVal = data.variant.metrics[key]
            const delta = data.diff.metrics_delta[key] ?? 0
            const isRate = rateMetrics.includes(key)
            if (pVal === undefined && vVal === undefined) return null
            return (
              <div key={key} className="bg-surface-container-lowest border border-outline-variant/20 rounded-2xl p-4 text-center">
                <div className="text-[10px] font-bold text-outline uppercase tracking-widest mb-3">{label}</div>
                <div className="flex justify-center gap-2 items-baseline">
                  <span className="text-on-surface-variant text-sm">
                    {isRate ? `${((pVal ?? 0) * 100).toFixed(0)}%` : (pVal ?? 0).toFixed(2)}
                  </span>
                  <span className="material-symbols-outlined text-[14px] text-outline">arrow_forward</span>
                  <span className="text-on-surface font-bold">
                    {isRate ? `${((vVal ?? 0) * 100).toFixed(0)}%` : (vVal ?? 0).toFixed(2)}
                  </span>
                </div>
                <div className="mt-2">
                  <DeltaArrow value={delta} isRate={isRate} />
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* Adoption Breakdown Comparison */}
      {(pAdoption || vAdoption) && (
        <section className="glass-panel rounded-3xl border border-white/40 p-6">
          <SectionHeader icon="how_to_reg" title="Adoption Breakdown" />
          <div className="grid grid-cols-2 gap-6">
            {[
              { label: 'Original', ab: pAdoption },
              { label: 'Variant', ab: vAdoption },
            ].map(({ label, ab }) => (
              <div key={label}>
                <h3 className="text-[10px] font-bold text-outline uppercase tracking-widest mb-3">{label}</h3>
                {ab ? (
                  <div className="space-y-3">
                    <div className="flex items-baseline gap-2">
                      <span className="text-2xl font-bold text-on-surface">{Math.round(ab.adoption_rate * 100)}%</span>
                      <span className="text-xs text-on-surface-variant">adopted ({ab.adopted_count}/{ab.aware_count} aware)</span>
                    </div>
                    {ab.top_blockers.length > 0 && (
                      <div className="space-y-1.5">
                        <span className="text-[10px] text-outline uppercase tracking-wider">Top Blockers</span>
                        {ab.top_blockers.slice(0, 4).map((b, i) => {
                          const maxCount = ab.top_blockers[0]?.count || 1
                          const pct = Math.round((b.count / maxCount) * 100)
                          return (
                            <div key={i} className="flex items-center gap-2">
                              <div className="flex-1">
                                <div className="flex justify-between text-xs mb-0.5">
                                  <span className="text-on-surface-variant">{b.blocker.replace(/_/g, ' ')}</span>
                                  <span className="text-on-surface font-medium">{b.count}</span>
                                </div>
                                <div className="h-1 bg-surface-container-high rounded-full overflow-hidden">
                                  <div className="h-full bg-error/60 rounded-full" style={{ width: `${pct}%` }} />
                                </div>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-outline">No adoption data</p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Archetype Impact */}
      {data.diff.archetype_comparison.length > 0 && (
        <section className="glass-panel rounded-3xl border border-white/40 p-6">
          <SectionHeader icon="groups" title="Archetype Impact" />
          <div className="space-y-2">
            {data.diff.archetype_comparison
              .sort((a, b) => Math.abs(b.interest_delta) - Math.abs(a.interest_delta))
              .map(arch => {
                const absDelta = Math.abs(arch.interest_delta)
                const isPositive = arch.interest_delta > 0
                return (
                  <div key={arch.archetype} className="bg-surface-container-lowest border border-outline-variant/20 rounded-2xl p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-semibold text-on-surface capitalize">
                          {arch.archetype.replace(/_/g, ' ')}
                        </span>
                        <span className="text-[10px] text-outline">n={arch.count}</span>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-right">
                          <span className="text-xs text-on-surface-variant">Interest</span>
                          <div className="flex items-center gap-1.5">
                            <span className="text-sm text-on-surface-variant">{Math.round(arch.mean_interest_parent * 100)}%</span>
                            <span className="material-symbols-outlined text-[12px] text-outline">arrow_forward</span>
                            <span className="text-sm font-semibold text-on-surface">{Math.round(arch.mean_interest_variant * 100)}%</span>
                          </div>
                        </div>
                        {arch.adoption_rate_parent !== undefined && arch.adoption_rate_variant !== undefined && (
                          <div className="text-right">
                            <span className="text-xs text-on-surface-variant">Adoption</span>
                            <div className="flex items-center gap-1.5">
                              <span className="text-sm text-on-surface-variant">{Math.round(arch.adoption_rate_parent * 100)}%</span>
                              <span className="material-symbols-outlined text-[12px] text-outline">arrow_forward</span>
                              <span className="text-sm font-semibold text-on-surface">{Math.round(arch.adoption_rate_variant * 100)}%</span>
                            </div>
                          </div>
                        )}
                        <div className={`text-sm font-bold ${absDelta < 0.01 ? 'text-outline' : isPositive ? 'text-green-600' : 'text-red-500'}`}>
                          {absDelta < 0.01 ? '~' : isPositive ? '\u2191' : '\u2193'}
                          {absDelta >= 0.01 ? ` ${(arch.interest_delta * 100).toFixed(0)}pp` : ''}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
          </div>
        </section>
      )}

      {/* Convergence */}
      {(pConvergence || vConvergence) && (
        <section className="glass-panel rounded-3xl border border-white/40 p-6">
          <SectionHeader icon="trending_flat" title="Convergence" />
          <div className="grid grid-cols-2 gap-6">
            {[
              { label: 'Original', conv: pConvergence },
              { label: 'Variant', conv: vConvergence },
            ].map(({ label, conv }) => {
              const style = RESULT_CLASS_STYLES[conv?.result_class || 'unknown'] || RESULT_CLASS_STYLES.unknown
              return (
                <div key={label}>
                  <h3 className="text-[10px] font-bold text-outline uppercase tracking-widest mb-3">{label}</h3>
                  {conv ? (
                    <div className="space-y-2">
                      <span className={`inline-block text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-lg ${style.color}`}>
                        {style.label}
                      </span>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <span className="text-outline">Polarization</span>
                          <p className="text-on-surface font-semibold">{(conv.polarization_score * 100).toFixed(0)}%</p>
                        </div>
                        <div>
                          <span className="text-outline">Stability</span>
                          <p className="text-on-surface font-semibold">{conv.stability_streak} ticks stable</p>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-outline">No convergence data</p>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* Objections Comparison */}
      {(data.diff.parent_top_objections.length > 0 || data.diff.variant_top_objections.length > 0) && (
        <section className="glass-panel rounded-3xl border border-white/40 p-6">
          <SectionHeader icon="report_problem" title="Top Objections" />
          <SideBySideHeader />
          <div className="grid grid-cols-2 gap-6">
            {[data.diff.parent_top_objections, data.diff.variant_top_objections].map((objections, side) => (
              <div key={side} className="space-y-2">
                {objections.map((obj, i) => (
                  <div key={i} className="text-sm flex items-start gap-2">
                    <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded flex-shrink-0 mt-0.5 ${
                      obj.severity === 'high' ? 'bg-red-50 text-red-700' :
                      obj.severity === 'medium' ? 'bg-amber-50 text-amber-700' :
                      'bg-surface-container text-outline'
                    }`}>{obj.severity}</span>
                    <span className="text-on-surface-variant">
                      {obj.objection}
                      <span className="text-outline text-xs ml-1">({obj.frequency})</span>
                    </span>
                  </div>
                ))}
                {objections.length === 0 && (
                  <p className="text-sm text-outline">No objections</p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Segments Comparison */}
      {(data.diff.parent_segments.length > 0 || data.diff.variant_segments.length > 0) && (
        <section className="glass-panel rounded-3xl border border-white/40 p-6">
          <SectionHeader icon="pie_chart" title="Segments" />
          <SideBySideHeader />
          <div className="grid grid-cols-2 gap-6">
            {[data.diff.parent_segments, data.diff.variant_segments].map((segments, side) => (
              <div key={side} className="space-y-2">
                {segments.map((seg, i) => (
                  <div key={i} className="bg-surface-container-lowest border border-outline-variant/20 rounded-xl p-3">
                    <div className="text-sm font-semibold text-on-surface">
                      {seg.name}
                      <span className="text-outline text-xs font-normal ml-1.5">({seg.size})</span>
                    </div>
                    <p className="text-xs text-on-surface-variant mt-1">{seg.typical_reaction}</p>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* AI Explanation */}
      <section className="glass-panel rounded-3xl border border-primary/20 p-6">
        <SectionHeader icon="psychology" title="AI Explanation" />
        {!explanation && !explaining && (
          <button
            onClick={handleExplain}
            className="flex items-center gap-2 bg-gradient-to-r from-primary to-primary-container text-on-primary px-5 py-2.5 rounded-xl text-sm font-semibold shadow-lg shadow-primary/20 hover:scale-[0.98] active:scale-95 transition-transform"
          >
            <span className="material-symbols-outlined text-[18px]">auto_awesome</span>
            Generate Explanation
          </button>
        )}
        {explaining && (
          <div className="flex items-center gap-3 text-on-surface-variant">
            <div className="w-5 h-5 border-2 border-primary/40 border-t-primary rounded-full animate-spin" />
            <span className="text-sm">Analyzing what drove the outcome difference...</span>
          </div>
        )}
        {explanation && (
          <div className="space-y-5">
            {/* Verdict */}
            <div className="bg-gradient-to-r from-primary/5 to-tertiary/5 rounded-2xl p-4 border border-primary/10">
              <p className="text-on-surface font-medium">{explanation.verdict}</p>
            </div>

            {/* Key Drivers */}
            {explanation.key_drivers.length > 0 && (
              <div>
                <h3 className="text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Key Drivers</h3>
                <div className="space-y-2">
                  {explanation.key_drivers.map((driver, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm text-on-surface-variant">
                      <span className="material-symbols-outlined text-[16px] text-primary mt-0.5 flex-shrink-0">arrow_right</span>
                      {driver}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Segment Shifts */}
            {explanation.segment_shifts.length > 0 && (
              <div>
                <h3 className="text-[10px] font-bold text-outline uppercase tracking-widest mb-2">Segment Shifts</h3>
                <div className="space-y-2">
                  {explanation.segment_shifts.map((shift, i) => (
                    <div key={i} className="bg-surface-container-lowest border border-outline-variant/20 rounded-xl p-3">
                      <div className="text-sm font-semibold text-on-surface">{shift.segment}</div>
                      <p className="text-xs text-on-surface-variant mt-0.5">{shift.change}</p>
                      <p className="text-xs text-outline mt-0.5">Why: {shift.reason}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recommendation */}
            {explanation.recommendation && (
              <div className="bg-surface-container-lowest border border-primary/15 rounded-2xl p-4">
                <div className="flex items-center gap-2 mb-1">
                  <span className="material-symbols-outlined text-[16px] text-primary">lightbulb</span>
                  <span className="text-[10px] font-bold text-primary uppercase tracking-widest">Recommendation</span>
                </div>
                <p className="text-sm text-on-surface">{explanation.recommendation}</p>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Verdict */}
      <section className="bg-gradient-to-r from-primary/5 to-tertiary/5 glass-panel rounded-3xl border border-primary/15 p-6">
        <SectionHeader icon="gavel" title="Verdict" />
        <p className="text-on-surface font-medium">{verdict}</p>
        {data.diff.parent_adoption_likelihood && data.diff.variant_adoption_likelihood && (
          <p className="text-sm text-on-surface-variant mt-2">
            Adoption likelihood: {data.diff.parent_adoption_likelihood.replace(/_/g, ' ')}
            <span className="material-symbols-outlined text-[14px] text-outline mx-1 align-middle">arrow_forward</span>
            {data.diff.variant_adoption_likelihood.replace(/_/g, ' ')}
          </p>
        )}
      </section>
    </div>
  )
}
