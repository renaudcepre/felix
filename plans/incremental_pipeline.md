# Pipeline d'import incrémental

## Idée centrale

Améliorer le pipeline actuel (batch fire-and-forget) en le rendant **incrémental** :
chaque scène est traitée, checkée contre la DB complète, puis importée — en s'appuyant
à chaque étape sur une base considérée de bonne qualité.

Le pipeline reste **fire-and-forget** : les issues détectées sont loggées en DB et
l'auteur décide quoi en faire. Pas de blocage, pas de rollback — un trou dans l'histoire
est pire qu'une issue signalée.

---

## Les deux piliers

### 1. Consistency check par scène, sur DB entière

Le check se déclenche **après chaque scène importée** (et non à la fin du batch),
contre l'état actuel de la DB + la scène qui vient d'être chargée.

**Actuellement :**
- Check en fin de batch, sur les nouvelles scènes seulement
- Les scènes des imports précédents ne sont jamais re-vérifiées entre elles

**Cible :**
- Check après chaque `load_scene()`, sur toute la DB
- Issue détectée → loggée en DB → pipeline continue (comportement actuel conservé)
- La scène qui vient d'être ajoutée est la seule candidate pour l'issue → localisation précise

#### Passes spécialisées

Plutôt qu'un seul prompt "détecte tout", le check est décomposé en passes ciblées.
Les petits modèles répondent mieux à des questions unidimensionnelles :

- **Pass dates/timeline** — "cette scène est-elle temporellement cohérente avec le corpus ?"
  Input : frise chronologique triée de toutes les scènes en DB
- **Pass spatiale** — "un personnage est-il au bon endroit au bon moment ?"
  Input : tableau personnage × scène × lieu × date
- **Pass narrative** — "cette scène présuppose-t-elle ou contredit-elle quelque chose ?"
  Input : résumés des scènes dans l'ordre chronologique

Les passes sont indépendantes logiquement, mais doivent s'exécuter **séquentiellement**.
Sur M4 avec LM Studio / llama.cpp, envoyer plusieurs requêtes en parallèle ne fait pas
tourner plusieurs inférences en même temps — le moteur les sérialise ou divise la bande
passante RAM unifiée, ce qui est plus lent. Le code reste asyncio, mais les appels LLM
sont `await`és l'un après l'autre.

---

### 2. Profiling incrémental sur baseline validée

Le profiler ne repart plus de zéro à la fin du batch. Après chaque scène chargée,
les profils des personnages qui y apparaissent sont **patchés** avec les nouvelles
informations.

```
Scène chargée → pour chaque personnage présent :
  ├── Profil existant en DB → "patch" (enrichissement avec la nouvelle scène)
  └── Pas de profil          → "création" (from scratch)
```

Prompt profiler en mode patch :
> "Voici le profil actuel de [personnage] (issu des scènes précédentes).
> Voici une nouvelle scène. Enrichis uniquement avec ce que cette scène apporte
> de nouveau. Ne modifie pas ce qui existe déjà."

**Pourquoi c'est mieux :**
- Le profil existant est la source de vérité — le modèle ne peut pas le dégrader
- Contexte bien plus petit → meilleure qualité sur petit modèle
- Progressive refinement : chaque scène améliore les profils
- Si une scène contredit le profil existant, le check l'a déjà signalé

---

## Flow global d'une scène

```
1. Analyse LLM        → titre, résumé, personnages, lieu, date, mood
2. Résolution entités → fuzzy match contre registry (clarification si ambigu)
3. load_scene()       → écriture en DB + Chroma (comportement actuel)
4. Consistency check  → passes spécialisées sur DB entière
   ├── OK             → profiling patch → scène suivante
   └── Issue          → loggée en DB   → profiling patch → scène suivante
```

---

## Ce qui change dans l'architecture actuelle

| Actuel | Cible |
|---|---|
| Consistency check en fin de batch | Check après chaque scène |
| Check sur nouvelles scènes seulement | Check sur DB entière |
| Un seul prompt généraliste | 2-3 passes spécialisées parallélisables |
| Profiling en batch à la fin | Profiling patch après chaque scène |

## Ce qui ne change pas

- `load_scene()` — inchangé, écrit directement en DB
- SSE + ClarificationSlot — inchangés (clarifications entités conservées)
- Comportement sur issue : log en DB, pipeline continue

---

## Risques et points ouverts

- **Performance** : N appels LLM par scène (2-3 passes séquentielles) au lieu de 1 à la fin.
  Acceptable car local, et le M4 est rapide sur des petites requêtes ciblées.

- **Scalabilité du contexte** : injecter toute la DB dans chaque check pose un problème
  dès la scène 50-100 — le prompt explose, le Time to First Token aussi.
  **Solution : utiliser ChromaDB (bge-m3) pour retrieval sémantique avant chaque check.**
  Pour la scène en cours d'import, on requête ChromaDB avec ses personnages + lieu + era
  pour récupérer uniquement les scènes les plus susceptibles de créer une incohérence.
  On n'injecte que ce contexte pertinent, pas toute la DB.
  Exemple : scène dans "le dépôt de Neo-Santiago" avec Lena → seules les scènes
  impliquant Lena ou ce lieu sont injectées dans les passes.

- **Premier import** : si la DB est vide, les passes ne peuvent détecter que les
  incohérences internes à la scène elle-même.

- **Scènes liées dans un même batch** : la seconde scène voit la première en DB
  (déjà chargée) → cohérence inter-scènes du batch bien gérée naturellement.
