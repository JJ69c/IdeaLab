import { useEffect, useReducer } from 'react'
import type { SimulationState, SimEvent, NpcNode, GraphEdge, Stance } from '../types'

const INITIAL_STATE: SimulationState = {
  npcs: {},
  edges: [],
  events: [],
  currentTick: 0,
  maxTicks: 0,
  metrics: null,
  previousMetrics: null,
  isRunning: false,
  isComplete: false,
  report: null,
  ideaTitle: '',
  activeDiscussions: [],
}

type Action = { type: string; payload: SimEvent }

function makeNpcNode(raw: Record<string, unknown>): NpcNode {
  return {
    id: raw.id as string,
    name: raw.name as string,
    age: raw.age as number,
    occupation: raw.occupation as string,
    income_level: raw.income_level as string,
    personality: raw.personality as NpcNode['personality'],
    interests: (raw.interests ?? []) as string[],
    values: (raw.values ?? []) as string[],
    pain_points: (raw.pain_points ?? []) as string[],
    communication_style: (raw.communication_style ?? '') as string,
    social_connections: (raw.social_connections ?? []) as string[],
    stance: (raw.stance ?? 'unaware') as Stance,
    interest_score: (raw.interest_score ?? 0) as number,
    aware: (raw.aware ?? false) as boolean,
    reasoning: '',
    objections: [],
    would_pay: false,
    would_recommend: false,
    emotional_reaction: '',
    history: [],
    influence_sources: [],
  }
}

function reducer(state: SimulationState, action: Action): SimulationState {
  const { type, payload } = action
  const d = payload.data as Record<string, unknown>

  switch (type) {
    case 'simulation_start': {
      const rawNpcs = d.npcs as Record<string, unknown>[]
      const npcs: Record<string, NpcNode> = {}
      for (const raw of rawNpcs) {
        const node = makeNpcNode(raw)
        npcs[node.id] = node
      }
      const idea = d.idea as Record<string, string>
      return {
        ...state,
        npcs,
        edges: d.edges as GraphEdge[],
        maxTicks: (d.config as Record<string, number>).num_ticks,
        isRunning: true,
        ideaTitle: idea?.title ?? '',
        events: [...state.events, payload],
      }
    }

    case 'tick_start':
      return {
        ...state,
        currentTick: payload.tick,
        activeDiscussions: [], // clear discussions from previous tick
        events: [...state.events, payload],
      }

    case 'npc_aware': {
      const npcId = d.npc_id as string
      const npc = state.npcs[npcId]
      if (!npc) return state
      return {
        ...state,
        npcs: {
          ...state.npcs,
          [npcId]: { ...npc, aware: true, stance: 'aware' as Stance },
        },
        events: [...state.events, payload],
      }
    }

    case 'npc_reaction': {
      const npcId = d.npc_id as string
      const npc = state.npcs[npcId]
      if (!npc) return state
      return {
        ...state,
        npcs: {
          ...state.npcs,
          [npcId]: {
            ...npc,
            stance: d.stance as Stance,
            interest_score: d.interest_score as number,
            reasoning: d.reasoning as string,
            objections: (d.objections ?? []) as string[],
            would_pay: d.would_pay as boolean,
            emotional_reaction: (d.emotional_reaction ?? '') as string,
          },
        },
        events: [...state.events, payload],
      }
    }

    case 'npc_state_change': {
      const npcId = d.npc_id as string
      const npc = state.npcs[npcId]
      if (!npc) return state
      const newStance = d.new_stance as Stance
      const newInterest = d.interest_score as number
      return {
        ...state,
        npcs: {
          ...state.npcs,
          [npcId]: {
            ...npc,
            stance: newStance,
            interest_score: newInterest,
            history: [...npc.history, { tick: payload.tick, stance: newStance, interest: newInterest }],
          },
        },
        events: [...state.events, payload],
      }
    }

    case 'discussion_start': {
      return {
        ...state,
        activeDiscussions: [
          ...state.activeDiscussions,
          { a: d.npc_a_id as string, b: d.npc_b_id as string },
        ],
        events: [...state.events, payload],
      }
    }

    case 'discussion_end': {
      const aId = d.npc_a_id as string
      const bId = d.npc_b_id as string
      const npcA = state.npcs[aId]
      const npcB = state.npcs[bId]
      const updatedNpcs = { ...state.npcs }
      if (npcA) {
        updatedNpcs[aId] = {
          ...npcA,
          interest_score: d.a_interest as number,
          stance: d.a_stance as Stance,
          influence_sources: npcA.influence_sources.includes(bId)
            ? npcA.influence_sources
            : [...npcA.influence_sources, bId],
        }
      }
      if (npcB) {
        updatedNpcs[bId] = {
          ...npcB,
          interest_score: d.b_interest as number,
          stance: d.b_stance as Stance,
          influence_sources: npcB.influence_sources.includes(aId)
            ? npcB.influence_sources
            : [...npcB.influence_sources, aId],
        }
      }
      return {
        ...state,
        npcs: updatedNpcs,
        events: [...state.events, payload],
      }
    }

    case 'npc_spread': {
      return { ...state, events: [...state.events, payload] }
    }

    case 'tick_end': {
      const metrics = d.metrics as SimulationState['metrics']
      return { ...state, previousMetrics: state.metrics, metrics, activeDiscussions: [], events: [...state.events, payload] }
    }

    case 'simulation_complete': {
      const report = d.report as Record<string, unknown>
      return { ...state, isRunning: false, isComplete: true, report, events: [...state.events, payload] }
    }

    case 'error': {
      return { ...state, isRunning: false, events: [...state.events, payload] }
    }

    default:
      return { ...state, events: [...state.events, payload] }
  }
}

/**
 * Hydrate state from a completed simulation's REST data.
 * Used as fallback when SSE stream is unavailable (e.g. returning to a finished sim).
 */
function hydrateFromRestData(sim: Record<string, unknown>): Action[] {
  const actions: Action[] = []
  const report = sim.report as Record<string, unknown> | null
  if (!report) return actions

  const npcResults = (report.npc_results ?? []) as Record<string, unknown>[]
  const metrics = (report.metrics ?? {}) as Record<string, unknown>
  const config = (sim.config ?? {}) as Record<string, number>

  // Build a simulation_start event from the NPC results
  const npcs = npcResults.map(n => ({
    id: n.npc_id as string,
    name: n.name as string,
    age: n.age as number,
    occupation: n.occupation as string,
    income_level: '',
    personality: { openness: 0.5, skepticism: 0.5, tech_savviness: 0.5, price_sensitivity: 0.5, social_influence: 0.5, novelty_seeking: 0.5 },
    interests: [],
    values: [],
    pain_points: [],
    communication_style: '',
    social_connections: [],
    stance: n.stance as string,
    interest_score: n.interest_score as number,
    aware: n.aware as boolean,
  }))

  actions.push({
    type: 'simulation_start',
    payload: {
      type: 'simulation_start', tick: 0,
      data: {
        npcs,
        edges: [],
        idea: { title: sim.idea_title as string },
        config: { num_ticks: config.num_ticks ?? 0, population_size: npcs.length },
      },
    },
  })

  // Apply final states to each NPC
  for (const n of npcResults) {
    actions.push({
      type: 'npc_reaction',
      payload: {
        type: 'npc_reaction', tick: 0,
        data: {
          npc_id: n.npc_id,
          name: n.name,
          stance: n.stance,
          interest_score: n.interest_score,
          reasoning: n.reasoning ?? '',
          objections: n.objections ?? [],
          would_pay: n.would_pay ?? false,
          emotional_reaction: n.emotional_reaction ?? '',
        },
      },
    })
  }

  // Mark complete with metrics + report
  actions.push({
    type: 'tick_end',
    payload: { type: 'tick_end', tick: config.num_ticks ?? 0, data: { metrics } },
  })

  actions.push({
    type: 'simulation_complete',
    payload: { type: 'simulation_complete', tick: config.num_ticks ?? 0, data: { report } },
  })

  return actions
}

export function useSimulationStream(simulationId: string | undefined): SimulationState {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE)

  useEffect(() => {
    if (!simulationId) return

    let eventSource: EventSource | null = null
    let didReceiveEvent = false
    let closed = false

    // Try SSE first
    eventSource = new EventSource(`/api/simulations/${simulationId}/stream`)

    eventSource.onmessage = (e) => {
      didReceiveEvent = true
      try {
        const event: SimEvent = JSON.parse(e.data)
        dispatch({ type: event.type, payload: event })
      } catch {
        // ignore malformed events
      }
    }

    eventSource.onerror = () => {
      eventSource?.close()
      // If we never got any events, fall back to REST API
      if (!didReceiveEvent && !closed) {
        loadFromRest()
      }
    }

    async function loadFromRest() {
      try {
        const res = await fetch(`/api/simulations/${simulationId}`)
        if (!res.ok) return
        const sim = await res.json()
        if (sim.status === 'completed' && sim.report) {
          const actions = hydrateFromRestData(sim)
          for (const action of actions) {
            dispatch(action)
          }
        }
      } catch {
        // silent fail
      }
    }

    return () => {
      closed = true
      eventSource?.close()
    }
  }, [simulationId])

  return state
}
