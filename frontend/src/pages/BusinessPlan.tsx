import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'

interface SubSection {
  [key: string]: string
}

interface BusinessPlanData {
  executive_summary: string
  market_opportunity: SubSection
  customer_validation: SubSection
  competitive_positioning: SubSection
  business_model: SubSection
  go_to_market: SubSection
  risk_assessment: SubSection
  financial_projections: SubSection
  strategic_recommendations: SubSection
}

interface SimMeta {
  idea_title: string
  idea_category: string
  idea_metadata: Record<string, string>
  config: Record<string, number>
  simulation_version: string
  metrics: Record<string, number> | null
}

const SECTION_CONFIG: {
  key: keyof BusinessPlanData
  title: string
  icon: string
  color: string
  subLabels?: Record<string, string>
}[] = [
  {
    key: 'executive_summary',
    title: 'Executive Summary',
    icon: 'summarize',
    color: 'from-indigo-500/20 to-blue-500/20 border-indigo-400/30',
  },
  {
    key: 'market_opportunity',
    title: 'Market Opportunity',
    icon: 'trending_up',
    color: 'from-emerald-500/20 to-teal-500/20 border-emerald-400/30',
    subLabels: {
      overview: 'Overview',
      tam_sam_som: 'TAM / SAM / SOM',
      timing: 'Why Now',
    },
  },
  {
    key: 'customer_validation',
    title: 'Customer Validation',
    icon: 'groups',
    color: 'from-blue-500/20 to-cyan-500/20 border-blue-400/30',
    subLabels: {
      headline_metric: 'Headline Metric',
      adoption_analysis: 'Adoption Analysis',
      segment_breakdown: 'Segment Breakdown',
      willingness_to_pay: 'Willingness to Pay',
      key_objections: 'Key Objections & Mitigation',
    },
  },
  {
    key: 'competitive_positioning',
    title: 'Competitive Positioning',
    icon: 'swords',
    color: 'from-amber-500/20 to-orange-500/20 border-amber-400/30',
    subLabels: {
      landscape: 'Competitive Landscape',
      differentiation: 'Core Differentiator',
      moat_assessment: 'Moat Assessment',
    },
  },
  {
    key: 'business_model',
    title: 'Business Model',
    icon: 'payments',
    color: 'from-green-500/20 to-emerald-500/20 border-green-400/30',
    subLabels: {
      revenue_model: 'Revenue Model',
      unit_economics: 'Unit Economics',
      pricing_recommendation: 'Pricing Recommendation',
    },
  },
  {
    key: 'go_to_market',
    title: 'Go-to-Market Strategy',
    icon: 'rocket_launch',
    color: 'from-purple-500/20 to-pink-500/20 border-purple-400/30',
    subLabels: {
      launch_strategy: 'Launch Strategy',
      growth_levers: 'Growth Levers',
      early_adopter_profile: 'Early Adopter Profile',
    },
  },
  {
    key: 'risk_assessment',
    title: 'Risk Assessment',
    icon: 'warning',
    color: 'from-red-500/20 to-rose-500/20 border-red-400/30',
    subLabels: {
      critical_risks: 'Critical Risks',
      mitigation_strategies: 'Mitigation Strategies',
      kill_criteria: 'Kill Criteria',
    },
  },
  {
    key: 'financial_projections',
    title: 'Financial Projections',
    icon: 'finance',
    color: 'from-cyan-500/20 to-blue-500/20 border-cyan-400/30',
    subLabels: {
      assumptions: 'Key Assumptions',
      year_1_outlook: 'Year 1 Outlook',
      year_3_outlook: 'Year 3 Outlook',
    },
  },
  {
    key: 'strategic_recommendations',
    title: 'Strategic Recommendations',
    icon: 'lightbulb',
    color: 'from-yellow-500/20 to-amber-500/20 border-yellow-400/30',
    subLabels: {
      immediate_actions: 'Immediate Actions (30 Days)',
      build_priorities: 'Build Priorities',
      what_to_avoid: 'What to Avoid',
    },
  },
]

function renderText(text: string) {
  return text.split('\n').map((line, i) => {
    const trimmed = line.trim()
    if (!trimmed) return <br key={i} />
    // Bullet points
    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      return (
        <li key={i} className="ml-4 text-sm text-on-surface-variant leading-relaxed">
          {trimmed.slice(2)}
        </li>
      )
    }
    // Numbered items
    const numMatch = trimmed.match(/^(\d+)\.\s(.+)/)
    if (numMatch) {
      return (
        <li key={i} className="ml-4 text-sm text-on-surface-variant leading-relaxed list-decimal">
          {numMatch[2]}
        </li>
      )
    }
    return (
      <p key={i} className="text-sm text-on-surface-variant leading-relaxed">
        {trimmed}
      </p>
    )
  })
}

const LOADING_PHASES = [
  { icon: 'database', label: 'Reading simulation data', detail: 'Extracting NPC reactions, adoption metrics, and segment analysis' },
  { icon: 'psychology', label: 'Analyzing customer signals', detail: 'Identifying adoption patterns, objection clusters, and willingness to pay' },
  { icon: 'trending_up', label: 'Sizing market opportunity', detail: 'Estimating TAM, SAM, and SOM from target audience and category data' },
  { icon: 'swords', label: 'Mapping competitive landscape', detail: 'Positioning against alternatives based on simulation differentiators' },
  { icon: 'payments', label: 'Modeling unit economics', detail: 'Building revenue projections from conversion signals and pricing data' },
  { icon: 'rocket_launch', label: 'Crafting go-to-market strategy', detail: 'Identifying early adopter profiles and growth levers from NPC archetypes' },
  { icon: 'warning', label: 'Assessing risks', detail: 'Surfacing critical barriers and kill criteria from objection data' },
  { icon: 'edit_document', label: 'Writing business plan', detail: 'Structuring all insights into a consultant-grade deliverable' },
]

function LoadingPhases() {
  const [phase, setPhase] = useState(0)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const phaseTimer = setInterval(() => {
      setPhase(p => (p < LOADING_PHASES.length - 1 ? p + 1 : p))
    }, 8000)
    const clockTimer = setInterval(() => {
      setElapsed(e => e + 1)
    }, 1000)
    return () => { clearInterval(phaseTimer); clearInterval(clockTimer) }
  }, [])

  const current = LOADING_PHASES[phase]
  const progress = Math.min(((phase + 1) / LOADING_PHASES.length) * 100, 95)

  return (
    <div className="max-w-2xl mx-auto text-center py-20 space-y-6">
      <div className="glass-panel rounded-3xl border border-white/40 p-10 space-y-8">
        {/* Animated icon */}
        <div className="relative w-16 h-16 mx-auto">
          <div className="absolute inset-0 rounded-full border-2 border-primary/20 animate-ping" />
          <div className="absolute inset-0 flex items-center justify-center rounded-full bg-primary/10">
            <span className="material-symbols-outlined text-[28px] text-primary animate-pulse">
              {current.icon}
            </span>
          </div>
        </div>

        <div className="space-y-2">
          <h2 className="text-lg font-semibold text-on-surface">{current.label}</h2>
          <p className="text-sm text-on-surface-variant">{current.detail}</p>
        </div>

        {/* Progress bar */}
        <div className="space-y-2">
          <div className="h-1.5 bg-surface-container rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-1000 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-outline">
            <span>{elapsed}s elapsed</span>
            <span>Step {phase + 1} of {LOADING_PHASES.length}</span>
          </div>
        </div>

        {/* Phase checklist */}
        <div className="text-left space-y-1.5 max-w-sm mx-auto">
          {LOADING_PHASES.map((p, i) => (
            <div
              key={i}
              className={`flex items-center gap-2 text-xs transition-all duration-500 ${
                i < phase
                  ? 'text-green-600'
                  : i === phase
                    ? 'text-primary font-semibold'
                    : 'text-outline/40'
              }`}
            >
              <span className="material-symbols-outlined text-[14px]">
                {i < phase ? 'check_circle' : i === phase ? 'pending' : 'radio_button_unchecked'}
              </span>
              {p.label}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function BusinessPlan() {
  const { id } = useParams<{ id: string }>()
  const [plan, setPlan] = useState<BusinessPlanData | null>(null)
  const [simMeta, setSimMeta] = useState<SimMeta | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [activeSection, setActiveSection] = useState(0)

  // Fetch simulation metadata + check for cached plan
  useEffect(() => {
    if (!id) return
    // Fetch sim metadata
    fetch(`/api/simulations/${id}`)
      .then(r => r.json())
      .then(data => setSimMeta({
        idea_title: data.idea_title,
        idea_category: data.idea_category,
        idea_metadata: data.idea_metadata || {},
        config: data.config || {},
        simulation_version: data.simulation_version || 'v1',
        metrics: data.metrics,
      }))
      .catch(() => {})
    // Check for cached plan
    fetch(`/api/simulations/${id}/business-plan`)
      .then(r => { if (r.ok) return r.json(); return null })
      .then(data => { if (data) setPlan(data) })
      .catch(() => {})
  }, [id])

  const generatePlan = async () => {
    if (!id) return
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`/api/simulations/${id}/business-plan`, { method: 'POST' })
      if (!res.ok) {
        const raw = await res.json().catch(() => null)
        const detail = typeof raw?.detail === 'string' ? raw.detail : `Server error: ${res.status}`
        throw new Error(detail)
      }
      const data = await res.json()
      setPlan(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate plan')
    } finally {
      setLoading(false)
    }
  }

  if (!simMeta) {
    return <p className="text-gray-500">Loading...</p>
  }

  // Pre-generation state
  if (!plan && !loading) {
    return (
      <div className="max-w-2xl mx-auto text-center py-20 space-y-6">
        <Link to={`/report/${id}`} className="text-indigo-600 text-sm">&larr; Back to Report</Link>
        <div className="glass-panel rounded-3xl border border-white/40 p-10 space-y-6">
          <span className="material-symbols-outlined text-[48px] text-primary">description</span>
          <h1 className="text-2xl font-bold text-on-surface">{simMeta.idea_title}</h1>
          <p className="text-on-surface-variant text-sm">
            Generate a consultant-grade business plan from your simulation data.
            This uses your simulation's NPC reactions, adoption metrics, and segment analysis
            to produce a structured plan grounded in evidence.
          </p>
          <div className="flex items-center justify-center gap-4 text-xs text-outline">
            <span>{simMeta.config.population_size || 30} NPCs</span>
            <span className="w-1 h-1 rounded-full bg-outline" />
            <span>{simMeta.config.num_ticks || 8} rounds</span>
            <span className="w-1 h-1 rounded-full bg-outline" />
            <span className="uppercase">{simMeta.simulation_version}</span>
          </div>
          <button
            onClick={generatePlan}
            className="bg-primary text-on-primary px-8 py-3 rounded-xl font-semibold hover:bg-primary/90 transition-all shadow-lg shadow-primary/20"
          >
            Generate Business Plan
          </button>
          {error && <p className="text-red-500 text-sm">{error}</p>}
        </div>
      </div>
    )
  }

  // Loading state — dynamic phases
  if (loading) {
    return <LoadingPhases />
  }

  if (error) {
    return (
      <div className="max-w-2xl mx-auto text-center py-20 space-y-4">
        <p className="text-red-500">{error}</p>
        <button onClick={generatePlan} className="text-sm text-primary underline">Try again</button>
      </div>
    )
  }

  // Plan display
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link to={`/report/${id}`} className="text-indigo-600 text-sm">&larr; Report</Link>
        <h1 className="text-2xl font-bold flex-1">{simMeta.idea_title}</h1>
        <span className="text-xs bg-primary/10 text-primary px-3 py-1 rounded-lg font-medium">
          Business Plan
        </span>
      </div>

      {/* Table of Contents */}
      <nav className="glass-panel rounded-2xl border border-white/40 p-4">
        <div className="flex flex-wrap gap-2">
          {SECTION_CONFIG.map((sec, i) => (
            <button
              key={sec.key}
              onClick={() => {
                setActiveSection(i)
                document.getElementById(`section-${i}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
              }}
              className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-all ${
                activeSection === i
                  ? 'bg-primary/10 text-primary border-primary/30 font-semibold'
                  : 'text-on-surface-variant border-outline-variant/20 hover:bg-surface-container'
              }`}
            >
              <span className="material-symbols-outlined text-[14px]">{sec.icon}</span>
              {sec.title}
            </button>
          ))}
        </div>
      </nav>

      {/* Sections */}
      {SECTION_CONFIG.map((sec, i) => {
        const content = plan![sec.key]
        return (
          <section
            key={sec.key}
            id={`section-${i}`}
            className={`glass-panel rounded-3xl border bg-gradient-to-br ${sec.color} p-6 space-y-4`}
          >
            {/* Section header */}
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-white/60 flex items-center justify-center">
                <span className="material-symbols-outlined text-[20px] text-on-surface">{sec.icon}</span>
              </div>
              <div>
                <span className="text-[10px] font-bold uppercase tracking-widest text-outline">
                  Section {i + 1}
                </span>
                <h2 className="text-lg font-bold text-on-surface">{sec.title}</h2>
              </div>
            </div>

            {/* Content */}
            {typeof content === 'string' ? (
              <div className="bg-white/50 rounded-2xl p-5 space-y-2">
                {renderText(content)}
              </div>
            ) : (
              <div className="space-y-3">
                {Object.entries(content as SubSection).map(([subKey, text]) => {
                  const label = sec.subLabels?.[subKey] || subKey.replace(/_/g, ' ')
                  return (
                    <div key={subKey} className="bg-white/50 rounded-2xl p-5 space-y-2">
                      <h3 className="text-sm font-bold text-on-surface uppercase tracking-wide">
                        {label}
                      </h3>
                      <div className="space-y-1">
                        {renderText(text)}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </section>
        )
      })}

      {/* Footer */}
      <div className="glass-panel rounded-2xl border border-white/40 p-4 text-center text-xs text-outline">
        Generated from simulation data ({simMeta.config.population_size || 30} NPCs, {simMeta.config.num_ticks || 8} rounds, {simMeta.simulation_version?.toUpperCase()}).
        This plan is grounded in simulated consumer reactions, not real market data.
      </div>
    </div>
  )
}
