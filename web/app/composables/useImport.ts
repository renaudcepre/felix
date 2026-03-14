import type { ClarificationRequest, ImportEvent, ImportProgress } from '~/types'
import { parseSSEStream } from '~/utils/parseSSE'

export function useImport() {
  const { apiStreamBase } = useRuntimeConfig().public
  const progress = ref<ImportProgress | null>(null)
  const loading = ref(false)
  const events = ref<ImportEvent[]>([])
  const clarification = ref<ClarificationRequest | null>(null)
  let abortController: AbortController | null = null

  async function startImport(files: File[], enrich: boolean = true) {
    loading.value = true
    progress.value = null
    events.value = []
    clarification.value = null

    const formData = new FormData()
    for (const file of files) {
      formData.append('files', file)
    }

    abortController = new AbortController()

    const params = new URLSearchParams()
    if (!enrich) params.set('enrich', 'false')
    const qs = params.toString() ? `?${params.toString()}` : ''

    try {
      const response = await fetch(`${apiStreamBase}/api/import/stream${qs}`, {
        method: 'POST',
        body: formData,
        signal: abortController.signal,
      })

      if (!response.ok) {
        const err = await response.text()
        throw new Error(err || `HTTP ${response.status}`)
      }

      // Initialize progress
      progress.value = {
        status: 'pending',
        total_scenes: 0,
        processed_scenes: 0,
        current_scene: '',
        issues_found: 0,
        error: '',
        new_characters: [],
        new_locations: [],
      }

      for await (const sse of parseSSEStream(response)) {
        const data = JSON.parse(sse.data) as ImportEvent
        data.event = sse.event
        events.value = [...events.value, data]

        switch (sse.event) {
          case 'status_change':
            if (progress.value) {
              progress.value = {
                ...progress.value,
                status: data.status ?? progress.value.status,
                current_scene: data.current_scene ?? progress.value.current_scene,
                processed_scenes: data.processed_scenes ?? progress.value.processed_scenes,
                total_scenes: data.total_scenes ?? progress.value.total_scenes,
              }
            }
            break

          case 'clarification_needed':
            clarification.value = {
              id: data.id!,
              question: data.question!,
              entity_name: data.entity_name!,
              candidate_name: data.candidate_name!,
              candidate_id: data.candidate_id!,
              score: data.score!,
              options: data.options!,
            }
            break

          case 'done':
            if (progress.value) {
              progress.value = {
                ...progress.value,
                status: 'done',
                issues_found: data.total_issues ?? 0,
                new_characters: data.new_characters ?? [],
                new_locations: data.new_locations ?? [],
              }
            }
            loading.value = false
            break

          case 'error':
            if (progress.value) {
              progress.value = {
                ...progress.value,
                status: 'error',
                error: data.message ?? 'Erreur inconnue',
              }
            }
            loading.value = false
            break
        }
      }
    }
    catch (err: unknown) {
      if ((err as Error).name === 'AbortError') return
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

  async function respondClarification(id: string, answer: 'link' | 'new') {
    clarification.value = null
    await fetch(`${apiStreamBase}/api/import/clarify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, answer }),
    })
  }

  function cancelImport() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    loading.value = false
  }

  function reset() {
    cancelImport()
    progress.value = null
    events.value = []
    clarification.value = null
  }

  onUnmounted(cancelImport)

  return { progress, loading, events, clarification, startImport, respondClarification, cancelImport, reset }
}
