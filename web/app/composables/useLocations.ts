import type { LocationDetail, LocationSummary } from '~/types'

export function useLocations() {
  const { data: locations, status } = useFetch<LocationSummary[]>('/api/locations')

  return { locations, status }
}

export function useLocation(id: string) {
  const { data: location, status } = useFetch<LocationDetail>(`/api/locations/${id}`)

  return { location, status }
}
