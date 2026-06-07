# Review — le prompting de Felix face à l'état de l'art

> 2026-06-06. Confronte le code actuel de Felix aux bonnes pratiques synthétisées dans
> [`prompting_best_practices.md`](prompting_best_practices.md).
> Contexte modèles : pipeline sur **Qwen 7B (Together)**, checker sur **Mistral Small**, chatbot sur **Ministral/OpenRouter** → on est en plein régime « petit modèle », donc *toutes* les conclusions sur les 7B/8B s'appliquent directement.

---

## Verdict en une phrase

Felix est **déjà un système neuro-symbolique bien décomposé** (force majeure et conforme à l'état de l'art), mais son prompting reste **majoritairement à base de règles abstraites et d'instructions négatives** — exactement le style que la littérature juge le plus fragile pour un 7B. Le few-shot, que ta propre doctrine pose comme prioritaire, n'est appliqué que dans **2 prompts sur ~9**.

---

## Ce que Felix fait déjà très bien (aligné état de l'art)

### ✅ Décomposition de tâches (principe n°4)
Le pipeline est franchement décomposé : `clean → analyze → resolve → write → profile → check`, et l'analyse elle-même **scinde méta et personnages en deux agents lancés en parallèle** (`analyzer.py:99-105`, `asyncio.gather`). C'est *exactement* la recommandation « une tâche par appel » qui réduit l'hallucination sur petit modèle — et qui ouvre la porte au remplacement d'étapes par du symbolique.

### ✅ Pas de CoT interne libre (principe n°3)
Felix ne demande jamais au 7B de « raisonner à voix haute » en texte libre : il s'appuie sur des sorties structurées et des étapes externes. C'est le bon réflexe, puisque le CoT libre *dégrade* les modèles < 10B.

### ✅ Sorties structurées + validation (principe n°5)
`output_type` pydantic-ai partout, `temperature` à 0.0–0.1, et un `output_validator` qui lève `ModelRetry` (`analyzer.py:90-94`, « au moins un personnage »). Format fiable par construction.

### ✅ Couche symbolique post-extraction (principe n°7 — « better later than sooner »)
C'est l'alignement le plus remarquable. Felix fait *déjà* ce que recommande OAK+MEND : laisser le LLM extraire, puis **valider/corriger en dehors du prompt** via le graphe — `check_duplicate_characters` (fuzzy), paires de contradictions par mots-clés (`{blonde}/{dark}`, `{ally}/{enemy}`…), résolution d'entités à seuils (0.85 / 0.60), blocage sur prénom différent. La rigueur vit dans le graphe, pas (seulement) dans le prompt.

### ✅ Structure de prompt (principe n°9)
Rôles explicites (« You are a specialized assistant… », « You are Felix… »), sections nommées (`RULES:`, `HOW TO ANSWER:`, `EXAMPLE:`), un exemple travaillé dans le chat agent. Bon socle.

### ✅ Évaluateurs majoritairement déterministes (principe n°8)
Les evals pipeline reposent surtout sur des évaluateurs **symboliques** (`character_ids_present`, `*_contains_keyword`, `min_relations_count`…) — plus stables qu'un LLM-juge. Excellent par défaut.

---

## Les écarts à corriger (par ordre de priorité)

### 🔴 P1 — Few-shot absent là où il compte le plus (principes n°2 et n°7)

**Constat.** Le few-shot n'existe que dans `BEAT_EXTRACTOR_PROMPT` (1 exemple) et `RELATION_DEDUP_PROMPT` (5 exemples). **`PROFILER_PROMPT` et `PROFILER_PATCH_PROMPT` sont 100 % règles abstraites** (`profiler.py:17-42`) — or c'est *précisément* le maillon où ton diagnostic LOTR a identifié la **contamination inter-personnages** (âge de Bilbo attribué à Pippin). La règle « Every field describes THIS character only » est une *instruction abstraite*, exactement ce qu'un 7B suit mal.

Idem pour `analyzer.py` (META/CHARACTER) et `checker.py` : zéro exemple.

**Pourquoi ça compte.** La littérature *et* ta propre mémoire (`feedback_prompt_engineering`) convergent : sur 7B, **montrer** bat **dire**. Le gain attendu est de l'ordre de +10 pts.

**Action (TDD, eval d'abord — cf. ta doctrine `feedback_tdd_evals`).**
1. Écrire/confirmer une eval qui *échoue* sur la contamination (un cas où deux personnages cohabitent et l'attribut de l'un fuite chez l'autre).
2. Ajouter 1–2 exemples few-shot de **non-attribution** dans `PROFILER_PATCH_PROMPT`, couvrant `age/physical/traits/relations` (pas seulement `arc/background`), avec des personnages **fictifs hors-eval et hors-LOTR** (cf. liste de noms autorisés : Haruki, Nadia, Oleg, Priya…).
3. Vérifier que l'eval passe *et* qu'un cas de généralisation (autre paire) passe aussi.

### 🔴 P2 — Risque d'eval circulaire dans `RELATION_DEDUP_PROMPT` (principes n°2 et n°8)

**Constat.** L'exemple #4 du prompt (`profiler.py:106-108`) est :
```
Existing: "companion"  /  Candidate: "travel companion"  → merge
```
C'est **mot pour mot** le cas d'échec décrit dans ta mémoire `project_lotr_import_issues` (« companion » vs « travel companion » ≈ 75 fuzzy, les dupes passent). Les exemples de ce prompt sont aussi très « quête/companion/war council » — la sémantique exacte du **boss final LOTR**.

**Pourquoi ça compte.** Ta règle (`feedback_prompt_engineering`) est explicite : *jamais d'exemples reproduisant un cas d'eval*, sinon l'eval devient circulaire — elle passera toujours sans rien prouver sur la généralisation.

**Action.** Reformuler les 5 exemples de `RELATION_DEDUP_PROMPT` avec des bonds **et un vocabulaire** totalement déconnectés du cast/des thèmes LOTR et des scénarios d'eval (éviter « quest », « companion », « war council », « Northern Wastes »). Garder la structure (elle est excellente), changer la matière.

### 🟠 P3 — Instructions négatives massives dans le checker (principe n°6)

**Constat.** `CHECKER_TIMELINE_PROMPT` / `CHECKER_NARRATIVE_PROMPT` / `ENTITY_CHECK_PROMPT` reposent sur de longues listes **« DO NOT REPORT … »** + « Detect ONLY … ». `analyzer.py` cumule « Invent NOTHING », « NEVER invent », « Exclude momentary states ». C'est le **pink elephant problem** : pour ne pas signaler les homonymes de famille, le modèle doit d'abord se les représenter.

**Pourquoi ça compte.** Sur petit modèle, le négatif augmente confusion et hallucination. Le positif (« always lowercase » > « don't uppercase ») est mesurablement supérieur.

**Action.**
- Convertir les « DO NOT REPORT X » en **définition positive du périmètre** (« Report exactly these two types: … ») + **2 exemples** : un cas à signaler, un cas piège à *ne pas* signaler (homonyme de famille, évolution normale d'entité). Le few-shot encode l'exclusion bien mieux qu'une règle négative.
- Reformuler « Invent NOTHING » en « Copy values verbatim from the text; use `null` when absent » (déjà à moitié fait — finir le virage positif).

### 🟠 P4 — Tension « schéma forcé vs raisonnement » dans le checker (principe n°5)

**Constat.** Les checkers font la tâche la plus *raisonnante* du pipeline (détecter une incohérence temporelle/narrative) **tout en** émettant directement un `ConsistencyReport` structuré. Or forcer le schéma trop tôt peut coûter jusqu'à 27 pts de raisonnement (le modèle « conclut avant d'avoir réfléchi »).

**Pourquoi ça compte.** C'est exactement le profil de tâche où la contrainte de format peut nuire — contrairement aux extractions pures (analyzer/profiler) où elle aide.

**Action (à valider par eval, pas à appliquer aveuglément).**
- Option A (peu invasive) : ajouter un champ `reasoning: str` **avant** la liste `issues` dans le schéma du checker (reason-first). Le modèle pose son analyse, puis remplit les issues.
- Option B : appel en deux temps (analyse libre courte → extraction structurée des issues).
- Mesurer recall/precision des issues avant/après sur la suite checker. Garder seulement si gain net.

### 🟡 P5 — Pousser davantage vers le symbolique (principe n°7)

**Constat.** Deux problèmes connus de ton diagnostic LOTR sont aujourd'hui traités (ou pas) côté LLM/prompt alors qu'ils sont **structurellement symboliques** :
- **Relations dupliquées** : un agent LLM (`relation_dedup_agent`) tranche merge/keep_both. OAK+MEND montre que la **redondance de prédicats** est mieux gérée par similarité d'embedding + règles que par appels LLM répétés (« 59 % du coût, +cohérence »).
- **Relations génériques** (« participant in the scene ») : c'est de la co-présence, filtrable par une **stoplist symbolique** déterministe — plus fiable qu'une règle de prompt qu'un 7B ignore.

**Action.**
- Ajouter un **pré-filtre symbolique** des relations de co-présence (stoplist : « participant », « present in scene », « appears with »…) *avant* l'appel LLM de dédup.
- Pour la dédup, tester un **tier embedding-similarity** (BAAI/bge-m3 est déjà là pour Chroma) en amont du LLM : merge auto au-dessus d'un seuil, LLM seulement sur la zone grise. Réduit coût *et* near-dupes.

### 🟡 P6 — Hygiène LLM-as-judge dans les evals (principe n°8)

**Constat.** Les commits récents introduisent un **Judge protocol** (LLM-juge) pour certains évaluateurs. Un juge unique sur petit modèle est statistiquement instable (corrélation fluctuant jusqu'à ~0,2).

**Action.**
- Garder les évaluateurs **déterministes en première intention** (déjà le cas — c'est bien).
- Pour les jugements vraiment sémantiques : **rubrique explicite** dans le prompt du juge + idéalement **panel** (2–3 juges, vote/moyenne), ou au minimum un modèle-juge plus fort que le modèle évalué.
- Ajouter un **garde-fou anti-circularité** (cf. P2) : un test/lint qui vérifie qu'aucun nom/cas d'eval n'apparaît dans les exemples de prompt.

---

## Tableau récapitulatif

| Principe (état de l'art) | État Felix | Action |
|---|---|---|
| Décomposition 1 tâche/appel | ✅ fort | — |
| Pas de CoT libre sur 7B | ✅ implicite | — |
| Sortie structurée + validation | ✅ fort | P4 (nuance checker) |
| Couche symbolique post-extraction | ✅ fort | P5 (aller plus loin) |
| Structure/rôles/sections | ✅ bon | délimiteurs plus nets (option) |
| Évaluateurs déterministes | ✅ bon | P6 (hygiène LLM-juge) |
| **Few-shot > règles abstraites** | ⚠️ 2 prompts / 9 | **P1** |
| **Pas d'exemples = cas d'eval** | ❌ violé (dedup) | **P2** |
| **Formuler en positif** | ⚠️ beaucoup de « DO NOT » | P3 |
| Reason-first si raisonnement | ⚠️ checker forcé | P4 |

---

## Ordre d'attaque suggéré (eval-first, conforme à ta doctrine TDD)

1. **P2** (rapide, et c'est une violation de ta propre règle d'or sur les evals) — reformuler les exemples de dédup.
2. **P1** (le plus gros gain qualité) — few-shot de non-attribution dans le profiler, eval de contamination d'abord.
3. **P5** (s'attaque aux dupes/relations génériques à la racine, côté symbolique).
4. **P3** puis **P4** (reformulation positive + reason-first, à valider par eval).
5. **P6** (hygiène evals + garde-fou anti-circularité, transversal).

> Tous ces changements sont à mener avec une eval *qui échoue d'abord*, puis le fix — et à ne conserver que s'ils améliorent le baseline (24–25/34 sur la suite unifiée d'après la mémoire).
