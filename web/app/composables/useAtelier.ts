import type { AtelierMsg } from '~/types/atelier'
import { parseSSEStream } from '~/utils/parseSSE'
import { currentProfile, profiles as atelierProfiles, useAtelierProfile } from './useAtelierProfile'
import { currentProject } from './useProject'

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

// Message persisté côté serveur (GET /api/atelier/conversation, #63).
interface ConversationMessageOut {
  id: string
  role: 'user' | 'felix'
  kind: 'text' | 'tool' | 'alert'
  body: string
  ord: number
  payload: Record<string, unknown> | null
}

// Repli si le backend n'a pas encore répondu à /api/atelier/profiles (offline,
// tout premier chargement) — neutre, aucun mot de fiction : le VRAI welcome
// vient du mode courant (cf. welcomeFor), pas de cette constante.
const FALLBACK_WELCOME = 'Bonjour. Décris ton sujet, et je tiendrai les fiches à jour au fil de la conversation.'

// Le message d'accueil vient du MODE courant (Étape 8, GET /api/atelier/profiles)
// — plus un seul texte scénario codé en dur pour tous les modes.
function welcomeFor(profileKey: string): string {
  return atelierProfiles.value.find(p => p.key === profileKey)?.welcome ?? FALLBACK_WELCOME
}

// État SINGLETON (hors de useAtelier) : survit au démontage/remontage de la page.
// Depuis #63 (brique 2), la conversation EST EN BASE Neo4j — source de vérité.
// Plus de localStorage pour le fil (felix.atelier.conversation.v1*) : les vieilles
// clés restent mortes dans les navigateurs, on ne migre pas (décision assumée).
// NE PAS TOUCHER à felix.project.v1 (useProject).
let _seq = 0
const uid = () => ++_seq

const messages = ref<AtelierMsg[]>([])
const typing = ref(false)
// Activité en cours côté backend (passes relieur/chroniqueur, check de
// cohérence) — affichée près de l'indicateur de frappe pour ne pas laisser
// l'auteur devant un long silence pendant ces passes non streamées.
const phase = ref<string | null>(null)
// Garde-fou « session muette » (issue #43) : si la bible est toujours vide après
// 3 tours d'auteur, on l'affiche au lieu de laisser la session se perdre en
// silence. Toute carte `tool` est une écriture (les lectures n'émettent pas de
// carte) — le compteur repart à zéro dès que la bible bouge.
// Ces deux flags sont désormais DÉRIVÉS du fil hydraté (pas stockés/lus de localStorage).
const silentTurns = ref(0)
const everWrote = ref(false)
const silentSession = computed(() => !everWrote.value && silentTurns.value >= 3)

let initialized = false

// Compteur de génération pour détecter les résultats périmés après un switch
// d'histoire pendant le fetch d'hydratation (évite d'afficher le fil de l'ancien
// projet si le nouveau projet répond en premier).
let _hydrationGen = 0

function freshWelcome() {
  _seq = 0
  messages.value = [{ id: uid(), role: 'felix', kind: 'text', body: welcomeFor(currentProfile.value) }]
  silentTurns.value = 0
  everWrote.value = false
}

// Dérive les compteurs de session muette depuis le fil hydraté.
// À appeler juste après avoir rempli messages.value depuis le serveur.
// everWrote = au moins une carte tool dans le fil (une écriture en base).
// silentTurns = si déjà écrit : 0 ; sinon le nombre de messages de l'auteur.
function deriveCounters() {
  const hasWrite = messages.value.some(m => m.kind === 'tool')
  everWrote.value = hasWrite
  silentTurns.value = hasWrite ? 0 : messages.value.filter(m => m.role === 'user').length
}

// Mapping ConversationMessageOut → AtelierMsg.
// Renvoie null pour les messages tool/alert dont le payload est absent (défensif :
// un bug de persistance ne doit pas faire planter l'hydratation entière).
function mapServerMsg(m: ConversationMessageOut): AtelierMsg | null {
  if (m.kind === 'text') {
    return {
      id: uid(),
      role: m.role === 'user' ? 'user' : 'felix',
      kind: 'text',
      body: m.body,
    }
  }
  if (m.kind === 'tool') {
    if (!m.payload) return null
    const p = m.payload as unknown as ToolCardPayload
    return {
      id: uid(),
      role: 'felix',
      kind: 'tool',
      tool: p.tool,
      title: p.title,
      subject: p.subject,
      field: p.field,
      added: p.added,
      entityId: p.entity_id ?? undefined,
      relation: p.relation ?? undefined,
    }
  }
  if (m.kind === 'alert') {
    if (!m.payload) return null
    const p = m.payload as unknown as AlertPayload
    return {
      id: uid(),
      role: 'felix',
      kind: 'alert',
      title: p.title,
      body: p.body,
      status: p.status,
    }
  }
  return null
}

// Hydratation depuis GET /api/atelier/conversation.
// Retourne :
//   'ok'    : fil chargé et appliqué dans messages.value
//   'empty' : fil vide ou fetch en erreur (l'appelant doit afficher freshWelcome)
//   'stale' : un switch d'histoire a eu lieu PENDANT le fetch — ne rien appliquer
//             (la nouvelle hydratation gèrera elle-même le résultat)
async function hydrateFromServer(project: string): Promise<'ok' | 'empty' | 'stale'> {
  const myGen = ++_hydrationGen
  try {
    const serverMsgs = await $fetch<ConversationMessageOut[]>(
      '/api/atelier/conversation',
      { query: { project } },
    )
    if (myGen !== _hydrationGen) return 'stale'
    if (!Array.isArray(serverMsgs) || serverMsgs.length === 0) return 'empty'
    _seq = 0
    const mapped = serverMsgs.map(mapServerMsg).filter((m): m is AtelierMsg => m !== null)
    if (mapped.length === 0) return 'empty'
    messages.value = mapped
    deriveCounters()
    return 'ok'
  }
  catch (err) {
    if (myGen !== _hydrationGen) return 'stale'
    console.error('[useAtelier] hydrateFromServer — échec du fetch :', err)
    return 'empty'
  }
}

// Charge la liste des modes (une fois) — nécessaire à welcomeFor AVANT le
// premier freshWelcome, sinon le tout premier accueil affiche le repli neutre
// au lieu du texte du mode courant (course avec le fetch d'hydratation).
let profilesLoaded: Promise<void> | null = null
function ensureProfilesLoaded(): Promise<void> {
  if (!profilesLoaded) {
    profilesLoaded = useAtelierProfile().refreshProfiles()
  }
  return profilesLoaded
}

function ensureInit() {
  if (initialized) return
  initialized = true
  if (!import.meta.client) return

  // Hydratation asynchrone : fire-and-forget.
  // Le fil reste VIDE pendant le chargement (pas de flash welcome → remplacement).
  // Si le serveur retourne un fil vide OU si le fetch échoue, on affiche le welcome.
  // 'stale' : un switch d'histoire a pris le relais avant la fin — on ne fait rien.
  void Promise.all([ensureProfilesLoaded(), hydrateFromServer(currentProject.value)]).then(
    ([, result]) => {
      if (result === 'empty') freshWelcome()
    },
  )

  // Scope DÉTACHÉ (effectScope(true)) : le watch survit au démontage de la 1ʳᵉ page.
  effectScope(true).run(() => {
    // Changement d'histoire : fil vide pendant le chargement, puis hydratation
    // depuis le serveur (fil du nouveau projet, ou welcome si vide).
    // Plus de flush/lecture localStorage — le serveur est la source de vérité.
    watch(currentProject, async (nv) => {
      messages.value = []
      const result = await hydrateFromServer(nv)
      if (result === 'empty') freshWelcome()
      // 'stale' : encore un switch entre-temps — la nouvelle instance gère
    })
  })
}

// Repartir d'une conversation vierge.
// Archive côté serveur (≠ suppression : les nœuds :Message restent en base pour
// le futur repêchage — brique 3), puis welcome local. En cas d'échec réseau,
// on conserve le fil courant (l'erreur est loggée, pas affichée dans l'UI).
async function newConversation() {
  try {
    await $fetch('/api/atelier/conversation/clear', {
      method: 'POST',
      query: { project: currentProject.value },
    })
    freshWelcome()
  }
  catch (err) {
    console.error('[useAtelier] newConversation — échec de l\'archivage serveur :', err)
  }
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
          // message_history supprimé (#63, brique 2) : le serveur tient le fil
          // LLM dans :Thread (nœud Neo4j). Le front n'a plus à gérer l'historique.
          // Les evals/e2e qui fournissent message_history dans le body continuent
          // à fonctionner côté backend sans aucune modification.
          project: currentProject.value,
          // Mode courant (Étape 3, plans/maintenance_profile.md) — sélecteur de
          // la topbar, persisté par useAtelierProfile. Défaut backend = scenario.
          profile: currentProfile.value,
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
            // Le serveur émet toujours `history` pour la compat e2e/evals (qui
            // fournissent message_history côté back) — le front n'en a plus besoin
            // depuis #63 (fil threadé géré côté serveur en :Thread).
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
    }
  }

  // Poste un message côté client sans passer par le tour de chat (SSE) — sert
  // à afficher le résultat d'un import de fiche (Étape 3) : carte de résumé en
  // succès, texte d'erreur sinon. Même helper `append` que le stream, donc
  // même id de rendu (pas une deuxième fonction qui ferait la même chose).
  const pushSystemMessage = append

  return { messages, typing, phase, sendMessage, silentSession, newConversation, pushSystemMessage }
}
