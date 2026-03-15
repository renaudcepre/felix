<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { TimelineEvent } from '~/types'

const eraFilter = ref<string | null>(null)
const { events, status } = useTimeline(eraFilter)
const selectedEvent = ref<TimelineEvent | null>(null)
const modalOpen = computed({
  get: () => selectedEvent.value !== null,
  set: (v: boolean) => { if (!v) selectedEvent.value = null },
})

const eras = computed(() => {
  if (!events.value) return []
  const unique = [...new Set(events.value.map(e => e.era))]
  return unique.sort()
})

const eraOptions = computed(() => [
  { label: 'Toutes les epoques', value: null },
  ...eras.value.map(e => ({ label: e, value: e })),
])

const columns: TableColumn<TimelineEvent>[] = [
  { accessorKey: 'date', header: 'Date' },
  { accessorKey: 'era', header: 'Epoque' },
  { accessorKey: 'title', header: 'Evenement' },
  { accessorKey: 'location', header: 'Lieu' },
  { accessorKey: 'characters', header: 'Personnages' },
]
</script>

<template>
  <div class="p-6 space-y-6 max-w-7xl mx-auto">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">
          Timeline
        </h1>
        <p class="text-sm text-muted mt-1">
          {{ events?.length ?? 0 }} evenement{{ (events?.length ?? 0) > 1 ? 's' : '' }}
        </p>
      </div>
      <USelect
        v-model="eraFilter"
        :items="eraOptions"
        value-key="value"
        class="w-48"
        placeholder="Filtrer par epoque"
      />
    </div>

    <UCard>
      <UTable
        :data="events ?? []"
        :columns="columns"
        :loading="status === 'pending'"
        @select="(_e: Event, row: any) => selectedEvent = row.original"
      >
        <template #era-cell="{ row }">
          <UBadge
            :color="row.original.era.includes('1940') ? 'warning' : 'info'"
            variant="subtle"
            size="xs"
          >
            {{ row.original.era }}
          </UBadge>
        </template>
        <template #location-cell="{ row }">
          <NuxtLink
            v-if="row.original.location_id"
            :to="`/locations/${row.original.location_id}`"
            class="text-primary hover:underline"
          >
            {{ row.original.location || '—' }}
          </NuxtLink>
          <span v-else class="text-sm text-muted">{{ row.original.location || '—' }}</span>
        </template>
        <template #characters-cell="{ row }">
          <div class="flex flex-wrap gap-1">
            <template v-if="row.original.characters_detail.length">
              <NuxtLink
                v-for="c in row.original.characters_detail"
                :key="c.id"
                :to="`/characters/${c.id}`"
                class="text-primary hover:underline text-sm"
              >
                {{ c.name }}
              </NuxtLink>
            </template>
            <span v-else class="text-sm text-muted">—</span>
          </div>
        </template>
      </UTable>
    </UCard>

    <UModal v-model:open="modalOpen" :close="{ onClick: () => selectedEvent = null }">
      <template v-if="selectedEvent" #content>
        <div class="p-6 space-y-4">
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold">
              {{ selectedEvent.title }}
            </h2>
            <UBadge
              :color="selectedEvent.era.includes('1940') ? 'warning' : 'info'"
              variant="subtle"
              size="xs"
            >
              {{ selectedEvent.era }}
            </UBadge>
          </div>

          <div class="flex gap-4 text-sm text-muted">
            <span>{{ selectedEvent.date }}</span>
            <NuxtLink
              v-if="selectedEvent.location_id"
              :to="`/locations/${selectedEvent.location_id}`"
              class="text-primary hover:underline"
            >
              {{ selectedEvent.location }}
            </NuxtLink>
            <span v-else-if="selectedEvent.location">{{ selectedEvent.location }}</span>
          </div>

          <p v-if="selectedEvent.description" class="whitespace-pre-wrap">
            {{ selectedEvent.description }}
          </p>
          <p v-else class="text-muted text-sm">
            Aucune description
          </p>

          <div v-if="selectedEvent.characters_detail.length">
            <p class="text-xs font-semibold text-muted uppercase tracking-wide mb-2">
              Personnages
            </p>
            <div class="flex flex-wrap gap-2">
              <NuxtLink
                v-for="c in selectedEvent.characters_detail"
                :key="c.id"
                :to="`/characters/${c.id}`"
                class="text-primary hover:underline text-sm"
              >
                {{ c.name }}
              </NuxtLink>
            </div>
          </div>
        </div>
      </template>
    </UModal>
  </div>
</template>

<style scoped>
:deep([data-slot="tr"]) {
  cursor: pointer;
}
</style>
