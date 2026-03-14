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

export interface TimelineEvent {
  id: string
  date: string
  era: string
  title: string
  description: string
  location: string
  characters: string
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
