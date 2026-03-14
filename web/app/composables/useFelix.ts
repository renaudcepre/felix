import type { ChatResponse, UsageInfo } from '~/types'

interface ChatMessage {
  role: 'user' | 'felix'
  content: string
}

export function useFelix() {
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)
  const messageHistory = ref<object[]>([])
  const lastUsage = ref<UsageInfo | null>(null)

  async function sendMessage(text: string) {
    messages.value.push({ role: 'user', content: text })
    loading.value = true
    lastUsage.value = null

    try {
      const data = await $fetch<ChatResponse>('/api/chat', {
        method: 'POST',
        body: {
          message: text,
          message_history: messageHistory.value,
        },
      })

      messages.value.push({ role: 'felix', content: data.output })
      messageHistory.value = data.message_history
      lastUsage.value = data.usage
    }
    catch (error) {
      const msg = error instanceof Error ? error.message : 'Erreur inconnue'
      messages.value.push({ role: 'felix', content: `Erreur : ${msg}` })
    }
    finally {
      loading.value = false
    }
  }

  function clearChat() {
    messages.value = []
    messageHistory.value = []
    lastUsage.value = null
  }

  return { messages, loading, lastUsage, sendMessage, clearChat }
}
