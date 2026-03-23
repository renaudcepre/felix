export interface ProviderConfig {
  id: string
  label: string
  modelName: string
  baseUrl: string | null
  apiKey: string | null
}

const STORAGE_KEY = 'felix-providers'

const DEFAULT_PROVIDERS: ProviderConfig[] = [
  {
    id: 'lm-studio',
    label: 'LM Studio (local)',
    modelName: 'qwen/qwen2.5-7b-instruct',
    baseUrl: 'http://127.0.0.1:1234/v1',
    apiKey: null,
  },
]

function loadProviders(): ProviderConfig[] {
  if (import.meta.server) return DEFAULT_PROVIDERS
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return DEFAULT_PROVIDERS
  try {
    return JSON.parse(raw) as ProviderConfig[]
  }
  catch {
    return DEFAULT_PROVIDERS
  }
}

function saveProviders(providers: ProviderConfig[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(providers))
}

const providers = ref<ProviderConfig[]>(loadProviders())
const activeId = ref<string | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

// Current model info from API
const currentModel = ref<{ model_name: string, base_url: string | null } | null>(null)

export function useSettings() {
  const { apiStreamBase } = useRuntimeConfig().public

  async function fetchCurrentModel() {
    try {
      const res = await fetch(`${apiStreamBase}/api/settings/model`)
      if (res.ok) {
        currentModel.value = await res.json()
      }
    }
    catch {
      // API not available yet
    }
  }

  async function switchModel(provider: ProviderConfig) {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(`${apiStreamBase}/api/settings/model`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model_name: provider.modelName,
          base_url: provider.baseUrl,
          api_key: provider.apiKey,
        }),
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `HTTP ${res.status}`)
      }
      currentModel.value = await res.json()
      activeId.value = provider.id
    }
    catch (e) {
      error.value = e instanceof Error ? e.message : 'Erreur inconnue'
    }
    finally {
      loading.value = false
    }
  }

  function addProvider(provider: Omit<ProviderConfig, 'id'>) {
    const id = `provider-${Date.now()}`
    const newProvider: ProviderConfig = { ...provider, id }
    providers.value = [...providers.value, newProvider]
    saveProviders(providers.value)
    return newProvider
  }

  function removeProvider(id: string) {
    providers.value = providers.value.filter(p => p.id !== id)
    saveProviders(providers.value)
    if (activeId.value === id) activeId.value = null
  }

  function updateProvider(id: string, updates: Partial<Omit<ProviderConfig, 'id'>>) {
    providers.value = providers.value.map(p =>
      p.id === id ? { ...p, ...updates } : p,
    )
    saveProviders(providers.value)
  }

  return {
    providers,
    activeId,
    currentModel,
    loading,
    error,
    fetchCurrentModel,
    switchModel,
    addProvider,
    removeProvider,
    updateProvider,
  }
}
