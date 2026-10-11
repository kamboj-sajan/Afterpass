/** Talking to the "Ask AfterPass" agent, and deciding where its map actions run. */

import { AGENT_URL } from './config'
import type { UiAction } from './store'

export const MAX_QUESTION_CHARS = 500

export interface ToolUse {
  name: string
  input: Record<string, unknown>
  ok: boolean
}

export interface AgentReply {
  answer: string
  tools_used: ToolUse[]
  ui_actions: UiAction[]
  /** Whether every figure in the answer was found in the data the agent looked up. */
  grounding?: { grounded: boolean; unmatched: string[] }
  error?: string
}

export class AgentError extends Error {
  readonly kind: 'unreachable' | 'failed'

  constructor(kind: 'unreachable' | 'failed') {
    super(kind)
    this.name = 'AgentError'
    this.kind = kind
  }
}

export async function askAgent(question: string, signal?: AbortSignal): Promise<AgentReply> {
  let response: Response
  try {
    response = await fetch(`${AGENT_URL}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
      signal,
    })
  } catch {
    throw new AgentError('unreachable')
  }
  // A 400 carries a normal reply explaining what was wrong with the question.
  if (!response.ok && response.status !== 400) throw new AgentError('failed')
  return (await response.json()) as AgentReply
}

const KEY_NUMBER = new RegExp('(\\d[\\d,.\\u00a0\\u2009\\u202f]*)\\s?(%|ha\\b|hectares?\\b|हेक्टेयर)')

/** The first figure with a unit in an answer ("850.6 ha", "98.9 %"), to show large. */
export function keyNumber(answer: string): string | null {
  const match = KEY_NUMBER.exec(answer)
  if (!match) return null
  const digits = match[1].replace(/[.,]$/, '')
  return match[2] === '%' ? `${digits}%` : `${digits} ${match[2]}`
}

/** The place, week or topic a tool call was about, for its chip. */
export function toolDetail(use: ToolUse): string[] {
  const parts: string[] = []
  for (const key of ['district', 'place', 'topic', 'week', 'start_date'] as const) {
    const value = use.input[key]
    if (typeof value === 'string' && value !== '') parts.push(value.replaceAll('_', ' '))
  }
  if (typeof use.input.season === 'number') parts.push(String(use.input.season))
  return parts
}

/** Actions the Delhi screen can show without leaving it. */
const DELHI_ACTIONS: UiAction['type'][] = ['play_smoke', 'highlight_locality', 'fly_to']

/**
 * Where a reply's map actions should run. The Delhi screen keeps smoke actions; anything about
 * districts, villages or imagery belongs on the Explorer, so the app goes there first.
 */
export function actionTarget(actions: UiAction[], screen: 'map' | 'delhi'): 'none' | 'map' | 'delhi' {
  if (actions.length === 0) return 'none'
  if (screen === 'map') return 'map'
  const smoke = actions.some((action) => action.type === 'play_smoke' || action.type === 'highlight_locality')
  return smoke && actions.every((action) => DELHI_ACTIONS.includes(action.type)) ? 'delhi' : 'map'
}

export type Rich = { kind: 'line'; marker: string | null; parts: { text: string; bold: boolean }[] }

/** The little Markdown the agent writes: bold, and numbered or dashed lines. Nothing else. */
export function richText(answer: string): Rich[] {
  const lines: Rich[] = []
  for (const raw of answer.split('\n')) {
    // "**1. Name – 850 ha**" is a numbered line whose text is bold.
    let text = raw.trim().replace(/^\*\*(\d+\.)\s+/, '$1 **')
    if (text === '') continue
    let marker: string | null = null
    const item = /^(\d+\.|[-•])\s+/.exec(text)
    if (item) {
      marker = item[1] === '-' ? '•' : item[1]
      text = text.slice(item[0].length)
    }
    // Bold runs alternate with plain ones; stray emphasis asterisks are dropped.
    const parts = text
      .split('**')
      .map((piece, index) => ({ text: piece.replaceAll('*', ''), bold: index % 2 === 1 }))
      .filter((part) => part.text !== '')
    if (parts.length > 0) lines.push({ kind: 'line', marker, parts })
  }
  return lines
}
