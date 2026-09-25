<script setup lang="ts">
import type { EntitySummary } from '~/types/entities'

const props = defineProps<{
  entity: EntitySummary
}>()

const initial = computed(() => (props.entity.name?.[0] ?? '?').toUpperCase())

// « N propriétés · M liens » — toujours au pluriel/singulier correct, quel
// que soit le schéma de l'entité (#73, remplace l'ancien aperçu de la
// première prop libre, arbitraire selon l'ordre de retour de Neo4j).
const meta = computed(() => {
  const p = props.entity.prop_count
  const r = props.entity.relation_count
  return `${p} propriété${p > 1 ? 's' : ''} · ${r} lien${r > 1 ? 's' : ''}`
})

// « p. 1 » ou « p. 1-2 » (première et dernière page — pas un détail de chaque
// page touchée, la carte reste un aperçu).
const sourceLabel = computed(() => {
  const source = props.entity.source
  if (!source) return null
  const pages = source.pages
  if (!pages.length) return source.title
  const range = pages.length === 1 || pages[0] === pages[pages.length - 1]
    ? `${pages[0]}`
    : `${pages[0]}-${pages[pages.length - 1]}`
  return `${source.title}, p. ${range}`
})
</script>

<template>
  <NuxtLink class="ent-card" :to="`/entities/${entity.id}`">
    <span class="mono-avatar neutral" :style="{ width: '40px', height: '40px', fontSize: '17px' }">
      {{ initial }}
    </span>
    <div class="ent-card-body">
      <div class="ent-card-name">{{ entity.name }}</div>
      <span v-if="entity.entity_type" class="badge badge-rel cap">{{ entity.entity_type }}</span>
      <p class="ent-card-meta">{{ meta }}</p>
      <p v-if="sourceLabel" class="ent-card-source">{{ sourceLabel }}</p>
    </div>
  </NuxtLink>
</template>
