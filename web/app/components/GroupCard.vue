<script setup lang="ts">
import type { GroupSummary } from '~/types'

defineProps<{
  group: GroupSummary
}>()
</script>

<template>
  <NuxtLink :to="`/groups/${group.id}`">
    <UCard
      class="tape-effect hover:shadow-lg transition-shadow cursor-pointer"
      :ui="{ body: 'p-4' }"
    >
      <div class="flex items-center gap-3">
        <UAvatar
          icon="i-lucide-users"
          size="lg"
          color="neutral"
        />
        <div class="min-w-0">
          <p class="font-semibold truncate">
            {{ group.name }}
          </p>
        </div>
      </div>
    </UCard>
  </NuxtLink>
</template>
