import { useState, useCallback, useRef, useEffect } from 'react'
import type { NpcNode, Stance, SimEvent, AskNpcResponse } from '../types'
import { STANCE_COLORS, getInfluenceRecords } from '../types'

// ---- Types ----

interface ChatMessage {
  id: string
  role: 'user' | 'npc'
  content: string
  timestamp: number
  stance?: string
  interestScore?: number
}

type ChatStatus = 'idle' | 'thinking' | 'recalling' | 'responding'

interface Props {
  npc: NpcNode
  events: SimEvent[]
  simulationId: string
}

// ---- Constants ----

const PROMPT_CHIPS = [
  { label: 'Why this stance?', question: 'Why do you feel this way about this idea?' },
  { label: 'Change your mind?', question: 'What would it take to change your mind?' },
  { label: 'Recommend it?', question: 'Would you recommend this to a friend? Why or why not?' },
  { label: 'Biggest concern', question: 'What is your single biggest concern about this idea?' },
]

const STATUS_SEQUENCE: { status: ChatStatus; label: string; delayMs: number }[] = [
  { status: 'thinking', label: 'is thinking', delayMs: 0 },
  { status: 'recalling', label: 'is recalling discussions', delayMs: 1200 },
  { status: 'responding', label: 'is choosing their words', delayMs: 3000 },
]

const STANCE_CHIP_STYLES: Record<string, string> = {
  opposed: 'bg-red-100 text-red-700',
  skeptical: 'bg-amber-100 text-amber-700',
  indifferent: 'bg-gray-100 text-gray-500',
  curious: 'bg-lime-100 text-lime-700',
  interested: 'bg-green-100 text-green-700',
  willing_to_try: 'bg-emerald-100 text-emerald-700',
  willing_to_pay: 'bg-emerald-100 text-emerald-800',
  aware: 'bg-blue-100 text-blue-600',
  unaware: 'bg-gray-100 text-gray-400',
}

// ---- Component ----

export default function NpcChat({ npc, events, simulationId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [status, setStatus] = useState<ChatStatus>('idle')
  const [statusLabel, setStatusLabel] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [expandedGrounding, setExpandedGrounding] = useState<string | null>(null)

  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const statusTimers = useRef<ReturnType<typeof setTimeout>[]>([])
  const firstName = npc.name.split(' ')[0]

  // Auto-scroll on new messages or status change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, status])

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 80) + 'px'
    }
  }, [input])

  // Cleanup timers on unmount
  useEffect(() => {
    return () => { statusTimers.current.forEach(clearTimeout) }
  }, [])

  // Derive grounding context for a given message
  const getGroundingContext = useCallback((msg: ChatMessage) => {
    const stance = msg.stance ?? npc.stance
    const interest = msg.interestScore ?? npc.interest_score
    const topObjection = npc.objections[0] ?? null

    // Most recent influence
    const influences = getInfluenceRecords(npc.id, events)
    const lastInfluence = influences.length > 0 ? influences[influences.length - 1] : null

    return { stance, interest, topObjection, lastInfluence }
  }, [npc, events])

  const startStatusSequence = useCallback(() => {
    // Clear any existing timers
    statusTimers.current.forEach(clearTimeout)
    statusTimers.current = []

    for (const step of STATUS_SEQUENCE) {
      const timer = setTimeout(() => {
        setStatus(step.status)
        setStatusLabel(`${firstName} ${step.label}`)
      }, step.delayMs)
      statusTimers.current.push(timer)
    }
  }, [firstName])

  const stopStatusSequence = useCallback(() => {
    statusTimers.current.forEach(clearTimeout)
    statusTimers.current = []
    setStatus('idle')
    setStatusLabel('')
  }, [])

  const sendMessage = useCallback(async (question: string) => {
    const trimmed = question.trim()
    if (!trimmed || status !== 'idle') return

    // Add user message
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
    }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setError(null)

    // Start status animation
    startStatusSequence()

    try {
      const res = await fetch(`/api/simulations/${simulationId}/ask-npc`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ npc_id: npc.id, question: trimmed }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Request failed' }))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }
      const data: AskNpcResponse = await res.json()

      // Add NPC response
      const npcMsg: ChatMessage = {
        id: `npc-${Date.now()}`,
        role: 'npc',
        content: data.answer,
        timestamp: Date.now(),
        stance: data.stance,
        interestScore: data.interest_score,
      }
      setMessages(prev => [...prev, npcMsg])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      stopStatusSequence()
    }
  }, [simulationId, npc.id, status, startStatusSequence, stopStatusSequence])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }, [input, sendMessage])

  const stanceColor = STANCE_COLORS[npc.stance as Stance] ?? '#9ca3af'
  const isLoading = status !== 'idle'

  return (
    <section className="border-t pt-3">
      {/* Section header with NPC presence */}
      <div className="flex items-center gap-2 mb-2">
        <div
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: stanceColor }}
        />
        <span className="text-xs font-medium text-gray-400 uppercase flex-1">
          Chat with {firstName}
        </span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${STANCE_CHIP_STYLES[npc.stance] ?? 'bg-gray-100 text-gray-500'}`}>
          {npc.stance.replace(/_/g, ' ')}
        </span>
      </div>

      {/* Chat area */}
      <div
        ref={scrollRef}
        className="bg-gray-50 rounded-lg border border-gray-100 overflow-y-auto mb-2"
        style={{ maxHeight: '280px', minHeight: '120px' }}
      >
        {/* Empty state */}
        {messages.length === 0 && !isLoading && (
          <div className="flex items-center justify-center h-[120px] text-xs text-gray-400 px-4 text-center">
            Ask {firstName} about their reaction to the idea.
            <br />
            Responses are grounded in their actual simulation experience.
          </div>
        )}

        {/* Messages */}
        <div className="p-2 space-y-2">
          {messages.map(msg => (
            <div key={msg.id}>
              {msg.role === 'user' ? (
                /* User bubble — right aligned */
                <div className="flex justify-end">
                  <div className="max-w-[85%] bg-indigo-600 text-white rounded-2xl rounded-br-sm px-3 py-1.5 text-xs">
                    {msg.content}
                  </div>
                </div>
              ) : (
                /* NPC bubble — left aligned */
                <div className="flex flex-col items-start">
                  <div className="max-w-[85%] bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-3 py-2 shadow-sm">
                    <p className="text-xs text-gray-700 leading-relaxed">{msg.content}</p>
                  </div>
                  {/* Grounding transparency toggle */}
                  <button
                    onClick={() => setExpandedGrounding(
                      expandedGrounding === msg.id ? null : msg.id
                    )}
                    className="text-[10px] text-gray-400 hover:text-gray-500 mt-0.5 ml-1 flex items-center gap-0.5"
                  >
                    <span>{expandedGrounding === msg.id ? '▾' : '▸'}</span>
                    based on simulation state
                  </button>
                  {/* Grounding detail */}
                  {expandedGrounding === msg.id && (
                    <GroundingDetail
                      context={getGroundingContext(msg)}
                      stanceColor={stanceColor}
                    />
                  )}
                </div>
              )}
            </div>
          ))}

          {/* Typing indicator */}
          {isLoading && (
            <div className="flex flex-col items-start">
              <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-3 py-2 shadow-sm">
                <TypingDots />
              </div>
              {statusLabel && (
                <span className="text-[10px] text-gray-400 mt-0.5 ml-1 animate-pulse">
                  {statusLabel}...
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="text-[11px] text-red-500 bg-red-50 rounded px-2 py-1 mb-2">
          {error}
        </div>
      )}

      {/* Prompt chips */}
      {messages.length < 2 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {PROMPT_CHIPS.map(chip => (
            <button
              key={chip.label}
              onClick={() => sendMessage(chip.question)}
              disabled={isLoading}
              className="text-[10px] px-2 py-0.5 rounded-full border border-gray-200 text-gray-500 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {chip.label}
            </button>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className="flex gap-1.5 items-end">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={`Ask ${firstName} something...`}
          disabled={isLoading}
          maxLength={500}
          rows={1}
          className="flex-1 text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 resize-none focus:outline-none focus:border-indigo-300 focus:ring-1 focus:ring-indigo-100 disabled:opacity-50 disabled:bg-gray-50"
          style={{ minHeight: '32px' }}
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={isLoading || !input.trim()}
          className="text-xs px-3 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1 flex-shrink-0"
          style={{ height: '32px' }}
        >
          {isLoading ? (
            <div className="w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
          ) : (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          )}
        </button>
      </div>
    </section>
  )
}


// ---- Typing dots indicator ----

function TypingDots() {
  return (
    <div className="flex items-center gap-1 h-4 px-0.5">
      {[0, 1, 2].map(i => (
        <div
          key={i}
          className="w-1.5 h-1.5 bg-gray-400 rounded-full"
          style={{
            animation: 'npc-typing-bounce 1.2s ease-in-out infinite',
            animationDelay: `${i * 0.15}s`,
          }}
        />
      ))}
      <style>{`
        @keyframes npc-typing-bounce {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
          30% { transform: translateY(-4px); opacity: 1; }
        }
      `}</style>
    </div>
  )
}


// ---- Grounding transparency detail ----

interface GroundingContext {
  stance: string
  interest: number
  topObjection: string | null
  lastInfluence: { fromName: string; tick: number; delta: number } | null
}

function GroundingDetail({ context, stanceColor }: { context: GroundingContext; stanceColor: string }) {
  return (
    <div className="ml-1 mt-1 mb-1 bg-gray-50 border border-gray-100 rounded-lg px-2.5 py-1.5 space-y-1 max-w-[85%]">
      <div className="flex items-center gap-2 flex-wrap">
        <span
          className="text-[10px] px-1.5 py-0.5 rounded text-white"
          style={{ backgroundColor: stanceColor }}
        >
          {context.stance.replace(/_/g, ' ')}
        </span>
        <span className="text-[10px] text-gray-400">
          Interest: {Math.round(context.interest * 100)}%
        </span>
      </div>
      {context.topObjection && (
        <p className="text-[10px] text-gray-500">
          <span className="text-gray-400">Top concern:</span> {context.topObjection}
        </p>
      )}
      {context.lastInfluence && (
        <p className="text-[10px] text-gray-500">
          <span className="text-gray-400">Last influenced by:</span>{' '}
          {context.lastInfluence.fromName} (R{context.lastInfluence.tick},{' '}
          {context.lastInfluence.delta > 0 ? '+' : ''}
          {(context.lastInfluence.delta * 100).toFixed(0)}%)
        </p>
      )}
    </div>
  )
}
