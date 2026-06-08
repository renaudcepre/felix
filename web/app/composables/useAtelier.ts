import type { AtelierMsg } from '~/types/atelier'
import { parseSSEStream } from '~/utils/parseSSE'

// Carte tool émise par le backend (event SSE `tool`) — cf. felix/atelier/models.py
interface ToolCardPayload {
  kind: 'tool'
  tool: 'fiche' | 'people'
  title: string
  subject: string
  field: string
  added: string
}

// Alerte d'incohérence émise par le backend (event SSE `alert`) — cf. la route
// atelier (consistency_check sur les entités touchées).
interface AlertPayload {
  kind: 'alert'
  title: string
  body: string
  status: 'open' | 'resolving' | 'resolved' | 'dismissed'
}

const WELCOME: Omit<AtelierMsg, 'id'> = {
  role: 'felix',
  kind: 'text',
  body: 'Bonjour. Raconte-moi ton histoire : décris tes personnages au fil de l\'eau, et je tiendrai leurs fiches à jour dans la bible.',
}

export function useAtelier() {
  const { apiStreamBase } = useRuntimeConfig().public

  let _id = 0
  const uid = () => ++_id

  const messages = ref<AtelierMsg[]>([{ id: uid(), ...WELCOME }])
  const typing = ref(false)
  const messageHistory = ref<object[]>([])

  function append(msg: Omit<AtelierMsg, 'id'>): AtelierMsg {
    messages.value.push({ id: uid(), ...msg })
    // Renvoyer le PROXY réactif (pas l'objet brut) : sinon `current.body += …`
    // mute hors réactivité et l'enfant ne re-render qu'au 1ᵉ chunk de texte.
    return messages.value[messages.value.length - 1]!
  }

  async function sendMessage(text: string) {
    const t = text.trim()
    if (!t) return
    append({ role: 'user', kind: 'text', body: t })
    typing.value = true

    // Message texte felix en cours de stream ; une carte tool le clôt,
    // le delta suivant ouvre alors un nouveau message.
    let current: AtelierMsg | null = null

    try {
      const response = await fetch(`${apiStreamBase}/api/atelier/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: t,
          message_history: messageHistory.value,
        }),
      })

      if (!response.ok) {
        const err = await response.text()
        throw new Error(err || `HTTP ${response.status}`)
      }

      for await (const sse of parseSSEStream(response)) {
        switch (sse.event) {
          case 'text':
            typing.value = false
            if (!current) current = append({ role: 'felix', kind: 'text', body: '' })
            current.body += sse.data
            messages.value = [...messages.value]
            break
          case 'tool': {
            const card = JSON.parse(sse.data) as ToolCardPayload
            current = null
            append({
              role: 'felix',
              kind: 'tool',
              tool: card.tool,
              title: card.title,
              subject: card.subject,
              field: card.field,
              added: card.added,
            })
            break
          }
          case 'alert': {
            const a = JSON.parse(sse.data) as AlertPayload
            current = null
            append({ role: 'felix', kind: 'alert', title: a.title, body: a.body, status: a.status })
            break
          }
          case 'history':
            messageHistory.value = JSON.parse(sse.data) as object[]
            break
          case 'error':
            append({ role: 'felix', kind: 'text', body: `Erreur : ${sse.data}` })
            break
          case 'done':
            break
        }
      }
    }
    catch (error) {
      const msg = error instanceof Error ? error.message : 'Erreur inconnue'
      append({ role: 'felix', kind: 'text', body: `Erreur : ${msg}` })
    }
    finally {
      typing.value = false
    }
  }

  return { messages, typing, sendMessage }
}
