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

const ROLE_STYLES: Record<string, { bg: string; text: string; icon: string }> = {
  champion:    { bg: 'bg-green-50', text: 'text-green-700', icon: 'star' },
  detractor:   { bg: 'bg-red-50',   text: 'text-red-700', icon: 'thumb_down' },
  bridge:      { bg: 'bg-purple-50', text: 'text-purple-700', icon: 'hub' },
  persuadable: { bg: 'bg-amber-50', text: 'text-amber-700', icon: 'psychology' },
  amplifier:   { bg: 'bg-blue-50',  text: 'text-blue-700', icon: 'campaign' },
  passive:     { bg: 'bg-surface-container', text: 'text-outline', icon: 'remove' },
}

const TIMELINE_ICONS: Record<string, string> = {
  aware:      'visibility',
  reaction:   'psychology',
  discussion: 'forum',
  influence:  'swap_horiz',
}

export default function NpcDetailPanel({ npc, allNpcs, events, simulationId, onClose, onSelectNpc, onHighlightEdge }: Props) {
  const color = STANCE_COLORS[npc.stance as Stance] ?? '#d1d5db'
  const p = npc.personality

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

  const expandedDetail = useMemo(() => {
    if (!expandedInfluencerId) return null
    return getInfluencePairDetail(npc.id, expandedInfluencerId, events)
  }, [npc.id, expandedInfluencerId, events])

  const roleStyle = ROLE_STYLES[networkRole.role] ?? ROLE_STYLES.passive

  function handleInfluencerClick(influencerId: string) {
    if (expandedInfluencerId === influencerId) {
      setExpandedInfluencerId(null)
      onHighlightEdge(null)
    } else {
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
    <div className="fixed top-0 right-0 h-full w-[400px] glass-panel-solid border-l border-outline-variant/30 shadow-[-20px_0_60px_-15px_rgba(25,27,36,0.08)] z-50 overflow-y-auto glass-scrollbar">
      {/* Header */}
      <div className="sticky top-0 glass-panel border-b border-outline-variant/20 px-5 py-4 flex justify-between items-start z-10">
        <div>
          <div className="flex items-center gap-2.5">
            <h3 className="font-bold text-lg text-on-surface tracking-tight">{npc.name}</h3>
            <span className={`text-[10px] px-2 py-0.5 rounded-lg font-semibold flex items-center gap-1 ${roleStyle.bg} ${roleStyle.text}`}>
              <span className="material-symbols-outlined text-[12px]">{roleStyle.icon}</span>
              {networkRole.roleLabel}
            </span>
          </div>
          <p className="text-sm text-on-surface-variant mt-0.5">{npc.occupation}, {npc.age}</p>
        </div>
        <button onClick={handleClose} className="text-outline hover:text-on-surface transition-colors p-1 rounded-lg hover:bg-surface-container-high">
          <span className="material-symbols-outlined text-[20px]">close</span>
        </button>
      </div>

      <div className="px-5 py-4 space-y-6">
        {/* Current State */}
        <section>
          <div className="flex items-center gap-2 mb-3">
            <span className="material-symbols-outlined text-[16px] text-primary">radio_button_checked</span>
            <h4 className="text-xs font-semibold text-outline uppercase tracking-widest">Current State</h4>
          </div>
          <div className="flex items-center gap-3">
            <span
              className="px-3 py-1 rounded-full text-sm font-semibold text-white shadow-sm"
              style={{ backgroundColor: color }}
            >
              {npc.stance.replace(/_/g, ' ')}
            </span>
            <span className="text-sm text-on-surface-variant font-medium">
              Interest: <span className="text-on-surface font-bold">{Math.round(npc.interest_score * 100)}%</span>
            </span>
          </div>
          {npc.reasoning && (
            <p className="text-sm text-on-surface-variant mt-2.5 italic bg-surface-container-low rounded-xl px-3 py-2 border border-outline-variant/15">
              "{npc.reasoning}"
            </p>
          )}
          {npc.emotional_reaction && (
            <p className="text-xs text-outline mt-1.5 flex items-center gap-1">
              <span className="material-symbols-outlined text-[14px]">mood</span>
              Feeling: {npc.emotional_reaction}
            </p>
          )}
        </section>

        {/* Network Role */}
        <section className="bg-surface-container-low rounded-2xl p-4 border border-outline-variant/15">
          <div className="flex items-center gap-2 mb-3">
            <span className="material-symbols-outlined text-[16px] text-primary">hub</span>
            <h4 className="text-xs font-semibold text-outline uppercase tracking-widest">Network Role</h4>
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="bg-white/60 rounded-xl p-2.5">
              <div className="text-lg font-bold text-on-surface">#{networkRole.influenceRank}</div>
              <div className="text-[10px] text-outline uppercase tracking-wide">Influence</div>
            </div>
            <div className="bg-white/60 rounded-xl p-2.5">
              <div className="text-lg font-bold text-on-surface">{networkRole.affectedCount}</div>
              <div className="text-[10px] text-outline uppercase tracking-wide">Affected</div>
            </div>
            <div className="bg-white/60 rounded-xl p-2.5">
              <div className="text-lg font-bold text-on-surface">{networkRole.totalOutInfluence.toFixed(1)}</div>
              <div className="text-[10px] text-outline uppercase tracking-wide">Total Inf.</div>
            </div>
          </div>
        </section>

        {/* Influence Breakdown */}
        {influenceSummary.length > 0 && (
          <section>
            <div className="flex items-center gap-2 mb-3">
              <span className="material-symbols-outlined text-[16px] text-primary">people</span>
              <h4 className="text-xs font-semibold text-outline uppercase tracking-widest">
                Influenced By
              </h4>
              <span className="text-[10px] text-outline-variant font-normal normal-case">Click to inspect</span>
            </div>
            <div className="space-y-1">
              {influenceSummary.map(src => {
                const srcNpc = allNpcs[src.id]
                const srcColor = srcNpc ? STANCE_COLORS[srcNpc.stance as Stance] ?? '#9ca3af' : '#9ca3af'
                const isPositive = src.totalDelta > 0
                const isExpanded = expandedInfluencerId === src.id

                return (
                  <div key={src.id}>
                    <button
                      onClick={() => handleInfluencerClick(src.id)}
                      className={`w-full flex items-center gap-2 px-3 py-2 rounded-xl text-left transition-all ${
                        isExpanded
                          ? 'bg-primary/5 border border-primary/20 shadow-sm'
                          : 'hover:bg-surface-container-low border border-transparent'
                      }`}
                    >
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0 shadow-sm"
                        style={{ backgroundColor: srcColor }}
                      />
                      <span className="text-xs text-on-surface flex-1 truncate font-medium">{src.name}</span>
                      <span className="text-[10px] text-outline">{src.count}x</span>
                      <span className={`text-xs font-semibold ${isPositive ? 'text-green-600' : 'text-error'}`}>
                        {isPositive ? '+' : ''}{(src.totalDelta * 100).toFixed(0)}%
                      </span>
                      <span className="material-symbols-outlined text-[14px] text-outline-variant">
                        {isExpanded ? 'expand_more' : 'chevron_right'}
                      </span>
                    </button>

                    {isExpanded && expandedDetail && (
                      <div className="ml-6 mt-1 mb-2 border-l-2 border-primary/20 pl-3 space-y-2">
                        <div className="flex items-center gap-2 text-xs">
                          <span className={`font-semibold ${
                            expandedDetail.netDirection === 'positive' ? 'text-green-600' :
                            expandedDetail.netDirection === 'negative' ? 'text-error' :
                            'text-outline'
                          }`}>
                            Net: {expandedDetail.totalDelta > 0 ? '+' : ''}
                            {(expandedDetail.totalDelta * 100).toFixed(0)}%
                            ({expandedDetail.netDirection})
                          </span>
                          <span className="text-outline">
                            {expandedDetail.interactions.length} interaction{expandedDetail.interactions.length !== 1 ? 's' : ''}
                          </span>
                        </div>

                        {expandedDetail.interactions.map((int, i) => (
                          <div key={i} className="text-xs">
                            <div className="flex items-center gap-2">
                              <span className="text-outline font-mono w-6 text-[10px]">T{int.tick}</span>
                              <span className={`font-semibold ${int.delta > 0 ? 'text-green-600' : int.delta < 0 ? 'text-error' : 'text-outline'}`}>
                                {int.delta > 0 ? '+' : ''}{(int.delta * 100).toFixed(0)}%
                              </span>
                              {int.resultStance && (
                                <span
                                  className="text-[10px] px-1.5 py-0.5 rounded-md text-white font-medium"
                                  style={{ backgroundColor: STANCE_COLORS[int.resultStance as Stance] ?? '#9ca3af' }}
                                >
                                  {int.resultStance.replace(/_/g, ' ')}
                                </span>
                              )}
                            </div>
                            {int.keyPoint && (
                              <p className="text-on-surface-variant mt-0.5 ml-8 italic text-[11px]">"{int.keyPoint}"</p>
                            )}
                          </div>
                        ))}

                        <button
                          onClick={() => handleNavigateToNpc(src.id)}
                          className="text-[11px] text-primary hover:text-primary-container font-medium ml-8 flex items-center gap-0.5"
                        >
                          View {src.name.split(' ')[0]}'s profile
                          <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
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
            <div className="flex items-center gap-2 mb-3">
              <span className="material-symbols-outlined text-[16px] text-primary">timeline</span>
              <h4 className="text-xs font-semibold text-outline uppercase tracking-widest">
                Belief Timeline
              </h4>
              <span className="text-[10px] text-outline-variant font-normal normal-case">How their opinion formed</span>
            </div>
            <div className="space-y-0 relative">
              <div className="absolute left-[11px] top-2 bottom-2 w-px bg-outline-variant/30" />

              {timeline.map((entry, i) => (
                <div key={i} className="flex gap-3 py-2 relative">
                  <div className="w-6 h-6 flex items-center justify-center flex-shrink-0 bg-surface-container-lowest z-[1] rounded-full border border-outline-variant/20">
                    <span className="material-symbols-outlined text-[14px] text-primary">
                      {TIMELINE_ICONS[entry.type] ?? 'circle'}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[10px] text-outline font-mono font-semibold">T{entry.tick}</span>
                      {entry.stance && (
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded-md text-white font-medium"
                          style={{ backgroundColor: STANCE_COLORS[entry.stance as Stance] ?? '#9ca3af' }}
                        >
                          {entry.stance.replace(/_/g, ' ')}
                        </span>
                      )}
                      {entry.delta !== undefined && entry.delta !== 0 && (
                        <span className={`text-[10px] font-semibold ${entry.delta > 0 ? 'text-green-600' : 'text-error'}`}>
                          {entry.delta > 0 ? '+' : ''}{(entry.delta * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-on-surface-variant mt-0.5">{entry.detail}</p>
                    {entry.keyPoint && (
                      <p className="text-[10px] text-outline mt-0.5 italic">"{entry.keyPoint}"</p>
                    )}
                    {entry.partnerId && (
                      <button
                        onClick={() => handleInfluencerClick(entry.partnerId!)}
                        className="text-[10px] text-primary hover:text-primary-container mt-0.5 flex items-center gap-0.5 font-medium"
                      >
                        <span className="material-symbols-outlined text-[12px]">search</span>
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
          <div className="flex items-center gap-2 mb-3">
            <span className="material-symbols-outlined text-[16px] text-primary">tune</span>
            <h4 className="text-xs font-semibold text-outline uppercase tracking-widest">Personality</h4>
          </div>
          <div className="space-y-2.5">
            {([
              ['Openness', p.openness],
              ['Skepticism', p.skepticism],
              ['Tech Savviness', p.tech_savviness],
              ['Price Sensitivity', p.price_sensitivity],
              ['Social Influence', p.social_influence],
              ['Novelty Seeking', p.novelty_seeking],
            ] as [string, number][]).map(([label, val]) => (
              <div key={label} className="flex items-center gap-2 text-xs">
                <span className="w-28 text-on-surface-variant font-medium">{label}</span>
                <div className="flex-1 bg-surface-container-high rounded-full h-1.5 overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-primary to-primary-container h-1.5 rounded-full transition-all duration-300"
                    style={{ width: `${val * 100}%` }}
                  />
                </div>
                <span className="w-8 text-right text-outline font-semibold tabular-nums">{(val * 100).toFixed(0)}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Interests & Pain Points */}
        <section>
          <div className="flex items-center gap-2 mb-3">
            <span className="material-symbols-outlined text-[16px] text-primary">interests</span>
            <h4 className="text-xs font-semibold text-outline uppercase tracking-widest">Interests</h4>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {npc.interests.map(i => (
              <span key={i} className="text-xs bg-secondary-fixed text-on-secondary-fixed px-2.5 py-1 rounded-lg font-medium">{i}</span>
            ))}
          </div>
        </section>

        <section>
          <div className="flex items-center gap-2 mb-3">
            <span className="material-symbols-outlined text-[16px] text-error">warning</span>
            <h4 className="text-xs font-semibold text-outline uppercase tracking-widest">Pain Points</h4>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {npc.pain_points.map(pt => (
              <span key={pt} className="text-xs bg-error-container text-on-error-container px-2.5 py-1 rounded-lg font-medium">{pt}</span>
            ))}
          </div>
        </section>

        {/* Objections */}
        {npc.objections.length > 0 && (
          <section>
            <div className="flex items-center gap-2 mb-3">
              <span className="material-symbols-outlined text-[16px] text-error">report_problem</span>
              <h4 className="text-xs font-semibold text-outline uppercase tracking-widest">Objections</h4>
            </div>
            <ul className="space-y-1.5">
              {npc.objections.map((o, i) => (
                <li key={i} className="text-sm text-error flex items-start gap-2 bg-error-container/30 rounded-xl px-3 py-2">
                  <span className="material-symbols-outlined text-[14px] mt-0.5 flex-shrink-0">priority_high</span>
                  <span>{o}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Payment + Recommend */}
        <section className="flex gap-3 pt-3 border-t border-outline-variant/20">
          <span className={`text-xs px-3 py-1.5 rounded-xl font-semibold flex items-center gap-1.5 ${
            npc.would_pay
              ? 'bg-green-50 text-green-700'
              : 'bg-surface-container text-outline'
          }`}>
            <span className="material-symbols-outlined text-[14px]">
              {npc.would_pay ? 'check_circle' : 'cancel'}
            </span>
            {npc.would_pay ? 'Would pay' : 'Would not pay'}
          </span>
          <span className={`text-xs px-3 py-1.5 rounded-xl font-semibold flex items-center gap-1.5 ${
            npc.would_recommend
              ? 'bg-blue-50 text-blue-700'
              : 'bg-surface-container text-outline'
          }`}>
            <span className="material-symbols-outlined text-[14px]">
              {npc.would_recommend ? 'recommend' : 'block'}
            </span>
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
