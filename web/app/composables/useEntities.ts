import type { EntityDetail, EntitySummary } from '~/types/entities'
import { currentProject } from './useProject'

// Liste filtrable par entity_type. `type` et `project` sont réactifs : la liste
// se rafraîchit en changeant d'onglet (deep-link ?type=...) ou d'histoire (#60).
// Le proxy nitro route /api.
export function useEntities(type: Ref<string | undefined>) {
  const { data: entities, status, refresh } = useFetch<EntitySummary[]>('/api/entities', {
    query: { type, project: currentProject },
  })
  return { entities, status, refresh }
}

export function useEntity(id: string) {
  const { data: entity, status, refresh } = useFetch<EntityDetail>(`/api/entities/${id}`, {
    query: { project: currentProject },
  })
  return { entity, status, refresh }
}
