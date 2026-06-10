Explique comment utiliser le CLI `tools/view_history.py` pour consulter l'historique des evals Felix.

Le fichier par défaut est `.protest/history.jsonl` (protest 0.2.0). L'ancien fichier `evals/results/history.jsonl` reste consultable en passant le chemin explicitement.

Le CLI détecte automatiquement le format par ligne :
- **protest 0.2.0** : `suites.<nom>.cases` (dict case → {passed, duration, scores, labels, …})
- **legacy** : `cases` à la racine (dict case → bool)

## Commande de base (fichier protest, défaut)

```
uv run python tools/view_history.py
```

## Options disponibles

### Filtrer par modèle

`--model` / `-m` : n'affiche que les runs d'un modèle précis.

```
uv run python tools/view_history.py --model mistral-small-2506
```

Pour lister tous les modèles présents (les suites de tests unitaires n'ont pas de modèle et affichent `—`) :

```
uv run python tools/view_history.py --list-models
```

### Filtrer par eval (case)

`--eval` / `-e` : n'affiche que les runs qui contiennent un cas d'eval spécifique.

```
uv run python tools/view_history.py --eval bapteme_differe
```

Pour lister tous les cas présents (evals ET tests unitaires) :

```
uv run python tools/view_history.py --list-evals
```

### Limiter le nombre d'entrées

`--tail` / `-n` : affiche uniquement les N derniers records (après filtrage).

```
uv run python tools/view_history.py --tail 5
```

### Combinaisons utiles

Derniers 3 runs d'un eval précis :

```
uv run python tools/view_history.py --eval bapteme_differe --tail 3
```

Derniers 5 runs d'un modèle précis :

```
uv run python tools/view_history.py --model mistral-small-2506 --tail 5
```

### Consulter l'ancien fichier legacy

```
uv run python tools/view_history.py evals/results/history.jsonl --tail 5
uv run python tools/view_history.py evals/results/history.jsonl --eval amnesia_profile_survives_patching
```

## Notes

- Les suites de tests unitaires (kind: "test") n'ont pas de champ `model` → affichées avec `—`.
- Le label `majority_detail` (multi-run protest) est affiché entre crochets à côté du cas.
- `--model` filtre sur l'égalité exacte du nom.
