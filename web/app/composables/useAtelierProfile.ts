import type { AtelierProfile } from '~/types/atelier'

// Mode du bot (Étape 3, plans/maintenance_profile.md) — état SINGLETON partagé
// par le sélecteur de la topbar et useAtelier (porte `profile` à chaque tour
// de chat ET à chaque import de fiche). Persisté en localStorage, même schéma
// que useProject (felix.project.v1) : aucun état côté serveur, survit au reload.
const PROFILE_KEY = 'felix.profile.v1'
export const DEFAULT_ATELIER_PROFILE = 'scenario'

export const currentProfile = ref<string>(
  import.meta.client ? (localStorage.getItem(PROFILE_KEY) ?? DEFAULT_ATELIER_PROFILE) : DEFAULT_ATELIER_PROFILE,
)
const profiles = ref<AtelierProfile[]>([])

export function useAtelierProfile() {
  async function refreshProfiles() {
    try {
      profiles.value = await $fetch<AtelierProfile[]>('/api/atelier/profiles')
    }
    catch { /* backend absent : le sélecteur reste sur le mode courant */ }
  }

  function switchProfile(key: string) {
    currentProfile.value = key
    if (import.meta.client) localStorage.setItem(PROFILE_KEY, key)
  }

  return { currentProfile, profiles, refreshProfiles, switchProfile }
}
