import type { UsageInfo } from '~/types'
import { parseSSEStream } from '~/utils/parseSSE'

interface ChatMessage {
  role: 'user' | 'felix'
  content: string
}

export function useFelix() {
  const { apiStreamBase } = useRuntimeConfig().public
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)
  const streaming = ref(false)
  const messageHistory = ref<object[]>([])
  const lastUsage = ref<UsageInfo | null>(null)

  async function sendMessage(text: string) {
    messages.value.push({ role: 'user', content: text })
    loading.value = true
    streaming.value = false
    lastUsage.value = null

    try {
      const response = await fetch(`${apiStreamBase}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          message_history: messageHistory.value,
        }),
      })

      if (!response.ok) {
        const err = await response.text()
        throw new Error(err || `HTTP ${response.status}`)
      }

      const felixMsg: ChatMessage = { role: 'felix', content: '' }
      messages.value.push(felixMsg)

      for await (const sse of parseSSEStream(response)) {
        switch (sse.event) {
          case 'content':
            if (!streaming.value) streaming.value = true
            felixMsg.content += sse.data
            messages.value = [...messages.value]
            break
          case 'usage':
            lastUsage.value = JSON.parse(sse.data) as UsageInfo
            break
          case 'history':
            messageHistory.value = JSON.parse(sse.data) as object[]
            break
          case 'error':
            felixMsg.content += `\n\nErreur : ${sse.data}`
            messages.value = [...messages.value]
            break
          case 'done':
            break
        }
      }
    }
    catch (error) {
      const msg = error instanceof Error ? error.message : 'Erreur inconnue'
      const last = messages.value[messages.value.length - 1]
      if (last?.role === 'felix') {
        last.content = last.content ? `${last.content}\n\nErreur : ${msg}` : `Erreur : ${msg}`
        messages.value = [...messages.value]
      }
      else {
        messages.value.push({ role: 'felix', content: `Erreur : ${msg}` })
      }
    }
    finally {
      loading.value = false
      streaming.value = false
    }
  }

  function clearChat() {
    messages.value = []
    messageHistory.value = []
    lastUsage.value = null
  }

  return { messages, loading, streaming, lastUsage, sendMessage, clearChat }
}
