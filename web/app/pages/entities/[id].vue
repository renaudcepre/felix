<script setup lang="ts">
import type { EntityEvent, EntityRelation } from '~/types/entities'

definePageMeta({ layout: false })

const route = useRoute()
const id = route.params.id as string

const { entity, status, refresh } = useEntity(id)

// Histoire courante (#60) — affichée dans la barre, le switch vit sur /chat.
const { currentProjectName, refreshProjects } = useProject()
onMounted(() => { void refreshProjects() })

useHead({ title: () => `Felix — ${entity.value?.name ?? 'Entité'}` })

// props est un dict libre → on l'affiche tel quel, ordonné par clé.
const propEntries = computed(() =>
  Object.entries(entity.value?.props ?? {}).sort(([a], [b]) => a.localeCompare(b)),
)

const initial = computed(() => (entity.value?.name?.[0] ?? '?').toUpperCase())

// ───── Édition manuelle (#61) : si Felix se trompe, l'auteur corrige ICI.
// Chaque action laisse un tombstone côté backend — le LLM ne recrée pas.
const { deleteEntity, patchEntity, deleteRelation } = useEntityEdits()

const busy = ref(false)
const actionError = ref('')
// Une seule confirmation « armée » à la fois (clé : 'entity' | prop:k | rel:i | ev:id).
const confirming = ref<string | null>(null)

function arm(key: string): boolean {
  if (confirming.value === key) return true
  confirming.value = key
  setTimeout(() => {
    if (confirming.value === key) confirming.value = null
  }, 4000)
  return false
}

async function act(fn: () => Promise<void>) {
  busy.value = true
  actionError.value = ''
  try {
    await fn()
  }
  catch {
    actionError.value = 'L\'action a échoué — réessaie.'
  }
  finally {
    busy.value = false
    confirming.value = null
  }
}

// Renommage du titre — même effet que rename_entity : id migré, fusion sur collision.
const editingName = ref(false)
const nameDraft = ref('')

function startRename() {
  nameDraft.value = entity.value?.name ?? ''
  editingName.value = true
}

async function submitRename() {
  const name = nameDraft.value.trim()
  if (!name || name === entity.value?.name) {
    editingName.value = false
    return
  }
  await act(async () => {
    const res = await patchEntity(id, { name })
    editingName.value = false
    if (res.id !== id) await navigateTo(`/entities/${res.id}`, { replace: true })
    else await refresh()
  })
}

async function removeEntity() {
  if (!arm('entity')) return
  await act(async () => {
    await deleteEntity(id)
    await navigateTo('/entities')
  })
}

// Propriétés : corriger une valeur fausse, ou retirer la clé.
const editingProp = ref<string | null>(null)
const propDraft = ref('')

function startEditProp(key: string, value: unknown) {
  editingProp.value = key
  propDraft.value = String(value ?? '')
}

async function submitProp(key: string) {
  const value = propDraft.value.trim()
  await act(async () => {
    await patchEntity(id, { props: { [key]: value } })
    editingProp.value = null
    await refresh()
  })
}

async function removeProp(key: string) {
  if (!arm(`prop:${key}`)) return
  await act(async () => {
    await patchEntity(id, { remove_props: [key] })
    await refresh()
  })
}

// Relations : la clé orientée se reconstruit depuis la direction affichée.
// verbe_slug complète la clé d'une arête narrative (LIE_A) — la même paire
// peut porter plusieurs arêtes, une par verbe (#68).
async function removeRel(rel: EntityRelation, i: number) {
  if (!arm(`rel:${i}`)) return
  const [from_id, to_id] = rel.direction === 'out'
    ? [id, rel.other.id]
    : [rel.other.id, id]
  await act(async () => {
    await deleteRelation({ from_id, to_id, rel_type: rel.rel_type, verbe_slug: rel.verbe_slug })
    await refresh()
  })
}

// Chronologie : un événement supprimé recoud la chaîne NEXT côté backend.
async function removeEvent(ev: EntityEvent) {
  if (!arm(`ev:${ev.id}`)) return
  await act(async () => {
    await deleteEntity(ev.id)
    await refresh()
  })
}
</script>

<template>
  <div class="felix-fiche">
    <header class="fbar">
      <div class="fbar-left">
        <NuxtLink class="back-link" to="/entities">
          <AtelierIcon name="back" :size="17" />Retour aux entités
        </NuxtLink>
      </div>
      <div class="fbar-brand">
        <span class="felix-mark"><AtelierIcon name="felix" :size="15" /></span>
        <span class="fbar-project">{{ currentProjectName }}</span>
      </div>
    </header>

    <main class="fwrap">
      <div v-if="status === 'pending'" class="empty">Chargement…</div>

      <template v-else-if="entity">
        <!-- En-tête -->
        <div class="ent-head">
          <span class="mono-avatar" :style="{ width: '56px', height: '56px', fontSize: '24px' }">
            {{ initial }}
          </span>
          <div class="ent-head-main">
            <template v-if="editingName">
              <div class="name-edit-row">
                <input
                  v-model="nameDraft"
                  class="name-edit-input"
                  :disabled="busy"
                  @keydown.enter="submitRename"
                  @keydown.esc="editingName = false"
                >
                <button class="row-act" title="Valider" :disabled="busy" @click="submitRename">
                  <AtelierIcon name="check" :size="15" />
                </button>
                <button class="row-act" title="Annuler" :disabled="busy" @click="editingName = false">
                  <AtelierIcon name="close" :size="14" />
                </button>
              </div>
            </template>
            <h1 v-else class="ent-name">
              {{ entity.name }}
              <button class="row-act" title="Corriger le nom" :disabled="busy" @click="startRename">
                <AtelierIcon name="pencil" :size="15" />
              </button>
            </h1>
            <div class="ent-tags">
              <span v-if="entity.entity_type" class="badge cap">{{ entity.entity_type }}</span>
              <span class="ent-ref">#{{ entity.id }}</span>
            </div>
          </div>
          <button
            class="row-act danger ent-delete"
            :class="{ confirming: confirming === 'entity' }"
            :disabled="busy"
            @click="removeEntity"
          >
            <template v-if="confirming === 'entity'">Confirmer la suppression ?</template>
            <template v-else><AtelierIcon name="trash" :size="14" /> Supprimer la fiche</template>
          </button>
        </div>

        <p v-if="actionError" class="action-error">{{ actionError }}</p>

        <!-- Propriétés -->
        <section class="card">
          <h2 class="card-title">Propriétés</h2>
          <div v-if="propEntries.length" class="prop-grid">
            <div v-for="[key, value] in propEntries" :key="key" class="prop-row">
              <div class="prop-key">{{ key }}</div>
              <div class="prop-val">
                <template v-if="editingProp === key">
                  <input
                    v-model="propDraft"
                    class="prop-edit-input"
                    :disabled="busy"
                    @keydown.enter="submitProp(key)"
                    @keydown.esc="editingProp = null"
                  >
                </template>
                <template v-else>{{ value }}</template>
              </div>
              <div class="prop-actions">
                <template v-if="editingProp === key">
                  <button class="row-act" title="Valider" :disabled="busy" @click="submitProp(key)">
                    <AtelierIcon name="check" :size="14" />
                  </button>
                  <button class="row-act" title="Annuler" :disabled="busy" @click="editingProp = null">
                    <AtelierIcon name="close" :size="13" />
                  </button>
                </template>
                <template v-else>
                  <button class="row-act" title="Corriger" :disabled="busy" @click="startEditProp(key, value)">
                    <AtelierIcon name="pencil" :size="13" />
                  </button>
                  <button
                    class="row-act danger"
                    :class="{ confirming: confirming === `prop:${key}` }"
                    title="Supprimer cette propriété"
                    :disabled="busy"
                    @click="removeProp(key)"
                  >
                    <template v-if="confirming === `prop:${key}`">Confirmer ?</template>
                    <AtelierIcon v-else name="trash" :size="13" />
                  </button>
                </template>
              </div>
            </div>
          </div>
          <p v-else class="empty">Aucune propriété notée.</p>
        </section>

        <!-- Relations -->
        <section class="card">
          <h2 class="card-title">Relations</h2>
          <div v-if="entity.relations.length" class="rel-list">
            <div v-for="(rel, i) in entity.relations" :key="i" class="rel-row">
              <NuxtLink class="rel-left rel-link" :to="`/entities/${rel.other.id}`">
                <span class="mono-avatar neutral" :style="{ width: '30px', height: '30px', fontSize: '13px' }">
                  {{ (rel.other.name?.[0] ?? '?').toUpperCase() }}
                </span>
                <span class="rel-name">{{ rel.other.name }}</span>
                <span v-if="rel.other.entity_type" class="rel-meta">{{ rel.other.entity_type }}</span>
              </NuxtLink>
              <div class="rel-left">
                <!-- Arête narrative : les mots de l'auteur, pas le type (#68). -->
                <span class="badge badge-rel">{{ rel.verbe || rel.rel_type }}</span>
                <span class="rel-dir" :class="rel.direction === 'in' ? 'in' : ''">
                  <AtelierIcon name="arrow" :size="15" />
                </span>
                <button
                  class="row-act danger"
                  :class="{ confirming: confirming === `rel:${i}` }"
                  title="Supprimer cette relation"
                  :disabled="busy"
                  @click="removeRel(rel, i)"
                >
                  <template v-if="confirming === `rel:${i}`">Confirmer ?</template>
                  <AtelierIcon v-else name="trash" :size="13" />
                </button>
              </div>
            </div>
          </div>
          <p v-else class="empty">Aucune relation notée.</p>
        </section>

        <!-- Chronologie -->
        <section class="card">
          <h2 class="card-title">Chronologie</h2>
          <div v-if="entity.events.length" class="chrono-list">
            <div v-for="ev in entity.events" :key="ev.ordre" class="chrono-row">
              <span class="chrono-ord">#{{ ev.ordre }}</span>
              <span class="chrono-text">{{ ev.resume }}</span>
              <span class="chrono-spacer" />
              <button
                class="row-act danger"
                :class="{ confirming: confirming === `ev:${ev.id}` }"
                title="Supprimer cet événement"
                :disabled="busy"
                @click="removeEvent(ev)"
              >
                <template v-if="confirming === `ev:${ev.id}`">Confirmer ?</template>
                <AtelierIcon v-else name="trash" :size="13" />
              </button>
            </div>
          </div>
          <p v-else class="empty">Aucun événement.</p>
        </section>

        <p class="fiche-foot">
          Les fiches alimentent la mémoire de Felix. Corrige ou supprime ce qui est
          faux : il en tiendra compte, sans le recréer.
        </p>
      </template>

      <div v-else class="empty">
        Entité introuvable. <NuxtLink to="/entities">Retour aux entités</NuxtLink>
      </div>
    </main>
  </div>
</template>
