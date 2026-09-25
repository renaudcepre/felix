import type { AtelierProfile } from '~/types/atelier'

// Mode du bot (Étape 3, plans/maintenance_profile.md) — état SINGLETON partagé
// par le sélecteur de la topbar et useAtelier (porte `profile` à chaque tour
// de chat ET à chaque import de fiche). Persisté en localStorage, même schéma
// que useProject (felix.project.v1) : aucun état côté serveur, survit au reload.
const PROFILE_KEY = 'felix.profile.v1'
// Défaut = émergent (Étape 8, aligné sur felix.atelier.agent.DEFAULT_PROFILE) :
// le mode qui n'assume rien du domaine, pas scénario.
export const DEFAULT_ATELIER_PROFILE = 'emergent'

export const currentProfile = ref<string>(
  import.meta.client ? (localStorage.getItem(PROFILE_KEY) ?? DEFAULT_ATELIER_PROFILE) : DEFAULT_ATELIER_PROFILE,
)
// Exporté (pas seulement retourné par le composable) : useAtelier.ts en a
// besoin pour dériver le welcome/placeholder du mode courant sans dupliquer
// l'état ni dépendre de l'ordre de montage des composants.
export const profiles = ref<AtelierProfile[]>([])

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
