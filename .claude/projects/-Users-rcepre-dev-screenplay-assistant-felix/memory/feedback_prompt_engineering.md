---
name: feedback_prompt_engineering
description: Préférer les prompts simples avec exemples concrets plutôt que les règles abstraites, surtout pour les petits modèles
type: feedback
---

Pour les petits modèles (7B), les prompts few-shot avec exemples concrets surpassent
systématiquement les listes de règles abstraites.

**Why:** Lors de l'implémentation des narrative beats, un prompt avec 6 règles
abstraites ("never omit attacks", "active characters list is a hint not a filter"...)
échouait sur Qwen 7B qui ratait le beat `Nazgûl → plante une lame Morgul → Aldric`.
Remplacer par un prompt court + 1 exemple générique (guard/Elena) a immédiatement résolu
le problème.

**How to apply:** Quand un petit modèle rate une instruction complexe, avant d'ajouter
des règles, essayer d'abord un exemple concret qui illustre le cas difficile. Garder les
exemples génériques (pas orientés vers le cas de test spécifique).
