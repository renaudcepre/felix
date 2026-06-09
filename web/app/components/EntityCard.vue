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

const initial = computed(() => (props.entity.name?.[0] ?? '?').toUpperCase())
</script>

<template>
  <NuxtLink class="ent-card" :to="`/entities/${entity.id}`">
    <span class="mono-avatar neutral" :style="{ width: '40px', height: '40px', fontSize: '17px' }">
      {{ initial }}
    </span>
    <div class="ent-card-body">
      <div class="ent-card-name">{{ entity.name }}</div>
      <span v-if="entity.entity_type" class="badge badge-rel cap">{{ entity.entity_type }}</span>
      <p v-if="preview" class="ent-card-preview">
        <b>{{ preview.key }}</b> · {{ preview.value }}
      </p>
    </div>
  </NuxtLink>
</template>
