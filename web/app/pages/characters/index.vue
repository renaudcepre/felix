<script setup lang="ts">
const { characters, status } = useCharacters()

const eraFilter = ref<string | null>(null)

const eras = computed(() => {
  if (!characters.value) return []
  const unique = [...new Set(characters.value.map(c => c.era))]
  return unique.sort()
})

const filtered = computed(() => {
  if (!characters.value) return []
  if (!eraFilter.value) return characters.value
  return characters.value.filter(c => c.era === eraFilter.value)
})

const eraOptions = computed(() => [
  { label: 'Toutes les epoques', value: null },
  ...eras.value.map(e => ({ label: e, value: e })),
])
</script>

<template>
  <div class="p-6 space-y-6 max-w-7xl mx-auto">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">
          Personnages
        </h1>
        <p class="text-sm text-muted mt-1">
          {{ filtered.length }} personnage{{ filtered.length > 1 ? 's' : '' }}
        </p>
      </div>
      <USelect
        v-if="eras.length"
        v-model="eraFilter"
        :items="eraOptions"
        value-key="value"
        class="w-48"
        placeholder="Filtrer par epoque"
      />
    </div>

    <div v-if="status === 'pending'" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <USkeleton v-for="i in 8" :key="i" class="h-20" />
    </div>
    <div v-else-if="filtered.length" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <CharacterCard v-for="c in filtered" :key="c.id" :character="c" />
    </div>
    <p v-else class="text-muted text-sm">
      Aucun personnage
    </p>
  </div>
</template>
