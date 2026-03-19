import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CATEGORY_GROUPS: { label: string; options: { value: string; label: string }[] }[] = [
  {
    label: 'Software',
    options: [
      { value: 'saas', label: 'SaaS' },
      { value: 'mobile_app', label: 'Mobile App' },
      { value: 'productivity_tool', label: 'Productivity Tool' },
      { value: 'developer_tool', label: 'Developer Tool' },
      { value: 'ai_ml_product', label: 'AI / ML Product' },
      { value: 'browser_extension', label: 'Browser Extension' },
    ],
  },
  {
    label: 'Consumer',
    options: [
      { value: 'social_platform', label: 'Social Platform' },
      { value: 'marketplace', label: 'Marketplace' },
      { value: 'content_media', label: 'Content / Media' },
      { value: 'ecommerce', label: 'E-commerce' },
      { value: 'gaming', label: 'Gaming' },
      { value: 'subscription_box', label: 'Subscription Box' },
    ],
  },
  {
    label: 'Fintech',
    options: [
      { value: 'payments', label: 'Payments' },
      { value: 'lending', label: 'Lending' },
      { value: 'insurance', label: 'Insurance' },
      { value: 'investing', label: 'Investing' },
      { value: 'crypto_web3', label: 'Crypto / Web3' },
    ],
  },
  {
    label: 'Health',
    options: [
      { value: 'health_wellness', label: 'Health / Wellness' },
      { value: 'biotech', label: 'Biotech' },
      { value: 'mental_health', label: 'Mental Health' },
      { value: 'fitness', label: 'Fitness' },
    ],
  },
  {
    label: 'Hardware',
    options: [
      { value: 'consumer_hardware', label: 'Consumer Hardware' },
      { value: 'iot_smart_home', label: 'IoT / Smart Home' },
      { value: 'wearable', label: 'Wearable' },
    ],
  },
  {
    label: 'Other',
    options: [
      { value: 'education', label: 'Education' },
      { value: 'real_estate', label: 'Real Estate' },
      { value: 'food_beverage', label: 'Food / Beverage' },
      { value: 'transportation', label: 'Transportation' },
      { value: 'energy_climate', label: 'Energy / Climate' },
      { value: 'nonprofit', label: 'Nonprofit / Social Impact' },
    ],
  },
]

const STAGE_OPTIONS = [
  { value: 'concept', label: 'Just an idea' },
  { value: 'prototype', label: 'Prototype / Wireframes' },
  { value: 'mvp', label: 'Working MVP' },
  { value: 'launched', label: 'Already launched' },
]

const PRICE_PRESETS = [
  'Free',
  'Freemium',
  '< $5/mo',
  '$5\u2013$20/mo',
  '$20\u2013$50/mo',
  '$50\u2013$100/mo',
  '$100+/mo',
  'One-time purchase',
  'Usage-based',
]

const ASSET_TYPE_OPTIONS = [
  { value: 'website', label: 'Website / Landing Page' },
  { value: 'app_ui', label: 'App UI / Screenshot' },
  { value: 'product_photo', label: 'Product Photo' },
  { value: 'packaging', label: 'Packaging' },
  { value: 'prototype', label: 'Prototype' },
  { value: 'marketing_visual', label: 'Marketing Visual' },
]

const MAX_ASSETS = 5

interface AssetEntry {
  id: string          // client-side key
  file: File | null
  fileName: string
  assetType: string
  url: string
  note: string
  uploading: boolean
  assetId: string | null  // server-side ID after upload
  error: string
}

function createEmptyAsset(): AssetEntry {
  return {
    id: crypto.randomUUID(),
    file: null,
    fileName: '',
    assetType: 'prototype',
    url: '',
    note: '',
    uploading: false,
    assetId: null,
    error: '',
  }
}

const ROUNDS_LABELS: Record<number, string> = {
  3: 'Quick check',
  5: 'Light',
  8: 'Standard',
  12: 'Thorough',
  16: 'Deep',
  20: 'Exhaustive',
}

const POP_LABELS: Record<number, string> = {
  10: 'Small focus group',
  20: 'Medium panel',
  30: 'Standard panel',
  40: 'Large panel',
  50: 'Full population',
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function nearestLabel(value: number, labels: Record<number, string>): string {
  const keys = Object.keys(labels).map(Number).sort((a, b) => a - b)
  let best = keys[0]
  for (const k of keys) {
    if (Math.abs(k - value) < Math.abs(best - value)) best = k
  }
  return labels[best]
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SectionHeader({ number, title, subtitle }: {
  number: number
  title: string
  subtitle: string
}) {
  return (
    <div className="mb-4">
      <div className="flex items-center gap-2 mb-0.5">
        <span className="flex items-center justify-center w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 text-xs font-bold">
          {number}
        </span>
        <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
      </div>
      <p className="text-sm text-gray-500 ml-8">{subtitle}</p>
    </div>
  )
}

function CollapsibleSection({ number, title, subtitle, defaultOpen, children }: {
  number: number
  title: string
  subtitle: string
  defaultOpen: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full px-5 py-4 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="flex items-center justify-center w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 text-xs font-bold">
            {number}
          </span>
          <div className="text-left">
            <span className="text-sm font-semibold text-gray-900">{title}</span>
            <span className="text-xs text-gray-500 ml-2">{subtitle}</span>
          </div>
        </div>
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && <div className="px-5 py-4 space-y-4">{children}</div>}
    </div>
  )
}

function FieldLabel({ label, required, hint }: {
  label: string
  required?: boolean
  hint?: string
}) {
  return (
    <label className="block text-sm font-medium text-gray-700 mb-1">
      {label}
      {required && <span className="text-red-400 ml-0.5">*</span>}
      {hint && <span className="font-normal text-gray-400 ml-1.5">{hint}</span>}
    </label>
  )
}

const inputClass = 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none transition'
const selectClass = inputClass

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function Inject() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // --- Form state ---
  const [form, setForm] = useState({
    // Section 1: The Idea
    title: '',
    description: '',
    category: '',
    customCategory: '',
    stage: 'concept',

    // Section 2: Market Positioning
    target_audience: '',
    problem_statement: '',
    price_point: '',
    customPrice: '',
    existing_alternatives: '',
    differentiator: '',

    // Section 3: Strengths & Risks
    known_strengths: '',
    known_risks: '',

    // Section 4: Simulation Controls
    num_ticks: 8,
    population_size: 30,
    seed_count: 5,
  })

  const update = (field: string, value: string | number) =>
    setForm(f => ({ ...f, [field]: value }))

  // --- Asset state ---
  const [assets, setAssets] = useState<AssetEntry[]>([])

  const addAsset = () => {
    if (assets.length < MAX_ASSETS) {
      setAssets(a => [...a, createEmptyAsset()])
    }
  }

  const removeAsset = (id: string) => {
    setAssets(a => a.filter(x => x.id !== id))
  }

  const updateAsset = (id: string, updates: Partial<AssetEntry>) => {
    setAssets(a => a.map(x => x.id === id ? { ...x, ...updates } : x))
  }

  const uploadAssetFile = async (entry: AssetEntry, file: File) => {
    updateAsset(entry.id, { file, fileName: file.name, uploading: true, error: '' })

    const formData = new FormData()
    formData.append('file', file)
    formData.append('asset_type', entry.assetType)

    try {
      const res = await fetch('/api/assets/upload', { method: 'POST', body: formData })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail.detail || `Upload failed: ${res.status}`)
      }
      const data = await res.json()
      updateAsset(entry.id, { assetId: data.id, uploading: false })
    } catch (err) {
      updateAsset(entry.id, {
        uploading: false,
        error: err instanceof Error ? err.message : 'Upload failed',
      })
    }
  }

  // Resolve "custom" selects
  const resolvedCategory = form.category === '_custom'
    ? form.customCategory
    : form.category
  const resolvedPrice = form.price_point === '_custom'
    ? form.customPrice
    : form.price_point

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      // Build asset refs from successfully uploaded assets
      const assetRefs = assets
        .filter(a => a.assetId)
        .map(a => ({
          asset_id: a.assetId,
          asset_type: a.assetType,
          url: a.url || null,
          note: a.note,
        }))

      const res = await fetch('/api/simulations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          idea: {
            title: form.title,
            description: form.description,
            category: resolvedCategory || 'general',
            stage: form.stage,
            target_audience: form.target_audience || 'general public',
            problem_statement: form.problem_statement,
            price_point: resolvedPrice || 'not specified',
            existing_alternatives: form.existing_alternatives,
            differentiator: form.differentiator,
            known_strengths: form.known_strengths,
            known_risks: form.known_risks,
          },
          config: {
            num_ticks: form.num_ticks,
            population_size: form.population_size,
            seed_count: form.seed_count,
          },
          asset_refs: assetRefs,
        }),
      })

      if (!res.ok) throw new Error(`Server error: ${res.status}`)

      const data = await res.json()
      navigate(`/simulation/${data.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-1">Set Up Simulation</h1>
      <p className="text-sm text-gray-500 mb-8">
        Define your idea and configure how the simulated population will evaluate it.
      </p>

      <form onSubmit={handleSubmit} className="space-y-8">

        {/* ---- Section 1: The Idea ---- */}
        <section>
          <SectionHeader number={1} title="The Idea" subtitle="What are you testing?" />

          <div className="space-y-4 ml-8">
            <div>
              <FieldLabel label="Idea Name" required />
              <input
                type="text"
                required
                className={inputClass}
                placeholder="e.g. FocusFlow, PetBuddy, GreenLedger"
                value={form.title}
                onChange={e => update('title', e.target.value)}
              />
            </div>

            <div>
              <FieldLabel label="What is it?" required hint="Be specific — the simulation quality depends on this" />
              <textarea
                required
                rows={4}
                className={inputClass}
                placeholder={"Describe what the product does, who uses it, and how it works.\n\ne.g. \"An AI-powered focus timer that blocks distracting apps and uses gentle nudges to keep remote workers in deep focus sessions. Integrates with Slack to auto-set status.\""}
                value={form.description}
                onChange={e => update('description', e.target.value)}
              />
              <div className="text-xs text-gray-400 mt-1 text-right">
                {form.description.length > 0 && `${form.description.length} chars`}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <FieldLabel label="Category" required />
                <select
                  required
                  className={selectClass}
                  value={form.category}
                  onChange={e => update('category', e.target.value)}
                >
                  <option value="" disabled>Select a category...</option>
                  {CATEGORY_GROUPS.map(group => (
                    <optgroup key={group.label} label={group.label}>
                      {group.options.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </optgroup>
                  ))}
                  <option value="_custom">Custom...</option>
                </select>
                {form.category === '_custom' && (
                  <input
                    type="text"
                    required
                    className={`${inputClass} mt-2`}
                    placeholder="Enter custom category"
                    value={form.customCategory}
                    onChange={e => update('customCategory', e.target.value)}
                  />
                )}
              </div>

              <div>
                <FieldLabel label="Idea Stage" />
                <select
                  className={selectClass}
                  value={form.stage}
                  onChange={e => update('stage', e.target.value)}
                >
                  {STAGE_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </section>

        {/* ---- Section 2: Market Positioning ---- */}
        <section>
          <SectionHeader number={2} title="Market Positioning" subtitle="Who is this for and how does it compete?" />

          <div className="space-y-4 ml-8">
            <div>
              <FieldLabel label="Target Audience" required />
              <input
                type="text"
                required
                className={inputClass}
                placeholder="e.g. remote workers aged 25-40, indie game developers, small restaurant owners"
                value={form.target_audience}
                onChange={e => update('target_audience', e.target.value)}
              />
            </div>

            <div>
              <FieldLabel label="Problem it Solves" hint="optional" />
              <textarea
                rows={2}
                className={inputClass}
                placeholder="What pain point or unmet need does this address?"
                value={form.problem_statement}
                onChange={e => update('problem_statement', e.target.value)}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <FieldLabel label="Pricing" />
                <select
                  className={selectClass}
                  value={form.price_point}
                  onChange={e => update('price_point', e.target.value)}
                >
                  <option value="">Not decided yet</option>
                  {PRICE_PRESETS.map(p => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                  <option value="_custom">Custom...</option>
                </select>
                {form.price_point === '_custom' && (
                  <input
                    type="text"
                    className={`${inputClass} mt-2`}
                    placeholder="e.g. $299 one-time, $0.01 per API call"
                    value={form.customPrice}
                    onChange={e => update('customPrice', e.target.value)}
                  />
                )}
              </div>

              <div>
                <FieldLabel label="Existing Alternatives" hint="optional" />
                <input
                  type="text"
                  className={inputClass}
                  placeholder="e.g. Notion, Trello, pen and paper"
                  value={form.existing_alternatives}
                  onChange={e => update('existing_alternatives', e.target.value)}
                />
              </div>
            </div>

            <div>
              <FieldLabel label="Key Differentiator" hint="optional" />
              <input
                type="text"
                className={inputClass}
                placeholder="What makes this worth switching from alternatives?"
                value={form.differentiator}
                onChange={e => update('differentiator', e.target.value)}
              />
            </div>
          </div>
        </section>

        {/* ---- Section 3: Reference Assets (collapsible) ---- */}
        <CollapsibleSection
          number={3}
          title="Reference Assets"
          subtitle="optional \u2014 screenshots, mockups, photos"
          defaultOpen={false}
        >
          <p className="text-xs text-gray-500 mb-3">
            Upload product screenshots, UI mockups, packaging photos, or landing page screenshots.
            These will be analyzed to assess perceived polish, trust, and visual appeal.
          </p>

          {assets.map((entry) => (
            <div key={entry.id} className="border border-gray-200 rounded-lg p-3 space-y-2 relative">
              <button
                type="button"
                onClick={() => removeAsset(entry.id)}
                className="absolute top-2 right-2 text-gray-400 hover:text-red-500 text-sm"
                title="Remove asset"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <FieldLabel label="Image" />
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp,image/gif"
                    className="w-full text-sm text-gray-500 file:mr-2 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
                    onChange={e => {
                      const file = e.target.files?.[0]
                      if (file) uploadAssetFile(entry, file)
                    }}
                  />
                  {entry.uploading && (
                    <p className="text-xs text-indigo-500 mt-1">Uploading...</p>
                  )}
                  {entry.assetId && !entry.uploading && (
                    <p className="text-xs text-green-600 mt-1">Uploaded</p>
                  )}
                  {entry.error && (
                    <p className="text-xs text-red-500 mt-1">{entry.error}</p>
                  )}
                </div>
                <div>
                  <FieldLabel label="Asset Type" />
                  <select
                    className={selectClass}
                    value={entry.assetType}
                    onChange={e => updateAsset(entry.id, { assetType: e.target.value })}
                  >
                    {ASSET_TYPE_OPTIONS.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <FieldLabel label="URL" hint="optional" />
                  <input
                    type="text"
                    className={inputClass}
                    placeholder="https://..."
                    value={entry.url}
                    onChange={e => updateAsset(entry.id, { url: e.target.value })}
                  />
                </div>
                <div>
                  <FieldLabel label="Note" hint="optional" />
                  <input
                    type="text"
                    className={inputClass}
                    placeholder="e.g. final product look, early prototype"
                    maxLength={200}
                    value={entry.note}
                    onChange={e => updateAsset(entry.id, { note: e.target.value })}
                  />
                </div>
              </div>
            </div>
          ))}

          {assets.length < MAX_ASSETS && (
            <button
              type="button"
              onClick={addAsset}
              className="w-full border border-dashed border-gray-300 rounded-lg py-2 text-sm text-gray-500 hover:border-indigo-400 hover:text-indigo-600 transition-colors"
            >
              + Add Reference Asset {assets.length > 0 && `(${assets.length}/${MAX_ASSETS})`}
            </button>
          )}
        </CollapsibleSection>

        {/* ---- Section 4: Strengths & Risks (collapsible) ---- */}
        <CollapsibleSection
          number={4}
          title="Strengths & Risks"
          subtitle="optional \u2014 seed the simulation with what you already know"
          defaultOpen={false}
        >
          <div>
            <FieldLabel label="Known Strengths" hint="What do you think is strong about this idea?" />
            <textarea
              rows={2}
              className={inputClass}
              placeholder="e.g. Strong viral loop through team invites, solves a problem people actively complain about on Twitter"
              value={form.known_strengths}
              onChange={e => update('known_strengths', e.target.value)}
            />
          </div>
          <div>
            <FieldLabel label="Known Risks" hint="What concerns do you already have?" />
            <textarea
              rows={2}
              className={inputClass}
              placeholder="e.g. Crowded market, unclear monetization path, requires behavior change"
              value={form.known_risks}
              onChange={e => update('known_risks', e.target.value)}
            />
          </div>
        </CollapsibleSection>

        {/* ---- Section 5: Simulation Controls (collapsible) ---- */}
        <CollapsibleSection
          number={5}
          title="Simulation Controls"
          subtitle="tune the simulation parameters"
          defaultOpen={true}
        >
          <div>
            <div className="flex justify-between items-baseline mb-1">
              <FieldLabel label="Simulation Rounds" />
              <span className="text-xs text-indigo-600 font-medium">
                {form.num_ticks} rounds &middot; {nearestLabel(form.num_ticks, ROUNDS_LABELS)}
              </span>
            </div>
            <input
              type="range"
              min={3} max={20} step={1}
              className="w-full accent-indigo-600"
              value={form.num_ticks}
              onChange={e => update('num_ticks', parseInt(e.target.value))}
            />
            <div className="flex justify-between text-xs text-gray-400 mt-0.5">
              <span>3 (quick)</span>
              <span>20 (exhaustive)</span>
            </div>
          </div>

          <div>
            <div className="flex justify-between items-baseline mb-1">
              <FieldLabel label="Population Size" />
              <span className="text-xs text-indigo-600 font-medium">
                {form.population_size} NPCs &middot; {nearestLabel(form.population_size, POP_LABELS)}
              </span>
            </div>
            <input
              type="range"
              min={10} max={50} step={5}
              className="w-full accent-indigo-600"
              value={form.population_size}
              onChange={e => update('population_size', parseInt(e.target.value))}
            />
            <div className="flex justify-between text-xs text-gray-400 mt-0.5">
              <span>10 (focus group)</span>
              <span>50 (full population)</span>
            </div>
          </div>

          <div>
            <div className="flex justify-between items-baseline mb-1">
              <FieldLabel label="Initial Exposure" />
              <span className="text-xs text-indigo-600 font-medium">
                {form.seed_count} {form.seed_count === 1 ? 'person' : 'people'} hear about it first
              </span>
            </div>
            <input
              type="range"
              min={1} max={Math.min(15, form.population_size)} step={1}
              className="w-full accent-indigo-600"
              value={form.seed_count}
              onChange={e => update('seed_count', parseInt(e.target.value))}
            />
            <div className="flex justify-between text-xs text-gray-400 mt-0.5">
              <span>1 (organic)</span>
              <span>{Math.min(15, form.population_size)} (broad launch)</span>
            </div>
          </div>

          <div className="bg-gray-50 rounded-lg p-3 text-xs text-gray-500">
            Estimated cost: ~${(form.num_ticks * form.population_size * 0.0001 + 0.02).toFixed(2)} &middot;
            Duration: ~{Math.ceil(form.num_ticks * form.population_size * 0.12)}&ndash;{Math.ceil(form.num_ticks * form.population_size * 0.2)}s
          </div>
        </CollapsibleSection>

        {/* ---- Errors ---- */}
        {error && (
          <div className="bg-red-50 text-red-700 text-sm rounded-lg p-3">{error}</div>
        )}

        {/* ---- Submit ---- */}
        <button
          type="submit"
          disabled={loading}
          className="w-full bg-indigo-600 text-white py-3 rounded-xl font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? 'Launching Simulation...' : 'Launch Simulation'}
        </button>

        {loading && (
          <p className="text-sm text-gray-500 text-center">
            This typically takes 1-3 minutes depending on population size.
          </p>
        )}
      </form>
    </div>
  )
}
