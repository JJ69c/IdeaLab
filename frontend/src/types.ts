// ---- NPC & Graph types ----

export interface NpcPersonality {
  openness: number
  skepticism: number
  tech_savviness: number
  price_sensitivity: number
  social_influence: number
  novelty_seeking: number
}

export type Stance =
  | 'unaware' | 'aware'
  | 'opposed' | 'skeptical' | 'indifferent'
  | 'curious' | 'interested' | 'willing_to_try' | 'willing_to_pay'

export interface NpcNode {
  id: string
  name: string
  age: number
  occupation: string
  income_level: string
  personality: NpcPersonality
  interests: string[]
  values: string[]
  pain_points: string[]
  communication_style: string
  social_connections: string[]

  // Runtime state (updated by events)
  stance: Stance
  interest_score: number
  aware: boolean
  reasoning: string
  objections: string[]
  would_pay: boolean
  would_recommend: boolean
  emotional_reaction: string
  history: { tick: number; stance: string; interest: number }[]
  influence_sources: string[]
}

export interface GraphEdge {
  source: string
  target: string
  trust: number
}

// ---- Simulation events ----

export interface SimEvent {
  type: string
  tick: number
  data: Record<string, unknown>
}

// ---- Interpretability types ----

export interface CausalEntry {
  tick: number
  type: 'aware' | 'reaction' | 'discussion' | 'influence' | 'state_change'
  stance?: string
  interest?: number
  delta?: number
  detail: string
  partnerId?: string
  partnerName?: string
  keyPoint?: string
}

export interface InfluenceRecord {
  fromId: string
  fromName: string
  toId: string
  tick: number
  type: 'discussion' | 'peer_influence' | 'spread'
  delta: number
}

export interface NetworkRole {
  role: 'champion' | 'detractor' | 'bridge' | 'persuadable' | 'amplifier' | 'passive'
  roleLabel: string
  influenceRank: number
  affectedCount: number
  totalOutInfluence: number
}

// ---- Aggregate state ----

export interface SimMetrics {
  total_npcs: number
  aware_count: number
  awareness_rate: number
  interest_rate: number
  rejection_rate: number
  viral_coefficient: number
  net_sentiment: number
  would_pay_rate: number
  adoption_likelihood: number
  [key: string]: number
}

export interface SimulationState {
  npcs: Record<string, NpcNode>
  edges: GraphEdge[]
  events: SimEvent[]
  currentTick: number
  maxTicks: number
  metrics: SimMetrics | null
  previousMetrics: SimMetrics | null
  isRunning: boolean
  isComplete: boolean
  report: Record<string, unknown> | null
  ideaTitle: string
  activeDiscussions: { a: string; b: string }[]
}

// ---- Stance color map ----

export const STANCE_COLORS: Record<Stance, string> = {
  unaware:        '#d1d5db',
  aware:          '#93c5fd',
  opposed:        '#ef4444',
  skeptical:      '#fbbf24',
  indifferent:    '#9ca3af',
  curious:        '#a3e635',
  interested:     '#4ade80',
  willing_to_try: '#22c55e',
  willing_to_pay: '#15803d',
}

// ---- Interpretability helpers (pure functions, no state) ----

/** Build a causal timeline for a specific NPC from the event stream. */
export function buildCausalTimeline(npcId: string, events: SimEvent[]): CausalEntry[] {
  const timeline: CausalEntry[] = []

  for (const e of events) {
    const d = e.data
    switch (e.type) {
      case 'npc_aware':
        if (d.npc_id === npcId) {
          timeline.push({
            tick: e.tick,
            type: 'aware',
            detail: d.source === 'direct_exposure'
              ? 'Direct exposure to the idea'
              : `Heard about it from ${d.source_name}`,
            partnerId: d.source !== 'direct_exposure' ? d.source as string : undefined,
            partnerName: d.source_name as string | undefined,
          })
        }
        break
      case 'npc_reaction':
        if (d.npc_id === npcId) {
          timeline.push({
            tick: e.tick,
            type: 'reaction',
            stance: d.stance as string,
            interest: d.interest_score as number,
            detail: (d.reasoning as string) || 'Formed an initial opinion',
          })
        }
        break
      case 'discussion_end': {
        if (d.npc_a_id === npcId) {
          timeline.push({
            tick: e.tick,
            type: 'discussion',
            delta: d.a_delta as number,
            interest: d.a_interest as number,
            stance: d.a_stance as string,
            detail: `Discussed with ${d.npc_b_name}`,
            partnerId: d.npc_b_id as string,
            partnerName: d.npc_b_name as string,
            keyPoint: d.key_point as string,
          })
        } else if (d.npc_b_id === npcId) {
          timeline.push({
            tick: e.tick,
            type: 'discussion',
            delta: d.b_delta as number,
            interest: d.b_interest as number,
            stance: d.b_stance as string,
            detail: `Discussed with ${d.npc_a_name}`,
            partnerId: d.npc_a_id as string,
            partnerName: d.npc_a_name as string,
            keyPoint: d.key_point as string,
          })
        }
        break
      }
      case 'npc_state_change':
        if (d.npc_id === npcId && d.reason === 'peer_influence') {
          timeline.push({
            tick: e.tick,
            type: 'influence',
            stance: d.new_stance as string,
            interest: d.interest_score as number,
            detail: 'Shifted by social pressure from peers',
          })
        }
        break
    }
  }
  return timeline
}

/** Get all influence interactions involving a specific NPC. */
export function getInfluenceRecords(npcId: string, events: SimEvent[]): InfluenceRecord[] {
  const records: InfluenceRecord[] = []
  for (const e of events) {
    if (e.type === 'discussion_end') {
      const d = e.data
      if (d.npc_a_id === npcId) {
        records.push({
          fromId: d.npc_b_id as string, fromName: d.npc_b_name as string,
          toId: npcId, tick: e.tick, type: 'discussion',
          delta: d.a_delta as number,
        })
      }
      if (d.npc_b_id === npcId) {
        records.push({
          fromId: d.npc_a_id as string, fromName: d.npc_a_name as string,
          toId: npcId, tick: e.tick, type: 'discussion',
          delta: d.b_delta as number,
        })
      }
    }
    if (e.type === 'npc_aware') {
      const ad = e.data
      if (ad.npc_id === npcId && ad.source !== 'direct_exposure') {
        records.push({
          fromId: ad.source as string, fromName: (ad.source_name ?? ad.source) as string,
          toId: npcId, tick: e.tick, type: 'spread', delta: 0,
        })
      }
    }
  }
  return records
}

/** Compute the network role for a specific NPC based on event history. */
export function computeNetworkRole(
  npcId: string, allNpcs: Record<string, NpcNode>, events: SimEvent[]
): NetworkRole {
  // Count outward influence: how many other NPCs this NPC affected via discussion
  const affected = new Set<string>()
  let totalOut = 0

  for (const e of events) {
    if (e.type !== 'discussion_end') continue
    const d = e.data
    if (d.npc_a_id === npcId && Math.abs(d.b_delta as number) > 0.01) {
      affected.add(d.npc_b_id as string)
      totalOut += Math.abs(d.b_delta as number)
    }
    if (d.npc_b_id === npcId && Math.abs(d.a_delta as number) > 0.01) {
      affected.add(d.npc_a_id as string)
      totalOut += Math.abs(d.a_delta as number)
    }
  }

  // Compute influence rank (1-based, by total outward influence across all NPCs)
  const allNpcIds = Object.keys(allNpcs)
  const outScores: { id: string; score: number }[] = allNpcIds.map(id => {
    let score = 0
    for (const e of events) {
      if (e.type !== 'discussion_end') continue
      const d = e.data
      if (d.npc_a_id === id) score += Math.abs(d.b_delta as number)
      if (d.npc_b_id === id) score += Math.abs(d.a_delta as number)
    }
    return { id, score }
  })
  outScores.sort((a, b) => b.score - a.score)
  const rank = outScores.findIndex(s => s.id === npcId) + 1

  // Determine role
  const npc = allNpcs[npcId]
  const stance = npc?.stance ?? 'unaware'
  const historyLen = npc?.history?.length ?? 0
  const isPositive = ['interested', 'willing_to_try', 'willing_to_pay', 'curious'].includes(stance)
  const isNegative = ['skeptical', 'opposed'].includes(stance)

  // Bridge detection: connected to NPCs that aren't connected to each other
  const conns = npc?.social_connections ?? []
  let bridgeScore = 0
  for (let i = 0; i < conns.length; i++) {
    for (let j = i + 1; j < conns.length; j++) {
      const a = allNpcs[conns[i]]
      const b = allNpcs[conns[j]]
      if (a && b && !a.social_connections.includes(b.id)) bridgeScore++
    }
  }

  let role: NetworkRole['role'] = 'passive'
  let roleLabel = 'Passive Observer'

  if (affected.size >= 3 && isPositive) {
    role = 'champion'; roleLabel = 'Champion'
  } else if (affected.size >= 3 && isNegative) {
    role = 'detractor'; roleLabel = 'Detractor'
  } else if (bridgeScore >= 3) {
    role = 'bridge'; roleLabel = 'Bridge Node'
  } else if (historyLen >= 3) {
    role = 'persuadable'; roleLabel = 'Persuadable'
  } else if (affected.size >= 1 && isPositive) {
    role = 'amplifier'; roleLabel = 'Amplifier'
  }

  return { role, roleLabel, influenceRank: rank, affectedCount: affected.size, totalOutInfluence: totalOut }
}

/** Build per-edge influence magnitude from discussion events. */
export function computeEdgeInfluence(events: SimEvent[]): Record<string, number> {
  const map: Record<string, number> = {}
  for (const e of events) {
    if (e.type !== 'discussion_end') continue
    const d = e.data
    const key = [d.npc_a_id, d.npc_b_id].sort().join('|')
    map[key] = (map[key] ?? 0) + Math.abs(d.a_delta as number) + Math.abs(d.b_delta as number)
  }
  return map
}

// ---- Influence pair detail (for expanded influencer view) ----

export interface InfluencePairDetail {
  influencerId: string
  influencerName: string
  interactions: {
    tick: number
    delta: number
    keyPoint?: string
    resultStance?: string
    resultInterest?: number
  }[]
  totalDelta: number
  netDirection: 'positive' | 'negative' | 'mixed'
}

/** Get detailed influence interactions between two specific NPCs. */
export function getInfluencePairDetail(
  targetId: string,
  influencerId: string,
  events: SimEvent[],
): InfluencePairDetail {
  const interactions: InfluencePairDetail['interactions'] = []
  let influencerName = influencerId

  for (const e of events) {
    if (e.type !== 'discussion_end') continue
    const d = e.data

    if (d.npc_a_id === targetId && d.npc_b_id === influencerId) {
      influencerName = d.npc_b_name as string
      interactions.push({
        tick: e.tick,
        delta: d.a_delta as number,
        keyPoint: d.key_point as string | undefined,
        resultStance: d.a_stance as string,
        resultInterest: d.a_interest as number,
      })
    } else if (d.npc_b_id === targetId && d.npc_a_id === influencerId) {
      influencerName = d.npc_a_name as string
      interactions.push({
        tick: e.tick,
        delta: d.b_delta as number,
        keyPoint: d.key_point as string | undefined,
        resultStance: d.b_stance as string,
        resultInterest: d.b_interest as number,
      })
    }
  }

  const totalDelta = interactions.reduce((sum, i) => sum + i.delta, 0)
  const netDirection: InfluencePairDetail['netDirection'] =
    totalDelta > 0.01 ? 'positive' : totalDelta < -0.01 ? 'negative' : 'mixed'

  return { influencerId, influencerName, interactions, totalDelta, netDirection }
}

// ---- Ask NPC types ----

export interface AskNpcResponse {
  npc_id: string
  npc_name: string
  question: string
  answer: string
  stance: string
  interest_score: number
}

// ---- Round summary ----

export interface RoundSummaryData {
  tick: number
  newAware: number
  discussions: number
  positiveShifts: number
  negativeShifts: number
  avgDelta: number
  keyPoints: string[]
  headline: string
}

/** Compute a rich summary for a given round. */
export function computeRoundSummaryData(
  events: SimEvent[],
  tick: number,
): RoundSummaryData {
  const te = events.filter(e => e.tick === tick)
  const awareEvents = te.filter(e => e.type === 'npc_aware')
  const discussions = te.filter(e => e.type === 'discussion_end')
  const changes = te.filter(e => e.type === 'npc_state_change')

  const newAware = awareEvents.length
  const discussionCount = discussions.length

  const positiveStances = new Set(['curious', 'interested', 'willing_to_try', 'willing_to_pay'])
  const negativeStances = new Set(['skeptical', 'opposed'])

  const positiveShifts = changes.filter(e => positiveStances.has(e.data.new_stance as string)).length
  const negativeShifts = changes.filter(e => negativeStances.has(e.data.new_stance as string)).length

  const deltas: number[] = []
  const keyPoints: string[] = []
  for (const d of discussions) {
    deltas.push(d.data.a_delta as number, d.data.b_delta as number)
    if (d.data.key_point) keyPoints.push(d.data.key_point as string)
  }

  const avgDelta = deltas.length > 0 ? deltas.reduce((a, b) => a + b, 0) / deltas.length : 0

  let headline = ''
  if (tick === 0 || te.length === 0) {
    headline = 'Simulation warming up...'
  } else if (negativeShifts > positiveShifts * 2 && negativeShifts >= 2) {
    headline = 'Resistance is building — skepticism spreading through discussions.'
  } else if (positiveShifts > negativeShifts * 2 && positiveShifts >= 2) {
    headline = 'Enthusiasm growing — positive sentiment gaining momentum.'
  } else if (newAware >= 3 && discussionCount === 0) {
    headline = 'Awareness spreading rapidly, but discussions haven\'t started yet.'
  } else if (discussionCount > 0 && avgDelta < -0.05) {
    headline = 'Discussions turning negative — objections are resonating.'
  } else if (discussionCount > 0 && avgDelta > 0.05) {
    headline = 'Productive discussions — interest is climbing.'
  } else if (newAware > 0 && discussionCount > 0) {
    headline = 'Mixed signals — awareness growing but opinions are divided.'
  } else if (discussionCount > 0) {
    headline = 'Steady discussions with modest impact.'
  } else {
    headline = 'A quiet round with little new activity.'
  }

  const uniqueKeyPoints = [...new Set(keyPoints)]

  return {
    tick,
    newAware,
    discussions: discussionCount,
    positiveShifts,
    negativeShifts,
    avgDelta,
    keyPoints: uniqueKeyPoints.slice(0, 3),
    headline,
  }
}

/** Generate a concise narrative for a given tick. */
export function computeRoundNarrative(events: SimEvent[], tick: number): string {
  const te = events.filter(e => e.tick === tick)
  const awareEvents = te.filter(e => e.type === 'npc_aware')
  const directCount = awareEvents.filter(e => e.data.source === 'direct_exposure').length
  const spreadCount = awareEvents.length - directCount
  const discussions = te.filter(e => e.type === 'discussion_end').length
  const changes = te.filter(e => e.type === 'npc_state_change')
  const positive = changes.filter(e =>
    ['curious', 'interested', 'willing_to_try', 'willing_to_pay'].includes(e.data.new_stance as string)
  ).length
  const negative = changes.filter(e =>
    ['skeptical', 'opposed'].includes(e.data.new_stance as string)
  ).length

  const parts: string[] = []
  if (directCount > 0) parts.push(`${directCount} directly exposed`)
  if (spreadCount > 0) parts.push(`${spreadCount} heard via word of mouth`)
  if (discussions > 0) parts.push(`${discussions} discussion${discussions !== 1 ? 's' : ''}`)
  if (positive > 0) parts.push(`${positive} shifted positive`)
  if (negative > 0) parts.push(`${negative} grew skeptical`)

  return parts.length > 0 ? parts.join(' · ') : 'Quiet round'
}
