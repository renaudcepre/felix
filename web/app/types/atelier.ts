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

export interface AtelierMsg {
  id: number
  role: 'user' | 'felix'
  kind?: 'text' | 'tool' | 'choice' | 'cite' | 'alert'
  body?: string
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
