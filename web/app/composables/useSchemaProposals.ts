import type { Proposal, ProfileView, SchemaChange } from '~/types/schema'
import { currentProject } from './useProject'

// File de validation du schéma émergent (Étape 8) — état SINGLETON (même
// convention que useProject/useAtelierProfile) : le bouton « Propositions » de
// la topbar (compteur) et le panneau partagent la même liste, sans prop-drilling.
const proposals = ref<Proposal[]>([])
const profileView = ref<ProfileView | null>(null)
const loading = ref(false)

export function useSchemaProposals() {
  async function refreshProposals() {
    loading.value = true
    try {
      proposals.value = await $fetch<Proposal[]>('/api/schema/proposals', {
        query: { project: currentProject.value, profile: 'emergent' },
      })
    }
    catch {
      // backend absent, ou mode non émergent pour ce projet : liste vide plutôt
      // qu'une erreur bloquante — le bouton reste discret.
      proposals.value = []
    }
    finally {
      loading.value = false
    }
  }

  async function refreshProfileView() {
    try {
      profileView.value = await $fetch<ProfileView>('/api/schema/profile', {
        query: { project: currentProject.value },
      })
    }
    catch {
      profileView.value = null
    }
  }

  // Valide UNE proposition (POST /api/schema/apply) — migre le passé ET fait
  // évoluer le profil côté back ; on rafraîchit les deux vues ensuite.
  async function applyChange(change: SchemaChange) {
    await $fetch('/api/schema/apply', {
      method: 'POST',
      body: { project: currentProject.value, change },
    })
    await Promise.all([refreshProposals(), refreshProfileView()])
  }

  // Refuse UNE proposition (POST /api/schema/reject) — persisté côté back : le
  // détecteur ne la re-proposera plus (même ensemble source).
  async function rejectChange(change: SchemaChange) {
    await $fetch('/api/schema/reject', {
      method: 'POST',
      body: { project: currentProject.value, change },
    })
    await refreshProposals()
  }

  return { proposals, profileView, loading, refreshProposals, refreshProfileView, applyChange, rejectChange }
}
