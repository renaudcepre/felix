import type { ChatResponse } from '~/types'

interface ChatMessage {
  role: 'user' | 'felix'
  content: string
}

export function useFelix() {
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)
  const messageHistory = ref<object[]>([])

  async function sendMessage(text: string) {
    messages.value.push({ role: 'user', content: text })
    loading.value = true

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
  }

  return { messages, loading, sendMessage, clearChat }
}
