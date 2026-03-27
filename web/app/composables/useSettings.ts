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

  return {
    currentModel,
    fetchCurrentModel,
  }
}
