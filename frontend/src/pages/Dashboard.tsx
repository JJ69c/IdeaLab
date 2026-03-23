import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

interface SimSummary {
  id: string
  idea_title: string
  status: string
  created_at: string
  metrics: {
    awareness_rate?: number
    interest_rate?: number
    adoption_rate?: number
  } | null
  parent_simulation_id: string | null
  variant_name: string | null
}

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  completed: { bg: 'bg-green-50', text: 'text-green-700', label: 'COMPLETED' },
  running:   { bg: 'bg-blue-50',  text: 'text-blue-700',  label: 'ACTIVE' },
  pending:   { bg: 'bg-amber-50', text: 'text-amber-700', label: 'PENDING' },
  failed:    { bg: 'bg-red-50',   text: 'text-red-700',   label: 'FAILED' },
}

const METRIC_HINTS: Record<string, string> = {
  Awareness: 'Percentage of the simulated population that has heard about the idea.',
  Interest: 'Of those aware, the share who are interested or curious.',
  Adoption: 'Share of aware people who would actually adopt: interested enough, trust it, can afford it, and willing to switch.',
}

function MetricBar({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.round(value * 100)
  const hint = METRIC_HINTS[label]
  return (
    <div className="flex-1">
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className="text-[10px] font-semibold text-outline uppercase tracking-widest">{label}</span>
        {hint && (
          <span className="relative group/tip">
            <span className="material-symbols-outlined text-[13px] text-outline-variant cursor-help">info</span>
            <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-3 py-2 rounded-xl text-[11px] leading-snug font-normal normal-case tracking-normal text-on-surface bg-surface-container-lowest border border-outline-variant/20 shadow-lg w-48 text-center opacity-0 pointer-events-none group-hover/tip:opacity-100 group-hover/tip:pointer-events-auto transition-opacity z-10">
              {hint}
            </span>
          </span>
        )}
        <span className="text-sm font-bold text-on-surface ml-auto">{pct}%</span>
      </div>
      <div className="h-1.5 bg-surface-container-high rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' })
}

export default function Dashboard() {
  const [sims, setSims] = useState<SimSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/simulations')
      .then(r => r.json())
      .then(data => { setSims(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  // Build a lookup of sim id → title so variants can show their parent's name
  const titleMap: Record<string, string> = {}
  for (const sim of sims) {
    titleMap[sim.id] = sim.idea_title
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-outline gap-3">
        <span className="material-symbols-outlined text-[32px] animate-pulse">hourglass_empty</span>
        <span className="text-sm font-medium">Loading simulations...</span>
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="flex justify-between items-start mb-10">
        <div>
          <h1 className="text-3xl font-bold text-on-surface tracking-tight">Simulations</h1>
          <p className="text-on-surface-variant mt-1">Manage and monitor your active market experiments.</p>
        </div>
        <Link
          to="/inject"
          className="flex items-center gap-2 bg-gradient-to-r from-primary to-primary-container text-on-primary px-6 py-3 rounded-xl text-sm font-semibold shadow-xl shadow-primary/20 hover:scale-[0.98] active:scale-95 transition-transform"
        >
          <span className="material-symbols-outlined text-[18px]">add</span>
          Launch New
        </Link>
      </div>

      {sims.length === 0 ? (
        /* Empty state */
        <div className="flex flex-col items-center justify-center py-20">
          <div className="glass-panel border-2 border-dashed border-outline-variant/40 rounded-3xl p-12 text-center max-w-md">
            <span className="material-symbols-outlined text-[48px] text-outline-variant mb-4">add_circle</span>
            <h3 className="text-lg font-semibold text-on-surface mb-1">Start New Experiment</h3>
            <p className="text-sm text-on-surface-variant mb-6">Validate a new business hypothesis</p>
            <Link
              to="/inject"
              className="inline-flex items-center gap-2 bg-gradient-to-r from-primary to-primary-container text-on-primary px-6 py-3 rounded-xl text-sm font-semibold shadow-lg shadow-primary/20 hover:scale-[0.98] active:scale-95 transition-transform"
            >
              <span className="material-symbols-outlined text-[18px]">add</span>
              Launch New Simulation
            </Link>
          </div>
        </div>
      ) : (
        /* Cards grid */
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {sims.map(sim => {
            const statusStyle = STATUS_STYLES[sim.status] ?? STATUS_STYLES.pending
            const isLive = sim.status === 'running'
            const isCompleted = sim.status === 'completed'
            const linkTo = isCompleted ? `/report/${sim.id}` : `/simulation/${sim.id}`

            const awareness = sim.metrics?.awareness_rate ?? 0
            const interest = sim.metrics?.interest_rate ?? 0
            const adoption = sim.metrics?.adoption_rate ?? 0

            const parentTitle = sim.parent_simulation_id
              ? titleMap[sim.parent_simulation_id] ?? null
              : null

            return (
              <div
                key={sim.id}
                className="glass-panel rounded-3xl border border-white/40 shadow-sm hover:shadow-md hover:border-primary/15 transition-all group relative"
              >
                <div className="p-6">
                  {/* Top row: status badge + variant badge + menu */}
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-lg ${statusStyle.bg} ${statusStyle.text}`}>
                        {statusStyle.label}
                      </span>
                      {sim.parent_simulation_id && (
                        <span className="text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-lg bg-orange-50 text-orange-700">
                          {sim.variant_name || 'VARIANT'}
                        </span>
                      )}
                    </div>
                    <button className="text-outline-variant hover:text-on-surface transition-colors opacity-0 group-hover:opacity-100">
                      <span className="material-symbols-outlined text-[20px]">more_vert</span>
                    </button>
                  </div>

                  {/* Title + date */}
                  <h3 className="text-xl font-bold text-on-surface tracking-tight mb-1">{sim.idea_title}</h3>
                  <p className="text-xs text-outline mb-1">Created on {formatDate(sim.created_at)}</p>

                  {/* Variant lineage */}
                  {sim.parent_simulation_id && (
                    <div className="flex items-center gap-1.5 mb-4">
                      <span className="material-symbols-outlined text-[14px] text-orange-600">fork_right</span>
                      <span className="text-[11px] text-on-surface-variant">
                        Variant of{' '}
                        <Link
                          to={`/report/${sim.parent_simulation_id}`}
                          className="font-semibold text-primary hover:underline"
                        >
                          {parentTitle || 'parent simulation'}
                        </Link>
                      </span>
                    </div>
                  )}

                  {!sim.parent_simulation_id && <div className="mb-4" />}

                  {/* Metric bars */}
                  {sim.metrics && (
                    <div className="flex gap-5 mb-6">
                      <MetricBar label="Awareness" value={awareness} color="bg-primary" />
                      <MetricBar label="Interest" value={interest} color="bg-tertiary" />
                      <MetricBar label="Adoption" value={adoption} color="bg-secondary" />
                    </div>
                  )}

                  {/* Bottom row: avatars + action link */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center">
                      {/* NPC count indicator */}
                      <div className="w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center">
                        <span className="material-symbols-outlined text-[16px] text-on-surface-variant">group</span>
                      </div>
                    </div>
                    <Link
                      to={linkTo}
                      className="flex items-center gap-1.5 text-sm font-semibold text-primary hover:text-primary-container transition-colors"
                    >
                      {isCompleted ? 'View Results' : isLive ? 'Monitor Live' : 'View'}
                      <span className="material-symbols-outlined text-[16px]">
                        {isLive ? 'stream' : 'arrow_forward'}
                      </span>
                    </Link>
                  </div>
                </div>
              </div>
            )
          })}

        </div>
      )}
    </div>
  )
}
