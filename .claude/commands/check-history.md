Explique comment utiliser le CLI `tools/view_history.py` pour consulter l'historique des evals Felix.

Le fichier d'historique est `evals/results/history.jsonl`.

## Commande de base

```
uv run python tools/view_history.py evals/results/history.jsonl
```

## Options disponibles

### Filtrer par modèle

`--model` / `-m` : n'affiche que les runs d'un modèle précis.

```
uv run python tools/view_history.py evals/results/history.jsonl --model mistral-large-latest
```

Pour lister tous les modèles présents dans le fichier :

```
uv run python tools/view_history.py evals/results/history.jsonl --list-models
```

### Filtrer par eval (case)

`--eval` / `-e` : n'affiche que les runs qui contiennent une eval spécifique.

```
uv run python tools/view_history.py evals/results/history.jsonl --eval amnesia_profile_survives_patching
```

Pour lister toutes les evals présentes dans le fichier :

```
uv run python tools/view_history.py evals/results/history.jsonl --list-evals
```

### Limiter le nombre d'entrées

`--tail` / `-n` : affiche uniquement les N dernières entrées (après filtrage).

```
uv run python tools/view_history.py evals/results/history.jsonl --tail 5
```

### Combinaisons utiles

Derniers 3 runs d'un modèle précis sur une eval précise :

```
uv run python tools/view_history.py evals/results/history.jsonl \
  --model Qwen/Qwen2.5-7B-Instruct-Turbo \
  --eval amnesia_profile_survives_patching \
  --tail 3
```
