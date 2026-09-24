import type { ProjectCostPayload } from '~/types/costs'
import { currentProject } from './useProject'

// Total persistant du projet (#coût) — état SINGLETON (même convention que
// useProject/useSchemaProposals) : la topbar l'affiche, useAtelier/onFileSelected
// le rafraîchissent après chaque tour/import.
const cost = ref<ProjectCostPayload | null>(null)

async function refreshProjectCost(project?: string) {
  const p = project ?? currentProject.value
  try {
    cost.value = await $fetch<ProjectCostPayload>('/api/costs', { query: { project: p } })
  }
  catch {
    // backend absent, ou projet tout neuf sans encore d'opération : total
    // resté à sa dernière valeur connue plutôt qu'une erreur bloquante.
  }
}

export function useProjectCost() {
  return { cost, refreshProjectCost }
}
