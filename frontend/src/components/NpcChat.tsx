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
  { label: 'Why this stance?', question: 'Why do you feel this way about this idea?', icon: 'help' },
  { label: 'Change your mind?', question: 'What would it take to change your mind?', icon: 'swap_horiz' },
  { label: 'Recommend it?', question: 'Would you recommend this to a friend? Why or why not?', icon: 'share' },
  { label: 'Biggest concern', question: 'What is your single biggest concern about this idea?', icon: 'warning' },
]

const STATUS_SEQUENCE: { status: ChatStatus; label: string; delayMs: number }[] = [
  { status: 'thinking', label: 'is thinking', delayMs: 0 },
  { status: 'recalling', label: 'is recalling discussions', delayMs: 1200 },
  { status: 'responding', label: 'is choosing their words', delayMs: 3000 },
]

const STANCE_CHIP_STYLES: Record<string, string> = {
  opposed: 'bg-red-50 text-red-700',
  skeptical: 'bg-amber-50 text-amber-700',
  indifferent: 'bg-surface-container text-outline',
  curious: 'bg-lime-50 text-lime-700',
  interested: 'bg-green-50 text-green-700',
  willing_to_try: 'bg-emerald-50 text-emerald-700',
  willing_to_pay: 'bg-emerald-50 text-emerald-800',
  aware: 'bg-blue-50 text-blue-600',
  unaware: 'bg-surface-container text-outline',
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

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages, status])

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 80) + 'px'
    }
  }, [input])

  useEffect(() => {
    return () => { statusTimers.current.forEach(clearTimeout) }
  }, [])

  const getGroundingContext = useCallback((msg: ChatMessage) => {
    const stance = msg.stance ?? npc.stance
    const interest = msg.interestScore ?? npc.interest_score
    const topObjection = npc.objections[0] ?? null

    const influences = getInfluenceRecords(npc.id, events)
    const lastInfluence = influences.length > 0 ? influences[influences.length - 1] : null

    return { stance, interest, topObjection, lastInfluence }
  }, [npc, events])

  const startStatusSequence = useCallback(() => {
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

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
    }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setError(null)

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
    <section className="border-t border-outline-variant/20 pt-4">
      {/* Section header */}
      <div className="flex items-center gap-2 mb-3">
        <div
          className="w-2.5 h-2.5 rounded-full flex-shrink-0 shadow-sm"
          style={{ backgroundColor: stanceColor }}
        />
        <span className="material-symbols-outlined text-[16px] text-primary">chat</span>
        <span className="text-xs font-semibold text-outline uppercase tracking-widest flex-1">
          Chat with {firstName}
        </span>
        <span className={`text-[10px] px-2 py-0.5 rounded-lg font-semibold ${STANCE_CHIP_STYLES[npc.stance] ?? 'bg-surface-container text-outline'}`}>
          {npc.stance.replace(/_/g, ' ')}
        </span>
      </div>

      {/* Chat area */}
      <div
        ref={scrollRef}
        className="bg-surface-container-low rounded-2xl border border-outline-variant/15 overflow-y-auto mb-3 glass-scrollbar"
        style={{ maxHeight: '280px', minHeight: '120px' }}
      >
        {messages.length === 0 && !isLoading && (
          <div className="flex flex-col items-center justify-center h-[120px] text-xs text-outline px-4 text-center gap-1">
            <span className="material-symbols-outlined text-[24px] text-outline-variant">forum</span>
            <span>Ask {firstName} about their reaction to the idea.</span>
            <span className="text-[10px] text-outline-variant">Responses are grounded in their simulation experience.</span>
          </div>
        )}

        <div className="p-3 space-y-3">
          {messages.map(msg => (
            <div key={msg.id}>
              {msg.role === 'user' ? (
                <div className="flex justify-end">
                  <div className="max-w-[85%] bg-gradient-to-r from-primary to-primary-container text-on-primary rounded-2xl rounded-br-sm px-4 py-2 text-xs shadow-sm">
                    {msg.content}
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-start">
                  <div className="max-w-[85%] bg-surface-container-lowest border border-outline-variant/20 rounded-2xl rounded-bl-sm px-4 py-2.5 shadow-sm">
                    <p className="text-xs text-on-surface leading-relaxed">{msg.content}</p>
                  </div>
                  <button
                    onClick={() => setExpandedGrounding(
                      expandedGrounding === msg.id ? null : msg.id
                    )}
                    className="text-[10px] text-outline hover:text-on-surface-variant mt-1 ml-1 flex items-center gap-1 transition-colors"
                  >
                    <span className="material-symbols-outlined text-[12px]">
                      {expandedGrounding === msg.id ? 'expand_more' : 'chevron_right'}
                    </span>
                    based on simulation state
                  </button>
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

          {isLoading && (
            <div className="flex flex-col items-start">
              <div className="bg-surface-container-lowest border border-outline-variant/20 rounded-2xl rounded-bl-sm px-4 py-2.5 shadow-sm">
                <TypingDots />
              </div>
              {statusLabel && (
                <span className="text-[10px] text-outline mt-1 ml-1 animate-pulse flex items-center gap-1">
                  <span className="material-symbols-outlined text-[12px]">hourglass_empty</span>
                  {statusLabel}...
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="text-[11px] text-error bg-error-container/30 rounded-xl px-3 py-2 mb-3 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[14px]">error</span>
          {error}
        </div>
      )}

      {/* Prompt chips */}
      {messages.length < 2 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {PROMPT_CHIPS.map(chip => (
            <button
              key={chip.label}
              onClick={() => sendMessage(chip.question)}
              disabled={isLoading}
              className="text-[10px] px-2.5 py-1 rounded-xl border border-outline-variant/30 text-on-surface-variant hover:border-primary/30 hover:text-primary hover:bg-primary/5 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-1 font-medium"
            >
              <span className="material-symbols-outlined text-[12px]">{chip.icon}</span>
              {chip.label}
            </button>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className="flex gap-2 items-end">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={`Ask ${firstName} something...`}
          disabled={isLoading}
          maxLength={500}
          rows={1}
          className="flex-1 text-xs border border-outline-variant/30 rounded-xl px-3 py-2 resize-none focus:outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/10 disabled:opacity-50 disabled:bg-surface-container bg-surface-container-lowest text-on-surface placeholder:text-outline"
          style={{ minHeight: '36px' }}
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={isLoading || !input.trim()}
          className="text-xs px-3 py-2 rounded-xl bg-gradient-to-r from-primary to-primary-container text-on-primary hover:shadow-lg hover:shadow-primary/20 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-1 flex-shrink-0 font-semibold"
          style={{ height: '36px' }}
        >
          {isLoading ? (
            <div className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
          ) : (
            <span className="material-symbols-outlined text-[16px]">send</span>
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
          className="w-1.5 h-1.5 bg-outline rounded-full"
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
    <div className="ml-1 mt-1 mb-1 bg-surface-container-low border border-outline-variant/15 rounded-xl px-3 py-2 space-y-1 max-w-[85%]">
      <div className="flex items-center gap-2 flex-wrap">
        <span
          className="text-[10px] px-1.5 py-0.5 rounded-md text-white font-medium"
          style={{ backgroundColor: stanceColor }}
        >
          {context.stance.replace(/_/g, ' ')}
        </span>
        <span className="text-[10px] text-outline">
          Interest: {Math.round(context.interest * 100)}%
        </span>
      </div>
      {context.topObjection && (
        <p className="text-[10px] text-on-surface-variant">
          <span className="text-outline">Top concern:</span> {context.topObjection}
        </p>
      )}
      {context.lastInfluence && (
        <p className="text-[10px] text-on-surface-variant">
          <span className="text-outline">Last influenced by:</span>{' '}
          {context.lastInfluence.fromName} (R{context.lastInfluence.tick},{' '}
          {context.lastInfluence.delta > 0 ? '+' : ''}
          {(context.lastInfluence.delta * 100).toFixed(0)}%)
        </p>
      )}
    </div>
  )
}
