// Modèle schemaless (:GenEntity / :REL) — miroir des modèles backend
// (felix.api.models.Entity*). Aucune sémantique de domaine : props libres.

export interface EntityRef {
  id: string
  name: string
  entity_type: string | null
}

export interface EntitySummary {
  id: string
  name: string
  entity_type: string | null
  props: Record<string, unknown>
}

export interface EntityRelation {
  rel_type: string
  direction: 'out' | 'in'
  other: EntityRef
}

export interface EntityEvent {
  // clé de suppression d'un événement depuis la fiche (#61)
  id: string
  ordre: number
  resume: string
}

// Correction manuelle d'une fiche (#61) — miroir de EntityPatch côté backend.
export interface EntityPatch {
  name?: string
  props?: Record<string, string>
  remove_props?: string[]
}

// Référence complète d'une relation orientée (clé de suppression).
export interface RelationRef {
  from_id: string
  to_id: string
  rel_type: string
}

export interface EntityDetail {
  id: string
  name: string
  entity_type: string | null
  props: Record<string, unknown>
  relations: EntityRelation[]
  events: EntityEvent[]
}
