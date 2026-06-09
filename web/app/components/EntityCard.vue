<script setup lang="ts">
import type { EntitySummary } from '~/types/entities'

const props = defineProps<{
  entity: EntitySummary
}>()

// Aperçu : la première propriété libre, si elle existe. Aucune hypothèse sur
// la structure — l'entité peut n'avoir aucune prop.
const preview = computed(() => {
  const entries = Object.entries(props.entity.props ?? {})
  if (!entries.length) return null
  const [key, value] = entries[0]!
  return { key, value: String(value) }
})
</script>

<template>
  <NuxtLink :to="`/entities/${entity.id}`">
    <UCard
      class="tape-effect hover:shadow-lg transition-shadow cursor-pointer h-full"
      :ui="{ body: 'p-4' }"
    >
      <div class="flex items-start gap-3">
        <UAvatar
          :text="(entity.name?.[0] ?? '?').toUpperCase()"
          size="lg"
          color="primary"
        />
        <div class="min-w-0 flex-1">
          <p class="font-semibold truncate">
            {{ entity.name }}
          </p>
          <UBadge
            v-if="entity.entity_type"
            color="info"
            variant="subtle"
            size="xs"
            class="mt-0.5"
          >
            {{ entity.entity_type }}
          </UBadge>
          <p v-if="preview" class="text-xs text-muted mt-2 line-clamp-2">
            <span class="font-medium">{{ preview.key }}</span> · {{ preview.value }}
          </p>
        </div>
      </div>
    </UCard>
  </NuxtLink>
</template>
