import type { CharacterCreate, CharacterDetail, CharacterProfileUpdate, CharacterSummary, Relation, RelationUpsert } from '~/types'

export function useCharacters() {
  const { data: characters, status, refresh } = useFetch<CharacterSummary[]>('/api/characters')

  async function createCharacter(body: CharacterCreate): Promise<CharacterSummary> {
    const created = await $fetch<CharacterSummary>('/api/characters', { method: 'POST', body })
    await refresh()
    return created
  }

  return { characters, status, refresh, createCharacter }
}

export function useCharacter(id: string) {
  const { data: character, status, refresh } = useFetch<CharacterDetail>(`/api/characters/${id}`)

  async function updateCharacter(fields: CharacterProfileUpdate) {
    await $fetch(`/api/characters/${id}`, { method: 'PATCH', body: fields })
    await refresh()
  }

  async function upsertRelation(charB: string, body: RelationUpsert): Promise<Relation> {
    const rel = await $fetch<Relation>(`/api/characters/${id}/relations/${charB}`, { method: 'PUT', body })
    await refresh()
    return rel
  }

  async function deleteRelation(charB: string, relationType: string) {
    await $fetch(`/api/characters/${id}/relations/${charB}?relation_type=${encodeURIComponent(relationType)}`, { method: 'DELETE' })
    await refresh()
  }

  return { character, status, refresh, updateCharacter, upsertRelation, deleteRelation }
}
