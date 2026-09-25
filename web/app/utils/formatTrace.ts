// Mise en forme de la liste toujours visible des libellés d'outils (#78) —
// sous la ligne de coût, même esprit discret : quelques mots, pas la trace
// entière (celle-ci n'apparaît qu'au clic, cf. AtelierTrace.vue).

const MAX_VISIBLE_LABELS = 4

// Réduit les libellés IDENTIQUES qui se suivent à une seule occurrence (ex.
// trois `find_entity` d'affilée sur la même fiche) — pas une déduplication
// globale : deux appels au même tool séparés dans le temps restent deux lignes.
export function dedupeConsecutiveLabels(labels: string[]): string[] {
  const out: string[] = []
  for (const label of labels) {
    if (out[out.length - 1] !== label) out.push(label)
  }
  return out
}

export interface VisibleLabels {
  shown: string[]
  hiddenCount: number
}

// Liste courte à afficher toujours (après dédup des doublons consécutifs) +
// le nombre d'appels restants, résumé en « +N ».
export function visibleLabels(labels: string[]): VisibleLabels {
  const deduped = dedupeConsecutiveLabels(labels)
  if (deduped.length <= MAX_VISIBLE_LABELS) {
    return { shown: deduped, hiddenCount: 0 }
  }
  return {
    shown: deduped.slice(0, MAX_VISIBLE_LABELS),
    hiddenCount: deduped.length - MAX_VISIBLE_LABELS,
  }
}
