<script setup lang="ts">
import type { LocationSummary } from '~/types'

defineProps<{
  location: LocationSummary
}>()
</script>

<template>
  <NuxtLink :to="`/locations/${location.id}`">
    <UCard
      class="tape-effect hover:shadow-lg transition-shadow cursor-pointer"
      :ui="{ body: 'p-4' }"
    >
      <div class="flex items-center gap-3">
        <UAvatar
          icon="i-lucide-map-pin"
          size="lg"
          color="primary"
        />
        <div class="min-w-0">
          <p class="font-semibold truncate">
            {{ location.name }}
          </p>
          <UBadge
            v-if="location.era"
            :color="location.era.includes('1940') ? 'warning' : 'info'"
            variant="subtle"
            size="xs"
          >
            {{ location.era }}
          </UBadge>
        </div>
      </div>
    </UCard>
  </NuxtLink>
</template>
