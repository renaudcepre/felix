import type { GroupCreate, GroupDetail, GroupSummary } from '~/types'

export function useGroups() {
  const { data: groups, status, refresh } = useFetch<GroupSummary[]>('/api/groups')

  async function createGroup(body: GroupCreate): Promise<GroupSummary> {
    const created = await $fetch<GroupSummary>('/api/groups', { method: 'POST', body })
    await refresh()
    return created
  }

  return { groups, status, refresh, createGroup }
}

export function useGroup(id: string) {
  const { data: group, status, refresh } = useFetch<GroupDetail>(`/api/groups/${id}`)

  async function addMember(charId: string) {
    await $fetch(`/api/groups/${id}/members/${charId}`, { method: 'PUT' })
    await refresh()
  }

  async function removeMember(charId: string) {
    await $fetch(`/api/groups/${id}/members/${charId}`, { method: 'DELETE' })
    await refresh()
  }

  return { group, status, refresh, addMember, removeMember }
}
