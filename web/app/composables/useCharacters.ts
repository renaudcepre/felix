import type { CharacterDetail, CharacterSummary } from '~/types'

export function useCharacters() {
  const { data: characters, status } = useFetch<CharacterSummary[]>('/api/characters')

  return { characters, status }
}

export function useCharacter(id: string) {
  const { data: character, status } = useFetch<CharacterDetail>(`/api/characters/${id}`)

  return { character, status }
}
