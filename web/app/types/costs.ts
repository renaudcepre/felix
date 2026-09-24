// Coût LLM (#coût) — miroir de felix.cost.ModelCost / CostSummary, et de
// ProjectCostOut (GET /api/costs). `cost_usd` null = prix inconnu (jamais un
// faux 0, cf. felix.cost.DEFAULT_PRICING).

export interface ModelCostPayload {
  model: string
  request_tokens: number
  response_tokens: number
  total_tokens: number
  cost_usd: number | null
}

// Coût d'UNE opération (un tour de chat, un import de document) — porté par
// l'event SSE `usage` et par le payload `{ cost: ... }` des messages persistés.
export interface CostSummaryPayload {
  request_tokens: number
  response_tokens: number
  total_tokens: number
  cost_usd: number | null
  by_model: ModelCostPayload[]
}

// Total persistant du projet (GET /api/costs?project=), toutes opérations
// confondues depuis l'origine — indépendant de l'historique de conversation.
export interface ProjectCostPayload {
  request_tokens: number
  response_tokens: number
  total_tokens: number
  cost_usd: number | null
  count_by_kind: Record<string, number>
}
