import type { Issue } from '~/types'

export function useIssues(filters?: {
  type?: Ref<string | null>
  severity?: Ref<string | null>
  resolved?: Ref<boolean | null>
}) {
  const query = computed(() => {
    const q: Record<string, string | boolean> = {}
    if (filters?.type?.value) q.type = filters.type.value
    if (filters?.severity?.value) q.severity = filters.severity.value
    if (filters?.resolved?.value !== undefined && filters?.resolved?.value !== null) {
      q.resolved = filters.resolved.value
    }
    return q
  })

  const { data: issues, status, refresh } = useFetch<Issue[]>('/api/issues', { query })

  async function resolveIssue(id: string, resolved: boolean) {
    await $fetch(`/api/issues/${id}`, {
      method: 'PATCH',
      body: { resolved },
    })
    await refresh()
  }

  return { issues, status, refresh, resolveIssue }
}
