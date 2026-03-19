import { useMemo, useState } from 'react'
import type { NpcNode, Stance, SimEvent } from '../types'
import {
  STANCE_COLORS,
  buildCausalTimeline,
  getInfluenceRecords,
  getInfluencePairDetail,
  computeNetworkRole,
} from '../types'
import NpcChat from './NpcChat'

interface Props {
  npc: NpcNode
  allNpcs: Record<string, NpcNode>
  events: SimEvent[]
  simulationId: string
  onClose: () => void
  onSelectNpc: (id: string) => void
  onHighlightEdge: (edge: { source: string; target: string } | null) => void
}

const ROLE_STYLES: Record<string, { bg: string; text: string }> = {
  champion:    { bg: 'bg-green-100', text: 'text-green-700' },
  detractor:   { bg: 'bg-red-100',   text: 'text-red-700' },
  bridge:      { bg: 'bg-purple-100', text: 'text-purple-700' },
  persuadable: { bg: 'bg-yellow-100', text: 'text-yellow-700' },
  amplifier:   { bg: 'bg-blue-100',  text: 'text-blue-700' },
  passive:     { bg: 'bg-gray-100',  text: 'text-gray-500' },
}

const TIMELINE_ICONS: Record<string, string> = {
  aware:      '👁',
  reaction:   '💭',
  discussion: '💬',
  influence:  '🔄',
}

export default function NpcDetailPanel({ npc, allNpcs, events, simulationId, onClose, onSelectNpc, onHighlightEdge }: Props) {
  const color = STANCE_COLORS[npc.stance as Stance] ?? '#d1d5db'
  const p = npc.personality

  // Internal state: which influencer is expanded for detail view
  const [expandedInfluencerId, setExpandedInfluencerId] = useState<string | null>(null)

  const timeline = useMemo(
    () => buildCausalTimeline(npc.id, events),
    [npc.id, events],
  )

  const influenceRecords = useMemo(
    () => getInfluenceRecords(npc.id, events),
    [npc.id, events],
  )

  const networkRole = useMemo(
    () => computeNetworkRole(npc.id, allNpcs, events),
    [npc.id, allNpcs, events],
  )

  // Aggregate influence by source NPC
  const influenceSummary = useMemo(() => {
    const map: Record<string, { name: string; totalDelta: number; count: number }> = {}
    for (const r of influenceRecords) {
      if (!map[r.fromId]) {
        map[r.fromId] = { name: r.fromName, totalDelta: 0, count: 0 }
      }
      map[r.fromId].totalDelta += r.delta
      map[r.fromId].count += 1
    }
    return Object.entries(map)
      .map(([id, v]) => ({ id, ...v }))
      .sort((a, b) => Math.abs(b.totalDelta) - Math.abs(a.totalDelta))
  }, [influenceRecords])

  // Expanded influencer detail
  const expandedDetail = useMemo(() => {
    if (!expandedInfluencerId) return null
    return getInfluencePairDetail(npc.id, expandedInfluencerId, events)
  }, [npc.id, expandedInfluencerId, events])

  const roleStyle = ROLE_STYLES[networkRole.role] ?? ROLE_STYLES.passive

  // Handlers
  function handleInfluencerClick(influencerId: string) {
    if (expandedInfluencerId === influencerId) {
      // Collapse
      setExpandedInfluencerId(null)
      onHighlightEdge(null)
    } else {
      // Expand and highlight edge (influencer → this NPC)
      setExpandedInfluencerId(influencerId)
      onHighlightEdge({ source: influencerId, target: npc.id })
    }
  }

  function handleNavigateToNpc(id: string) {
    setExpandedInfluencerId(null)
    onHighlightEdge(null)
    onSelectNpc(id)
  }

  function handleClose() {
    onHighlightEdge(null)
    onClose()
  }

  return (
    <div className="fixed top-0 right-0 h-full w-96 bg-white border-l border-gray-200 shadow-xl z-50 overflow-y-auto">
      {/* Header */}
      <div className="sticky top-0 bg-white border-b px-4 py-3 flex justify-between items-start z-10">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-bold text-lg">{npc.name}</h3>
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${roleStyle.bg} ${roleStyle.text}`}>
              {networkRole.roleLabel}
            </span>
          </div>
          <p className="text-sm text-gray-500">{npc.occupation}, {npc.age}</p>
        </div>
        <button onClick={handleClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
      </div>

      <div className="px-4 py-3 space-y-5">
        {/* Current State */}
        <section>
          <h4 className="text-xs font-medium text-gray-400 uppercase mb-2">Current State</h4>
          <div className="flex items-center gap-3">
            <span
              className="px-3 py-1 rounded-full text-sm font-medium text-white"
              style={{ backgroundColor: color }}
            >
              {npc.stance.replace(/_/g, ' ')}
            </span>
            <span className="text-sm text-gray-600">
              Interest: {Math.round(npc.interest_score * 100)}%
            </span>
          </div>
          {npc.reasoning && (
            <p className="text-sm text-gray-600 mt-2 italic">"{npc.reasoning}"</p>
          )}
          {npc.emotional_reaction && (
            <p className="text-xs text-gray-400 mt-1">Feeling: {npc.emotional_reaction}</p>
          )}
        </section>

        {/* Network Role */}
        <section className="bg-gray-50 rounded-lg p-3">
          <h4 className="text-xs font-medium text-gray-400 uppercase mb-2">Network Role</h4>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-lg font-bold text-gray-800">#{networkRole.influenceRank}</div>
              <div className="text-[10px] text-gray-400">Influence Rank</div>
            </div>
            <div>
              <div className="text-lg font-bold text-gray-800">{networkRole.affectedCount}</div>
              <div className="text-[10px] text-gray-400">NPCs Affected</div>
            </div>
            <div>
              <div className="text-lg font-bold text-gray-800">{networkRole.totalOutInfluence.toFixed(1)}</div>
              <div className="text-[10px] text-gray-400">Total Influence</div>
            </div>
          </div>
        </section>

        {/* Influence Breakdown — interactive */}
        {influenceSummary.length > 0 && (
          <section>
            <h4 className="text-xs font-medium text-gray-400 uppercase mb-2">
              Influenced By
              <span className="ml-1 text-gray-300 normal-case font-normal">Click to inspect</span>
            </h4>
            <div className="space-y-1">
              {influenceSummary.map(src => {
                const srcNpc = allNpcs[src.id]
                const srcColor = srcNpc ? STANCE_COLORS[srcNpc.stance as Stance] ?? '#9ca3af' : '#9ca3af'
                const isPositive = src.totalDelta > 0
                const isExpanded = expandedInfluencerId === src.id

                return (
                  <div key={src.id}>
                    {/* Chip button */}
                    <button
                      onClick={() => handleInfluencerClick(src.id)}
                      className={`w-full flex items-center gap-2 px-2 py-1.5 rounded text-left transition-colors ${
                        isExpanded
                          ? 'bg-indigo-50 border border-indigo-200'
                          : 'hover:bg-gray-50 border border-transparent'
                      }`}
                    >
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: srcColor }}
                      />
                      <span className="text-xs text-gray-700 flex-1 truncate">{src.name}</span>
                      <span className="text-[10px] text-gray-400">{src.count}x</span>
                      <span className={`text-xs font-medium ${isPositive ? 'text-green-600' : 'text-red-500'}`}>
                        {isPositive ? '+' : ''}{(src.totalDelta * 100).toFixed(0)}%
                      </span>
                      <span className="text-gray-300 text-xs">{isExpanded ? '▾' : '▸'}</span>
                    </button>

                    {/* Expanded detail */}
                    {isExpanded && expandedDetail && (
                      <div className="ml-5 mt-1 mb-2 border-l-2 border-indigo-200 pl-3 space-y-2">
                        {/* Summary line */}
                        <div className="flex items-center gap-2 text-xs">
                          <span className={`font-medium ${
                            expandedDetail.netDirection === 'positive' ? 'text-green-600' :
                            expandedDetail.netDirection === 'negative' ? 'text-red-500' :
                            'text-gray-500'
                          }`}>
                            Net: {expandedDetail.totalDelta > 0 ? '+' : ''}
                            {(expandedDetail.totalDelta * 100).toFixed(0)}%
                            ({expandedDetail.netDirection})
                          </span>
                          <span className="text-gray-400">
                            {expandedDetail.interactions.length} interaction{expandedDetail.interactions.length !== 1 ? 's' : ''}
                          </span>
                        </div>

                        {/* Per-interaction timeline */}
                        {expandedDetail.interactions.map((int, i) => (
                          <div key={i} className="text-xs">
                            <div className="flex items-center gap-2">
                              <span className="text-gray-400 font-mono w-6">T{int.tick}</span>
                              <span className={`font-medium ${int.delta > 0 ? 'text-green-600' : int.delta < 0 ? 'text-red-500' : 'text-gray-400'}`}>
                                {int.delta > 0 ? '+' : ''}{(int.delta * 100).toFixed(0)}%
                              </span>
                              {int.resultStance && (
                                <span
                                  className="text-[10px] px-1.5 py-0.5 rounded text-white"
                                  style={{ backgroundColor: STANCE_COLORS[int.resultStance as Stance] ?? '#9ca3af' }}
                                >
                                  {int.resultStance.replace(/_/g, ' ')}
                                </span>
                              )}
                            </div>
                            {int.keyPoint && (
                              <p className="text-gray-500 mt-0.5 ml-8 italic">"{int.keyPoint}"</p>
                            )}
                          </div>
                        ))}

                        {/* Navigate to influencer */}
                        <button
                          onClick={() => handleNavigateToNpc(src.id)}
                          className="text-[11px] text-indigo-500 hover:text-indigo-700 ml-8"
                        >
                          View {src.name.split(' ')[0]}'s profile →
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {/* Causal Timeline */}
        {timeline.length > 0 && (
          <section>
            <h4 className="text-xs font-medium text-gray-400 uppercase mb-2">
              Belief Timeline
              <span className="ml-1 text-gray-300 normal-case font-normal">How their opinion formed</span>
            </h4>
            <div className="space-y-0 relative">
              <div className="absolute left-[11px] top-2 bottom-2 w-px bg-gray-200" />

              {timeline.map((entry, i) => (
                <div key={i} className="flex gap-3 py-1.5 relative">
                  <div className="w-6 h-6 flex items-center justify-center text-xs flex-shrink-0 bg-white z-[1]">
                    {TIMELINE_ICONS[entry.type] ?? '·'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[10px] text-gray-400 font-mono">T{entry.tick}</span>
                      {entry.stance && (
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded text-white"
                          style={{ backgroundColor: STANCE_COLORS[entry.stance as Stance] ?? '#9ca3af' }}
                        >
                          {entry.stance.replace(/_/g, ' ')}
                        </span>
                      )}
                      {entry.delta !== undefined && entry.delta !== 0 && (
                        <span className={`text-[10px] font-medium ${entry.delta > 0 ? 'text-green-600' : 'text-red-500'}`}>
                          {entry.delta > 0 ? '+' : ''}{(entry.delta * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-600 mt-0.5">{entry.detail}</p>
                    {entry.keyPoint && (
                      <p className="text-[10px] text-gray-400 mt-0.5 italic">"{entry.keyPoint}"</p>
                    )}
                    {entry.partnerId && (
                      <button
                        onClick={() => handleInfluencerClick(entry.partnerId!)}
                        className="text-[10px] text-indigo-500 hover:text-indigo-700 mt-0.5"
                      >
                        Inspect influence from {entry.partnerName ?? entry.partnerId}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Personality */}
        <section>
          <h4 className="text-xs font-medium text-gray-400 uppercase mb-2">Personality</h4>
          <div className="space-y-1.5">
            {([
              ['Openness', p.openness],
              ['Skepticism', p.skepticism],
              ['Tech Savviness', p.tech_savviness],
              ['Price Sensitivity', p.price_sensitivity],
              ['Social Influence', p.social_influence],
              ['Novelty Seeking', p.novelty_seeking],
            ] as [string, number][]).map(([label, val]) => (
              <div key={label} className="flex items-center gap-2 text-xs">
                <span className="w-28 text-gray-500">{label}</span>
                <div className="flex-1 bg-gray-100 rounded-full h-1.5">
                  <div
                    className="bg-indigo-400 h-1.5 rounded-full"
                    style={{ width: `${val * 100}%` }}
                  />
                </div>
                <span className="w-8 text-right text-gray-400">{(val * 100).toFixed(0)}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Interests & Pain Points */}
        <section>
          <h4 className="text-xs font-medium text-gray-400 uppercase mb-2">Interests</h4>
          <div className="flex flex-wrap gap-1">
            {npc.interests.map(i => (
              <span key={i} className="text-xs bg-blue-50 text-blue-600 px-2 py-0.5 rounded">{i}</span>
            ))}
          </div>
        </section>

        <section>
          <h4 className="text-xs font-medium text-gray-400 uppercase mb-2">Pain Points</h4>
          <div className="flex flex-wrap gap-1">
            {npc.pain_points.map(pt => (
              <span key={pt} className="text-xs bg-red-50 text-red-500 px-2 py-0.5 rounded">{pt}</span>
            ))}
          </div>
        </section>

        {/* Objections */}
        {npc.objections.length > 0 && (
          <section>
            <h4 className="text-xs font-medium text-gray-400 uppercase mb-2">Objections</h4>
            <ul className="space-y-1">
              {npc.objections.map((o, i) => (
                <li key={i} className="text-sm text-red-600 flex items-start gap-1">
                  <span className="mt-0.5">!</span> {o}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Payment + Recommend */}
        <section className="flex gap-3 pt-2 border-t">
          <span className={`text-xs px-2 py-1 rounded ${npc.would_pay ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
            {npc.would_pay ? 'Would pay' : 'Would not pay'}
          </span>
          <span className={`text-xs px-2 py-1 rounded ${npc.would_recommend ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-500'}`}>
            {npc.would_recommend ? 'Would recommend' : 'Would not recommend'}
          </span>
        </section>

        {/* Chat with this NPC */}
        {npc.aware && (
          <NpcChat npc={npc} events={events} simulationId={simulationId} />
        )}
      </div>
    </div>
  )
}
