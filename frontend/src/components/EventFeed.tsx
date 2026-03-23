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

const TYPE_ICONS: Record<string, { icon: string; color: string }> = {
  npc_aware: { icon: 'visibility', color: 'text-primary' },
  npc_reaction: { icon: 'psychology', color: 'text-on-surface-variant' },
  npc_state_change: { icon: 'swap_horiz', color: 'text-secondary font-medium' },
  discussion_start: { icon: 'forum', color: 'text-tertiary' },
  discussion_end: { icon: 'chat_bubble', color: 'text-tertiary' },
  npc_spread: { icon: 'share', color: 'text-green-600' },
  simulation_complete: { icon: 'check_circle', color: 'text-green-600 font-bold' },
  error: { icon: 'error', color: 'text-error font-medium' },
}

export default function EventFeed({ events }: { events: SimEvent[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  return (
    <div className="h-full overflow-y-auto glass-scrollbar text-xs space-y-0.5 px-1">
      {events.map((e, i) => {
        const text = formatEvent(e)
        if (!text) {
          if (e.type === 'tick_start') {
            return (
              <div key={i} className="sticky top-0 bg-surface-container/90 backdrop-blur-sm border-b border-outline-variant/15 py-1.5 px-3 text-outline font-semibold mt-2 rounded-lg uppercase tracking-widest text-[10px]">
                <span className="material-symbols-outlined text-[12px] mr-1 align-middle">schedule</span>
                Round {e.tick}
              </div>
            )
          }
          return null
        }
        const typeInfo = TYPE_ICONS[e.type]
        return (
          <div key={i} className={`py-1 px-2 flex items-start gap-1.5 rounded-lg hover:bg-surface-container-low/50 transition-colors ${typeInfo?.color || 'text-on-surface-variant'}`}>
            {typeInfo && <span className="material-symbols-outlined text-[12px] mt-0.5 flex-shrink-0">{typeInfo.icon}</span>}
            <span>{text}</span>
          </div>
        )
      })}
      <div ref={bottomRef} />
    </div>
  )
}
