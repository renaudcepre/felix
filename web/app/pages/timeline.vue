<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { TimelineEvent } from '~/types'

const eraFilter = ref<string | null>(null)
const { events, status } = useTimeline(eraFilter)

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
  </div>
</template>
