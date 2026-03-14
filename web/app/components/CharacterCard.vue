<script setup lang="ts">
import type { CharacterSummary } from '~/types'

defineProps<{
  character: CharacterSummary
}>()
</script>

<template>
  <NuxtLink :to="`/characters/${character.id}`">
    <UCard
      class="tape-effect hover:shadow-lg transition-shadow cursor-pointer"
      :ui="{ body: 'p-4' }"
    >
      <div class="flex items-center gap-3">
        <UAvatar
          :text="character.name[0]"
          size="lg"
          color="primary"
        />
        <div class="min-w-0">
          <p class="font-semibold truncate">
            {{ character.name }}
          </p>
          <UBadge
            :color="character.era.includes('1940') ? 'warning' : 'info'"
            variant="subtle"
            size="xs"
          >
            {{ character.era }}
          </UBadge>
        </div>
      </div>
    </UCard>
  </NuxtLink>
</template>
