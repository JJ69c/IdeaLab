import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import QuickVariantDrawer from '../components/QuickVariantDrawer'

interface VariantSummary {
  id: string
  idea_title: string
  status: string
  variant_name: string | null
  metrics: Record<string, number> | null
  created_at: string
}

interface SimDetail {
  id: string
  idea_title: string
  idea_description: string
  idea_category: string
  idea_metadata: Record<string, string>
  config: Record<string, number>
  status: string
  metrics: Record<string, number> | null
  parent_simulation_id: string | null
  variant_name: string | null
  changed_fields: string[] | null
  report: {
    metrics: Record<string, number>
    analysis: {
      executive_summary: string
      adoption_likelihood: string
      adoption_explanation?: string
      segments: { name: string; size: number; typical_reaction: string; key_driver: string }[]
      top_objections: { objection: string; frequency: number; severity: string }[]
      viral_potential?: { score: number; explanation: string }
      recommendations: string[]
      risk_factors: string[]
    }
    npc_results: {
      npc_id: string; name: string; occupation: string; age: number
      interest_score: number; stance: string; reasoning: string
      objections: string[]; would_pay: boolean; would_recommend: boolean
      adopted?: boolean; adoption_score?: number; adoption_blockers?: string[]
    }[]
    adoption_breakdown?: {
      adoption_rate: number
      adopted_count: number
      aware_count: number
      top_blockers: { blocker: string; count: number }[]
    }
    asset_signals?: {
      perceived_polish: number
      trustworthiness: number
      clarity: number
      visual_appeal: number
      premium_feel: number
      usability_impression: number
      differentiation_signal: number
      summary: string
    }
  } | null
}

const STANCE_COLORS: Record<string, string> = {
  interested: '#22c55e',
  curious: '#84cc16',
  indifferent: '#9ca3af',
  skeptical: '#f59e0b',
  opposed: '#ef4444',
}

export default function Report() {
  const { id } = useParams<{ id: string }>()
  const [sim, setSim] = useState<SimDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [variants, setVariants] = useState<VariantSummary[]>([])
  const [parentTitle, setParentTitle] = useState<string | null>(null)
  const [quickVariantOpen, setQuickVariantOpen] = useState(false)

  useEffect(() => {
    if (!id) return
    fetch(`/api/simulations/${id}`)
      .then(r => r.json())
      .then(data => {
        setSim(data)
        setLoading(false)
        // Fetch parent title if this is a variant
        if (data.parent_simulation_id) {
          fetch(`/api/simulations/${data.parent_simulation_id}`)
            .then(r => r.json())
            .then(parent => setParentTitle(parent.idea_title))
            .catch(() => {})
        }
      })
      .catch(() => setLoading(false))
    // Fetch variants of this simulation
    fetch(`/api/simulations/${id}/variants`)
      .then(r => r.json())
      .then(data => setVariants(data))
      .catch(() => {})
  }, [id])

  if (loading) return <p className="text-gray-500">Loading report...</p>
  if (!sim) return <p className="text-red-500">Simulation not found</p>
  if (sim.status !== 'completed' || !sim.report) {
    return <p className="text-yellow-600">Simulation status: {sim.status}</p>
  }

  const { analysis, npc_results, metrics } = sim.report

  // Chart data: NPC interest scores sorted descending
  const chartData = [...npc_results]
    .sort((a, b) => b.interest_score - a.interest_score)
    .map(n => ({
      name: n.name.split(' ')[0],
      interest: Math.round(n.interest_score * 100),
      stance: n.stance,
    }))

  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <div className="flex items-center gap-4">
          <Link to="/dashboard" className="text-indigo-600 text-sm">&larr; Dashboard</Link>
          <h1 className="text-2xl font-bold flex-1">{sim.idea_title}</h1>
          <button
            onClick={() => setQuickVariantOpen(true)}
            className="flex items-center gap-1.5 text-sm border border-primary/30 text-primary px-4 py-2 rounded-lg hover:bg-primary/5 transition-all"
          >
            <span className="material-symbols-outlined text-[16px]">science</span>
            Quick Variant
          </button>
          <Link
            to={`/inject?variant_of=${id}`}
            className="text-sm border border-indigo-600 text-indigo-600 px-4 py-2 rounded-lg hover:bg-indigo-50"
          >
            Full Variant
          </Link>
          <Link
            to={`/simulation/${id}`}
            className="text-sm bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700"
          >
            View Simulation Map
          </Link>
        </div>

        {sim.parent_simulation_id && (
          <div className="flex items-center gap-3 text-sm">
            <span className="bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full text-xs font-medium">
              Variant{sim.variant_name ? `: ${sim.variant_name}` : ''}
            </span>
            <span className="text-gray-500">of</span>
            <Link
              to={`/report/${sim.parent_simulation_id}`}
              className="text-indigo-600 underline hover:text-indigo-800"
            >
              {parentTitle || 'Original simulation'}
            </Link>
            <Link
              to={`/compare/${id}`}
              className="ml-auto text-sm border border-green-600 text-green-700 px-3 py-1 rounded-lg hover:bg-green-50"
            >
              Compare with Original
            </Link>
          </div>
        )}
      </div>

      {/* Executive Summary */}
      <section className="bg-white rounded-lg border p-6">
        <h2 className="text-lg font-semibold mb-2">Executive Summary</h2>
        <p className="text-gray-700">{analysis.executive_summary}</p>
        <div className="mt-4 inline-block px-3 py-1 rounded-full text-sm font-medium bg-indigo-50 text-indigo-700">
          Adoption Likelihood: {analysis.adoption_likelihood?.replace(/_/g, ' ')}
        </div>
        {analysis.adoption_explanation && (
          <p className="text-sm text-gray-500 mt-2">{analysis.adoption_explanation}</p>
        )}
      </section>

      {/* Key Metrics */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Object.entries(metrics).filter(([k]) => !['total_npcs', 'aware_count'].includes(k)).map(([key, val]) => (
          <div key={key} className="bg-white rounded-lg border p-4 text-center">
            <div className="text-xs text-gray-400 uppercase">{key.replace(/_/g, ' ')}</div>
            <div className="text-2xl font-bold mt-1">
              {typeof val === 'number' ? (val <= 1 ? `${(val * 100).toFixed(0)}%` : val) : val}
            </div>
          </div>
        ))}
      </section>

      {/* Adoption Breakdown */}
      {sim.report.adoption_breakdown && (
        <section className="bg-white rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-4">Adoption Breakdown</h2>
          <div className="flex items-center gap-6 mb-4">
            <div className="text-center">
              <div className="text-3xl font-bold text-indigo-600">
                {(sim.report.adoption_breakdown.adoption_rate * 100).toFixed(0)}%
              </div>
              <div className="text-xs text-gray-400 uppercase mt-1">Adoption Rate</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold">
                {sim.report.adoption_breakdown.adopted_count}/{sim.report.adoption_breakdown.aware_count}
              </div>
              <div className="text-xs text-gray-400 uppercase mt-1">Adopted / Aware</div>
            </div>
          </div>
          {sim.report.adoption_breakdown.top_blockers.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-gray-600 mb-2">Top Barriers to Adoption</h3>
              <div className="space-y-2">
                {sim.report.adoption_breakdown.top_blockers.map((b, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <div className="flex-1">
                      <div className="flex justify-between text-sm mb-1">
                        <span>{b.blocker}</span>
                        <span className="text-gray-400">{b.count} NPCs</span>
                      </div>
                      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full bg-red-400"
                          style={{ width: `${(b.count / sim.report!.adoption_breakdown!.aware_count) * 100}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* Asset Signals */}
      {sim.report.asset_signals && (
        <section className="bg-white rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-2">Reference Asset Analysis</h2>
          <p className="text-sm text-gray-600 mb-4">{sim.report.asset_signals.summary}</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {([
              ['Polish', sim.report.asset_signals.perceived_polish],
              ['Trustworthiness', sim.report.asset_signals.trustworthiness],
              ['Clarity', sim.report.asset_signals.clarity],
              ['Visual Appeal', sim.report.asset_signals.visual_appeal],
              ['Premium Feel', sim.report.asset_signals.premium_feel],
              ['Usability', sim.report.asset_signals.usability_impression],
              ['Differentiation', sim.report.asset_signals.differentiation_signal],
            ] as [string, number][]).map(([label, value]) => (
              <div key={label} className="text-center">
                <div className="text-xs text-gray-400 uppercase mb-1">{label}</div>
                <div className="text-lg font-bold">{(value * 100).toFixed(0)}%</div>
                <div className="mt-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full bg-indigo-500"
                    style={{ width: `${value * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Interest Chart */}
      <section className="bg-white rounded-lg border p-6">
        <h2 className="text-lg font-semibold mb-4">NPC Interest Scores</h2>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData}>
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey="interest" radius={[4, 4, 0, 0]}>
              {chartData.map((entry, i) => (
                <Cell key={i} fill={STANCE_COLORS[entry.stance] || '#6366f1'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <div className="flex gap-4 mt-3 text-xs text-gray-500 justify-center">
          {Object.entries(STANCE_COLORS).map(([stance, color]) => (
            <div key={stance} className="flex items-center gap-1">
              <div className="w-3 h-3 rounded" style={{ backgroundColor: color }} />
              {stance}
            </div>
          ))}
        </div>
      </section>

      {/* Segments */}
      {analysis.segments?.length > 0 && (
        <section className="bg-white rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-4">User Segments</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {analysis.segments.map((seg, i) => (
              <div key={i} className="border rounded-lg p-4">
                <div className="flex justify-between items-start">
                  <h3 className="font-medium">{seg.name}</h3>
                  <span className="text-xs bg-gray-100 px-2 py-1 rounded">{seg.size} NPCs</span>
                </div>
                <p className="text-sm text-gray-600 mt-2">{seg.typical_reaction}</p>
                <p className="text-xs text-gray-400 mt-1">Driver: {seg.key_driver}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Objections */}
      {analysis.top_objections?.length > 0 && (
        <section className="bg-white rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-4">Top Objections</h2>
          <div className="space-y-3">
            {analysis.top_objections.map((obj, i) => (
              <div key={i} className="flex items-start gap-3">
                <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                  obj.severity === 'high' ? 'bg-red-100 text-red-700' :
                  obj.severity === 'medium' ? 'bg-yellow-100 text-yellow-700' :
                  'bg-gray-100 text-gray-600'
                }`}>
                  {obj.severity}
                </span>
                <div>
                  <p className="text-sm">{obj.objection}</p>
                  <p className="text-xs text-gray-400">{obj.frequency} NPCs raised this</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Recommendations */}
      {analysis.recommendations?.length > 0 && (
        <section className="bg-white rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-4">Recommendations</h2>
          <ul className="space-y-2">
            {analysis.recommendations.map((rec, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className="text-indigo-500 mt-0.5">&#10003;</span>
                {rec}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Individual NPC Results */}
      <section className="bg-white rounded-lg border p-6">
        <h2 className="text-lg font-semibold mb-4">Individual Reactions</h2>
        <div className="space-y-3">
          {npc_results
            .sort((a, b) => b.interest_score - a.interest_score)
            .map(npc => (
            <div key={npc.npc_id} className="border rounded-lg p-3">
              <div className="flex justify-between items-start">
                <div>
                  <span className="font-medium">{npc.name}</span>
                  <span className="text-gray-400 text-sm ml-2">{npc.occupation}, {npc.age}</span>
                </div>
                <div className="flex gap-2 items-center">
                  {npc.adopted !== undefined && (
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                      npc.adopted ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-500'
                    }`}>
                      {npc.adopted ? 'adopted' : 'not adopted'}
                    </span>
                  )}
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    npc.would_pay ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                  }`}>
                    {npc.would_pay ? 'would pay' : 'no pay'}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded" style={{
                    backgroundColor: (STANCE_COLORS[npc.stance] || '#6366f1') + '20',
                    color: STANCE_COLORS[npc.stance] || '#6366f1',
                  }}>
                    {npc.stance} ({Math.round(npc.interest_score * 100)}%)
                  </span>
                </div>
              </div>
              <p className="text-sm text-gray-600 mt-2">{npc.reasoning}</p>
              {npc.objections.length > 0 && (
                <div className="mt-2 flex gap-2 flex-wrap">
                  {npc.objections.map((obj, i) => (
                    <span key={i} className="text-xs bg-red-50 text-red-600 px-2 py-0.5 rounded">
                      {obj}
                    </span>
                  ))}
                </div>
              )}
              {npc.adoption_blockers && npc.adoption_blockers.length > 0 && (
                <div className="mt-2 flex gap-2 flex-wrap">
                  {npc.adoption_blockers.map((b, i) => (
                    <span key={i} className="text-xs bg-amber-50 text-amber-700 px-2 py-0.5 rounded">
                      {b}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Risk Factors */}
      {analysis.risk_factors?.length > 0 && (
        <section className="bg-white rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-4">Risk Factors</h2>
          <ul className="space-y-2">
            {analysis.risk_factors.map((risk, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                <span className="text-red-400 mt-0.5">!</span>
                {risk}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Variants */}
      {variants.length > 0 && (
        <section className="bg-white rounded-lg border p-6">
          <h2 className="text-lg font-semibold mb-4">Variants</h2>
          <div className="space-y-2">
            {variants.map(v => (
              <Link
                key={v.id}
                to={`/report/${v.id}`}
                className="block border rounded-lg p-3 hover:border-indigo-300 transition-colors"
              >
                <div className="flex justify-between items-center">
                  <div>
                    <span className="font-medium text-sm">{v.idea_title}</span>
                    {v.variant_name && (
                      <span className="ml-2 text-xs bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded">
                        {v.variant_name}
                      </span>
                    )}
                  </div>
                  <div className="flex gap-3 text-xs text-gray-500">
                    <span className={v.status === 'completed' ? 'text-green-600' : 'text-yellow-600'}>
                      {v.status}
                    </span>
                    {v.metrics && (
                      <span>
                        Interest: {((v.metrics.interest_rate ?? 0) * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Quick Variant Drawer */}
      <QuickVariantDrawer
        open={quickVariantOpen}
        onClose={() => setQuickVariantOpen(false)}
        parentSimulation={{
          id: sim.id,
          idea_title: sim.idea_title,
          idea_description: sim.idea_description,
          idea_category: sim.idea_category || 'general',
          idea_metadata: sim.idea_metadata || {},
          config: sim.config || {},
        }}
      />
    </div>
  )
}
