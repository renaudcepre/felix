import type { TimelineEvent } from '~/types'

export function useTimeline(era?: Ref<string | null>) {
  const query = computed(() => {
    if (era?.value) return { era: era.value }
    return {}
  })

  const { data: events, status, refresh } = useFetch<TimelineEvent[]>('/api/timeline', {
    query,
  })

  return { events, status, refresh }
}
