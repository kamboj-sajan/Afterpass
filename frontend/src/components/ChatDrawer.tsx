import { CircleAlert, MessageCircle, Mic, SendHorizontal, X } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import {
  actionTarget,
  keyNumber,
  MAX_QUESTION_CHARS,
  richText,
  toolDetail,
  type AgentReply,
  type ToolUse,
} from '@/lib/agent'
import { useChat, type ChatMessage } from '@/lib/chatStore'
import { cn } from '@/lib/cn'
import { useDelhi } from '@/lib/delhiStore'
import { useExplorer } from '@/lib/store'

/** The questions offered before anyone has asked one (brief §12.7). */
const SUGGESTIONS = [
  'Which 10 villages in Sangrur had the most burning missing from official counts?',
  'Why do official counts miss so many fires?',
  'Will smoke reach Dwarka in the next 48 hours?',
  'संगरूर के किन गाँवों में सबसे ज़्यादा पराली जली जो सरकारी गिनती में नहीं आई?',
  'क्या अगले 48 घंटों में द्वारका तक धुआँ पहुँचेगा?',
]

/** The slice of the Web Speech API this drawer uses; browsers without it get no microphone button. */
interface Recognition {
  lang: string
  interimResults: boolean
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}

function recognition(): Recognition | null {
  const scope = window as unknown as Record<string, (new () => Recognition) | undefined>
  const Speech = scope.SpeechRecognition ?? scope.webkitSpeechRecognition
  return Speech ? new Speech() : null
}

const canListen =
  typeof window !== 'undefined' && ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)

/** Opens the drawer. Sits beside the timeline on every screen. */
export function AskButton() {
  const { t } = useTranslation()
  const open = useChat((s) => s.open)
  const setOpen = useChat((s) => s.setOpen)
  // The open drawer has its own close button and would cover this one.
  if (open) return null
  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      aria-expanded={false}
      data-testid="ask-button"
      className="panel focus-ring text-text hover:border-ember/60 inline-flex shrink-0 cursor-pointer items-center gap-2 px-4 text-sm font-medium transition-colors duration-200"
    >
      <MessageCircle size={17} className="text-ember-2" aria-hidden />
      <span className="max-lg:sr-only">{t('chat.open')}</span>
    </button>
  )
}

function ToolChip(props: { use: ToolUse }) {
  const { t } = useTranslation()
  const detail = toolDetail(props.use)
  return (
    <span className="border-hairline text-text-2 inline-flex items-center rounded-full border bg-black/25 px-2 py-0.5 text-[10px]">
      {[t(`chat.tool.${props.use.name}`, { defaultValue: props.use.name }), ...detail].join(' · ')}
      {!props.use.ok && ` · ${t('chat.toolFailed')}`}
    </span>
  )
}

function Answer(props: { reply: AgentReply }) {
  const { t } = useTranslation()
  const { reply } = props
  const headline = reply.error === undefined ? keyNumber(reply.answer) : null
  return (
    <div className="border-hairline rounded-xl border bg-black/25 p-3" data-testid="chat-answer">
      {headline !== null && (
        <p className="font-display text-ember-2 mb-1.5 text-2xl leading-none font-semibold" data-testid="chat-number">
          {headline}
        </p>
      )}
      <div className="text-text flex flex-col gap-1.5 text-[13px] leading-relaxed">
        {richText(reply.answer).map((line, index) => (
          <p key={index} className={cn(line.marker !== null && 'flex gap-2')}>
            {line.marker !== null && <span className="text-text-2 tabular shrink-0">{line.marker}</span>}
            <span>
              {line.parts.map((part, i) =>
                part.bold ? (
                  <strong key={i} className="font-semibold">
                    {part.text}
                  </strong>
                ) : (
                  <span key={i}>{part.text}</span>
                ),
              )}
            </span>
          </p>
        ))}
      </div>
      {reply.grounding?.grounded === false && (
        <p className="text-ember-2 mt-2 flex items-start gap-1.5 text-[11px]" role="note">
          <CircleAlert size={13} className="mt-px shrink-0" aria-hidden />
          {t('chat.unverified')}
        </p>
      )}
      {reply.tools_used.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1" aria-label={t('chat.toolsUsed')}>
          {reply.tools_used.map((use, index) => (
            <ToolChip key={index} use={use} />
          ))}
        </div>
      )}
    </div>
  )
}

function Exchange(props: { message: ChatMessage }) {
  const { t } = useTranslation()
  const { message } = props
  return (
    <li className="flex flex-col gap-2">
      <p className="bg-ember/15 text-text ml-8 self-end rounded-xl rounded-br-sm px-3 py-2 text-[13px]">
        {message.question}
      </p>
      {message.status === 'pending' && (
        <div className="flex flex-col gap-2" role="status" aria-label={t('chat.thinking')}>
          <div className="skeleton h-6 w-28" />
          <div className="skeleton h-14" />
          <p className="text-text-2 text-[11px]">{t('chat.thinking')}</p>
        </div>
      )}
      {message.status === 'error' && (
        <p className="border-hairline text-text-2 rounded-xl border p-3 text-xs" role="alert">
          {t(message.error === 'unreachable' ? 'chat.unreachable' : 'chat.failed')}
        </p>
      )}
      {message.reply && <Answer reply={message.reply} />}
    </li>
  )
}

/** The "Ask AfterPass" drawer (brief §12.7). Its answers come from the agent; it also runs their map actions. */
export function ChatDrawer(props: { screen: 'map' | 'delhi' }) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const open = useChat((s) => s.open)
  const setOpen = useChat((s) => s.setOpen)
  const messages = useChat((s) => s.messages)
  const ask = useChat((s) => s.ask)
  const [draft, setDraft] = useState('')
  const [listening, setListening] = useState(false)
  const listRef = useRef<HTMLOListElement>(null)
  const heard = useRef<Recognition | null>(null)
  const busy = messages.some((message) => message.status === 'pending')

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, setOpen])

  const runActions = (reply: AgentReply) => {
    const target = actionTarget(reply.ui_actions, props.screen)
    if (target === 'none') return
    if (target === 'delhi') {
      const delhi = useDelhi.getState()
      for (const action of reply.ui_actions) {
        if (action.type === 'play_smoke') delhi.requestRun(action.run_id, action.from_hour)
        else if (action.type === 'highlight_locality') delhi.setLocality(action.id)
        else if (action.type === 'fly_to') {
          delhi.flyTo({ longitude: action.lon, latitude: action.lat, zoom: action.zoom })
        }
      }
    } else {
      // The Explorer picks these up from its store, including when it opens a moment later.
      useExplorer.getState().runUiActions(reply.ui_actions)
      if (props.screen !== 'map') navigate('/map')
    }
    toast(t('chat.moved'))
  }

  const send = async (question: string) => {
    const text = question.trim()
    if (text === '' || busy) return
    setDraft('')
    const reply = await ask(text.slice(0, MAX_QUESTION_CHARS))
    if (reply !== null) runActions(reply)
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    void send(draft)
  }

  const listen = () => {
    if (listening) {
      heard.current?.stop()
      return
    }
    const session = recognition()
    if (session === null) return
    session.lang = i18n.language.startsWith('hi') ? 'hi-IN' : 'en-IN'
    session.interimResults = false
    session.onresult = (event) => setDraft(event.results[0][0].transcript.slice(0, MAX_QUESTION_CHARS))
    session.onend = () => setListening(false)
    heard.current = session
    setListening(true)
    session.start()
  }

  if (!open) return null
  return (
    <aside
      className="panel fixed top-(--edge) right-(--edge) bottom-(--edge) z-30 flex w-[min(400px,calc(100vw-2*var(--edge)))] flex-col"
      role="dialog"
      aria-label={t('chat.title')}
      data-testid="chat-drawer"
    >
      <header className="flex items-center justify-between gap-2 px-4 pt-3.5 pb-2">
        <h2 className="font-display text-text flex items-center gap-2 text-sm font-semibold tracking-[0.14em] uppercase">
          <MessageCircle size={15} className="text-ember-2" aria-hidden />
          {t('chat.title')}
        </h2>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label={t('chat.close')}
          className="focus-ring text-text-2 inline-flex size-7 cursor-pointer items-center justify-center rounded-md hover:text-white"
        >
          <X size={15} aria-hidden />
        </button>
      </header>

      <ol ref={listRef} className="scroll-thin flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 pb-3">
        {messages.length === 0 && (
          <li className="flex flex-col gap-3">
            <p className="text-text-2 text-xs leading-relaxed">{t('chat.intro')}</p>
            <p className="text-text-2 text-[11px] font-medium tracking-[0.12em] uppercase">{t('chat.suggestions')}</p>
            <div className="flex flex-col gap-1.5">
              {SUGGESTIONS.map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => void send(question)}
                  className="focus-ring border-hairline text-text cursor-pointer rounded-xl border bg-black/20 px-3 py-2 text-left text-xs leading-snug hover:bg-white/10"
                >
                  {question}
                </button>
              ))}
            </div>
          </li>
        )}
        {messages.map((message) => (
          <Exchange key={message.id} message={message} />
        ))}
      </ol>

      <form onSubmit={submit} className="border-hairline flex items-end gap-2 border-t p-3">
        <label className="min-w-0 flex-1">
          <span className="sr-only">{t('chat.placeholder')}</span>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value.slice(0, MAX_QUESTION_CHARS))}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void send(draft)
              }
            }}
            rows={2}
            placeholder={listening ? t('chat.listening') : t('chat.placeholder')}
            className="border-hairline text-text placeholder:text-text-2 focus-ring w-full resize-none rounded-lg border bg-black/25 px-2.5 py-2 text-[13px] outline-none"
          />
          <span className="tabular text-text-2 block text-right text-[10px]">
            {draft.length} / {MAX_QUESTION_CHARS}
          </span>
        </label>
        {canListen && (
          <button
            type="button"
            onClick={listen}
            aria-label={t('chat.voice')}
            aria-pressed={listening}
            title={t('chat.voice')}
            className={cn(
              'focus-ring border-hairline mb-4 inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full border',
              listening ? 'bg-ember text-bg' : 'text-text-2 hover:text-white',
            )}
          >
            <Mic size={15} aria-hidden />
          </button>
        )}
        <button
          type="submit"
          disabled={busy || draft.trim() === ''}
          aria-label={t('chat.send')}
          title={t('chat.send')}
          className="focus-ring bg-text text-bg mb-4 inline-flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full disabled:cursor-not-allowed disabled:opacity-40"
        >
          <SendHorizontal size={15} aria-hidden />
        </button>
      </form>
    </aside>
  )
}
