<script setup lang="ts">
// Panneau de propositions (Étape 8, plans/maintenance_profile.md ; réécrit le
// 2026-09-24 après un retour utilisateur en direct : un cluster de LIE_A
// « est une évolution du slogan pour » ressortait en rel_type « UNE »
// (stoplist incomplet, cf. felix.core.schema_detector), affiché en jargon
// (« A —[verbe]→ B » → « A —[UNE]→ B ») avec des chips non expliqués. Refonte :
// une phrase d'abord, des exemples en clair, « Relie : » avec son sens dit,
// jamais de « avant/après » ni de crochets. Design papier, pas de nouvelle
// couleur. Lit GET /api/schema/proposals + /profile, valide (POST /apply) ou
// refuse (POST /reject) chaque proposition.
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

// Énumération FR « a, b et c » — pour la phrase de fusion (sources multiples,
// même si le détecteur n'en produit qu'une aujourd'hui, cf. schema_detector).
function joinFr(items: string[]): string {
  if (items.length <= 1) return items[0] ?? ''
  return `${items.slice(0, -1).join(', ')} et ${items[items.length - 1]}`
}

// La phrase d'accroche — ce que l'humain lit EN PREMIER, pas un badge de
// jargon graphe. Une phrase par nature de proposition (promote_verbs /
// merge_types), cf. plan Étape 8bis.
function proposalSentence(p: Proposal): string {
  if (p.change.kind === 'promote_verbs') {
    const [main, ...others] = p.phrases.length ? p.phrases : [p.change.rel_type.toLowerCase()]
    const also = others.length
      ? ` (aussi formulé ${others.map(o => `« ${o} »`).join(', ')})`
      : ''
    return `Le lien « ${main} »${also} apparaît ${p.occurrences} fois. En faire un type de lien officiel ?`
  }
  const target = p.change.target
  return `Les types « ${joinFr(p.change.sources)} » et « ${target} » semblent identiques. `
    + `Les fusionner sous « ${target} » ?`
}

function fieldLabel(change: SchemaChange): string {
  return change.kind === 'promote_verbs' ? 'Nom du type' : 'Type cible'
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
      <p class="schema-panel-intro">
        Felix repère les liens qui reviennent souvent et vous propose d'en faire des types
        officiels. Valider les applique aussi aux fiches déjà créées.
      </p>

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
        <p v-else class="schema-empty">Felix n'a pas encore appris de type de lien officiel.</p>
      </section>

      <section class="schema-section">
        <h3 class="schema-section-title">Propositions</h3>
        <p v-if="loading" class="schema-empty">Chargement…</p>
        <p v-else-if="!proposals.length" class="schema-empty">Aucune proposition en attente.</p>
        <div v-else class="schema-proposal-list">
          <div v-for="(p, i) in proposals" :key="i" class="schema-proposal">
            <p class="schema-proposal-sentence">{{ proposalSentence(p) }}</p>

            <template v-if="p.change.kind === 'promote_verbs'">
              <div v-if="p.examples.length" class="schema-examples">
                <p class="schema-examples-title">Exemples :</p>
                <p v-for="(ex, ei) in p.examples" :key="ei" class="schema-example-line">
                  {{ ex.from }} → {{ ex.to }}
                </p>
              </div>
              <p v-if="p.pairs_readable" class="schema-relie">
                Relie : {{ p.pairs_readable }}
                <span class="schema-relie-hint">(types des fiches reliées)</span>
              </p>
            </template>
            <template v-else>
              <p v-if="p.report.entities_retyped" class="schema-relie">
                Concerne {{ p.report.entities_retyped }}
                fiche{{ p.report.entities_retyped > 1 ? 's' : '' }}.
              </p>
            </template>

            <div class="schema-edit-row">
              <label>{{ fieldLabel(p.change) }}</label>
              <input
                class="schema-edit-input"
                :value="draftFor(i, p.change)"
                :disabled="busyIdx[i]"
                @input="setDraft(i, ($event.target as HTMLInputElement).value)"
              >
              <p v-if="p.change.kind === 'promote_verbs'" class="schema-edit-hint">
                Ce nom sera utilisé pour tous les liens de ce genre, passés et futurs.
              </p>
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
