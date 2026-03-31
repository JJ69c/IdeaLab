import { useEffect, useMemo, useState } from 'react'
import type { SimEvent } from '../types'
import { computeRoundNarrative } from '../types'

interface Props {
  currentTick: number
  maxTicks: number
  isRunning: boolean
  isComplete: boolean
  ideaTitle: string
  events: SimEvent[]
}

// Rotating flavor messages shown during prep phases
const PREP_FLAVORS: Record<string, string[]> = {
  competitor_research: [
    'Investigating market landscape...',
    'Analyzing competitor positioning...',
    'Comparing pricing strategies...',
    'Mapping competitive strengths...',
    'Evaluating market saturation...',
  ],
  world_builder: [
    'Constructing market environment...',
    'Modeling economic conditions...',
    'Calibrating cultural context...',
    'Mapping industry dynamics...',
    'Setting up the stage...',
  ],
  npc_enrichment: [
    'Getting to know the population...',
    'Building personal histories...',
    'Calibrating consumer preferences...',
    'Modeling decision patterns...',
    'Assigning life experiences...',
  ],
}

const PHASE_LABELS: Record<string, string> = {
  competitor_research: 'Competitor Research',
  world_builder: 'World Building',
  world_builder_complete: 'World Ready',
  npc_enrichment: 'NPC Enrichment',
  npc_enrichment_complete: 'Population Ready',
}

const PHASE_ORDER = ['competitor_research', 'world_builder', 'npc_enrichment']

function useRotatingText(texts: string[], intervalMs = 3000): string {
  const [index, setIndex] = useState(0)
  useEffect(() => {
    if (texts.length <= 1) return
    const id = setInterval(() => setIndex(i => (i + 1) % texts.length), intervalMs)
    return () => clearInterval(id)
  }, [texts, intervalMs])
  return texts[index] || texts[0]
}

export default function TickProgress({ currentTick, maxTicks, isRunning, isComplete, ideaTitle, events }: Props) {
  const pct = maxTicks > 0 ? (currentTick / maxTicks) * 100 : 0

  const narrative = useMemo(
    () => currentTick > 0 ? computeRoundNarrative(events, currentTick) : '',
    [events, currentTick],
  )

  // V2 prep phase: show world-building / enrichment progress
  const v2Progress = useMemo(() => {
    const v2Events = events.filter(e => e.type === 'v2_progress')
    if (v2Events.length === 0) return null
    const latest = v2Events[v2Events.length - 1]
    return latest.data as { phase: string; message: string }
  }, [events])

  // Track which phases have been completed
  const completedPhases = useMemo(() => {
    const phases = new Set<string>()
    for (const e of events) {
      if (e.type === 'v2_progress') {
        const phase = (e.data as { phase: string }).phase
        if (phase.endsWith('_complete')) {
          phases.add(phase.replace('_complete', ''))
        }
        // competitor_research doesn't have a _complete event, it transitions to world_builder
        if (phase === 'world_builder' || phase === 'world_builder_complete') {
          phases.add('competitor_research')
        }
        if (phase === 'npc_enrichment' || phase === 'npc_enrichment_complete') {
          phases.add('world_builder')
        }
      }
    }
    return phases
  }, [events])

  // Get the current active phase key (without _complete suffix)
  const activePhaseKey = useMemo(() => {
    if (!v2Progress) return ''
    return v2Progress.phase.replace('_complete', '')
  }, [v2Progress])

  // Rotating flavor text for the current phase
  const flavorTexts = PREP_FLAVORS[activePhaseKey] || [v2Progress?.message || 'Preparing...']
  const rotatingText = useRotatingText(flavorTexts)

  // If we're in V2 prep phase (no ticks started yet), show prep UI
  if (v2Progress && currentTick === 0 && isRunning) {
    return (
      <div className="flex flex-col gap-2">
        {/* Top row: title + status */}
        <div className="flex items-center gap-4">
          <h2 className="font-semibold text-on-surface truncate max-w-xs tracking-tight">
            {ideaTitle || 'Simulation'}
          </h2>
          <div className="flex-1 flex items-center gap-3">
            {/* Phase steps */}
            <div className="flex items-center gap-1">
              {PHASE_ORDER.map((phase, i) => {
                const isDone = completedPhases.has(phase)
                const isActive = activePhaseKey === phase && !isDone
                return (
                  <div key={phase} className="flex items-center gap-1">
                    {i > 0 && (
                      <div className={`w-4 h-px ${isDone ? 'bg-purple-400' : 'bg-outline-variant/30'}`} />
                    )}
                    <div className="flex items-center gap-1.5">
                      <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-all duration-500 ${
                        isDone
                          ? 'bg-purple-500 text-white'
                          : isActive
                            ? 'bg-purple-100 text-purple-600 ring-2 ring-purple-400/50 animate-pulse'
                            : 'bg-surface-container text-outline'
                      }`}>
                        {isDone ? (
                          <span className="material-symbols-outlined text-[12px]">check</span>
                        ) : (
                          i + 1
                        )}
                      </div>
                      <span className={`text-[10px] font-medium hidden md:inline transition-colors ${
                        isDone ? 'text-purple-600' : isActive ? 'text-purple-600' : 'text-outline'
                      }`}>
                        {PHASE_LABELS[phase] || phase}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-purple-500 animate-pulse" />
            <span className="text-xs text-purple-600 font-medium">V2 Prep</span>
          </div>
        </div>

        {/* Bottom row: rotating flavor text */}
        <div className="flex items-center gap-2 ml-0 md:ml-[calc(theme(maxWidth.xs)+1rem)]">
          <span className="material-symbols-outlined text-[14px] text-purple-400 animate-spin">progress_activity</span>
          <span
            key={rotatingText}
            className="text-xs text-on-surface-variant animate-[fadeIn_0.5s_ease-in-out]"
          >
            {rotatingText}
          </span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-4">
      <h2 className="font-semibold text-on-surface truncate max-w-xs tracking-tight">
        {ideaTitle || 'Simulation'}
      </h2>
      <div className="flex items-center gap-3 flex-1">
        <span className="text-xs text-outline whitespace-nowrap font-medium">
          Round {currentTick}/{maxTicks}
        </span>
        <div className="flex-1 bg-surface-container-high rounded-full h-2 max-w-xs overflow-hidden">
          <div
            className="bg-gradient-to-r from-primary to-primary-container h-2 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        {narrative && (
          <span className="text-xs text-on-surface-variant truncate max-w-md" title={narrative}>
            {narrative}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <span className={`inline-block w-2 h-2 rounded-full ${
          isComplete ? 'bg-green-500' : isRunning ? 'bg-primary animate-pulse' : 'bg-outline-variant'
        }`} />
        <span className="text-xs text-on-surface-variant font-medium">
          {isComplete ? 'Complete' : isRunning ? 'Live' : 'Waiting'}
        </span>
      </div>
    </div>
  )
}
