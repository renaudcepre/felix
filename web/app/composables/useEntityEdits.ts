import type { EntityPatch, RelationRef } from '~/types/entities'

// Édition manuelle de la bible (#61) — quand Felix se trompe, l'auteur corrige
// DEPUIS l'UI. Chaque appel laisse un tombstone :UserEdit côté backend, injecté
// au LLM au tour suivant : supprimer une fiche ici ne la fait PAS renaître.
export function useEntityEdits() {
  async function deleteEntity(id: string): Promise<void> {
    await $fetch(`/api/entities/${encodeURIComponent(id)}`, { method: 'DELETE' })
  }

  // Rename + set/retrait de props. Renvoie l'id final (il change au rename,
  // et une collision de nom FUSIONNE les fiches — même effet que rename_entity).
  async function patchEntity(id: string, patch: EntityPatch): Promise<{ id: string, merged: boolean }> {
    return await $fetch<{ id: string, merged: boolean }>(
      `/api/entities/${encodeURIComponent(id)}`,
      { method: 'PATCH', body: patch },
    )
  }

  async function deleteRelation(rel: RelationRef): Promise<void> {
    await $fetch(
      `/api/entities/${encodeURIComponent(rel.from_id)}/relations/${encodeURIComponent(rel.rel_type)}/${encodeURIComponent(rel.to_id)}`,
      { method: 'DELETE' },
    )
  }

  return { deleteEntity, patchEntity, deleteRelation }
}
