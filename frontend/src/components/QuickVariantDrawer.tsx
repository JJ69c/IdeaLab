import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

const PRICE_PRESETS = [
  'Free', 'Freemium', '< $5/mo', '$5\u2013$20/mo', '$20\u2013$50/mo',
  '$50\u2013$100/mo', '$100+/mo', 'One-time purchase', 'Usage-based',
]

const inputClass = 'w-full border border-outline-variant/30 bg-surface-container-lowest rounded-xl px-4 py-2.5 text-sm text-on-surface placeholder:text-outline focus:outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10 transition-all'

interface QuickVariantDrawerProps {
  open: boolean
  onClose: () => void
  parentSimulation: {
    id: string
    idea_title: string
    idea_description: string
    idea_category: string
    idea_metadata: Record<string, string>
    config: Record<string, number>
  }
}

export default function QuickVariantDrawer({ open, onClose, parentSimulation }: QuickVariantDrawerProps) {
  const navigate = useNavigate()
  const meta = parentSimulation.idea_metadata || {}
  const config = parentSimulation.config || {}

  const [form, setForm] = useState({
    price_point: meta.price_point || '',
    target_audience: meta.target_audience || '',
    differentiator: meta.differentiator || '',
    existing_alternatives: meta.existing_alternatives || '',
    num_ticks: config.num_ticks ?? 8,
    population_size: config.population_size ?? 30,
  })
  const [variantName, setVariantName] = useState('')
  const [useParentSeeds, setUseParentSeeds] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const update = (field: string, value: string | number) =>
    setForm(f => ({ ...f, [field]: value }))

  const handleSubmit = async () => {
    setLoading(true)
    setError('')

    try {
      const body = {
        idea: {
          title: parentSimulation.idea_title,
          description: parentSimulation.idea_description,
          category: parentSimulation.idea_category,
          stage: meta.stage || 'concept',
          target_audience: form.target_audience || 'general public',
          problem_statement: meta.problem_statement || '',
          price_point: form.price_point || 'not specified',
          existing_alternatives: form.existing_alternatives || '',
          differentiator: form.differentiator || '',
          known_strengths: meta.known_strengths || '',
          known_risks: meta.known_risks || '',
        },
        config: {
          num_ticks: form.num_ticks,
          population_size: form.population_size,
          seed_count: config.seed_count ?? 8,
        },
        parent_simulation_id: parentSimulation.id,
        variant_name: variantName.trim() || undefined,
        use_parent_seeds: useParentSeeds,
        asset_refs: [],
      }

      const res = await fetch('/api/simulations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) throw new Error(`Server error: ${res.status}`)

      const data = await res.json()
      navigate(`/simulation/${data.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
      setLoading(false)
    }
  }

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40 transition-opacity"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed right-0 top-0 bottom-0 w-full max-w-md z-50 overflow-y-auto">
        <div className="glass-panel h-full border-l border-outline-variant/30 p-6 space-y-5">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-[20px] text-primary">science</span>
              <h2 className="text-lg font-bold text-on-surface tracking-tight">Quick Variant</h2>
            </div>
            <button
              onClick={onClose}
              className="text-outline hover:text-on-surface transition-colors p-1"
            >
              <span className="material-symbols-outlined text-[20px]">close</span>
            </button>
          </div>

          <p className="text-xs text-on-surface-variant">
            Test a "what-if" by adjusting key parameters. Everything else stays the same as the original.
          </p>

          {/* Variant Name */}
          <div>
            <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-1.5">
              Variant Label <span className="font-normal normal-case tracking-normal text-outline">optional</span>
            </label>
            <input
              type="text"
              className={inputClass}
              placeholder="e.g. Lower price test, Different audience"
              maxLength={200}
              value={variantName}
              onChange={e => setVariantName(e.target.value)}
            />
          </div>

          {/* Seed Population Mode */}
          <div>
            <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-2">
              Starting Exposure
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setUseParentSeeds(false)}
                className={`flex flex-col items-start gap-1 rounded-xl border px-3 py-2.5 text-left transition-all ${
                  !useParentSeeds
                    ? 'border-primary/40 bg-primary/5 ring-1 ring-primary/20'
                    : 'border-outline-variant/30 hover:border-outline-variant/50'
                }`}
              >
                <span className="flex items-center gap-1.5 text-xs font-semibold text-on-surface">
                  <span className="material-symbols-outlined text-[14px]">shuffle</span>
                  Fresh seeds
                </span>
                <span className="text-[10px] text-outline leading-snug">
                  Re-select who hears first — adds realistic variance
                </span>
              </button>
              <button
                type="button"
                onClick={() => setUseParentSeeds(true)}
                className={`flex flex-col items-start gap-1 rounded-xl border px-3 py-2.5 text-left transition-all ${
                  useParentSeeds
                    ? 'border-primary/40 bg-primary/5 ring-1 ring-primary/20'
                    : 'border-outline-variant/30 hover:border-outline-variant/50'
                }`}
              >
                <span className="flex items-center gap-1.5 text-xs font-semibold text-on-surface">
                  <span className="material-symbols-outlined text-[14px]">lock</span>
                  Same seeds
                </span>
                <span className="text-[10px] text-outline leading-snug">
                  Fix who hears first — isolates the product change
                </span>
              </button>
            </div>
          </div>

          <div className="border-t border-outline-variant/20 pt-4" />

          {/* Pricing */}
          <div>
            <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-1.5">
              Pricing
            </label>
            <select
              className={inputClass}
              value={PRICE_PRESETS.includes(form.price_point) ? form.price_point : ''}
              onChange={e => update('price_point', e.target.value)}
            >
              <option value="">Not decided yet</option>
              {PRICE_PRESETS.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>

          {/* Target Audience */}
          <div>
            <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-1.5">
              Target Audience
            </label>
            <input
              type="text"
              className={inputClass}
              placeholder="e.g. remote workers aged 25-40"
              value={form.target_audience}
              onChange={e => update('target_audience', e.target.value)}
            />
          </div>

          {/* Differentiator */}
          <div>
            <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-1.5">
              Key Differentiator
            </label>
            <input
              type="text"
              className={inputClass}
              placeholder="What makes this worth switching?"
              value={form.differentiator}
              onChange={e => update('differentiator', e.target.value)}
            />
          </div>

          {/* Alternatives */}
          <div>
            <label className="block text-[10px] font-bold text-outline uppercase tracking-widest mb-1.5">
              Existing Alternatives
            </label>
            <input
              type="text"
              className={inputClass}
              placeholder="e.g. Notion, Trello, pen and paper"
              value={form.existing_alternatives}
              onChange={e => update('existing_alternatives', e.target.value)}
            />
          </div>

          <div className="border-t border-outline-variant/20 pt-4" />

          {/* Simulation Rounds */}
          <div>
            <div className="flex justify-between items-baseline mb-2">
              <label className="text-[10px] font-bold text-outline uppercase tracking-widest">
                Rounds
              </label>
              <span className="text-xs font-semibold text-primary">{form.num_ticks}</span>
            </div>
            <input
              type="range"
              min={3} max={20} step={1}
              className="w-full accent-primary h-2 rounded-full"
              value={form.num_ticks}
              onChange={e => update('num_ticks', parseInt(e.target.value))}
            />
          </div>

          {/* Population Size */}
          <div>
            <div className="flex justify-between items-baseline mb-2">
              <label className="text-[10px] font-bold text-outline uppercase tracking-widest">
                Population
              </label>
              <span className="text-xs font-semibold text-primary">{form.population_size} NPCs</span>
            </div>
            <input
              type="range"
              min={10} max={50} step={5}
              className="w-full accent-primary h-2 rounded-full"
              value={form.population_size}
              onChange={e => update('population_size', parseInt(e.target.value))}
            />
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
              className="flex-1 text-sm font-semibold text-on-surface-variant px-4 py-2.5 rounded-xl border border-outline-variant/30 hover:border-outline-variant/50 transition-all"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-2 bg-gradient-to-r from-primary to-primary-container text-on-primary px-4 py-2.5 rounded-xl text-sm font-semibold shadow-lg shadow-primary/20 hover:scale-[0.98] active:scale-95 disabled:opacity-50 disabled:hover:scale-100 transition-all"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                  Launching...
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-[16px]">rocket_launch</span>
                  Launch Variant
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
