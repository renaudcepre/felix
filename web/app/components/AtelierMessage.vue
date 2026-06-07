<script setup lang="ts">
import type { AtelierMsg, ChoiceOption, ResolveOption } from '~/types/atelier'

const props = defineProps<{ msg: AtelierMsg }>()
const emit = defineEmits<{
  pick: [msg: AtelierMsg, opt: ChoiceOption]
  free: [msg: AtelierMsg, text: string]
  resolve: [msg: AtelierMsg, res: ResolveOption]
  status: [msg: AtelierMsg, status: string]
}>()

const freeText = ref('')

// Met *en valeur* le texte entre astérisques (titres d'œuvres).
const parts = computed(() => {
  const body = props.msg.body ?? ''
  return body
    .split(/(\*[^*]+\*)/g)
    .filter(Boolean)
    .map(p => (p.startsWith('*') && p.endsWith('*') ? { t: p.slice(1, -1), em: true } : { t: p, em: false }))
})

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
      <!-- text -->
      <p v-if="msg.kind === 'text'" class="felix-text">
        <template v-for="(p, i) in parts" :key="i">
          <em v-if="p.em" class="work">{{ p.t }}</em>
          <template v-else>{{ p.t }}</template>
        </template>
      </p>

      <!-- tool use -->
      <div v-else-if="msg.kind === 'tool'" class="tool-card">
        <div class="tool-head">
          <span class="tool-ic"><AtelierIcon :name="msg.tool === 'people' ? 'people' : 'fiche'" :size="15" /></span>
          <span class="tool-label">{{ msg.title }}</span>
          <span class="tool-spacer" />
          <NuxtLink class="tool-link" to="/characters">Voir la fiche <AtelierIcon name="arrow" :size="13" /></NuxtLink>
        </div>
        <div class="tool-body">
          <div class="tool-meta">
            <span class="tool-subj">{{ msg.subject }}</span>
            <span class="tool-fdot" />
            <span class="tool-field">{{ msg.field }}</span>
          </div>
          <div class="tool-added">
            <span class="tool-plus">+ ajouté</span>
            <span class="tool-text">{{ msg.added }}</span>
          </div>
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
