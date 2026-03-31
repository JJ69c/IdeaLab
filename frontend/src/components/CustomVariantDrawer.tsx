import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'

interface NpcInfo {
  npc_id: string
  name: string
  archetype?: string
}

interface CustomVariantDrawerProps {
  open: boolean
  onClose: () => void
  parentSimulation: {
    id: string
    idea_title: string
    idea_description: string
    idea_category: string
    idea_metadata: Record<string, string>
    config: Record<string, number>
    parent_simulation_id?: string | null
  }
  npcs: NpcInfo[]
  seedIds: Set<string>
}

const ARCHETYPE_SHORT: Record<string, string> = {
  analytical_skeptic: 'SKEPTIC',
  trend_adopter: 'TREND ADOPTER',
  price_pragmatist: 'PRICE PRAGMATIST',
  health_evaluator: 'HEALTH EVALUATOR',
  brand_buyer: 'BRAND BUYER',
  social_follower: 'SOCIAL FOLLOWER',
  convenience_user: 'CONVENIENCE USER',
  values_buyer: 'VALUES BUYER',
}

export default function CustomVariantDrawer({
  open, onClose, parentSimulation, npcs, seedIds,
}: CustomVariantDrawerProps) {
  const navigate = useNavigate()
  const config = parentSimulation.config || {}

  // State: which NPCs are in population and which are seeds
  const [populationIds, setPopulationIds] = useState<Set<string>>(() => new Set(npcs.map(n => n.npc_id)))
  const [customSeedIds, setCustomSeedIds] = useState<Set<string>>(() => new Set(seedIds))
  const [numTicks, setNumTicks] = useState(config.num_ticks ?? 8)
  const [variantName, setVariantName] = useState('')
  const [simulationVersion, setSimulationVersion] = useState<'v1' | 'v2'>('v1')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Sort NPCs: parent seeds first, then rest, all A-Z within groups
  const sortedNpcs = useMemo(() => {
    const seeds = npcs.filter(n => seedIds.has(n.npc_id)).sort((a, b) => a.name.localeCompare(b.name))
    const rest = npcs.filter(n => !seedIds.has(n.npc_id)).sort((a, b) => a.name.localeCompare(b.name))
    return [...seeds, ...rest]
  }, [npcs, seedIds])

  // Derived counts
  const populationSize = populationIds.size
  const seedCount = customSeedIds.size

  const togglePopulation = (id: string) => {
    setPopulationIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
        // Also remove from seeds if it was a seed
        setCustomSeedIds(s => { const ns = new Set(s); ns.delete(id); return ns })
      } else {
        next.add(id)
      }
      return next
    })
  }

  const toggleSeed = (id: string) => {
    if (!populationIds.has(id)) return
    setCustomSeedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectAllPopulation = () => {
    setPopulationIds(new Set(npcs.map(n => n.npc_id)))
  }

  const deselectAllPopulation = () => {
    setPopulationIds(new Set())
    setCustomSeedIds(new Set())
  }

  const handleLaunch = async () => {
    if (populationSize < 10) {
      setError('Population must be at least 10 NPCs.')
      return
    }
    if (seedCount < 1) {
      setError('Select at least 1 NPC as initial seed.')
      return
    }
    if (seedCount > 15) {
      setError('Initial exposure cannot exceed 15.')
      return
    }

    setLoading(true)
    setError('')
    const meta = parentSimulation.idea_metadata || {}

    try {
      const body = {
        idea: {
          title: parentSimulation.idea_title,
          description: parentSimulation.idea_description,
          category: parentSimulation.idea_category,
          stage: meta.stage || 'concept',
          target_audience: meta.target_audience || 'general public',
          problem_statement: meta.problem_statement || '',
          price_point: meta.price_point || 'not specified',
          existing_alternatives: meta.existing_alternatives || '',
          differentiator: meta.differentiator || '',
          known_strengths: meta.known_strengths || '',
          known_risks: meta.known_risks || '',
          monetization_approach: meta.monetization_approach || 'not specified',
        },
        config: {
          num_ticks: numTicks,
          population_size: populationSize,
          seed_count: seedCount,
        },
        parent_simulation_id: parentSimulation.id,
        variant_name: variantName.trim() || undefined,
        simulation_version: simulationVersion,
        custom_seed_ids: [...customSeedIds],
        custom_population_ids: [...populationIds],
      }

      const res = await fetch('/api/simulations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => null)
        const raw = data?.detail
        const detail = typeof raw === 'string' ? raw : (raw?.msg || JSON.stringify(raw) || `Server error: ${res.status}`)
        throw new Error(detail)
      }

      const data = await res.json()
      navigate(`/simulation/${data.id}`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Something went wrong'
      setError(msg.includes('fetch') ? 'Could not reach server — is the backend running?' : msg)
      setLoading(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/20 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-surface border-l border-outline-variant/20 shadow-2xl overflow-y-auto">
        <div className="p-6 space-y-5">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-primary">tune</span>
              <h2 className="text-lg font-bold text-on-surface">Custom Variant</h2>
            </div>
            <button onClick={onClose} className="text-outline hover:text-on-surface">
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>

          <p className="text-xs text-on-surface-variant">
            Hand-pick which NPCs to include and who hears first. The idea stays the same — only the population and seeds change.
          </p>

          {/* Based on */}
          <div className="flex items-center gap-2 bg-surface-container rounded-xl px-3 py-2 text-sm text-on-surface-variant">
            <span className="material-symbols-outlined text-[16px] text-primary">fork_right</span>
            Based on: <span className="font-semibold text-on-surface">{parentSimulation.idea_title}</span>
          </div>

          {/* Variant name */}
          <div>
            <label className="text-[10px] font-bold uppercase tracking-widest text-outline">Variant Label <span className="font-normal text-outline/60">optional</span></label>
            <input
              type="text"
              value={variantName}
              onChange={e => setVariantName(e.target.value)}
              placeholder="e.g. Without price-sensitive NPCs"
              className="mt-1 w-full border border-outline-variant/30 rounded-xl px-3 py-2 text-sm bg-surface-container-lowest focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          {/* Engine version */}
          <div>
            <label className="text-[10px] font-bold uppercase tracking-widest text-outline">Engine Version</label>
            <div className="grid grid-cols-2 gap-3 mt-1">
              {(['v1', 'v2'] as const).map(v => (
                <button
                  key={v}
                  onClick={() => setSimulationVersion(v)}
                  className={`rounded-xl px-3 py-2 text-left text-sm border transition-all ${
                    simulationVersion === v
                      ? 'bg-primary/10 border-primary text-primary font-semibold'
                      : 'border-outline-variant/20 text-on-surface-variant hover:border-outline'
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-[16px]">{v === 'v1' ? 'grid_4x4' : 'auto_awesome'}</span>
                    {v === 'v1' ? 'V1 Deterministic' : 'V2 LLM-Primary'}
                  </div>
                  <div className="text-[10px] text-outline mt-0.5">
                    {v === 'v1' ? 'Fast, consistent, math-driven' : 'Slower, costlier, more nuanced'}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Rounds */}
          <div>
            <div className="flex justify-between items-center">
              <label className="text-[10px] font-bold uppercase tracking-widest text-outline">Rounds</label>
              <span className="text-xs font-semibold text-primary">{numTicks}</span>
            </div>
            <input
              type="range"
              min={3} max={20} step={1}
              className="w-full accent-primary h-2 rounded-full"
              value={numTicks}
              onChange={e => setNumTicks(parseInt(e.target.value))}
            />
          </div>

          {/* Summary counters */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-surface-container rounded-xl px-3 py-2 text-center">
              <div className="text-[10px] font-bold uppercase tracking-widest text-outline">Population</div>
              <div className="text-xl font-bold text-on-surface">{populationSize}</div>
              <div className="text-[10px] text-outline">of {npcs.length} NPCs</div>
            </div>
            <div className="bg-primary/5 border border-primary/20 rounded-xl px-3 py-2 text-center">
              <div className="text-[10px] font-bold uppercase tracking-widest text-primary">Initial Exposure</div>
              <div className="text-xl font-bold text-primary">{seedCount}</div>
              <div className="text-[10px] text-outline">seeds selected</div>
            </div>
          </div>

          {/* Bulk actions */}
          <div className="flex items-center justify-between">
            <label className="text-[10px] font-bold uppercase tracking-widest text-outline">NPC Selection</label>
            <div className="flex gap-2">
              <button onClick={selectAllPopulation} className="text-[10px] text-primary hover:underline">Select All</button>
              <button onClick={deselectAllPopulation} className="text-[10px] text-error hover:underline">Deselect All</button>
            </div>
          </div>

          {/* NPC list */}
          <div className="space-y-1 max-h-[400px] overflow-y-auto border border-outline-variant/20 rounded-xl p-2">
            {sortedNpcs.map((npc) => {
              const inPop = populationIds.has(npc.npc_id)
              const isSeed = customSeedIds.has(npc.npc_id)
              const wasParentSeed = seedIds.has(npc.npc_id)

              return (
                <div
                  key={npc.npc_id}
                  className={`flex items-center gap-2 rounded-lg px-2 py-1.5 transition-all ${
                    isSeed
                      ? 'bg-primary/8 border border-primary/20'
                      : inPop
                        ? 'bg-surface-container-lowest border border-outline-variant/10'
                        : 'opacity-40 border border-transparent'
                  }`}
                >
                  {/* Population checkbox */}
                  <input
                    type="checkbox"
                    checked={inPop}
                    onChange={() => togglePopulation(npc.npc_id)}
                    className="accent-primary w-3.5 h-3.5 shrink-0"
                    title="Include in population"
                  />

                  {/* Seed checkbox */}
                  <input
                    type="checkbox"
                    checked={isSeed}
                    onChange={() => toggleSeed(npc.npc_id)}
                    disabled={!inPop}
                    className="accent-tertiary w-3.5 h-3.5 shrink-0"
                    title="Include as initial seed"
                  />

                  {/* NPC info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className={`text-sm font-medium truncate ${inPop ? 'text-on-surface' : 'text-outline'}`}>
                        {npc.name}
                      </span>
                      {wasParentSeed && (
                        <span className="text-[8px] px-1 py-0.5 rounded bg-primary/10 text-primary font-bold shrink-0">SEED</span>
                      )}
                    </div>
                  </div>

                  {/* Archetype badge */}
                  {npc.archetype && (
                    <span className="text-[9px] font-bold uppercase tracking-wider text-outline bg-surface-container px-1.5 py-0.5 rounded shrink-0">
                      {ARCHETYPE_SHORT[npc.archetype] || npc.archetype.replace(/_/g, ' ')}
                    </span>
                  )}
                </div>
              )
            })}
          </div>

          {/* Legend */}
          <div className="flex gap-4 text-[10px] text-outline">
            <div className="flex items-center gap-1">
              <input type="checkbox" checked readOnly className="accent-primary w-3 h-3" />
              <span>Population</span>
            </div>
            <div className="flex items-center gap-1">
              <input type="checkbox" checked readOnly className="accent-tertiary w-3 h-3" />
              <span>Initial seed</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-[8px] px-1 py-0.5 rounded bg-primary/10 text-primary font-bold">SEED</span>
              <span>Was parent seed</span>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="bg-error/10 border border-error/20 rounded-xl px-4 py-2 flex items-center gap-2">
              <span className="material-symbols-outlined text-[16px] text-error">error</span>
              <span className="text-sm text-error">{error}</span>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              onClick={onClose}
              className="flex-1 py-2.5 rounded-xl border border-outline-variant/30 text-on-surface-variant text-sm font-semibold hover:bg-surface-container transition-all"
            >
              Cancel
            </button>
            <button
              onClick={handleLaunch}
              disabled={loading || populationSize < 10 || seedCount < 1}
              className="flex-1 py-2.5 rounded-xl bg-primary text-on-primary text-sm font-semibold hover:bg-primary/90 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="material-symbols-outlined text-[16px] animate-spin">progress_activity</span>
                  Launching...
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-[16px]">rocket_launch</span>
                  Launch Custom Variant
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
