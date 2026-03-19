import { useEffect, useMemo, useState, useRef, useCallback } from 'react'
import type { NpcNode, GraphEdge, Stance, SimEvent } from '../types'
import { STANCE_COLORS, computeEdgeInfluence } from '../types'

// ─── Types ───────────────────────────────────────────────────────────────────

interface Props {
  npcs: Record<string, NpcNode>
  edges: GraphEdge[]
  events: SimEvent[]
  activeDiscussions: { a: string; b: string }[]
  selectedNpcId: string | null
  highlightedEdge: { source: string; target: string } | null
  onSelectNpc: (id: string | null) => void
}

interface Position { x: number; y: number }
interface ViewTransform { x: number; y: number; scale: number }
interface Rect { x: number; y: number; w: number; h: number }
interface PositionedLabel {
  npcId: string
  text: string
  x: number
  y: number
  anchor: 'middle' | 'start' | 'end'
}

// ─── Constants ───────────────────────────────────────────────────────────────

const W = 800
const H = 550
const DEFAULT_VIEW: ViewTransform = { x: 0, y: 0, scale: 1 }
const MIN_SCALE = 0.4
const MAX_SCALE = 3.0
const FOCUS_SCALE = 1.6
const ZOOM_STEP = 1.15
const ANIM_EASE = 'cubic-bezier(0.4, 0, 0.2, 1)'
const ANIM_MS_FOCUS = 400
const ANIM_MS_RESET = 500

// ─── Utilities ───────────────────────────────────────────────────────────────

function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
}

// ─── Force-directed layout ──────────────────────────────────────────────────

function computeLayout(
  npcIds: string[],
  edges: GraphEdge[],
  width: number,
  height: number,
): Record<string, Position> {
  const n = npcIds.length
  if (n === 0) return {}

  const positions: Record<string, { x: number; y: number; vx: number; vy: number }> = {}
  const cx = width / 2
  const cy = height / 2
  const initRadius = Math.min(width, height) * 0.42

  // Circular initial placement
  npcIds.forEach((id, i) => {
    const angle = (2 * Math.PI * i) / n
    positions[id] = {
      x: cx + initRadius * Math.cos(angle),
      y: cy + initRadius * Math.sin(angle),
      vx: 0, vy: 0,
    }
  })

  // Tuned parameters: more spread, less central compression
  const repulsion = 2000 + n * 25
  const springRest = 160
  const springK = 0.04
  const gravity = 0.003
  const pad = 25
  const iterations = 400

  for (let iter = 0; iter < iterations; iter++) {
    const alpha = 0.1 * (1 - iter / iterations)
    const damping = iter < iterations / 2 ? 0.5 : 0.65

    // Repulsion (all pairs)
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = positions[npcIds[i]]
        const b = positions[npcIds[j]]
        let dx = b.x - a.x
        let dy = b.y - a.y
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
        const force = repulsion / (dist * dist)
        dx = (dx / dist) * force * alpha
        dy = (dy / dist) * force * alpha
        a.vx -= dx; a.vy -= dy
        b.vx += dx; b.vy += dy
      }
    }

    // Spring attraction (edges only)
    for (const edge of edges) {
      const a = positions[edge.source]
      const b = positions[edge.target]
      if (!a || !b) continue
      let dx = b.x - a.x
      let dy = b.y - a.y
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
      const force = (dist - springRest) * springK * alpha
      dx = (dx / dist) * force
      dy = (dy / dist) * force
      a.vx += dx; a.vy += dy
      b.vx -= dx; b.vy -= dy
    }

    // Weak center gravity
    for (const id of npcIds) {
      const p = positions[id]
      p.vx += (cx - p.x) * gravity * alpha
      p.vy += (cy - p.y) * gravity * alpha
    }

    // Apply velocity with damping
    for (const id of npcIds) {
      const p = positions[id]
      p.vx *= damping
      p.vy *= damping
      p.x += p.vx
      p.y += p.vy
      p.x = Math.max(pad, Math.min(width - pad, p.x))
      p.y = Math.max(pad, Math.min(height - pad, p.y))
    }
  }

  const result: Record<string, Position> = {}
  for (const id of npcIds) {
    result[id] = { x: positions[id].x, y: positions[id].y }
  }
  return result
}

// ─── Label placement with collision avoidance ────────────────────────────────

function computeLabelPlacements(
  npcInfos: { id: string; name: string; radius: number }[],
  positions: Record<string, Position>,
  scale: number,
  selectedId: string | null,
  connectedIds: Set<string>,
  activeIds: Set<string>,
  twoHopIds?: Set<string>,
): { labels: PositionedLabel[]; placedIds: Set<string> } {
  if (Object.keys(positions).length === 0 || npcInfos.length === 0) {
    return { labels: [], placedIds: new Set() }
  }

  const CHAR_W = 5.5
  const LABEL_H = 11
  const PAD = 2

  // Assign priorities
  const candidates = npcInfos.map(info => {
    let priority = 10
    if (info.id === selectedId) priority = 100
    else if (connectedIds.has(info.id)) priority = 80
    else if (activeIds.has(info.id)) priority = 60
    else if (twoHopIds?.has(info.id)) priority = 40
    return { ...info, priority }
  }).sort((a, b) => b.priority - a.priority)

  // Budget by zoom level
  const maxLabels = scale >= 2.0 ? candidates.length
    : scale >= 1.5 ? Math.min(25, candidates.length)
    : scale >= 1.0 ? Math.min(15, candidates.length)
    : Math.min(8, candidates.length)

  // Must-show: selected + connected + active
  const mustShow = new Set<string>()
  if (selectedId) mustShow.add(selectedId)
  for (const id of connectedIds) mustShow.add(id)
  for (const id of activeIds) mustShow.add(id)

  // Determine eligible set (must-show always included, then by priority up to budget)
  const eligible = new Set<string>(mustShow)
  for (const c of candidates) {
    if (eligible.size >= maxLabels) break
    eligible.add(c.id)
  }

  // Place labels with collision avoidance
  const placedBoxes: Rect[] = []
  const labels: PositionedLabel[] = []
  const placedIds = new Set<string>()

  for (const c of candidates) {
    if (!eligible.has(c.id)) continue
    const pos = positions[c.id]
    if (!pos) continue

    const text = scale > 1.8 ? c.name : c.name.split(' ')[0]
    const textW = text.length * CHAR_W
    const r = c.radius

    // Try 4 positions: below, above, right, left
    const tries: { x: number; y: number; anchor: PositionedLabel['anchor']; box: Rect }[] = [
      { x: pos.x, y: pos.y + r + 12, anchor: 'middle',
        box: { x: pos.x - textW / 2 - PAD, y: pos.y + r + 2, w: textW + PAD * 2, h: LABEL_H + PAD } },
      { x: pos.x, y: pos.y - r - 4, anchor: 'middle',
        box: { x: pos.x - textW / 2 - PAD, y: pos.y - r - 4 - LABEL_H, w: textW + PAD * 2, h: LABEL_H + PAD } },
      { x: pos.x + r + 5, y: pos.y + 3, anchor: 'start',
        box: { x: pos.x + r + 3, y: pos.y + 3 - LABEL_H, w: textW + PAD * 2, h: LABEL_H + PAD } },
      { x: pos.x - r - 5, y: pos.y + 3, anchor: 'end',
        box: { x: pos.x - r - 5 - textW - PAD, y: pos.y + 3 - LABEL_H, w: textW + PAD * 2, h: LABEL_H + PAD } },
    ]

    let best = tries[0]
    let bestOverlaps = Infinity

    for (const t of tries) {
      let overlaps = 0
      for (const pb of placedBoxes) {
        if (rectsOverlap(t.box, pb)) overlaps++
      }
      if (overlaps < bestOverlaps) {
        bestOverlaps = overlaps
        best = t
      }
      if (overlaps === 0) break
    }

    // Skip non-must-show labels that overlap
    if (bestOverlaps > 0 && !mustShow.has(c.id)) continue

    labels.push({ npcId: c.id, text, x: best.x, y: best.y, anchor: best.anchor })
    placedIds.add(c.id)
    placedBoxes.push(best.box)
  }

  return { labels, placedIds }
}

// ─── Edge hover detail ──────────────────────────────────────────────────────

interface EdgeHoverDetail {
  sourceName: string
  targetName: string
  trust: number
  totalInfluence: number
  discussionCount: number
  keyPoints: string[]
}

// ═══════════════════════════════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════════════════════════════

export default function SimulationGraph({
  npcs, edges, events, activeDiscussions,
  selectedNpcId, highlightedEdge, onSelectNpc,
}: Props) {

  // ── Data memos ─────────────────────────────────────────────────────────────

  const npcList = useMemo(() => Object.values(npcs), [npcs])
  const npcIds = useMemo(() => npcList.map(n => n.id), [npcList])

  const edgeInfluence = useMemo(() => computeEdgeInfluence(events), [events])
  const maxInfluence = useMemo(() => {
    const vals = Object.values(edgeInfluence)
    return vals.length > 0 ? Math.max(...vals) : 1
  }, [edgeInfluence])

  // Layout (computed once when NPC set arrives)
  const [positions, setPositions] = useState<Record<string, Position>>({})
  useEffect(() => {
    if (npcIds.length === 0) return
    setPositions(computeLayout(npcIds, edges, W, H))
  }, [npcIds.length])

  // Active discussions set
  const activeSet = useMemo(() => {
    const s = new Set<string>()
    for (const d of activeDiscussions) {
      s.add(`${d.a}|${d.b}`)
      s.add(`${d.b}|${d.a}`)
    }
    return s
  }, [activeDiscussions])

  // Connected nodes for selection (1-hop)
  const connectedSet = useMemo(() => {
    const s = new Set<string>()
    if (!selectedNpcId) return s
    for (const edge of edges) {
      if (edge.source === selectedNpcId) s.add(edge.target)
      if (edge.target === selectedNpcId) s.add(edge.source)
    }
    return s
  }, [selectedNpcId, edges])

  // 2-hop neighbors (neighbors of 1-hop, excluding selected + 1-hop)
  const twoHopSet = useMemo(() => {
    const s = new Set<string>()
    if (!selectedNpcId) return s
    for (const connId of connectedSet) {
      for (const edge of edges) {
        if (edge.source === connId) s.add(edge.target)
        if (edge.target === connId) s.add(edge.source)
      }
    }
    s.delete(selectedNpcId)
    for (const id of connectedSet) s.delete(id)
    return s
  }, [selectedNpcId, connectedSet, edges])

  const isEdgeSelected = (source: string, target: string) =>
    selectedNpcId !== null && (source === selectedNpcId || target === selectedNpcId)

  // Get the neighborhood tier for a node: 3=selected, 2=1-hop, 1=2-hop, 0=outside
  const getNodeTier = useCallback((id: string): number => {
    if (id === selectedNpcId) return 3
    if (connectedSet.has(id)) return 2
    if (twoHopSet.has(id)) return 1
    return 0
  }, [selectedNpcId, connectedSet, twoHopSet])

  // Recently active NPCs (stance changes in last 2 ticks)
  const activeNpcIds = useMemo(() => {
    const ids = new Set<string>()
    const maxTick = events.reduce((max, e) => Math.max(max, e.tick), 0)
    for (const e of events) {
      if (e.tick < maxTick - 1) continue
      if (e.type === 'npc_state_change' || e.type === 'npc_reaction') {
        ids.add(e.data.npc_id as string)
      }
    }
    return ids
  }, [events])

  // Stance-based cluster groups for background indicators
  const stanceGroups = useMemo(() => {
    if (Object.keys(positions).length === 0) return {}
    const opinionStances = new Set(['opposed', 'skeptical', 'indifferent', 'curious', 'interested', 'willing_to_try', 'willing_to_pay'])
    const groups: Record<string, { ids: string[]; cx: number; cy: number; r: number }> = {}
    for (const npc of npcList) {
      if (!opinionStances.has(npc.stance)) continue
      if (!groups[npc.stance]) groups[npc.stance] = { ids: [], cx: 0, cy: 0, r: 0 }
      groups[npc.stance].ids.push(npc.id)
    }
    for (const [stance, group] of Object.entries(groups)) {
      if (group.ids.length < 2) { delete groups[stance]; continue }
      let sumX = 0, sumY = 0
      for (const id of group.ids) {
        sumX += positions[id]?.x ?? 0
        sumY += positions[id]?.y ?? 0
      }
      group.cx = sumX / group.ids.length
      group.cy = sumY / group.ids.length
      let maxDist = 0
      for (const id of group.ids) {
        const pos = positions[id]
        if (!pos) continue
        const dist = Math.sqrt((pos.x - group.cx) ** 2 + (pos.y - group.cy) ** 2)
        maxDist = Math.max(maxDist, dist)
      }
      group.r = maxDist + 30
    }
    return groups
  }, [npcList, positions])

  // Edge hover state
  const [hoveredEdgeKey, setHoveredEdgeKey] = useState<string | null>(null)

  const edgeDetails = useMemo(() => {
    const map: Record<string, EdgeHoverDetail> = {}
    for (const edge of edges) {
      const key = [edge.source, edge.target].sort().join('|')
      const sourceNpc = npcs[edge.source]
      const targetNpc = npcs[edge.target]
      if (!sourceNpc || !targetNpc) continue

      let totalInf = 0
      let count = 0
      const kps: string[] = []

      for (const e of events) {
        if (e.type !== 'discussion_end') continue
        const d = e.data
        const eKey = [d.npc_a_id, d.npc_b_id].sort().join('|')
        if (eKey !== key) continue
        count++
        totalInf += Math.abs(d.a_delta as number) + Math.abs(d.b_delta as number)
        if (d.key_point) kps.push(d.key_point as string)
      }

      map[key] = {
        sourceName: sourceNpc.name,
        targetName: targetNpc.name,
        trust: edge.trust,
        totalInfluence: totalInf,
        discussionCount: count,
        keyPoints: [...new Set(kps.filter(Boolean))].slice(0, 2),
      }
    }
    return map
  }, [edges, events, npcs])

  const isEdgeHighlighted = (source: string, target: string) => {
    if (!highlightedEdge) return false
    return (
      (source === highlightedEdge.source && target === highlightedEdge.target) ||
      (source === highlightedEdge.target && target === highlightedEdge.source)
    )
  }

  // ── View transform state ───────────────────────────────────────────────────

  const svgRef = useRef<SVGSVGElement>(null)
  const [view, setView] = useState<ViewTransform>(DEFAULT_VIEW)
  const [isAnimating, setIsAnimating] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const viewRef = useRef(view)
  useEffect(() => { viewRef.current = view }, [view])

  const dragRef = useRef<{
    startX: number
    startY: number
    startView: ViewTransform
    moved: boolean
  } | null>(null)

  const [hoveredNpcId, setHoveredNpcId] = useState<string | null>(null)

  // Track whether selection came from an internal click (no auto-focus)
  const internalSelectRef = useRef(false)

  // ── Convert client coords → SVG viewBox coords ────────────────────────────

  const clientToSvg = useCallback((clientX: number, clientY: number) => {
    const svg = svgRef.current
    if (!svg) return { x: 0, y: 0 }
    const ctm = svg.getScreenCTM()
    if (!ctm) return { x: 0, y: 0 }
    return {
      x: (clientX - ctm.e) / ctm.a,
      y: (clientY - ctm.f) / ctm.d,
    }
  }, [])

  // ── Wheel zoom (attached via native addEventListener for non-passive) ──────

  const svgAvailable = npcIds.length > 0

  useEffect(() => {
    if (!svgAvailable) return
    const svg = svgRef.current
    if (!svg) return

    const handler = (e: WheelEvent) => {
      e.preventDefault()
      const ctm = svg.getScreenCTM()
      if (!ctm) return
      const svgX = (e.clientX - ctm.e) / ctm.a
      const svgY = (e.clientY - ctm.f) / ctm.d

      // Normalize delta across input types
      let delta = e.deltaY
      if (e.deltaMode === 1) delta *= 40  // lines → px
      if (e.deltaMode === 2) delta *= 800 // pages → px

      let factor: number
      if (e.ctrlKey) {
        // Trackpad pinch: small continuous delta
        factor = 1 - delta * 0.01
      } else {
        // Mouse wheel: discrete steps
        factor = delta < 0 ? ZOOM_STEP : 1 / ZOOM_STEP
      }

      setView(prev => {
        const newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, prev.scale * factor))
        if (Math.abs(newScale - prev.scale) < 0.001) return prev
        const worldX = (svgX - prev.x) / prev.scale
        const worldY = (svgY - prev.y) / prev.scale
        return {
          x: svgX - worldX * newScale,
          y: svgY - worldY * newScale,
          scale: newScale,
        }
      })
      setIsAnimating(false)
    }

    svg.addEventListener('wheel', handler, { passive: false })
    return () => svg.removeEventListener('wheel', handler)
  }, [svgAvailable])

  // ── Focus helpers ──────────────────────────────────────────────────────────

  const focusOnNpc = useCallback((npcId: string) => {
    const pos = positions[npcId]
    if (!pos) return
    setIsAnimating(true)
    setView({
      x: W / 2 - pos.x * FOCUS_SCALE,
      y: H / 2 - pos.y * FOCUS_SCALE,
      scale: FOCUS_SCALE,
    })
    setTimeout(() => setIsAnimating(false), ANIM_MS_FOCUS + 50)
  }, [positions])

  const resetViewAnimated = useCallback(() => {
    setIsAnimating(true)
    setView(DEFAULT_VIEW)
    setTimeout(() => setIsAnimating(false), ANIM_MS_RESET + 50)
  }, [])

  // Auto-focus when selection changes from OUTSIDE the graph (e.g. panel nav)
  useEffect(() => {
    if (internalSelectRef.current) {
      internalSelectRef.current = false
      return
    }
    if (selectedNpcId && positions[selectedNpcId]) {
      focusOnNpc(selectedNpcId)
    }
  }, [selectedNpcId])

  // ── Pan handlers ───────────────────────────────────────────────────────────

  const handlePointerDown = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    const isNode = (e.target as Element).closest('[data-npc]')
    if (isNode) return

    const svgPt = clientToSvg(e.clientX, e.clientY)
    dragRef.current = {
      startX: svgPt.x,
      startY: svgPt.y,
      startView: { ...viewRef.current },
      moved: false,
    }
    svgRef.current?.setPointerCapture(e.pointerId)
    setIsDragging(true)
    setIsAnimating(false)
  }, [clientToSvg])

  const handlePointerMove = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    if (!dragRef.current) return
    const svgPt = clientToSvg(e.clientX, e.clientY)
    const dx = svgPt.x - dragRef.current.startX
    const dy = svgPt.y - dragRef.current.startY
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) dragRef.current.moved = true
    setView({
      x: dragRef.current.startView.x + dx,
      y: dragRef.current.startView.y + dy,
      scale: dragRef.current.startView.scale,
    })
  }, [clientToSvg])

  const handlePointerUp = useCallback(() => {
    const drag = dragRef.current
    dragRef.current = null
    setIsDragging(false)
    if (drag && !drag.moved) {
      // Background single-click: deselect (no view change)
      internalSelectRef.current = true
      onSelectNpc(null)
    }
  }, [onSelectNpc])

  // ── Click / double-click ───────────────────────────────────────────────────

  const handleNodeClick = useCallback((npcId: string) => {
    internalSelectRef.current = true
    onSelectNpc(npcId)
  }, [onSelectNpc])

  const handleDoubleClick = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    const nodeEl = (e.target as Element).closest('[data-npc]')
    if (nodeEl) {
      const npcId = nodeEl.getAttribute('data-npc')
      if (npcId) focusOnNpc(npcId)
    } else {
      // Background double-click: deselect + reset
      internalSelectRef.current = true
      onSelectNpc(null)
      resetViewAnimated()
    }
  }, [focusOnNpc, onSelectNpc, resetViewAnimated])

  // ── Keyboard ───────────────────────────────────────────────────────────────

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        internalSelectRef.current = true
        if (selectedNpcId) onSelectNpc(null)
        resetViewAnimated()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [selectedNpcId, onSelectNpc, resetViewAnimated])

  // ── Zoom controls ──────────────────────────────────────────────────────────

  const zoomIn = useCallback(() => {
    setIsAnimating(true)
    setView(prev => {
      const s = Math.min(MAX_SCALE, prev.scale * ZOOM_STEP)
      const wx = (W / 2 - prev.x) / prev.scale
      const wy = (H / 2 - prev.y) / prev.scale
      return { x: W / 2 - wx * s, y: H / 2 - wy * s, scale: s }
    })
    setTimeout(() => setIsAnimating(false), 300)
  }, [])

  const zoomOut = useCallback(() => {
    setIsAnimating(true)
    setView(prev => {
      const s = Math.max(MIN_SCALE, prev.scale / ZOOM_STEP)
      const wx = (W / 2 - prev.x) / prev.scale
      const wy = (H / 2 - prev.y) / prev.scale
      return { x: W / 2 - wx * s, y: H / 2 - wy * s, scale: s }
    })
    setTimeout(() => setIsAnimating(false), 300)
  }, [])

  // ── Label placement ────────────────────────────────────────────────────────

  const { labels: labelPlacements, placedIds: labelPlacedIds } = useMemo(() => {
    const infos = npcList.map(n => ({
      id: n.id,
      name: n.name,
      radius: 8 + n.personality.social_influence * 10,
    }))
    return computeLabelPlacements(infos, positions, view.scale, selectedNpcId, connectedSet, activeNpcIds, twoHopSet)
  }, [npcList, positions, view.scale, selectedNpcId, connectedSet, activeNpcIds, twoHopSet])

  // ── Render ─────────────────────────────────────────────────────────────────

  if (npcIds.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        Waiting for simulation data...
      </div>
    )
  }

  const hasSelection = selectedNpcId !== null
  const hoveredDetail = hoveredEdgeKey ? edgeDetails[hoveredEdgeKey] : null
  const zoomPercent = Math.round(view.scale * 100)

  // Animation CSS
  const animDuration = view.scale === 1 && view.x === 0 && view.y === 0
    ? ANIM_MS_RESET : ANIM_MS_FOCUS
  const transformTransition = isAnimating
    ? `transform ${animDuration}ms ${ANIM_EASE}`
    : 'none'

  return (
    <div className="relative w-full h-full">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-full"
        style={{
          touchAction: 'none',
          userSelect: 'none',
          WebkitUserSelect: 'none',
          cursor: isDragging ? 'grabbing' : 'grab',
        }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onDoubleClick={handleDoubleClick}
      >
        {/* SVG-level defs (outside transform) */}
        <defs>
          <style>{`
            @keyframes halo-pulse {
              0%   { opacity: 0.5; }
              50%  { opacity: 0.15; }
              100% { opacity: 0.5; }
            }
            .halo-ring { animation: halo-pulse 2s ease-in-out infinite; }
          `}</style>
          <marker
            id="influence-arrow"
            markerWidth="8" markerHeight="6"
            refX="8" refY="3"
            orient="auto"
          >
            <polygon points="0 0, 8 3, 0 6" fill="#6366f1" />
          </marker>
        </defs>

        {/* Background hit-area (outside transform, always covers viewport) */}
        <rect x="0" y="0" width={W} height={H} fill="transparent" />

        {/* ── Transformed content ── */}
        <g
          style={{
            transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
            transformOrigin: '0 0',
            transition: transformTransition,
          }}
        >
          {/* ── Stance cluster backgrounds (behind everything) ── */}
          {Object.entries(stanceGroups).map(([stance, group]) => {
            const clusterColor = STANCE_COLORS[stance as Stance] ?? '#d1d5db'
            return (
              <circle
                key={`cluster-${stance}`}
                cx={group.cx}
                cy={group.cy}
                r={group.r}
                fill={clusterColor}
                opacity={hasSelection ? 0.03 : 0.05}
                style={{ transition: 'opacity 400ms ease, cx 400ms ease, cy 400ms ease, r 400ms ease' }}
              />
            )
          })}

          {/* ── Edges (visible) ── */}
          {edges.map(edge => {
            const s = positions[edge.source]
            const t = positions[edge.target]
            if (!s || !t) return null
            const key = `${edge.source}|${edge.target}`
            const sortedKey = [edge.source, edge.target].sort().join('|')
            const isActive = activeSet.has(key)
            const isRelated = isEdgeSelected(edge.source, edge.target)
            const isHl = isEdgeHighlighted(edge.source, edge.target)
            const isBetweenConnected = connectedSet.has(edge.source) && connectedSet.has(edge.target)

            const inf = edgeInfluence[sortedKey] ?? 0
            const infNorm = maxInfluence > 0 ? inf / maxInfluence : 0

            let stroke = inf > 0
              ? `rgba(99, 102, 241, ${0.2 + infNorm * 0.6})`
              : '#e5e7eb'
            let strokeWidth = inf > 0 ? 1 + infNorm * 2.5 : 1
            let opacity = inf > 0 ? 0.4 + infNorm * 0.5 : edge.trust * 0.4 + 0.1

            if (isActive) {
              stroke = '#6366f1'
              strokeWidth = 2.5
              opacity = 1
            } else if (isHl) {
              opacity = 0.15
            } else if (isRelated) {
              stroke = '#a5b4fc'
              strokeWidth = Math.max(strokeWidth, 2)
              opacity = 0.8
            } else if (hasSelection || highlightedEdge) {
              // 2-hop tiered dimming
              const edgeTier = Math.min(getNodeTier(edge.source), getNodeTier(edge.target))
              if (isBetweenConnected) {
                opacity = 0.2
              } else if (edgeTier >= 1) {
                // At least one end is 2-hop, other is 1-hop or 2-hop
                opacity = 0.1
                stroke = '#c7d2fe'
              } else {
                opacity = 0.03
              }
            }

            return (
              <line
                key={key}
                x1={s.x} y1={s.y} x2={t.x} y2={t.y}
                stroke={stroke}
                strokeWidth={strokeWidth}
                strokeDasharray={isActive ? '6,4' : undefined}
                opacity={opacity}
                className={isActive ? 'animate-pulse' : ''}
                style={{ transition: 'opacity 300ms ease, stroke 300ms ease' }}
              />
            )
          })}

          {/* ── Highlighted influence edge (glow + arrowhead) ── */}
          {highlightedEdge && (() => {
            const srcPos = positions[highlightedEdge.source]
            const tgtPos = positions[highlightedEdge.target]
            if (!srcPos || !tgtPos) return null

            const srcNpc = npcs[highlightedEdge.source]
            const tgtNpc = npcs[highlightedEdge.target]
            if (!srcNpc || !tgtNpc) return null

            const dx = tgtPos.x - srcPos.x
            const dy = tgtPos.y - srcPos.y
            const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
            const srcR = 8 + srcNpc.personality.social_influence * 10
            const tgtR = 8 + tgtNpc.personality.social_influence * 10

            const x1 = srcPos.x + (dx / dist) * srcR
            const y1 = srcPos.y + (dy / dist) * srcR
            const x2 = tgtPos.x - (dx / dist) * (tgtR + 4)
            const y2 = tgtPos.y - (dy / dist) * (tgtR + 4)

            return (
              <>
                <line
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke="#6366f1" strokeWidth={6} opacity={0.15}
                  strokeLinecap="round"
                />
                <line
                  x1={x1} y1={y1} x2={x2} y2={y2}
                  stroke="#6366f1" strokeWidth={2.5} opacity={0.9}
                  markerEnd="url(#influence-arrow)"
                  strokeLinecap="round"
                />
              </>
            )
          })()}

          {/* ── Edge hover hitboxes ── */}
          {edges.map(edge => {
            const s = positions[edge.source]
            const t = positions[edge.target]
            if (!s || !t) return null
            const sortedKey = [edge.source, edge.target].sort().join('|')
            return (
              <line
                key={`hit-${sortedKey}`}
                x1={s.x} y1={s.y} x2={t.x} y2={t.y}
                stroke="transparent"
                strokeWidth={14}
                onMouseEnter={() => { if (!dragRef.current) setHoveredEdgeKey(sortedKey) }}
                onMouseLeave={() => setHoveredEdgeKey(null)}
              />
            )
          })}

          {/* ── Nodes (circles + selection rings, NO labels here) ── */}
          {npcList.map(npc => {
            const pos = positions[npc.id]
            if (!pos) return null
            const r = 8 + npc.personality.social_influence * 10
            const color = STANCE_COLORS[npc.stance as Stance] ?? '#d1d5db'
            const isSelected = selectedNpcId === npc.id
            const isConnected = connectedSet.has(npc.id)
            const isHlNode = highlightedEdge &&
              (highlightedEdge.source === npc.id || highlightedEdge.target === npc.id)
            const is2Hop = twoHopSet.has(npc.id)

            // Tiered opacity: selected/1-hop = 1, 2-hop = 0.35, outside = 0.06
            let nodeOpacity = 1
            if (highlightedEdge !== null && !isHlNode && !isSelected) {
              nodeOpacity = 0.06
            } else if (hasSelection) {
              if (isSelected || isConnected) nodeOpacity = 1
              else if (is2Hop) nodeOpacity = 0.35
              else nodeOpacity = 0.06
            }

            return (
              <g
                key={npc.id}
                data-npc={npc.id}
                onClick={() => handleNodeClick(npc.id)}
                onMouseEnter={() => setHoveredNpcId(npc.id)}
                onMouseLeave={() => setHoveredNpcId(null)}
                className="cursor-pointer"
                opacity={nodeOpacity}
                style={{ transition: 'opacity 300ms ease' }}
              >
                {isSelected && (
                  <circle
                    cx={pos.x} cy={pos.y} r={r + 8}
                    fill="none" stroke="#6366f1" strokeWidth={1.5}
                    className="halo-ring"
                  />
                )}
                {isSelected && (
                  <circle
                    cx={pos.x} cy={pos.y} r={r + 4}
                    fill="none" stroke="#4f46e5" strokeWidth={2}
                    opacity={0.6}
                  />
                )}
                {isConnected && !isSelected && (
                  <circle
                    cx={pos.x} cy={pos.y} r={r + 3}
                    fill="none" stroke="#a5b4fc" strokeWidth={1.5}
                    opacity={0.5}
                  />
                )}
                {isHlNode && !isSelected && (
                  <circle
                    cx={pos.x} cy={pos.y} r={r + 4}
                    fill="none" stroke="#6366f1" strokeWidth={2}
                    opacity={0.7}
                  />
                )}
                <circle
                  cx={pos.x} cy={pos.y} r={r}
                  fill={color}
                  stroke={isSelected ? '#1e1b4b' : '#fff'}
                  strokeWidth={isSelected ? 2.5 : 1.5}
                  style={{ transition: 'fill 700ms ease, stroke 300ms ease' }}
                />
              </g>
            )
          })}

          {/* ── Labels (top layer, pointer-events: none) ── */}
          <g style={{ pointerEvents: 'none' }}>
            {labelPlacements.map(lbl => {
              const isHlLabel = highlightedEdge &&
                (highlightedEdge.source === lbl.npcId || highlightedEdge.target === lbl.npcId || lbl.npcId === selectedNpcId)
              const is1Hop = lbl.npcId === selectedNpcId || connectedSet.has(lbl.npcId)
              const is2Hop = twoHopSet.has(lbl.npcId)

              let labelOpacity = 1
              let labelFill = '#6b7280'

              if (highlightedEdge !== null && !isHlLabel) {
                labelOpacity = 0.15
                labelFill = '#d1d5db'
              } else if (hasSelection) {
                if (is1Hop) { labelOpacity = 1; labelFill = '#6b7280' }
                else if (is2Hop) { labelOpacity = 0.5; labelFill = '#9ca3af' }
                else { labelOpacity = 0.15; labelFill = '#d1d5db' }
              }

              return (
                <text
                  key={`lbl-${lbl.npcId}`}
                  x={lbl.x}
                  y={lbl.y}
                  textAnchor={lbl.anchor}
                  fontSize="9"
                  fill={labelFill}
                  fontFamily="system-ui"
                  opacity={labelOpacity}
                  style={{ transition: 'fill 300ms ease, opacity 200ms ease' }}
                >
                  {lbl.text}
                </text>
              )
            })}
            {/* Hovered label (always visible even if not in placed set) */}
            {hoveredNpcId && !labelPlacedIds.has(hoveredNpcId) && positions[hoveredNpcId] && (() => {
              const npc = npcs[hoveredNpcId]
              if (!npc) return null
              const pos = positions[hoveredNpcId]
              const r = 8 + npc.personality.social_influence * 10
              return (
                <text
                  x={pos.x}
                  y={pos.y + r + 12}
                  textAnchor="middle"
                  fontSize="9"
                  fill="#6b7280"
                  fontFamily="system-ui"
                >
                  {view.scale > 1.8 ? npc.name : npc.name.split(' ')[0]}
                </text>
              )
            })()}
          </g>
        </g>
      </svg>

      {/* ── Zoom controls ── */}
      <div className="absolute top-3 left-3 flex flex-col items-center gap-1 select-none">
        <button
          onClick={zoomIn}
          className="w-8 h-8 flex items-center justify-center bg-white/90 border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50 text-sm font-medium shadow-sm backdrop-blur-sm"
          title="Zoom in"
        >
          +
        </button>
        <span className="text-[10px] text-gray-400 tabular-nums">{zoomPercent}%</span>
        <button
          onClick={zoomOut}
          className="w-8 h-8 flex items-center justify-center bg-white/90 border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50 text-sm font-medium shadow-sm backdrop-blur-sm"
          title="Zoom out"
        >
          &minus;
        </button>
        <button
          onClick={resetViewAnimated}
          className="w-8 h-8 flex items-center justify-center bg-white/90 border border-gray-200 rounded-lg text-gray-500 hover:bg-gray-50 shadow-sm backdrop-blur-sm mt-1"
          title="Reset view"
        >
          <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="2" y="2" width="12" height="12" rx="1.5" />
            <circle cx="8" cy="8" r="2" />
          </svg>
        </button>
      </div>

      {/* ── Edge hover tooltip ── */}
      {hoveredDetail && (
        <div className="absolute bottom-3 left-3 bg-white/95 border border-gray-200 rounded-lg px-3 py-2 shadow-md text-xs max-w-[260px] backdrop-blur-sm pointer-events-none">
          <div className="font-medium text-gray-700 mb-1">
            {hoveredDetail.sourceName.split(' ')[0]} &harr; {hoveredDetail.targetName.split(' ')[0]}
          </div>
          <div className="flex gap-3 text-gray-500">
            <span>Trust: {(hoveredDetail.trust * 100).toFixed(0)}%</span>
            {hoveredDetail.discussionCount > 0 && (
              <span>{hoveredDetail.discussionCount} discussion{hoveredDetail.discussionCount !== 1 ? 's' : ''}</span>
            )}
            {hoveredDetail.totalInfluence > 0 && (
              <span>Influence: {(hoveredDetail.totalInfluence * 100).toFixed(0)}%</span>
            )}
          </div>
          {hoveredDetail.keyPoints.length > 0 && (
            <div className="mt-1 text-gray-400 italic">
              {hoveredDetail.keyPoints.map((kp, i) => (
                <span key={i}>"{kp}"{i < hoveredDetail.keyPoints.length - 1 ? ' · ' : ''}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
