// Modèle de message du chat « atelier » (porté depuis le proto Claude Design).
// Reflète la spec produit B : text / tool / choice / cite / alert.

export interface ChoiceOption {
  k: string
  label: string
  desc: string
}

export interface ResolveOption {
  id: string
  label: string
  desc: string
}

export type AlertStatus = 'open' | 'resolving' | 'resolved' | 'dismissed'

// Mode du bot (Étape 3, plans/maintenance_profile.md) — cf. GET /api/atelier/profiles.
// welcome/input_placeholder (Étape 8) : vocabulaire UI DU MODE — plus aucun
// texte scénario codé en dur côté front, cf. felix.atelier.agent.profile_summary.
export interface AtelierProfile {
  key: string
  label: string
  welcome: string
  input_placeholder: string
  // Vrai pour un mode dont le schéma s'apprend au fil des documents (émergent) —
  // affiche le panneau de propositions (cf. SchemaProposalsPanel).
  evolving: boolean
}

// Résumé d'un import de fiche (Étape 3) — miroir d'IngestReport (API), cf.
// felix.ingest.document.IngestReport.
export interface IngestReportPayload {
  document_id: string
  title: string
  chunks: number
  entities_touched: number
  relations: number
  alerts: string[]
  errors: string[]
}

export interface AtelierMsg {
  id: number
  role: 'user' | 'felix'
  kind?: 'text' | 'tool' | 'choice' | 'cite' | 'alert' | 'report'
  body?: string
  // report (import de fiche)
  report?: IngestReportPayload
  // tool
  tool?: 'fiche' | 'people'
  title?: string
  subject?: string
  field?: string
  added?: string
  // cible de la carte pour les actions ✎/🗑 (#61) — absente : pas d'action
  entityId?: string
  relation?: { from_id: string, to_id: string, rel_type: string, verbe_slug?: string | null }
  // état après action manuelle de l'auteur (affichage barré + désactivation)
  edited?: 'deleted' | 'renamed'
  // choice
  question?: string
  options?: ChoiceOption[]
  answered?: boolean
  chosen?: string
  // cite
  quote?: string
  source?: string
  note?: string
  // alert
  status?: AlertStatus
  resolves?: ResolveOption[]
  resolution?: string
}
