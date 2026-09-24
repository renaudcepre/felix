<script setup lang="ts">
// Panneau de propositions (Étape 8, plans/maintenance_profile.md) — la file de
// validation humaine du schéma émergent, directement dans la page : lit
// GET /api/schema/proposals + /profile, valide (POST /apply) ou refuse
// (POST /reject) chaque proposition. Design papier, pas de jargon graphe
// (« Types de liens appris », « Propositions » — pas « schéma », pas « edges »).
import type { Proposal, SchemaChange } from '~/types/schema'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const { proposals, profileView, loading, refreshProposals, refreshProfileView, applyChange, rejectChange }
  = useSchemaProposals()

// Brouillon éditable par proposition (index dans `proposals`) : le nom cible
// (rel_type ou target) avant validation — l'auteur peut le corriger.
const drafts = ref<Record<number, string>>({})
const busyIdx = ref<Record<number, boolean>>({})
const errors = ref<Record<number, string>>({})

const UPPER_SNAKE = /^[A-Z][A-Z0-9_]*$/

function targetName(change: SchemaChange): string {
  return change.kind === 'promote_verbs' ? change.rel_type : change.target
}

function draftFor(i: number, change: SchemaChange): string {
  return drafts.value[i] ?? targetName(change)
}

function setDraft(i: number, value: string) {
  drafts.value[i] = value
}

function kindLabel(change: SchemaChange): string {
  return change.kind === 'promote_verbs' ? 'Nouveau type de lien' : 'Fusion de types'
}

function fieldLabel(change: SchemaChange): string {
  return change.kind === 'promote_verbs' ? 'Nom du type (MAJUSCULES_SOULIGNÉES)' : 'Type cible'
}

function validate(change: SchemaChange, value: string): string {
  const v = value.trim()
  if (!v) return 'Nom requis.'
  if (change.kind === 'promote_verbs' && !UPPER_SNAKE.test(v)) {
    return 'Format attendu : MAJUSCULES_SOULIGNÉES (ex. CONTROLS).'
  }
  return ''
}

function changeWithDraft(change: SchemaChange, value: string): SchemaChange {
  const v = value.trim()
  return change.kind === 'promote_verbs' ? { ...change, rel_type: v } : { ...change, target: v }
}

async function accept(i: number, proposal: Proposal) {
  const value = draftFor(i, proposal.change)
  const err = validate(proposal.change, value)
  if (err) {
    errors.value[i] = err
    return
  }
  errors.value[i] = ''
  busyIdx.value[i] = true
  try {
    await applyChange(changeWithDraft(proposal.change, value))
  }
  catch {
    errors.value[i] = 'La validation a échoué — réessaie.'
  }
  finally {
    busyIdx.value[i] = false
  }
}

async function refuse(i: number, proposal: Proposal) {
  errors.value[i] = ''
  busyIdx.value[i] = true
  try {
    await rejectChange(proposal.change)
  }
  catch {
    errors.value[i] = 'Le refus a échoué — réessaie.'
  }
  finally {
    busyIdx.value[i] = false
  }
}

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    void refreshProposals()
    void refreshProfileView()
  }
})

// Exposé pour que le parent (chat.vue) rafraîchisse la liste après un import de
// fiche, même si le panneau est fermé — même instance singleton, donc un appel
// direct à useSchemaProposals().refreshProposals() suffirait aussi ; exposé ici
// par cohérence pour un appel depuis un ref de composant.
defineExpose({ refreshProposals })
</script>

<template>
  <aside v-if="open" class="schema-panel">
    <div class="schema-panel-head">
      <span class="schema-panel-title">Propositions</span>
      <button class="row-act" title="Fermer" @click="emit('close')">
        <AtelierIcon name="close" :size="15" />
      </button>
    </div>

    <div class="schema-panel-body">
      <section class="schema-section">
        <h3 class="schema-section-title">
          Types de liens appris
          <span v-if="profileView" class="schema-version">v{{ profileView.version }}</span>
        </h3>
        <ul v-if="profileView?.relation_vocabulary.length" class="schema-vocab-list">
          <li v-for="spec in profileView.relation_vocabulary" :key="spec.name" class="schema-vocab-item">
            <span class="schema-badge">{{ spec.name }}</span>
            <span class="schema-vocab-gloss">{{ spec.gloss }}</span>
            <span class="schema-vocab-pairs">
              {{ spec.subjects.join(', ') || '—' }} → {{ spec.objects.join(', ') || '—' }}
            </span>
          </li>
        </ul>
        <p v-else class="schema-empty">Aucun type appris pour l'instant.</p>
      </section>

      <section class="schema-section">
        <h3 class="schema-section-title">Propositions</h3>
        <p v-if="loading" class="schema-empty">Chargement…</p>
        <p v-else-if="!proposals.length" class="schema-empty">Aucune proposition en attente.</p>
        <div v-else class="schema-proposal-list">
          <div v-for="(p, i) in proposals" :key="i" class="schema-proposal">
            <div class="schema-proposal-head">
              <span class="schema-badge">{{ kindLabel(p.change) }}</span>
            </div>
            <ul v-if="p.report.samples.length" class="schema-samples">
              <li v-for="(s, si) in p.report.samples" :key="si">{{ s }}</li>
            </ul>
            <p v-if="p.report.observed_pairs.length" class="schema-pairs">
              <span v-for="(pair, pi) in p.report.observed_pairs" :key="pi" class="schema-pair-chip">
                {{ pair[0] }} → {{ pair[1] }}
              </span>
            </p>
            <div class="schema-edit-row">
              <label>{{ fieldLabel(p.change) }}</label>
              <input
                class="schema-edit-input"
                :value="draftFor(i, p.change)"
                :disabled="busyIdx[i]"
                @input="setDraft(i, ($event.target as HTMLInputElement).value)"
              >
            </div>
            <p v-if="errors[i]" class="tool-error">{{ errors[i] }}</p>
            <div class="schema-actions">
              <button class="btn btn-outline" :disabled="busyIdx[i]" @click="accept(i, p)">Valider</button>
              <button class="btn btn-ghost" :disabled="busyIdx[i]" @click="refuse(i, p)">Refuser</button>
            </div>
          </div>
        </div>
      </section>
    </div>
  </aside>
</template>
