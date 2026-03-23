<script setup lang="ts">
import type { ProviderConfig } from '~/composables/useSettings'

const open = defineModel<boolean>('open', { default: false })

const {
  providers,
  activeId,
  currentModel,
  loading,
  error,
  fetchCurrentModel,
  switchModel,
  addProvider,
  removeProvider,
} = useSettings()

// Form state for adding a new provider
const showForm = ref(false)
const form = reactive({
  label: '',
  modelName: '',
  baseUrl: '',
  apiKey: '',
})

function resetForm() {
  form.label = ''
  form.modelName = ''
  form.baseUrl = ''
  form.apiKey = ''
  showForm.value = false
}

function handleAdd() {
  if (!form.label || !form.modelName) return
  addProvider({
    label: form.label,
    modelName: form.modelName,
    baseUrl: form.baseUrl || null,
    apiKey: form.apiKey || null,
  })
  resetForm()
}

async function handleSelect(provider: ProviderConfig) {
  await switchModel(provider)
}

function handleRemove(id: string) {
  removeProvider(id)
}

// Fetch current model on open
watch(open, (val) => {
  if (val) fetchCurrentModel()
})
</script>

<template>
  <USlideover v-model:open="open" title="Settings" description="Providers LLM">
    <template #body>
      <div class="space-y-6">
        <!-- Current model indicator -->
        <div v-if="currentModel" class="rounded-lg bg-elevated p-3 space-y-1">
          <p class="text-xs text-muted font-medium uppercase tracking-wide">
            Actif
          </p>
          <p class="text-sm font-mono font-semibold text-default">
            {{ currentModel.model_name }}
          </p>
          <p class="text-xs text-muted font-mono">
            {{ currentModel.base_url || 'Mistral API' }}
          </p>
        </div>

        <!-- Error -->
        <div v-if="error" class="rounded-lg bg-error/10 border border-error p-3">
          <p class="text-sm text-error">{{ error }}</p>
        </div>

        <!-- Provider list -->
        <div class="space-y-2">
          <h3 class="text-sm font-semibold text-default">
            Providers
          </h3>
          <div
            v-for="provider in providers"
            :key="provider.id"
            class="flex items-center gap-2 rounded-lg border p-3 transition-colors"
            :class="activeId === provider.id ? 'border-primary bg-primary/5' : 'border-default'"
          >
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium truncate">{{ provider.label }}</p>
              <p class="text-xs text-muted font-mono truncate">{{ provider.modelName }}</p>
              <p class="text-xs text-dimmed font-mono truncate">{{ provider.baseUrl || 'Mistral API' }}</p>
            </div>
            <div class="flex items-center gap-1 shrink-0">
              <UButton
                size="xs"
                variant="soft"
                :loading="loading && activeId !== provider.id"
                :disabled="loading"
                icon="i-lucide-play"
                @click="handleSelect(provider)"
              />
              <UButton
                v-if="provider.id !== 'lm-studio'"
                size="xs"
                variant="soft"
                color="error"
                icon="i-lucide-trash-2"
                @click="handleRemove(provider.id)"
              />
            </div>
          </div>
        </div>

        <!-- Add provider form -->
        <div>
          <UButton
            v-if="!showForm"
            variant="outline"
            icon="i-lucide-plus"
            block
            @click="showForm = true"
          >
            Ajouter un provider
          </UButton>

          <div v-else class="space-y-3 rounded-lg border border-default p-3">
            <UFormField label="Nom">
              <UInput v-model="form.label" placeholder="Together AI" />
            </UFormField>
            <UFormField label="Nom du modele">
              <UInput v-model="form.modelName" placeholder="meta-llama/Llama-3-70b" class="font-mono" />
            </UFormField>
            <UFormField label="Base URL">
              <UInput v-model="form.baseUrl" placeholder="https://api.together.xyz/v1" class="font-mono" />
            </UFormField>
            <UFormField label="API Key">
              <UInput v-model="form.apiKey" type="password" placeholder="sk-..." class="font-mono" />
            </UFormField>
            <div class="flex gap-2">
              <UButton
                :disabled="!form.label || !form.modelName"
                icon="i-lucide-check"
                @click="handleAdd"
              >
                Ajouter
              </UButton>
              <UButton variant="ghost" @click="resetForm">
                Annuler
              </UButton>
            </div>
          </div>
        </div>
      </div>
    </template>
  </USlideover>
</template>
