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
