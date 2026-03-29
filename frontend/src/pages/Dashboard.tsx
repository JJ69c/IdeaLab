import { useEffect, useMemo, useState } from 'react'
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
  root_simulation_id: string | null
  variant_name: string | null
  simulation_version: string
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

interface SimGroup {
  parent: SimSummary
  variants: SimSummary[]
}

export default function Dashboard() {
  const [sims, setSims] = useState<SimSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/simulations')
      .then(r => r.json())
      .then(data => { setSims(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!confirm('Delete this simulation? This cannot be undone.')) return
    setDeleting(id)
    try {
      const res = await fetch(`/api/simulations/${id}`, { method: 'DELETE' })
      if (res.ok) {
        setSims(prev => prev.filter(s => s.id !== id))
      }
    } finally {
      setDeleting(null)
    }
  }

  const [sortOrder, setSortOrder] = useState<'newest' | 'oldest'>('newest')

  // Build a lookup of sim id → title
  const titleMap: Record<string, string> = {}
  for (const sim of sims) {
    titleMap[sim.id] = sim.idea_title
  }

  // Flat grouping by root: all variants appear one level under their root simulation.
  const { groups, orphanVariants } = useMemo(() => {
    const gs: SimGroup[] = []
    const orphans: SimSummary[] = []

    // First pass: index root simulations (no parent)
    for (const sim of sims) {
      if (!sim.parent_simulation_id) {
        gs.push({ parent: sim, variants: [] })
      }
    }

    // Second pass: assign ALL variants flat under their root
    for (const sim of sims) {
      if (sim.parent_simulation_id) {
        const rootId = sim.root_simulation_id || sim.parent_simulation_id
        const group = gs.find(g => g.parent.id === rootId)
        if (group) {
          group.variants.push(sim)
        } else {
          orphans.push(sim)
        }
      }
    }

    // Sort groups by root's created_at
    const dir = sortOrder === 'newest' ? -1 : 1
    gs.sort((a, b) => dir * (new Date(a.parent.created_at).getTime() - new Date(b.parent.created_at).getTime()))

    // Sort variants within each group by created_at (latest first always)
    for (const g of gs) {
      g.variants.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    }

    // Sort orphans same as groups
    orphans.sort((a, b) => dir * (new Date(a.created_at).getTime() - new Date(b.created_at).getTime()))

    return { groups: gs, orphanVariants: orphans }
  }, [sims, sortOrder])

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
        <div className="flex items-center gap-3">
          {sims.length > 0 && (
            <button
              onClick={() => setSortOrder(prev => prev === 'newest' ? 'oldest' : 'newest')}
              className="flex items-center gap-1.5 text-sm text-on-surface-variant border border-outline-variant/30 px-3 py-2 rounded-lg hover:bg-surface-container transition-colors"
              title={`Sorted by ${sortOrder === 'newest' ? 'newest first' : 'oldest first'}`}
            >
              <span className="material-symbols-outlined text-[16px]">
                {sortOrder === 'newest' ? 'arrow_downward' : 'arrow_upward'}
              </span>
              {sortOrder === 'newest' ? 'Newest' : 'Oldest'}
            </button>
          )}
          <Link
            to="/inject"
            className="flex items-center gap-2 bg-gradient-to-r from-primary to-primary-container text-on-primary px-6 py-3 rounded-xl text-sm font-semibold shadow-xl shadow-primary/20 hover:scale-[0.98] active:scale-95 transition-transform"
          >
            <span className="material-symbols-outlined text-[18px]">add</span>
            Launch New
          </Link>
        </div>
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
        /* Grouped vertical stack */
        <div className="space-y-6">
          {/* Parent groups */}
          {groups.map(group => {
            const sim = group.parent
            const statusStyle = STATUS_STYLES[sim.status] ?? STATUS_STYLES.pending
            const isLive = sim.status === 'running'
            const isCompleted = sim.status === 'completed'
            const linkTo = isCompleted ? `/report/${sim.id}` : `/simulation/${sim.id}`

            const awareness = sim.metrics?.awareness_rate ?? 0
            const interest = sim.metrics?.interest_rate ?? 0
            const adoption = sim.metrics?.adoption_rate ?? 0

            return (
              <div key={sim.id} className="space-y-0">
                {/* Parent card — full width */}
                <div className="glass-panel rounded-3xl border border-white/40 shadow-sm hover:shadow-md hover:border-primary/15 transition-all group relative">
                  <div className="p-6">
                    {/* Top row: status badge + menu */}
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-lg ${statusStyle.bg} ${statusStyle.text}`}>
                          {statusStyle.label}
                        </span>
                        <span className={`text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-lg ${sim.simulation_version === 'v2' ? 'bg-purple-50 text-purple-700' : 'bg-slate-50 text-slate-500'}`}>
                          {sim.simulation_version?.toUpperCase() || 'V1'}
                        </span>
                      </div>
                      <button
                        onClick={(e) => handleDelete(sim.id, e)}
                        disabled={deleting === sim.id}
                        className="text-outline-variant hover:text-red-600 transition-colors opacity-0 group-hover:opacity-100 disabled:opacity-50"
                        title="Delete simulation"
                      >
                        <span className="material-symbols-outlined text-[20px]">
                          {deleting === sim.id ? 'hourglass_empty' : 'delete'}
                        </span>
                      </button>
                    </div>

                    {/* Title + date */}
                    <h3 className="text-xl font-bold text-on-surface tracking-tight mb-1">{sim.idea_title}</h3>
                    <p className="text-xs text-outline mb-4">Created on {formatDate(sim.created_at)}</p>

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

                {/* Variant cards — indented row below parent */}
                {group.variants.length > 0 && (
                  <div className="ml-6 pl-4 border-l-2 border-outline-variant/30 space-y-2 pt-2 pb-1">
                    {group.variants.map(variant => {
                      const vStatusStyle = STATUS_STYLES[variant.status] ?? STATUS_STYLES.pending
                      const vIsLive = variant.status === 'running'
                      const vIsCompleted = variant.status === 'completed'
                      const vLinkTo = vIsCompleted ? `/report/${variant.id}` : `/simulation/${variant.id}`

                      const vAwareness = variant.metrics?.awareness_rate ?? 0
                      const vInterest = variant.metrics?.interest_rate ?? 0
                      const vAdoption = variant.metrics?.adoption_rate ?? 0

                      return (
                        <div
                          key={variant.id}
                          className="glass-panel rounded-2xl border border-white/40 shadow-sm hover:shadow-md hover:border-primary/15 transition-all group relative"
                        >
                          <div className="px-5 py-3.5">
                            <div className="flex items-center gap-2 mb-2">
                              {/* Status badge */}
                              <span className={`text-[9px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-md ${vStatusStyle.bg} ${vStatusStyle.text}`}>
                                {vStatusStyle.label}
                              </span>
                              {/* Variant badge */}
                              <span className="text-[9px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-md bg-orange-50 text-orange-700">
                                {variant.variant_name || 'VARIANT'}
                              </span>
                              {/* Engine version badge */}
                              <span className={`text-[9px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-md ${variant.simulation_version === 'v2' ? 'bg-purple-50 text-purple-700' : 'bg-slate-50 text-slate-500'}`}>
                                {variant.simulation_version?.toUpperCase() || 'V1'}
                              </span>
                              {/* Metrics as compact text */}
                              {variant.metrics && (
                                <span className="text-[11px] text-on-surface-variant ml-2">
                                  Aware {Math.round(vAwareness * 100)}%
                                  <span className="mx-1 text-outline-variant/50">·</span>
                                  Interest {Math.round(vInterest * 100)}%
                                  <span className="mx-1 text-outline-variant/50">·</span>
                                  Adopt {Math.round(vAdoption * 100)}%
                                </span>
                              )}
                              {/* Spacer */}
                              <div className="flex-1" />
                              {/* Date */}
                              <span className="text-[10px] text-outline">{formatDate(variant.created_at)}</span>
                              {/* Delete button */}
                              <button
                                onClick={(e) => handleDelete(variant.id, e)}
                                disabled={deleting === variant.id}
                                className="text-outline-variant hover:text-red-600 transition-colors opacity-0 group-hover:opacity-100 disabled:opacity-50 ml-1"
                                title="Delete simulation"
                              >
                                <span className="material-symbols-outlined text-[17px]">
                                  {deleting === variant.id ? 'hourglass_empty' : 'delete'}
                                </span>
                              </button>
                              {/* Link */}
                              <Link
                                to={vLinkTo}
                                className="flex items-center gap-1 text-xs font-semibold text-primary hover:text-primary-container transition-colors ml-2"
                              >
                                {vIsCompleted ? 'View Results' : vIsLive ? 'Monitor' : 'View'}
                                <span className="material-symbols-outlined text-[14px]">
                                  {vIsLive ? 'stream' : 'arrow_forward'}
                                </span>
                              </Link>
                            </div>
                            {/* Variant idea title */}
                            <p className="text-sm font-semibold text-on-surface leading-snug">{variant.idea_title}</p>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}

          {/* Orphan variants — standalone at the end */}
          {orphanVariants.map(sim => {
            const statusStyle = STATUS_STYLES[sim.status] ?? STATUS_STYLES.pending
            const isLive = sim.status === 'running'
            const isCompleted = sim.status === 'completed'
            const linkTo = isCompleted ? `/report/${sim.id}` : `/simulation/${sim.id}`

            const awareness = sim.metrics?.awareness_rate ?? 0
            const interest = sim.metrics?.interest_rate ?? 0
            const adoption = sim.metrics?.adoption_rate ?? 0

            const parentTitle = titleMap[sim.parent_simulation_id!] ?? null

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
                      <span className="text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-lg bg-orange-50 text-orange-700">
                        {sim.variant_name || 'VARIANT'}
                      </span>
                      <span className={`text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-lg ${sim.simulation_version === 'v2' ? 'bg-purple-50 text-purple-700' : 'bg-slate-50 text-slate-500'}`}>
                        {sim.simulation_version?.toUpperCase() || 'V1'}
                      </span>
                    </div>
                    <button
                      onClick={(e) => handleDelete(sim.id, e)}
                      disabled={deleting === sim.id}
                      className="text-outline-variant hover:text-red-600 transition-colors opacity-0 group-hover:opacity-100 disabled:opacity-50"
                      title="Delete simulation"
                    >
                      <span className="material-symbols-outlined text-[20px]">
                        {deleting === sim.id ? 'hourglass_empty' : 'delete'}
                      </span>
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

                  {/* Metric bars */}
                  {sim.metrics && (
                    <div className="flex gap-5 mb-6">
                      <MetricBar label="Awareness" value={awareness} color="bg-primary" />
                      <MetricBar label="Interest" value={interest} color="bg-tertiary" />
                      <MetricBar label="Adoption" value={adoption} color="bg-secondary" />
                    </div>
                  )}

                  {/* Bottom row */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center">
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
