<script setup lang="ts">
definePageMeta({ layout: false })
useHead({ title: 'Felix — Entités · Rivière basse' })

const route = useRoute()
const router = useRouter()

// Un seul fetch (toutes sauf événements) : il alimente à la fois les filtres
// (types réellement présents) et la grille. Le filtre est client-side → pas de
// re-fetch en changeant d'onglet, et le deep-link ?type=… reste honoré.
const { entities, status } = useEntities(ref<string | undefined>(undefined))

const selectedType = computed(() => (route.query.type as string | undefined) || undefined)

const types = computed(() => {
  const set = new Set<string>()
  for (const e of entities.value ?? []) {
    if (e.entity_type) set.add(e.entity_type)
  }
  return [...set].sort()
})

const filtered = computed(() => {
  const t = selectedType.value
  const list = entities.value ?? []
  return t ? list.filter(e => e.entity_type === t) : list
})

function selectType(type: string | undefined) {
  void router.replace({ query: type ? { type } : {} })
}
</script>

<template>
  <div class="felix-fiche">
    <header class="fbar">
      <div class="fbar-left">
        <NuxtLink class="back-link" to="/chat">
          <AtelierIcon name="back" :size="17" />Retour au chat
        </NuxtLink>
      </div>
      <div class="fbar-brand">
        <span class="felix-mark"><AtelierIcon name="felix" :size="15" /></span>
        <span class="fbar-project">Rivière basse</span>
      </div>
    </header>

    <main class="fwrap">
      <div class="list-head">
        <h1 class="list-title">Entités</h1>
        <p class="list-sub">Ce que Felix a noté dans la bible.</p>
      </div>

      <!-- Filtres par type -->
      <div class="filter-row">
        <button class="chip" :class="{ active: selectedType === undefined }" @click="selectType(undefined)">
          Toutes
        </button>
        <button
          v-for="t in types"
          :key="t"
          class="chip cap"
          :class="{ active: selectedType === t }"
          @click="selectType(t)"
        >
          {{ t }}
        </button>
      </div>

      <!-- Grille -->
      <div v-if="status === 'pending'" class="empty">Chargement…</div>
      <div v-else-if="filtered.length" class="ent-grid">
        <EntityCard v-for="e in filtered" :key="e.id" :entity="e" />
      </div>
      <p v-else class="empty">
        Aucune entité{{ selectedType ? ` de type « ${selectedType} »` : '' }}.
        Raconte ton histoire dans <NuxtLink to="/chat">le chat</NuxtLink> pour en créer.
      </p>
    </main>
  </div>
</template>
