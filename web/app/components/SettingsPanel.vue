<script setup lang="ts">
const open = defineModel<boolean>('open', { default: false })
const { currentModel, fetchCurrentModel } = useSettings()

watch(open, (val) => {
  if (val) fetchCurrentModel()
})
</script>

<template>
  <USlideover v-model:open="open" title="Settings" description="LLM configuration (read-only)">
    <template #body>
      <div class="space-y-6">
        <div v-if="currentModel" class="rounded-lg bg-elevated p-3 space-y-1">
          <p class="text-xs text-muted font-medium uppercase tracking-wide">
            Active model
          </p>
          <p class="text-sm font-mono font-semibold text-default">
            {{ currentModel.model_name }}
          </p>
          <p class="text-xs text-muted font-mono">
            {{ currentModel.base_url || 'Mistral API' }}
          </p>
        </div>
        <p class="text-xs text-muted">
          Models are configured server-side via environment variables.
        </p>
      </div>
    </template>
  </USlideover>
</template>
