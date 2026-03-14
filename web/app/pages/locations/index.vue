<script setup lang="ts">
const { locations, status } = useLocations()

const eraFilter = ref<string | null>(null)

const eras = computed(() => {
  if (!locations.value) return []
  const unique = [...new Set(locations.value.map(l => l.era).filter(Boolean))]
  return unique.sort()
})

const filtered = computed(() => {
  if (!locations.value) return []
  if (!eraFilter.value) return locations.value
  return locations.value.filter(l => l.era === eraFilter.value)
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
          Lieux
        </h1>
        <p class="text-sm text-muted mt-1">
          {{ filtered.length }} lieu{{ filtered.length > 1 ? 'x' : '' }}
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
      <LocationCard v-for="l in filtered" :key="l.id" :location="l" />
    </div>
    <p v-else class="text-muted text-sm">
      Aucun lieu
    </p>
  </div>
</template>
