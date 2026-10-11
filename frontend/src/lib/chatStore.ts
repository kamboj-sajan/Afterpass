/** The "Ask AfterPass" conversation. It lives outside the screens so it survives moving between them. */

import { create } from 'zustand'
import { AgentError, askAgent, type AgentReply } from './agent'

export interface ChatMessage {
  id: number
  question: string
  status: 'pending' | 'done' | 'error'
  reply?: AgentReply
  error?: AgentError['kind']
}

interface ChatState {
  open: boolean
  messages: ChatMessage[]
  setOpen: (open: boolean) => void
  /** Sends a question and resolves with the reply, or null if it could not be answered. */
  ask: (question: string) => Promise<AgentReply | null>
}

let nextId = 1

export const useChat = create<ChatState>((set, get) => ({
  open: false,
  messages: [],
  setOpen: (open) => set({ open }),
  ask: async (question) => {
    if (get().messages.some((message) => message.status === 'pending')) return null
    const id = nextId
    nextId += 1
    const update = (patch: Partial<ChatMessage>) =>
      set((state) => ({ messages: state.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)) }))
    set((state) => ({ messages: [...state.messages, { id, question, status: 'pending' }] }))
    try {
      const reply = await askAgent(question)
      update({ status: 'done', reply })
      return reply
    } catch (error) {
      update({ status: 'error', error: error instanceof AgentError ? error.kind : 'failed' })
      return null
    }
  },
}))
