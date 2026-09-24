// Formatage FR du coût LLM (#coût) — même paire tokens/prix partout : sous
// chaque réponse de Felix, sur la carte d'import, dans le total de la topbar.

const tokensFormatter = new Intl.NumberFormat('fr-FR')
const millionsFormatter = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 })
const usdFormatter = new Intl.NumberFormat('fr-FR', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})

const MILLION = 1_000_000

export function formatTokens(n: number): string {
  if (n >= MILLION) return `${millionsFormatter.format(n / MILLION)} M tokens`
  return `${tokensFormatter.format(n)} tokens`
}

export function formatCostUsd(usd: number | null): string {
  if (usd === null) return 'prix inconnu'
  return `${usdFormatter.format(usd)} $`
}

export function formatCostLine(tokens: number, usd: number | null): string {
  return `${formatTokens(tokens)} · ${formatCostUsd(usd)}`
}
