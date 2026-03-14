export interface CharacterSummary {
  id: string
  name: string
  era: string
}

export interface Relation {
  relation_type: string
  other_name: string
  era: string | null
  description: string | null
}

export interface CharacterDetail {
  id: string
  name: string
  aliases: string[]
  era: string
  age: string | null
  physical: string | null
  background: string | null
  arc: string | null
  traits: string | null
  status: string | null
  relations: Relation[]
}

export interface LocationSummary {
  id: string
  name: string
  era: string | null
}

export interface LocationDetail {
  id: string
  name: string
  era: string | null
  description: string | null
  address: string | null
  scenes: SceneSummary[]
}

export interface TimelineCharacter {
  id: string
  name: string
}

export interface TimelineEvent {
  id: string
  date: string
  era: string
  title: string
  description: string
  location: string
  location_id: string | null
  characters: string
  characters_detail: TimelineCharacter[]
}

export interface Issue {
  id: string
  type: string
  severity: string
  scene_id: string | null
  entity_id: string | null
  description: string
  suggestion: string | null
  resolved: boolean
  created_at: string | null
}

export interface ImportProgress {
  status: string
  total_scenes: number
  processed_scenes: number
  current_scene: string
  issues_found: number
  error: string
  new_characters: string[]
  new_locations: string[]
}

export interface SceneSummary {
  id: string
  filename: string
  title: string | null
  era: string | null
  date: string | null
}

export interface ChatRequest {
  message: string
  message_history: object[]
}

export interface UsageInfo {
  request_tokens: number
  response_tokens: number
  total_tokens: number
}

export interface ChatResponse {
  output: string
  message_history: object[]
  usage: UsageInfo | null
}

export interface ImportEvent {
  event: string
  // status_change
  status?: string
  current_scene?: string
  processed_scenes?: number
  total_scenes?: number
  // scene_analyzed
  scene_id?: string
  title?: string
  characters?: { name: string, role: string }[]
  location?: string
  era?: string
  // entity_resolved
  name?: string
  action?: 'created' | 'linked' | 'ambiguous'
  linked_to?: string
  score?: number
  // issue_found
  type?: string
  severity?: string
  description?: string
  // clarification_needed
  id?: string
  question?: string
  entity_name?: string
  candidate_name?: string
  candidate_id?: string
  options?: string[]
  // profiling_character
  fragment_count?: number
  scene_count?: number
  // character_profiled
  filled_fields?: string[]
  relations?: { other_name: string, relation: string }[]
  // done
  total_issues?: number
  new_characters?: string[]
  new_locations?: string[]
  // error
  message?: string
}

export interface ClarificationRequest {
  id: string
  question: string
  entity_name: string
  candidate_name: string
  candidate_id: string
  score: number
  options: string[]
}
