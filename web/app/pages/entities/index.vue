<script setup lang="ts">
useHead({ title: 'Felix — Entités' })

const route = useRoute()
const router = useRouter()

// Un seul fetch (toutes sauf événements) : il alimente à la fois les onglets
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
  <div class="p-6 space-y-6 max-w-7xl mx-auto">
    <div>
      <h1 class="text-2xl font-bold">
        Entités
      </h1>
      <p class="text-muted text-sm mt-1">
        Ce que le copilote a modélisé
      </p>
    </div>

    <!-- Onglets de types -->
    <div class="flex flex-wrap gap-2">
      <UButton
        size="sm"
        :variant="selectedType === undefined ? 'solid' : 'outline'"
        :color="selectedType === undefined ? 'primary' : 'neutral'"
        @click="selectType(undefined)"
      >
        Tous
      </UButton>
      <UButton
        v-for="t in types"
        :key="t"
        size="sm"
        :variant="selectedType === t ? 'solid' : 'outline'"
        :color="selectedType === t ? 'primary' : 'neutral'"
        class="capitalize"
        @click="selectType(t)"
      >
        {{ t }}
      </UButton>
    </div>

    <!-- Grille -->
    <div v-if="status === 'pending'" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <USkeleton v-for="i in 8" :key="i" class="h-24" />
    </div>
    <div v-else-if="filtered.length" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <EntityCard v-for="e in filtered" :key="e.id" :entity="e" />
    </div>
    <p v-else class="text-muted text-sm">
      Aucune entité{{ selectedType ? ` de type « ${selectedType} »` : '' }}.
      Discute avec le copilote dans <NuxtLink to="/chat" class="text-felix-400 underline">le Chat</NuxtLink> pour en créer.
    </p>
  </div>
</template>
