import { useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useSimulationStream } from '../hooks/useSimulationStream'
import SimulationGraph from '../components/SimulationGraph'
import EventFeed from '../components/EventFeed'
import NpcDetailPanel from '../components/NpcDetailPanel'
import TickProgress from '../components/TickProgress'
import MetricsBar from '../components/MetricsBar'
import RoundSummaryCard from '../components/RoundSummaryCard'
import type { Stance } from '../types'
import { STANCE_COLORS } from '../types'

export default function LiveSimulation() {
  const { id } = useParams<{ id: string }>()
  const state = useSimulationStream(id)
  const [selectedNpcId, setSelectedNpcId] = useState<string | null>(null)
  const [highlightedEdge, setHighlightedEdge] = useState<{ source: string; target: string } | null>(null)

  const selectedNpc = selectedNpcId ? state.npcs[selectedNpcId] : null

  const handleSelectNpc = useCallback((npcId: string | null) => {
    setSelectedNpcId(npcId)
    setHighlightedEdge(null)
  }, [])

  const handleClosePanel = useCallback(() => {
    setSelectedNpcId(null)
    setHighlightedEdge(null)
  }, [])

  return (
    <div className="fixed inset-0 flex flex-col bg-background font-inter">
      {/* Background glow accents */}
      <div className="fixed top-[-10%] right-[-5%] w-[40%] h-[40%] bg-primary/10 rounded-full blur-[120px] -z-10 pointer-events-none" />
      <div className="fixed bottom-[-10%] left-[20%] w-[30%] h-[30%] bg-secondary-container/20 rounded-full blur-[100px] -z-10 pointer-events-none" />

      {/* Top bar */}
      <div className="flex items-center gap-4 glass-panel border-b border-outline-variant/30 px-5 py-2.5 z-10">
        <Link
          to="/dashboard"
          className="flex items-center gap-1.5 text-primary text-sm font-medium hover:text-primary-container transition-colors"
        >
          <span className="material-symbols-outlined text-[18px]">arrow_back</span>
          Dashboard
        </Link>
        <div className="flex-1">
          <TickProgress
            currentTick={state.currentTick}
            maxTicks={state.maxTicks}
            isRunning={state.isRunning}
            isComplete={state.isComplete}
            ideaTitle={state.ideaTitle}
            events={state.events}
          />
        </div>
        {state.isComplete && (
          <Link
            to={`/report/${id}`}
            className="flex items-center gap-1.5 text-xs bg-gradient-to-r from-primary to-primary-container text-on-primary px-4 py-2 rounded-xl font-semibold shadow-lg shadow-primary/20 hover:scale-[0.98] active:scale-95 transition-transform"
          >
            <span className="material-symbols-outlined text-[16px]">analytics</span>
            View Full Report
          </Link>
        )}
      </div>

      {/* Round summary card */}
      <RoundSummaryCard
        events={state.events}
        currentTick={state.currentTick}
      />

      {/* Error overlay */}
      {state.events.some(e => e.type === 'error') && !state.isComplete && (
        <div className="mx-4 mt-2 glass-panel rounded-2xl border border-red-200 px-5 py-3 flex items-center gap-3">
          <span className="material-symbols-outlined text-[20px] text-red-500">error</span>
          <div className="flex-1">
            <span className="text-sm font-semibold text-red-700">Simulation failed</span>
            <p className="text-xs text-red-600 mt-0.5">
              {(state.events.find(e => e.type === 'error')?.data?.message as string) || 'An unexpected error occurred'}
            </p>
          </div>
          <Link
            to="/dashboard"
            className="text-xs font-semibold text-red-600 hover:text-red-800 px-3 py-1.5 rounded-lg border border-red-200 hover:border-red-300 transition-colors"
          >
            Back to Dashboard
          </Link>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex min-h-0">
        {/* Graph area */}
        <div className="flex-1 relative p-2">
          <SimulationGraph
            npcs={state.npcs}
            edges={state.edges}
            events={state.events}
            activeDiscussions={state.activeDiscussions}
            selectedNpcId={selectedNpcId}
            highlightedEdge={highlightedEdge}
            onSelectNpc={handleSelectNpc}
          />
          {/* Legend */}
          <div className="absolute bottom-3 right-3 flex flex-wrap gap-2.5 glass-panel rounded-2xl px-4 py-2.5 border border-white/40 shadow-sm">
            {(Object.entries(STANCE_COLORS) as [Stance, string][])
              .filter(([s]) => s !== 'aware')
              .map(([stance, color]) => (
                <div key={stance} className="flex items-center gap-1.5 text-xs text-on-surface-variant">
                  <div className="w-2.5 h-2.5 rounded-full shadow-sm" style={{ backgroundColor: color }} />
                  <span className="capitalize">{stance.replace(/_/g, ' ')}</span>
                </div>
              ))}
          </div>
        </div>

        {/* Event feed sidebar */}
        <div className="w-72 glass-panel-solid border-l border-outline-variant/30 flex flex-col">
          <div className="px-4 py-3 border-b border-outline-variant/20 flex items-center gap-2">
            <span className="material-symbols-outlined text-[16px] text-primary">rss_feed</span>
            <span className="text-xs font-semibold text-on-surface-variant uppercase tracking-widest">Event Feed</span>
          </div>
          <div className="flex-1 min-h-0">
            <EventFeed events={state.events} />
          </div>
        </div>
      </div>

      {/* Bottom metrics bar */}
      <MetricsBar metrics={state.metrics} previousMetrics={state.previousMetrics} />

      {/* NPC detail panel (slide-in) */}
      {selectedNpc && (
        <NpcDetailPanel
          key={selectedNpc.id}
          npc={selectedNpc}
          allNpcs={state.npcs}
          events={state.events}
          simulationId={id!}
          onClose={handleClosePanel}
          onSelectNpc={handleSelectNpc}
          onHighlightEdge={setHighlightedEdge}
        />
      )}
    </div>
  )
}
