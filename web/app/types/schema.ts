// Schéma ÉMERGENT (Étape 8, plans/maintenance_profile.md) — la file de
// validation humaine. Miroir des modèles backend (felix.core.schema_changes,
// felix.core.schema_detector, felix.api.routes.schema).

export interface PromoteVerbsChange {
  kind: 'promote_verbs'
  verbe_slugs: string[]
  rel_type: string
  reverse?: boolean
}

export interface MergeTypesChange {
  kind: 'merge_types'
  sources: string[]
  target: string
}

export type SchemaChange = PromoteVerbsChange | MergeTypesChange

export interface ChangeReport {
  change: SchemaChange
  edges_converted: number
  edges_collapsed: number
  entities_retyped: number
  observed_pairs: [string, string][]
  samples: string[]
  verbes: string[]
}

export interface Proposal {
  change: SchemaChange
  report: ChangeReport
}

// Un type de relation appris (felix.core.profile.RelationSpec, sérialisé).
export interface RelationSpecView {
  name: string
  gloss: string
  subjects: string[]
  objects: string[]
  allow_self: boolean
  examples: string
}

// Vue en lecture seule du profil appris (GET /api/schema/profile).
export interface ProfileView {
  name: string
  description: string
  relation_vocabulary: RelationSpecView[]
  narrative_rel: string
  manages_events: boolean
  version: number
}
