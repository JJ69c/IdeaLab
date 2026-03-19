import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'

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
    metrics_delta: Record<string, number>
    parent_top_objections: { objection: string; frequency: number; severity: string }[]
    variant_top_objections: { objection: string; frequency: number; severity: string }[]
    parent_segments: { name: string; size: number; typical_reaction: string }[]
    variant_segments: { name: string; size: number; typical_reaction: string }[]
    parent_adoption_likelihood: string | null
    variant_adoption_likelihood: string | null
  }
}

const FIELD_LABELS: Record<string, string> = {
  title: 'Idea Name',
  description: 'Description',
  category: 'Category',
  stage: 'Stage',
  target_audience: 'Target Audience',
  problem_statement: 'Problem Statement',
  price_point: 'Pricing',
  existing_alternatives: 'Alternatives',
  differentiator: 'Differentiator',
  known_strengths: 'Strengths',
  known_risks: 'Risks',
  num_ticks: 'Rounds',
  population_size: 'Population',
  seed_count: 'Initial Exposure',
}

const METRIC_LABELS: Record<string, string> = {
  awareness_rate: 'Awareness',
  interest_rate: 'Interest',
  rejection_rate: 'Rejection',
  viral_coefficient: 'Viral Coeff.',
  net_sentiment: 'Net Sentiment',
  would_pay_rate: 'Would Pay',
  adoption_likelihood: 'Adoption',
}

function getFieldValue(
  field: string,
  data: CompareData,
  side: 'parent' | 'variant',
): string {
  const src = data[side]
  // Top-level idea fields
  if (field === 'title') return src.idea_title
  // Config fields
  if (['num_ticks', 'population_size', 'seed_count'].includes(field)) {
    return String(src.config?.[field] ?? '')
  }
  // Metadata fields
  return String(src.idea_metadata?.[field] ?? '')
}

function DeltaArrow({ value, isRate }: { value: number; isRate: boolean }) {
  if (Math.abs(value) < 0.001) {
    return <span className="text-gray-400 text-xs">no change</span>
  }
  const positive = value > 0
  const display = isRate
    ? `${positive ? '+' : ''}${(value * 100).toFixed(1)}pp`
    : `${positive ? '+' : ''}${value.toFixed(2)}`
  return (
    <span className={`text-sm font-medium ${positive ? 'text-green-600' : 'text-red-500'}`}>
      {positive ? '\u2191' : '\u2193'} {display}
    </span>
  )
}

export default function Compare() {
  const { variantId } = useParams<{ variantId: string }>()
  const [data, setData] = useState<CompareData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!variantId) return

    // First get the variant to find parent ID
    fetch(`/api/simulations/${variantId}`)
      .then(r => r.json())
      .then(variant => {
        if (!variant.parent_simulation_id) {
          setError('This simulation is not a variant')
          setLoading(false)
          return
        }
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

  if (loading) return <p className="text-gray-500">Loading comparison...</p>
  if (error) return <p className="text-red-500">{error}</p>
  if (!data) return <p className="text-red-500">No comparison data available</p>

  const rateMetrics = ['awareness_rate', 'interest_rate', 'rejection_rate', 'would_pay_rate', 'adoption_likelihood']

  // Generate a verdict
  const interestDelta = data.diff.metrics_delta.interest_rate ?? 0
  const adoptionDelta = data.diff.metrics_delta.adoption_likelihood ?? 0
  const changedLabels = data.diff.changed_fields
    .map(f => FIELD_LABELS[f] || f)
    .join(', ')
  let verdict = ''
  if (interestDelta > 0.05) {
    verdict = `Changing ${changedLabels} improved interest by ${(interestDelta * 100).toFixed(0)} percentage points.`
  } else if (interestDelta < -0.05) {
    verdict = `Changing ${changedLabels} decreased interest by ${(Math.abs(interestDelta) * 100).toFixed(0)} percentage points.`
  } else if (adoptionDelta > 0.05) {
    verdict = `Changing ${changedLabels} improved adoption likelihood by ${(adoptionDelta * 100).toFixed(0)} percentage points.`
  } else if (adoptionDelta < -0.05) {
    verdict = `Changing ${changedLabels} decreased adoption likelihood by ${(Math.abs(adoptionDelta) * 100).toFixed(0)} percentage points.`
  } else {
    verdict = `Changing ${changedLabels} had minimal impact on key metrics.`
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <Link to={`/report/${variantId}`} className="text-indigo-600 text-sm">
          &larr; Back to Report
        </Link>
        <div className="flex items-center gap-4 mt-2">
          <h1 className="text-2xl font-bold">Comparison</h1>
          {data.variant.variant_name && (
            <span className="bg-indigo-100 text-indigo-700 px-3 py-1 rounded-full text-sm font-medium">
              {data.variant.variant_name}
            </span>
          )}
        </div>
        <p className="text-sm text-gray-500 mt-1">
          <Link to={`/report/${data.parent.id}`} className="text-indigo-600 hover:underline">
            {data.parent.idea_title}
          </Link>
          {' '}&rarr;{' '}
          <Link to={`/report/${data.variant.id}`} className="text-indigo-600 hover:underline">
            {data.variant.idea_title}
          </Link>
        </p>
      </div>

      {/* What Changed */}
      {data.diff.changed_fields.length > 0 && (
        <section className="bg-white rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-4">What Changed</h2>
          <div className="space-y-3">
            {data.diff.changed_fields.map(field => {
              const oldVal = getFieldValue(field, data, 'parent')
              const newVal = getFieldValue(field, data, 'variant')
              return (
                <div key={field} className="border rounded-lg p-3">
                  <div className="text-xs text-gray-400 font-medium uppercase mb-1">
                    {FIELD_LABELS[field] || field}
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-xs text-gray-400">Before:</span>
                      <p className="text-gray-600 line-through">{oldVal || '(empty)'}</p>
                    </div>
                    <div>
                      <span className="text-xs text-gray-400">After:</span>
                      <p className="text-gray-900 font-medium">{newVal || '(empty)'}</p>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* Metrics Comparison */}
      <section className="bg-white rounded-lg border p-6">
        <h2 className="text-lg font-semibold mb-4">Metrics Comparison</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {Object.entries(METRIC_LABELS).map(([key, label]) => {
            const pVal = data.parent.metrics[key]
            const vVal = data.variant.metrics[key]
            const delta = data.diff.metrics_delta[key] ?? 0
            const isRate = rateMetrics.includes(key)
            if (pVal === undefined && vVal === undefined) return null
            return (
              <div key={key} className="border rounded-lg p-3 text-center">
                <div className="text-xs text-gray-400 uppercase mb-2">{label}</div>
                <div className="flex justify-center gap-3 items-baseline">
                  <span className="text-gray-500 text-sm">
                    {isRate ? `${((pVal ?? 0) * 100).toFixed(0)}%` : (pVal ?? 0).toFixed(2)}
                  </span>
                  <span className="text-gray-300">&rarr;</span>
                  <span className="text-gray-900 font-semibold">
                    {isRate ? `${((vVal ?? 0) * 100).toFixed(0)}%` : (vVal ?? 0).toFixed(2)}
                  </span>
                </div>
                <div className="mt-1">
                  <DeltaArrow value={delta} isRate={isRate} />
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* Objections Comparison */}
      {(data.diff.parent_top_objections.length > 0 || data.diff.variant_top_objections.length > 0) && (
        <section className="bg-white rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-4">Top Objections</h2>
          <div className="grid grid-cols-2 gap-6">
            <div>
              <h3 className="text-sm font-medium text-gray-500 mb-2">Original</h3>
              <div className="space-y-2">
                {data.diff.parent_top_objections.map((obj, i) => (
                  <div key={i} className="text-sm">
                    <span className={`text-xs px-1.5 py-0.5 rounded mr-2 ${
                      obj.severity === 'high' ? 'bg-red-100 text-red-700' :
                      obj.severity === 'medium' ? 'bg-yellow-100 text-yellow-700' :
                      'bg-gray-100 text-gray-600'
                    }`}>{obj.severity}</span>
                    {obj.objection}
                    <span className="text-gray-400 text-xs ml-1">({obj.frequency})</span>
                  </div>
                ))}
                {data.diff.parent_top_objections.length === 0 && (
                  <p className="text-sm text-gray-400">No objections</p>
                )}
              </div>
            </div>
            <div>
              <h3 className="text-sm font-medium text-gray-500 mb-2">Variant</h3>
              <div className="space-y-2">
                {data.diff.variant_top_objections.map((obj, i) => (
                  <div key={i} className="text-sm">
                    <span className={`text-xs px-1.5 py-0.5 rounded mr-2 ${
                      obj.severity === 'high' ? 'bg-red-100 text-red-700' :
                      obj.severity === 'medium' ? 'bg-yellow-100 text-yellow-700' :
                      'bg-gray-100 text-gray-600'
                    }`}>{obj.severity}</span>
                    {obj.objection}
                    <span className="text-gray-400 text-xs ml-1">({obj.frequency})</span>
                  </div>
                ))}
                {data.diff.variant_top_objections.length === 0 && (
                  <p className="text-sm text-gray-400">No objections</p>
                )}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Segments Comparison */}
      {(data.diff.parent_segments.length > 0 || data.diff.variant_segments.length > 0) && (
        <section className="bg-white rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-4">Segments</h2>
          <div className="grid grid-cols-2 gap-6">
            <div>
              <h3 className="text-sm font-medium text-gray-500 mb-2">Original</h3>
              <div className="space-y-2">
                {data.diff.parent_segments.map((seg, i) => (
                  <div key={i} className="border rounded p-2 text-sm">
                    <div className="font-medium">{seg.name} <span className="text-gray-400 text-xs">({seg.size})</span></div>
                    <p className="text-gray-500 text-xs mt-1">{seg.typical_reaction}</p>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h3 className="text-sm font-medium text-gray-500 mb-2">Variant</h3>
              <div className="space-y-2">
                {data.diff.variant_segments.map((seg, i) => (
                  <div key={i} className="border rounded p-2 text-sm">
                    <div className="font-medium">{seg.name} <span className="text-gray-400 text-xs">({seg.size})</span></div>
                    <p className="text-gray-500 text-xs mt-1">{seg.typical_reaction}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Verdict */}
      <section className="bg-gradient-to-r from-indigo-50 to-purple-50 rounded-lg border border-indigo-200 p-6">
        <h2 className="text-lg font-semibold mb-2">Verdict</h2>
        <p className="text-gray-700">{verdict}</p>
        {data.diff.parent_adoption_likelihood && data.diff.variant_adoption_likelihood && (
          <p className="text-sm text-gray-500 mt-2">
            Adoption likelihood: {data.diff.parent_adoption_likelihood.replace(/_/g, ' ')} &rarr;{' '}
            {data.diff.variant_adoption_likelihood.replace(/_/g, ' ')}
          </p>
        )}
      </section>
    </div>
  )
}
