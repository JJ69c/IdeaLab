import { useEffect, useRef } from 'react'
import type { SimEvent } from '../types'

function formatEvent(e: SimEvent): string | null {
  const d = e.data as Record<string, unknown>
  switch (e.type) {
    case 'tick_start':
      return null // shown as separator
    case 'npc_aware':
      if (d.source === 'direct_exposure')
        return `${d.name} noticed the idea (direct exposure)`
      return `${d.name} heard about it from ${d.source_name}`
    case 'npc_reaction':
      return `${d.name} reacted: ${d.stance} (${Math.round((d.interest_score as number) * 100)}%)`
    case 'npc_state_change':
      return `${d.name} → ${(d.new_stance as string).replace(/_/g, ' ')}`
    case 'discussion_start':
      return `${d.npc_a_name} is discussing with ${d.npc_b_name}...`
    case 'discussion_end':
      return `Discussion: ${d.key_point || 'exchanged views'}`
    case 'npc_spread':
      return `${d.source_name} spread the idea to ${d.target_name}`
    case 'simulation_complete':
      return 'Simulation complete!'
    case 'error':
      return `Error: ${d.message}`
    default:
      return null
  }
}

const TYPE_COLORS: Record<string, string> = {
  npc_aware: 'text-blue-500',
  npc_reaction: 'text-gray-600',
  npc_state_change: 'text-indigo-600 font-medium',
  discussion_start: 'text-purple-500',
  discussion_end: 'text-purple-700',
  npc_spread: 'text-green-600',
  simulation_complete: 'text-emerald-700 font-bold',
  error: 'text-red-600 font-medium',
}

export default function EventFeed({ events }: { events: SimEvent[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  let lastTick = 0

  return (
    <div className="h-full overflow-y-auto text-xs space-y-0.5 pr-1">
      {events.map((e, i) => {
        const text = formatEvent(e)
        if (!text) {
          // Tick separator
          if (e.type === 'tick_start') {
            lastTick = e.tick
            return (
              <div key={i} className="sticky top-0 bg-gray-50 border-b border-gray-200 py-1 px-1 text-gray-400 font-medium mt-2">
                Round {e.tick}
              </div>
            )
          }
          return null
        }
        return (
          <div key={i} className={`py-0.5 px-1 ${TYPE_COLORS[e.type] || 'text-gray-500'}`}>
            {text}
          </div>
        )
      })}
      <div ref={bottomRef} />
    </div>
  )
}
