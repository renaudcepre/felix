<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { TimelineEvent } from '~/types'

const eraFilter = ref<string | null>(null)
const { events, status } = useTimeline(eraFilter)

const eraOptions = [
  { label: 'Toutes les epoques', value: null },
  { label: '1940s', value: '1940s' },
  { label: '1970s', value: '1970s' },
]

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
        <template #characters-cell="{ row }">
          <span class="text-sm text-muted">{{ row.original.characters || '—' }}</span>
        </template>
      </UTable>
    </UCard>
  </div>
</template>
