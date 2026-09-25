// Trace des appels d'outil + Cypher exécutée (#78) — miroir de felix.trace
// (ToolCallEntry / QueryEntry / TraceSummary). Porté par l'event SSE `trace`
// et par le payload `{ trace: ... }` des messages persistés, même convention
// que le coût (cf. costs.ts).

// Un appel d'outil du LLM — nom + args bruts + libellé humain (calculé côté
// back à la capture, cf. felix.core.tools.label_for_tool_call).
export interface ToolCallEntryPayload {
  name: string
  args: Record<string, unknown>
  label: string
}

// Une requête Cypher RÉELLEMENT exécutée par cet appel — texte + paramètres
// (valeurs longues tronquées côté back).
export interface QueryEntryPayload {
  query: string
  params: Record<string, unknown>
}

// Trace d'UNE opération (un tour de chat, un import de document).
export interface TraceSummaryPayload {
  tool_calls: ToolCallEntryPayload[]
  queries: QueryEntryPayload[]
  // Requêtes vues au-delà du cap, non listées individuellement mais comptées.
  queries_omitted: number
}
