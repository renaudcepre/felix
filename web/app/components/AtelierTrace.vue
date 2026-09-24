<script setup lang="ts">
// Trace d'un tour (#78) : sous la ligne de coût, une liste discrète des
// libellés humains des appels d'outil, toujours visible ; un clic déplie le
// détail (appels exacts + Cypher exécutée). Même thème papier que le reste
// de l'atelier — aucune couleur neuve.
import type { TraceSummaryPayload } from '~/types/trace'
import { visibleLabels } from '~/utils/formatTrace'

const props = defineProps<{ trace: TraceSummaryPayload }>()

const open = ref(false)

const labels = computed(() => props.trace.tool_calls.map(c => c.label))
const view = computed(() => visibleLabels(labels.value))
const hasDetails = computed(
  () => props.trace.tool_calls.length > 0 || props.trace.queries.length > 0,
)
</script>

<template>
  <div v-if="hasDetails" class="msg-trace">
    <button class="trace-toggle" :class="{ open }" type="button" @click="open = !open">
      <span class="trace-labels">
        {{ view.shown.join(' · ') }}<template v-if="view.hiddenCount"> · +{{ view.hiddenCount }}</template>
      </span>
      <AtelierIcon name="chevron" :size="11" />
    </button>
    <div v-if="open" class="trace-details">
      <div v-if="trace.tool_calls.length" class="trace-section">
        <div class="trace-section-title">Appels</div>
        <div v-for="(c, i) in trace.tool_calls" :key="`tc-${i}`" class="trace-line">
          <span class="trace-name">{{ c.name }}</span>
          <span class="trace-json">{{ JSON.stringify(c.args) }}</span>
        </div>
      </div>
      <div v-if="trace.queries.length" class="trace-section">
        <div class="trace-section-title">Requêtes Cypher</div>
        <div v-for="(q, i) in trace.queries" :key="`q-${i}`" class="trace-line">
          <pre class="trace-query">{{ q.query.trim() }}</pre>
          <span v-if="Object.keys(q.params).length" class="trace-json">{{ JSON.stringify(q.params) }}</span>
        </div>
        <div v-if="trace.queries_omitted" class="trace-more">+{{ trace.queries_omitted }} requêtes</div>
      </div>
    </div>
  </div>
</template>
