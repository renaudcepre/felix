import type { AtelierMsg } from '~/types/atelier'
import { parseSSEStream } from '~/utils/parseSSE'
import { currentProject, DEFAULT_PROJECT } from './useProject'

// Carte tool émise par le backend (event SSE `tool`) — cf. felix/core/models.py
interface ToolCardPayload {
  kind: 'tool'
  tool: 'fiche' | 'people'
  title: string
  subject: string
  field: string
  added: string
  // cible de la carte (#61) : id de fiche/événement, ou référence de relation
  entity_id: string | null
  relation: { from_id: string, to_id: string, rel_type: string, verbe_slug?: string | null } | null
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

// Conversation PAR PROJET (#60) : changer d'histoire change de fil — le fil
// threadé du maître référence les entités de SON histoire, le partager
// contaminerait l'autre. Le projet par défaut garde la clé historique (la
// conversation d'avant le scoping survit au passage à #60).
const STORAGE_BASE = 'felix.atelier.conversation.v1'
const storageKey = (project: string) =>
  project === DEFAULT_PROJECT ? STORAGE_BASE : `${STORAGE_BASE}:${project}`

// État SINGLETON (hors de useAtelier) : il survit au démontage/remontage de la
// page. Avant, useAtelier() recréait des refs neuves à chaque appel → quitter
// /chat et revenir repartait de zéro. Ici on le persiste aussi en localStorage
// pour survivre au reload (F5). La bible (Neo4j) gardait déjà l'univers ; ce
// qu'on garde ici, c'est le FIL de conversation + l'historique threadé au LLM
// (messageHistory) sans quoi Felix perdrait le contexte en reprenant.
// Hypothèse assumée : app local-first MONO-utilisateur (pas de fuite inter-requêtes).
let _seq = 0
const uid = () => ++_seq

const messages = ref<AtelierMsg[]>([])
const typing = ref(false)
// Activité en cours côté backend (passes relieur/chroniqueur, check de
// cohérence) — affichée près de l'indicateur de frappe pour ne pas laisser
// l'auteur devant un long silence pendant ces passes non streamées.
const phase = ref<string | null>(null)
const messageHistory = ref<object[]>([])
// Garde-fou « session muette » (issue #43) : si la bible est toujours vide après
// 3 tours d'auteur, on l'affiche au lieu de laisser la session se perdre en
// silence. Toute carte `tool` est une écriture (les lectures n'émettent pas de
// carte) — le compteur repart à zéro dès que la bible bouge.
const silentTurns = ref(0)
const everWrote = ref(false)
const silentSession = computed(() => !everWrote.value && silentTurns.value >= 3)

let initialized = false
let persistTimer: ReturnType<typeof setTimeout> | null = null

function persist(project: string = currentProject.value) {
  if (!import.meta.client) return
  try {
    localStorage.setItem(storageKey(project), JSON.stringify({
      seq: _seq,
      messages: messages.value,
      messageHistory: messageHistory.value,
      silentTurns: silentTurns.value,
      everWrote: everWrote.value,
    }))
  }
  catch { /* quota / mode privé : on dégrade silencieusement vers le non-persisté */ }
}

function schedulePersist() {
  if (!import.meta.client) return
  if (persistTimer) clearTimeout(persistTimer)
  // Débounce : le stream pousse beaucoup de deltas texte, inutile d'écrire à chaque.
  persistTimer = setTimeout(persist, 300)
}

function freshWelcome() {
  _seq = 0
  messages.value = [{ id: uid(), ...WELCOME }]
  messageHistory.value = []
  silentTurns.value = 0
  everWrote.value = false
}

function hydrate(): boolean {
  if (!import.meta.client) return false
  const raw = localStorage.getItem(storageKey(currentProject.value))
  if (!raw) return false
  try {
    const s = JSON.parse(raw) as {
      seq?: number
      messages?: AtelierMsg[]
      messageHistory?: object[]
      silentTurns?: number
      everWrote?: boolean
    }
    if (!Array.isArray(s.messages) || s.messages.length === 0) return false
    messages.value = s.messages
    messageHistory.value = Array.isArray(s.messageHistory) ? s.messageHistory : []
    silentTurns.value = s.silentTurns ?? 0
    everWrote.value = s.everWrote ?? false
    _seq = s.seq ?? messages.value.reduce((m, x) => Math.max(m, x.id), 0)
    return true
  }
  catch {
    return false
  }
}

function ensureInit() {
  if (initialized) return
  initialized = true
  if (!hydrate()) freshWelcome()
  // Persiste à chaque évolution du fil : texte streamé, cartes, édits (#61),
  // nouvel historique threadé. Scope DÉTACHÉ (effectScope(true)) sinon le watch,
  // créé pendant le setup de la 1ʳᵉ page, serait tué à son démontage → la
  // persistance des édits s'arrêterait après la 1ʳᵉ navigation.
  if (import.meta.client) {
    effectScope(true).run(() => {
      watch([messages, messageHistory], schedulePersist, { deep: true })
      // Changement d'histoire : on fige le fil de l'ANCIEN projet sous sa clé
      // (flush du débounce), puis on charge celui du nouveau (ou un fil vierge).
      watch(currentProject, (_nv, ov) => {
        if (persistTimer) clearTimeout(persistTimer)
        persist(ov)
        if (!hydrate()) freshWelcome()
        persist()
      })
    })
  }
}

// Repartir d'une conversation vierge (et oublier la persistée).
function newConversation() {
  freshWelcome()
  persist()
}

export function useAtelier() {
  const { apiStreamBase } = useRuntimeConfig().public
  ensureInit()

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
    let wroteThisTurn = false

    try {
      const response = await fetch(`${apiStreamBase}/api/atelier/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: t,
          message_history: messageHistory.value,
          // Histoire courante (#60) : le serveur est stateless, chaque tour la porte.
          project: currentProject.value,
        }),
      })

      if (!response.ok) {
        const err = await response.text()
        throw new Error(err || `HTTP ${response.status}`)
      }

      for await (const sse of parseSSEStream(response)) {
        switch (sse.event) {
          case 'phase':
            // Une passe non streamée commence (relieur / chroniqueur / check).
            phase.value = sse.data
            typing.value = true
            break
          case 'text':
            typing.value = false
            phase.value = null
            if (!current) current = append({ role: 'felix', kind: 'text', body: '' })
            current.body += sse.data
            messages.value = [...messages.value]
            break
          case 'tool': {
            const card = JSON.parse(sse.data) as ToolCardPayload
            current = null
            wroteThisTurn = true
            append({
              role: 'felix',
              kind: 'tool',
              tool: card.tool,
              title: card.title,
              subject: card.subject,
              field: card.field,
              added: card.added,
              entityId: card.entity_id ?? undefined,
              relation: card.relation ?? undefined,
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
      phase.value = null
      if (wroteThisTurn) {
        everWrote.value = true
        silentTurns.value = 0
      }
      else {
        silentTurns.value += 1
      }
      persist()
    }
  }

  return { messages, typing, phase, sendMessage, silentSession, newConversation }
}
