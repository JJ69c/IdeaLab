import { useEffect, useState, useRef } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'

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
  { value: 'concept', label: 'Just an idea', icon: 'lightbulb' },
  { value: 'prototype', label: 'Prototype', icon: 'draw' },
  { value: 'mvp', label: 'Working MVP', icon: 'code' },
  { value: 'launched', label: 'Launched', icon: 'rocket_launch' },
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
  id: string
  file: File | null
  fileName: string
  assetType: string
  url: string
  note: string
  uploading: boolean
  assetId: string | null
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

function SectionPanel({ number, title, subtitle, icon, children }: {
  number: number
  title: string
  subtitle: string
  icon: string
  children: React.ReactNode
}) {
  return (
    <section className="glass-panel rounded-3xl border border-white/40 p-6">
      <div className="flex items-center gap-3 mb-5">
        <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-gradient-to-br from-primary to-primary-container text-white text-sm font-bold shadow-lg shadow-primary/20">
          {number}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px] text-primary">{icon}</span>
            <h2 className="text-lg font-bold text-on-surface tracking-tight">{title}</h2>
          </div>
          <p className="text-xs text-on-surface-variant mt-0.5">{subtitle}</p>
        </div>
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  )
}

function FieldLabel({ label, required, hint }: {
  label: string
  required?: boolean
  hint?: string
}) {
  return (
    <label className="block text-xs font-semibold text-on-surface-variant mb-1.5 uppercase tracking-wider">
      {label}
      {required && <span className="text-error ml-0.5">*</span>}
      {hint && <span className="font-normal text-outline normal-case tracking-normal ml-1.5">{hint}</span>}
    </label>
  )
}

const inputClass = 'w-full border border-outline-variant/30 bg-surface-container-lowest rounded-xl px-4 py-2.5 text-sm text-on-surface placeholder:text-outline focus:outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10 transition-all'
const selectClass = inputClass

function TagInput({ value, onChange, placeholder }: {
  value: string
  onChange: (v: string) => void
  placeholder: string
}) {
  const [inputValue, setInputValue] = useState('')
  const tags = value ? value.split(',').map(s => s.trim()).filter(Boolean) : []

  const addTag = (tag: string) => {
    const trimmed = tag.trim()
    if (!trimmed) return
    const newTags = [...tags, trimmed]
    onChange(newTags.join(', '))
    setInputValue('')
  }

  const removeTag = (index: number) => {
    const newTags = tags.filter((_, i) => i !== index)
    onChange(newTags.join(', '))
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addTag(inputValue)
    }
  }

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {tags.map((tag, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 text-xs font-medium px-3 py-1 rounded-lg bg-primary/8 text-primary border border-primary/15"
          >
            {tag}
            <button
              type="button"
              onClick={() => removeTag(i)}
              className="text-primary/50 hover:text-primary transition-colors"
            >
              <span className="material-symbols-outlined text-[14px]">close</span>
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          className={inputClass}
          placeholder={placeholder}
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button
          type="button"
          onClick={() => addTag(inputValue)}
          disabled={!inputValue.trim()}
          className="flex-shrink-0 flex items-center gap-1 text-xs font-semibold px-3 py-2 rounded-xl border border-primary/20 text-primary hover:bg-primary/5 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
        >
          <span className="material-symbols-outlined text-[14px]">add</span>
          Add
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function Inject() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const variantOf = searchParams.get('variant_of')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [variantParent, setVariantParent] = useState<{
    id: string; idea_title: string
  } | null>(null)
  const [variantName, setVariantName] = useState('')
  const [prefilling, setPrefilling] = useState(!!variantOf)

  // --- Form state ---
  const [form, setForm] = useState({
    title: '',
    description: '',
    category: '',
    customCategory: '',
    stage: 'concept',
    target_audience: '',
    problem_statement: '',
    price_point: '',
    customPrice: '',
    existing_alternatives: '',
    differentiator: '',
    known_strengths: '',
    known_risks: '',
    num_ticks: 8,
    population_size: 30,
    seed_count: 8,
  })

  const update = (field: string, value: string | number) =>
    setForm(f => ({ ...f, [field]: value }))

  // --- Variant pre-fill ---
  useEffect(() => {
    if (!variantOf) return
    fetch(`/api/simulations/${variantOf}`)
      .then(r => r.json())
      .then(data => {
        setVariantParent({ id: data.id, idea_title: data.idea_title })
        const meta = data.idea_metadata || {}
        const config = data.config || {}

        const allKnownCategories = CATEGORY_GROUPS.flatMap(g => g.options.map(o => o.value))
        const isKnownCategory = allKnownCategories.includes(data.idea_category)
        const isKnownPrice = PRICE_PRESETS.includes(meta.price_point || '')

        setForm({
          title: data.idea_title || '',
          description: data.idea_description || '',
          category: isKnownCategory ? data.idea_category : (data.idea_category ? '_custom' : ''),
          customCategory: isKnownCategory ? '' : (data.idea_category || ''),
          stage: meta.stage || 'concept',
          target_audience: meta.target_audience || '',
          problem_statement: meta.problem_statement || '',
          price_point: isKnownPrice ? (meta.price_point || '') : (meta.price_point ? '_custom' : ''),
          customPrice: isKnownPrice ? '' : (meta.price_point || ''),
          existing_alternatives: meta.existing_alternatives || '',
          differentiator: meta.differentiator || '',
          known_strengths: meta.known_strengths || '',
          known_risks: meta.known_risks || '',
          num_ticks: config.num_ticks ?? 8,
          population_size: config.population_size ?? 30,
          seed_count: config.seed_count ?? 8,
        })
        setPrefilling(false)
      })
      .catch(() => setPrefilling(false))
  }, [variantOf])

  // --- Asset state ---
  const [assets, setAssets] = useState<AssetEntry[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    if (assets.length >= MAX_ASSETS) return
    const file = e.dataTransfer.files?.[0]
    if (file && file.type.startsWith('image/')) {
      const newAsset = createEmptyAsset()
      setAssets(a => [...a, newAsset])
      uploadAssetFile(newAsset, file)
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
      // Include both uploaded assets and URL-only assets
      const assetRefs = assets
        .filter(a => a.assetId || a.url.trim())
        .map(a => ({
          asset_id: a.assetId || null,
          asset_type: a.assetType,
          url: a.url || null,
          note: a.note,
        }))

      const body: Record<string, unknown> = {
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
      }
      if (variantOf) {
        body.parent_simulation_id = variantOf
        if (variantName.trim()) body.variant_name = variantName.trim()
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

  const estimatedCost = (form.num_ticks * form.population_size * 0.0001 + 0.02).toFixed(2)
  const durationMin = Math.ceil(form.num_ticks * form.population_size * 0.12)
  const durationMax = Math.ceil(form.num_ticks * form.population_size * 0.2)

  if (prefilling) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-outline gap-3">
        <span className="material-symbols-outlined text-[32px] animate-pulse">hourglass_empty</span>
        <span className="text-sm font-medium">Loading parent simulation data...</span>
      </div>
    )
  }

  return (
    <div className="max-w-2xl pb-28">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-on-surface tracking-tight">
          {variantParent ? 'Create Variant' : 'Set Up Simulation'}
        </h1>
        <p className="text-on-surface-variant mt-1">
          {variantParent
            ? 'Adjust parameters and re-run to compare results.'
            : 'Define your idea and configure how the simulated population will evaluate it.'}
        </p>
      </div>

      {/* Variant banner */}
      {variantParent && (
        <div className="glass-panel rounded-2xl border border-primary/20 px-5 py-3 mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm">
            <span className="material-symbols-outlined text-[18px] text-primary">fork_right</span>
            <span className="text-on-surface-variant font-medium">Variant of:</span>
            <Link
              to={`/report/${variantParent.id}`}
              className="text-primary font-semibold hover:underline"
            >
              {variantParent.idea_title}
            </Link>
          </div>
          <span className="text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-lg bg-primary/10 text-primary">
            What-If
          </span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">

        {/* ---- Section 1: The Idea ---- */}
        <SectionPanel number={1} title="The Idea" subtitle="What are you testing?" icon="lightbulb">
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
              <div className="flex gap-1.5 flex-wrap">
                {STAGE_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => update('stage', opt.value)}
                    className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-xl border transition-all ${
                      form.stage === opt.value
                        ? 'bg-primary text-on-primary border-primary shadow-lg shadow-primary/20'
                        : 'border-outline-variant/30 text-on-surface-variant hover:border-primary/30 hover:text-primary hover:bg-primary/5'
                    }`}
                  >
                    <span className="material-symbols-outlined text-[14px]">{opt.icon}</span>
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
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
            {form.description.length > 0 && (
              <div className="text-[10px] text-outline mt-1 text-right">
                {form.description.length} chars
              </div>
            )}
          </div>
        </SectionPanel>

        {/* ---- Section 2: Market Positioning ---- */}
        <SectionPanel number={2} title="Market Positioning" subtitle="Who is this for and how does it compete?" icon="storefront">
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

          <div className="grid grid-cols-2 gap-4">
            <div>
              <FieldLabel label="Pricing Strategy" />
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
            <FieldLabel label="Problem it Solves" hint="optional" />
            <textarea
              rows={2}
              className={inputClass}
              placeholder="What pain point or unmet need does this address?"
              value={form.problem_statement}
              onChange={e => update('problem_statement', e.target.value)}
            />
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
        </SectionPanel>

        {/* ---- Section 3: Reference Assets ---- */}
        <SectionPanel number={3} title="Reference Assets" subtitle="Optional — screenshots, mockups, photos" icon="image">
          <p className="text-xs text-on-surface-variant -mt-1">
            Upload product screenshots, UI mockups, packaging photos, or landing page screenshots.
            These will be analyzed to assess perceived polish, trust, and visual appeal.
          </p>

          {/* Drag-and-drop zone */}
          {assets.length < MAX_ASSETS && (
            <div
              onDragOver={e => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-outline-variant/30 rounded-2xl p-8 text-center cursor-pointer hover:border-primary/30 hover:bg-primary/3 transition-all group"
            >
              <span className="material-symbols-outlined text-[32px] text-outline-variant group-hover:text-primary transition-colors">cloud_upload</span>
              <p className="text-sm text-on-surface-variant mt-2">Drag & drop images here or click to browse</p>
              <p className="text-[10px] text-outline mt-1">JPEG, PNG, WebP, GIF — up to {MAX_ASSETS} files</p>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                className="hidden"
                onChange={e => {
                  const file = e.target.files?.[0]
                  if (file && assets.length < MAX_ASSETS) {
                    const newAsset = createEmptyAsset()
                    setAssets(a => [...a, newAsset])
                    uploadAssetFile(newAsset, file)
                  }
                  e.target.value = ''
                }}
              />
            </div>
          )}

          {/* Uploaded assets */}
          {assets.map((entry) => (
            <div key={entry.id} className="bg-surface-container-lowest border border-outline-variant/20 rounded-2xl p-4 space-y-3 relative">
              <button
                type="button"
                onClick={() => removeAsset(entry.id)}
                className="absolute top-3 right-3 text-outline hover:text-error transition-colors"
                title="Remove asset"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
              </button>

              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-surface-container flex items-center justify-center flex-shrink-0">
                  <span className="material-symbols-outlined text-[20px] text-on-surface-variant">
                    {entry.uploading ? 'hourglass_empty' : entry.assetId ? 'check_circle' : 'image'}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-on-surface truncate">
                    {entry.fileName || 'No file selected'}
                  </p>
                  {entry.uploading && (
                    <p className="text-[10px] text-primary animate-pulse">Uploading...</p>
                  )}
                  {entry.assetId && !entry.uploading && (
                    <p className="text-[10px] text-green-600">Uploaded successfully</p>
                  )}
                  {entry.error && (
                    <p className="text-[10px] text-error">{entry.error}</p>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
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
                <div>
                  <FieldLabel label="Note" hint="optional" />
                  <input
                    type="text"
                    className={inputClass}
                    placeholder="e.g. final product look"
                    maxLength={200}
                    value={entry.note}
                    onChange={e => updateAsset(entry.id, { note: e.target.value })}
                  />
                </div>
              </div>

              {!entry.fileName && (
                <div>
                  <FieldLabel label="Or provide a URL" hint="optional" />
                  <input
                    type="text"
                    className={inputClass}
                    placeholder="https://..."
                    value={entry.url}
                    onChange={e => updateAsset(entry.id, { url: e.target.value })}
                  />
                </div>
              )}

              {!entry.fileName && (
                <div>
                  <FieldLabel label="Image" />
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp,image/gif"
                    className="w-full text-sm text-on-surface-variant file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-medium file:bg-primary/10 file:text-primary hover:file:bg-primary/15 transition-colors"
                    onChange={e => {
                      const file = e.target.files?.[0]
                      if (file) uploadAssetFile(entry, file)
                    }}
                  />
                </div>
              )}
            </div>
          ))}

          {assets.length > 0 && assets.length < MAX_ASSETS && (
            <button
              type="button"
              onClick={addAsset}
              className="w-full border border-dashed border-outline-variant/30 rounded-xl py-2.5 text-xs font-semibold text-on-surface-variant hover:border-primary/30 hover:text-primary hover:bg-primary/5 transition-all flex items-center justify-center gap-1.5"
            >
              <span className="material-symbols-outlined text-[16px]">add</span>
              Add Another Asset ({assets.length}/{MAX_ASSETS})
            </button>
          )}
        </SectionPanel>

        {/* ---- Section 4: Strengths & Risks ---- */}
        <SectionPanel number={4} title="Analysis" subtitle="Optional — seed the simulation with what you already know" icon="analytics">
          <div>
            <FieldLabel label="Key Strengths" hint="Press Enter to add each strength" />
            <TagInput
              value={form.known_strengths}
              onChange={v => update('known_strengths', v)}
              placeholder="e.g. Strong viral loop through team invites"
            />
          </div>

          <div>
            <FieldLabel label="Major Risks" hint="Press Enter to add each risk" />
            <TagInput
              value={form.known_risks}
              onChange={v => update('known_risks', v)}
              placeholder="e.g. Crowded market, unclear monetization"
            />
          </div>
        </SectionPanel>

        {/* ---- Section 5: Simulation Controls ---- */}
        <SectionPanel number={5} title="Controls" subtitle="Tune the simulation parameters" icon="tune">
          <div>
            <div className="flex justify-between items-baseline mb-2">
              <FieldLabel label="Simulation Rounds" />
              <span className="text-xs font-semibold text-primary">
                {form.num_ticks} rounds &middot; {nearestLabel(form.num_ticks, ROUNDS_LABELS)}
              </span>
            </div>
            <input
              type="range"
              min={3} max={20} step={1}
              className="w-full accent-primary h-2 rounded-full"
              value={form.num_ticks}
              onChange={e => update('num_ticks', parseInt(e.target.value))}
            />
            <div className="flex justify-between text-[10px] text-outline mt-1">
              <span>3 (quick)</span>
              <span>20 (exhaustive)</span>
            </div>
          </div>

          <div>
            <div className="flex justify-between items-baseline mb-2">
              <FieldLabel label="Population Size" />
              <span className="text-xs font-semibold text-primary">
                {form.population_size} NPCs &middot; {nearestLabel(form.population_size, POP_LABELS)}
              </span>
            </div>
            <input
              type="range"
              min={10} max={50} step={5}
              className="w-full accent-primary h-2 rounded-full"
              value={form.population_size}
              onChange={e => update('population_size', parseInt(e.target.value))}
            />
            <div className="flex justify-between text-[10px] text-outline mt-1">
              <span>10 (focus group)</span>
              <span>50 (full population)</span>
            </div>
          </div>

          <div>
            <div className="flex justify-between items-baseline mb-2">
              <FieldLabel label="Initial Exposure" />
              <span className="text-xs font-semibold text-primary">
                {form.seed_count} {form.seed_count === 1 ? 'person' : 'people'} hear about it first
              </span>
            </div>
            <input
              type="range"
              min={1} max={Math.min(15, form.population_size)} step={1}
              className="w-full accent-primary h-2 rounded-full"
              value={form.seed_count}
              onChange={e => update('seed_count', parseInt(e.target.value))}
            />
            <div className="flex justify-between text-[10px] text-outline mt-1">
              <span>1 (organic)</span>
              <span>{Math.min(15, form.population_size)} (broad launch)</span>
            </div>
          </div>
        </SectionPanel>

        {/* ---- Variant Name (only for variants) ---- */}
        {variantOf && (
          <SectionPanel number={6} title="Variant Label" subtitle="What are you testing with this variant?" icon="science">
            <div>
              <FieldLabel label="Variant Name" hint="optional label for this variant" />
              <input
                type="text"
                className={inputClass}
                placeholder="e.g. Lower price, Different audience, Simpler description"
                maxLength={200}
                value={variantName}
                onChange={e => setVariantName(e.target.value)}
              />
            </div>
          </SectionPanel>
        )}

        {/* ---- Error ---- */}
        {error && (
          <div className="glass-panel rounded-2xl border border-error/20 px-5 py-3 flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px] text-error">error</span>
            <span className="text-sm text-error">{error}</span>
          </div>
        )}
      </form>

      {/* ---- Bottom Action Bar ---- */}
      <div className="fixed bottom-0 left-0 right-0 z-50">
        <div className="glass-panel border-t border-outline-variant/30">
          <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[16px] text-outline">payments</span>
                <span className="text-xs text-on-surface-variant">
                  Est. cost: <span className="font-semibold text-on-surface">${estimatedCost}</span>
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[16px] text-outline">schedule</span>
                <span className="text-xs text-on-surface-variant">
                  Duration: <span className="font-semibold text-on-surface">{durationMin}&ndash;{durationMax}s</span>
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Link
                to="/dashboard"
                className="text-sm font-semibold text-on-surface-variant hover:text-on-surface px-4 py-2.5 rounded-xl border border-outline-variant/30 hover:border-outline-variant/50 transition-all"
              >
                Cancel
              </Link>
              <button
                type="submit"
                form={undefined}
                onClick={handleSubmit as unknown as React.MouseEventHandler}
                disabled={loading || !form.title || !form.description}
                className="flex items-center gap-2 bg-gradient-to-r from-primary to-primary-container text-on-primary px-6 py-2.5 rounded-xl text-sm font-semibold shadow-xl shadow-primary/20 hover:scale-[0.98] active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100 transition-all"
              >
                {loading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                    Launching...
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-[18px]">rocket_launch</span>
                    {variantOf ? 'Launch Variant' : 'Run Simulation'}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {loading && (
        <div className="text-center mt-4">
          <p className="text-xs text-on-surface-variant">
            This typically takes 1-3 minutes depending on population size.
          </p>
        </div>
      )}
    </div>
  )
}
