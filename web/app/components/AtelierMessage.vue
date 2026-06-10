<script setup lang="ts">
import type { AtelierMsg, ChoiceOption, ResolveOption } from '~/types/atelier'
import { marked } from 'marked'

const props = defineProps<{ msg: AtelierMsg }>()
const emit = defineEmits<{
  pick: [msg: AtelierMsg, opt: ChoiceOption]
  free: [msg: AtelierMsg, text: string]
  resolve: [msg: AtelierMsg, res: ResolveOption]
  status: [msg: AtelierMsg, status: string]
  // #61 : action manuelle réussie sur la cible d'une carte — le parent patche
  // le message (pattern immutable, comme `status`).
  edited: [msg: AtelierMsg, changes: Partial<AtelierMsg>]
}>()

const freeText = ref('')

// ───── Actions ✎/🗑 des cartes tool (#61) : si Felix se trompe, l'auteur corrige ici.
const { deleteEntity, patchEntity, deleteRelation } = useEntityEdits()
const editing = ref(false)
const editText = ref('')
const confirmDelete = ref(false)
const busy = ref(false)
const actionError = ref('')

// Sans cible (cartes d'avant #61, fusion déjà résorbée…), pas d'action.
const canDelete = computed(() =>
  !props.msg.edited && (!!props.msg.entityId || !!props.msg.relation))
// Renommer un ÉVÉNEMENT n'a pas de sens (son nom EST l'action) — suppression seule.
const canRename = computed(() =>
  !props.msg.edited && !!props.msg.entityId && props.msg.title !== 'Événement')
const ficheLink = computed(() =>
  props.msg.entityId && props.msg.title !== 'Événement'
    ? `/entities/${props.msg.entityId}`
    : '/entities')

function startEdit() {
  editing.value = true
  editText.value = props.msg.subject ?? ''
}

async function submitEdit() {
  const name = editText.value.trim()
  if (!name || !props.msg.entityId || name === props.msg.subject) {
    editing.value = false
    return
  }
  busy.value = true
  actionError.value = ''
  try {
    // Même effet que le tool rename_entity : id migré, fusion sur collision —
    // on suit l'id final pour que les actions suivantes visent la bonne fiche.
    const res = await patchEntity(props.msg.entityId, { name })
    emit('edited', props.msg, { subject: name, entityId: res.id, edited: 'renamed' })
    editing.value = false
  }
  catch {
    actionError.value = 'La correction a échoué — réessaie.'
  }
  finally {
    busy.value = false
  }
}

async function removeTarget() {
  if (!confirmDelete.value) {
    confirmDelete.value = true
    setTimeout(() => (confirmDelete.value = false), 4000)
    return
  }
  busy.value = true
  actionError.value = ''
  try {
    if (props.msg.relation) await deleteRelation(props.msg.relation)
    else if (props.msg.entityId) await deleteEntity(props.msg.entityId)
    emit('edited', props.msg, { edited: 'deleted' })
  }
  catch {
    actionError.value = 'La suppression a échoué — réessaie.'
  }
  finally {
    busy.value = false
    confirmDelete.value = false
  }
}

// Felix répond en markdown (**gras**, listes, *italique* pour les titres).
// On le rend tel quel — gfm + breaks pour respecter les retours à la ligne.
marked.setOptions({ breaks: true, gfm: true })
const html = computed(() => marked.parse(props.msg.body ?? '') as string)

function submitFree() {
  const t = freeText.value.trim()
  if (!t) return
  emit('free', props.msg, t)
  freeText.value = ''
}
</script>

<template>
  <!-- Message utilisateur -->
  <div v-if="msg.role === 'user'" class="msg msg-user">
    <div class="bubble">{{ msg.body }}</div>
  </div>

  <!-- Message Felix -->
  <div v-else class="msg msg-felix">
    <div class="msg-av">
      <span class="mono-avatar">F</span>
    </div>
    <div class="msg-main">
      <!-- text (markdown rendu via marked) -->
      <div v-if="msg.kind === 'text'" class="felix-text" v-html="html" />

      <!-- tool use -->
      <div v-else-if="msg.kind === 'tool'" class="tool-card" :class="{ 'is-removed': msg.edited === 'deleted' }">
        <div class="tool-head">
          <span class="tool-ic"><AtelierIcon :name="msg.tool === 'people' ? 'people' : 'fiche'" :size="15" /></span>
          <span class="tool-label">{{ msg.title }}</span>
          <span class="tool-spacer" />
          <span v-if="msg.edited === 'deleted'" class="tool-edited-tag">supprimé par toi</span>
          <template v-else>
            <button v-if="canRename" class="tool-act" title="Corriger le nom" :disabled="busy" @click="startEdit">
              <AtelierIcon name="pencil" :size="13" />
            </button>
            <button
              v-if="canDelete"
              class="tool-act danger"
              :class="{ confirming: confirmDelete }"
              :title="msg.relation ? 'Supprimer cette relation' : 'Supprimer de la bible'"
              :disabled="busy"
              @click="removeTarget"
            >
              <template v-if="confirmDelete">Confirmer ?</template>
              <AtelierIcon v-else name="trash" :size="13" />
            </button>
            <NuxtLink class="tool-link" :to="ficheLink">Voir la fiche <AtelierIcon name="arrow" :size="13" /></NuxtLink>
          </template>
        </div>
        <div class="tool-body">
          <div class="tool-meta">
            <template v-if="editing">
              <input
                v-model="editText"
                class="tool-edit-input"
                :disabled="busy"
                @keydown.enter="submitEdit"
                @keydown.esc="editing = false"
              >
              <button class="tool-act" title="Valider" :disabled="busy" @click="submitEdit">
                <AtelierIcon name="check" :size="14" />
              </button>
              <button class="tool-act" title="Annuler" :disabled="busy" @click="editing = false">
                <AtelierIcon name="close" :size="13" />
              </button>
            </template>
            <template v-else>
              <span class="tool-subj">{{ msg.subject }}</span>
              <span class="tool-fdot" />
              <span class="tool-field">{{ msg.field }}</span>
              <span v-if="msg.edited === 'renamed'" class="tool-edited-tag">corrigé par toi</span>
            </template>
          </div>
          <div class="tool-added">
            <span class="tool-plus">+ ajouté</span>
            <span class="tool-text">{{ msg.added }}</span>
          </div>
          <p v-if="actionError" class="tool-error">{{ actionError }}</p>
        </div>
      </div>

      <!-- choix multiple + champ libre -->
      <div v-else-if="msg.kind === 'choice'" class="choice-card" :class="{ 'is-done': msg.answered }">
        <div class="choice-q">{{ msg.question }}</div>
        <div class="choice-opts">
          <button
            v-for="opt in msg.options"
            :key="opt.k"
            class="choice-opt"
            :class="{ chosen: msg.answered && msg.chosen === opt.k, dim: msg.answered && msg.chosen !== opt.k }"
            :disabled="msg.answered"
            @click="emit('pick', msg, opt)"
          >
            <span class="opt-k">
              <AtelierIcon v-if="msg.answered && msg.chosen === opt.k" name="check" :size="14" />
              <template v-else>{{ opt.k }}</template>
            </span>
            <span class="opt-main">
              <span class="opt-label">{{ opt.label }}</span>
              <span class="opt-desc">{{ opt.desc }}</span>
            </span>
          </button>
        </div>
        <div v-if="!msg.answered" class="choice-free">
          <span class="free-or">ou précise</span>
          <div class="free-row">
            <input
              v-model="freeText"
              class="free-input"
              placeholder="Écris ta propre réponse…"
              @keydown.enter="submitFree"
            >
            <button class="free-send" :disabled="!freeText.trim()" @click="submitFree">
              <AtelierIcon name="send" :size="16" />
            </button>
          </div>
        </div>
      </div>

      <!-- citation d'extrait -->
      <div v-else-if="msg.kind === 'cite'" class="cite-card">
        <span class="cite-mark"><AtelierIcon name="quote" :size="20" /></span>
        <blockquote class="cite-quote">{{ msg.quote }}</blockquote>
        <div class="cite-source">{{ msg.source }}</div>
        <p v-if="msg.note" class="cite-note">{{ msg.note }}</p>
      </div>

      <!-- alerte d'incohérence -->
      <template v-else-if="msg.kind === 'alert'">
        <div v-if="msg.status === 'dismissed'" class="alert-dismissed">
          <AtelierIcon name="dot" :size="14" /> Incohérence ignorée.
          <button class="redo" @click="emit('status', msg, 'open')">Revoir</button>
        </div>

        <div v-else-if="msg.status === 'resolved'" class="alert-card resolved">
          <div class="alert-head">
            <span class="alert-ic ok"><AtelierIcon name="check" :size="15" /></span>
            <span class="alert-title">Incohérence résolue</span>
          </div>
          <p class="alert-body">{{ msg.resolution }}</p>
        </div>

        <div v-else class="alert-card">
          <div class="alert-head">
            <span class="alert-ic"><AtelierIcon name="alert" :size="15" /></span>
            <span class="alert-title">{{ msg.title }}</span>
          </div>
          <p class="alert-body">{{ msg.body }}</p>
          <div v-if="msg.status === 'resolving'" class="alert-resolves">
            <button v-for="r in msg.resolves" :key="r.id" class="resolve-opt" @click="emit('resolve', msg, r)">
              <span class="ro-label">{{ r.label }}</span>
              <span class="ro-desc">{{ r.desc }}</span>
            </button>
          </div>
          <div v-else class="alert-actions">
            <button class="btn btn-outline alert-btn" @click="emit('status', msg, 'resolving')">
              <AtelierIcon name="verify" :size="15" /> Résoudre
            </button>
            <button class="btn btn-ghost" @click="emit('status', msg, 'dismissed')">Ignorer</button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
