import type { ImportProgress } from '~/types'

export function useImport() {
  const progress = ref<ImportProgress | null>(null)
  const loading = ref(false)
  let pollInterval: ReturnType<typeof setInterval> | null = null

  async function startImport(files: File[]) {
    loading.value = true
    progress.value = null

    const formData = new FormData()
    for (const file of files) {
      formData.append('files', file)
    }

    try {
      const res = await $fetch<ImportProgress>('/api/import', {
        method: 'POST',
        body: formData,
      })
      progress.value = res
      startPolling()
    }
    catch (err: unknown) {
      const e = err as { data?: { detail?: string }, message?: string }
      progress.value = {
        status: 'error',
        total_scenes: 0,
        processed_scenes: 0,
        current_scene: '',
        issues_found: 0,
        error: e?.data?.detail || e?.message || 'Erreur inconnue',
        new_characters: [],
        new_locations: [],
      }
      loading.value = false
    }
  }

  function startPolling() {
    stopPolling()
    pollInterval = setInterval(async () => {
      try {
        const res = await $fetch<ImportProgress>('/api/import/status')
        progress.value = res
        if (res.status === 'done' || res.status === 'error') {
          stopPolling()
          loading.value = false
        }
      }
      catch {
        stopPolling()
        loading.value = false
      }
    }, 2000)
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval)
      pollInterval = null
    }
  }

  onUnmounted(stopPolling)

  return { progress, loading, startImport }
}
