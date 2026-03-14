import type { SceneSummary } from '~/types'

export function useScenes() {
  const { data: scenes, status, refresh } = useFetch<SceneSummary[]>('/api/scenes')

  return { scenes, status, refresh }
}
