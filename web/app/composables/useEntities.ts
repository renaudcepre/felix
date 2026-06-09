import type { EntityDetail, EntitySummary } from '~/types/entities'

// Liste filtrable par entity_type. `type` est réactif : la liste se rafraîchit
// quand on change d'onglet (deep-link ?type=...). Le proxy nitro route /api.
export function useEntities(type: Ref<string | undefined>) {
  const { data: entities, status, refresh } = useFetch<EntitySummary[]>('/api/entities', {
    query: { type },
  })
  return { entities, status, refresh }
}

export function useEntity(id: string) {
  const { data: entity, status, refresh } = useFetch<EntityDetail>(`/api/entities/${id}`)
  return { entity, status, refresh }
}
