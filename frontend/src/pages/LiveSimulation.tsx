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
    setHighlightedEdge(null) // Clear edge highlight when switching NPCs
  }, [])

  const handleClosePanel = useCallback(() => {
    setSelectedNpcId(null)
    setHighlightedEdge(null)
  }, [])

  return (
    <div className="fixed inset-0 flex flex-col bg-gray-50">
      {/* Top bar */}
      <div className="flex items-center gap-4 bg-white border-b px-4 py-2">
        <Link to="/dashboard" className="text-indigo-600 text-sm font-medium">&larr; Dashboard</Link>
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
            className="text-xs bg-indigo-600 text-white px-3 py-1.5 rounded hover:bg-indigo-700"
          >
            View Full Report
          </Link>
        )}
      </div>

      {/* Round summary card */}
      <RoundSummaryCard
        events={state.events}
        currentTick={state.currentTick}
      />

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
          <div className="absolute bottom-3 right-3 flex flex-wrap gap-2 bg-white/80 rounded-lg px-3 py-2 backdrop-blur-sm">
            {(Object.entries(STANCE_COLORS) as [Stance, string][])
              .filter(([s]) => s !== 'aware')
              .map(([stance, color]) => (
                <div key={stance} className="flex items-center gap-1 text-xs text-gray-500">
                  <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                  {stance.replace(/_/g, ' ')}
                </div>
              ))}
          </div>
        </div>

        {/* Event feed sidebar */}
        <div className="w-72 border-l border-gray-200 bg-white flex flex-col">
          <div className="px-3 py-2 border-b border-gray-100 text-xs font-medium text-gray-400 uppercase">
            Event Feed
          </div>
          <div className="flex-1 min-h-0">
            <EventFeed events={state.events} />
          </div>
        </div>
      </div>

      {/* Bottom metrics bar */}
      <MetricsBar metrics={state.metrics} previousMetrics={state.previousMetrics} />

      {/* NPC detail panel (slide-in) — key resets internal state on NPC change */}
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
