import type { Project } from '~/types/projects'

// Projet/histoire courant (#60) — état SINGLETON partagé par le chat, les pages
// d'entités et les édits : tout appel API porte ce projet, le serveur reste
// stateless. Persisté en localStorage pour survivre au reload (même hypothèse
// local-first mono-utilisateur que la conversation, cf. useAtelier).
const PROJECT_KEY = 'felix.project.v1'
export const DEFAULT_PROJECT = 'defaut'

export const currentProject = ref<string>(
  import.meta.client ? (localStorage.getItem(PROJECT_KEY) ?? DEFAULT_PROJECT) : DEFAULT_PROJECT,
)
const projects = ref<Project[]>([])

export function useProject() {
  async function refreshProjects() {
    try {
      projects.value = await $fetch<Project[]>('/api/projects')
      // Registre vide (premier lancement avant tout tour de chat) : le projet
      // par défaut existe côté back (migration au boot), on l'affiche quand même.
      if (!projects.value.some(p => p.id === currentProject.value)) {
        projects.value = [
          ...projects.value,
          { id: DEFAULT_PROJECT, name: 'Histoire par défaut' },
        ]
      }
    }
    catch { /* backend absent : le sélecteur reste sur le projet courant */ }
  }

  function switchProject(id: string) {
    currentProject.value = id
    if (import.meta.client) localStorage.setItem(PROJECT_KEY, id)
  }

  async function createProject(name: string): Promise<Project | null> {
    const t = name.trim()
    if (!t) return null
    const p = await $fetch<Project>('/api/projects', { method: 'POST', body: { name: t } })
    await refreshProjects()
    switchProject(p.id)
    return p
  }

  const currentProjectName = computed(() =>
    projects.value.find(p => p.id === currentProject.value)?.name ?? currentProject.value,
  )

  return { currentProject, currentProjectName, projects, refreshProjects, switchProject, createProject }
}
