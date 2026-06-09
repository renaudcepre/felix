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
  ordre: number
  resume: string
}

export interface EntityDetail {
  id: string
  name: string
  entity_type: string | null
  props: Record<string, unknown>
  relations: EntityRelation[]
  events: EntityEvent[]
}
