# Journal de developpement — Felix

## Front : page « atelier » (le bot B) portée React→Vue — 2026-06-07

Première brique UI de B : le **chat** du design Claude Design, porté du proto **React (CDN+Babel)** vers **Nuxt 4 / Vue 3**. Décision produit : on **refait une page neuve** plutôt que re-skinner l'existant ; l'app cyan reste comme **référence vivante** (rien jeté). Route dédiée **`/atelier`** (`layout: false`), isolée du thème cyan.

**Stratégie CSS = hybride (choix retenu)** : tokens papier de `felix.css` exposés à Tailwind 4 via `@theme` (`web/app/assets/css/felix-atelier.css`, importé dans `main.css`) — noms neufs `--color-paper/-gold/-terra/-sage…`, **additifs**, n'altèrent pas le thème « Felix Cyan ». Composants signature reconstruits à la main ; styles scopés sous `.felix-atelier` (valeurs littérales → indépendants du cyan). Polices Newsreader/Hanken Grotesk/IBM Plex Mono via `@nuxt/fonts`.

**Fichiers** : `app/pages/atelier.vue`, `app/components/AtelierMessage.vue`, `app/components/AtelierIcon.vue` (icônes SVG inline portées), `app/types/atelier.ts`. Édits : `main.css` (+1 import), `nuxt.config.ts` (+ fonts). Le **modèle de message** porte la spec B telle quelle : `text / tool (fiche maj) / choice (posture Intervieweur) / cite (traçabilité) / alert (incohérence + résolution, auteur souverain)`.

**État** : données **scriptées** côté front (seed *Rivière basse* + réponses simulées), **pas encore câblé au vrai bot** (tool-calls réels + checker) — naturel vu que le back est en cours. **Vérifié** : eslint clean, dev boote, **build prod OK** (`atelier.css` émis, polices téléchargées), app cyan intacte. À voir : `cd web && pnpm dev` → http://localhost:3007/atelier.

**Prochain pas** : câbler `/atelier` au backend (remplacer seed/canned par appels API + tool-calls d'écriture du graphe + checker à chaque écriture), puis la fiche personnage.

## Design system UI ajouté (handoff Claude Design) — 2026-06-07

Bundle de design pour l'UI de B récupéré depuis un lien claude.ai/design (servi en tar.gz) et versionné dans `resources/design-system/`. Thème **« atelier d'écriture »** papier/chaleureux, primaire or ; **couleurs sémantiques qui encodent la cohérence** (terracotta = incohérence, sage = validé) — alignement direct avec le concept de B. Directive forte : **aucun vocabulaire « graphe »** dans l'UI. Contient maquettes HTML, composants JSX, `felix.css` (système partagé), screenshots et le transcript de design (`chats/chat1.md` = l'intention). Rien implémenté — référence pour le futur chantier UI de B (cf. `memory` reference_design_system).

## Bascule pipeline + chatbot → Mistral Small (stack unifiée) — 2026-06-07

Décision prise (FR/RGPD + la parallélisation via API gérée, point soulevé par Felix, est un vrai gain de débit vs un seul modèle local sur le M4). **Acté** : `.env` `FLX_LLM_MODEL=mistral-small-latest`, `FLX_LLM_BASE_URL` vidé → routing `MistralModel` natif. Pipeline d'ingest + checker unifiés sur Mistral. Phi-4 14B gardé en réserve (futur 100 % local/offline ou produit A). Ancien : `Qwen/Qwen2.5-7B-Instruct-Turbo` + Together (pour rollback).

**Validation eval (eval-first)** : **52/86 (60 %) vs 34/86 (40 %)** avec le Qwen 7B. **+18 cas**, et **158 s vs 423 s** (~2,7× plus rapide), $0.0074, **zéro crash grammar**.
- *pipeline* **29/39 (74 % vs 34 %)** : `char_id_recall` 0.05→**1.00**, `date_score` 0.50→**1.00**, `bg_score` 0.00→0.39, `relations` 0.90. Mistral extrait les noms complets, ORACLE, **6 groupes**, et les persos long_mission (segmentation OK).
- *ingest* **7/7 (100 %)**.
- *chatbot* d'abord 16/26 (OpenRouter), **puis basculé lui aussi sur Mistral natif → 17/26 (68 %)** : léger gain, zéro régression, 18 s.

**Stack désormais 100 % Mistral natif** (`mistral-small-latest` pour pipeline + checker + chatbot + judge d'eval) — un seul provider, une seule clé (`FLX_LLM_API_KEY`), RGPD/EU. OpenRouter & Together ne servent plus à l'inférence (clés conservées mais inutilisées — nettoyage optionnel). Total evals unifié ≈ **53/86**.

**Fails restants ≠ modèle** (le modèle est désormais bon) :
1. `group_id_recall` 0.00 = **FAUX NÉGATIF d'eval** : groupe extrait `the-sentinels` mais l'expected est `sentinel` (intersection de sets *exacte*). Mistral sort 6 groupes corrects. → assouplir `group_ids_present` (substring) ou corriger les `expected`. Quick win.
2. `bg_score` 0.39 = profiling partiel → chantier profiler/prompt (few-shot, cf. `docs/` prompting).

Conclusion : **décision Mistral validée sur données**. Le « vrai » niveau de qualité d'extraction est au-dessus de 60 % (plusieurs fails sont des tests rigides). Prochains pas : (1) assouplir les evals à match exact, (2) creuser `bg_score`.

## Recherche modèles M4 + finding grammar — 2026-06-07

Recherche web approfondie (deep-research, 101 agents, 19 sources, 17 claims vérifiés 3-vote) : « quel petit modèle fiable en structured-output tourne sur Mac M4 ? ». Rapport complet archivé (le workflow `deep-research` a été sauvé dans `.claude/workflows/`).

**Réponses clés** :
1. **Le palier ~24B n'est PAS le minimum.** **Phi-4 14B** est le producteur JSON le plus fiable de la seule étude head-to-head (100 % parseabilité), devant Qwen3-14B (98.1 %), Qwen3-4B, Llama-3.x, Mistral-8B. Classement pour notre cas : (1) **Phi-4 14B** (~8-9 Go Q4, 24-32 Go RAM), (2) **Mistral Small 3.x 24B** (meilleur IFEval 82.9, ~15 Go Q4, 32 Go), (3) **Granite 3.3/4.1 8B** (bon tool-calling, 128K ctx, 16 Go, IF plus faible), (4) **Qwen3-14B**. Spécialiste : **NuExtract 3.8B** (texte→JSON pur).
2. **META-FINDING (high, 3-0)** : le crash `failed to compile grammar` est probablement un **bug du compilateur json_schema→grammar** (Ollama/llama.cpp #8444/#21228, et vraisemblablement Together), déclenché par les schémas **`$defs`/`$ref`** que pydantic-ai émet — pas une déficience du modèle. **Vérifié sur notre code** : `list[ExtractedCharacter]` génère bien `$defs`+`$ref`. → 2 remèdes à tester : **aplatir le schéma Pydantic** (inline $defs/$ref) OU changer de runtime (MLX). Changer juste de modèle sur la même stack pourrait ne pas suffire à tuer le crash (mais réglerait la variance/qualité).
3. **BFCL/IFEval ne prédisent PAS la discipline de format** (aucun modèle >80 % sur IFEval-FC). → **valider tout candidat sur NOTRE schéma**, pas par rang de leaderboard.
4. RAM M4 : 16 Go→7-8B, 32 Go→14-32B, 64 Go→70B. Format conseillé Apple Silicon : MLX 4/8-bit ou GGUF Q4_K_M.

**Caveats** : preuve dominante = 1 étude (domaine clinique, parseabilité syntaxique ≠ validation Pydantic stricte, greedy decoding). Pas de benchmark direct sur extraction texte→graphe. Attention aux guides AI-générés avec modèles hallucinés (« Qwen 3.6-27B » n'existe pas) — vérifier les IDs sur HF/Ollama.

**Prochain pas (eval-first)** : (a) test rapide « schéma aplati » pour isoler infra vs modèle sur le crash ; (b) si on va local, valider Phi-4 14B (et Qwen3-14B) sur la scène forge comme on l'a fait pour Mistral ; (c) à défaut, bascule Mistral Small (déjà dans la stack, API native sans bug grammar).

## Investigation régression evals — cause racine = Qwen 7B non fiable — 2026-06-07

Investigation du pré-requis bloquant (evals tombées de 70 % → 40 %). **Diagnostic confirmé, le code Felix est sain — c'est le modèle.**

**Méthode** — pas besoin d'instrumenter : protest archive déjà chaque cas en `.protest/results/<suite>_<ts>/<cas>.md` (Input / Output / Expected / Scores). Relecture de ces fichiers + benchmark direct multi-modèles sur `evals/fixtures/unified/01_the_forge.txt` (qui contient bien « Borin Ironfist », « Elara Nightshade », « the Sentinels », ORACLE).

**Findings** :
1. **Cause racine = le couple `Qwen2.5-7B + structured-output` est non fiable.** Deux appels identiques dos à dos : l'un passe (mais rate le groupe Sentinels), l'autre **crashe** `422 failed to compile grammar` côté Together. Intermittence + forte variance (tantôt `borin-ironfist`, tantôt `borin`). Pour une brique de fondation, c'est éliminatoire indépendamment du score.
2. **La stack pydantic-ai 1.68 est saine** : avec exactement le même code/prompt/schéma, **Mistral Small 24B** extrait sans faute — noms complets, groupes, ORACLE, 11 persos. Donc ni le code, ni pydantic-ai en cause.
3. **Cascade d'ID** : `character_ids_present` fait une intersection *exacte* de sets, et les lookups aval (`profile:borin-ironfist`, `scene_date:…`, `relations:…`) interrogent le graphe **par l'ID canonique**. Un ID raté (`borin` au lieu de `borin-ironfist`) → lookup `None` → `bg_score`/`date_score` à **0 net**. Les zéros ne sont pas une perte de profiling, c'est qu'on interroge un ID inexistant.
4. **Palier de fiabilité ≈ 24B** : Mistral Small 24B et Llama-3.3-70B passent proprement et à l'identique ; les petits (Llama-3.1-8B, Gemma-2-9B) ne sont même pas servis correctement par Together serverless.
5. Facteur secondaire : les evals à **match exact d'ID** amplifient la chute (un `borin` sémantiquement correct échoue quand même) — à assouplir.

**Décision en cours** : recherche web (deep-research) des petits modèles fiables en structured-output tournant sur Mac M4 ; **à défaut, bascule sur Mistral Small** (déjà dans la stack checker+chatbot, API native sans bug grammar, RGPD). Scripts d'investigation jetables dans `/tmp` (non versionnés).

## Réflexion produit — pivot envisagé puis recadré — 2026-06-07

Discussion stratégique partie d'un constat (« les résultats ne sont pas là ») et d'une envie de recentrer le projet. Deux produits ont émergé :

- **A — Moteur d'extraction texte→graphe *fiable* (générique, API).** Le cœur de Felix (extraction + résolution d'entités + cohérence) est réutilisable hors scénario. Angle marché vérifié : l'extraction LLM→graphe se commoditise (GraphRAG, Neo4j LLM KG Builder), mais sa **fiabilité** non — c'est le moat. Vision documentée dans `docs/vision_produit_moteur_extraction.md` (niveau produit, pas de code). **Parkée comme option.**
- **B — Copilote scénario conversationnel (PRIORITAIRE).** Le but réel reste d'aider Felix avec son scénario. Un chatbot qui **construit le world model au fil de la parole** : l'auteur décrit, le bot mute le graphe via tool-calls (lecture-seule → lecture+écriture), relance (posture **Intervieweur**), et **vérifie la cohérence à chaque écriture**. Vision + design d'interaction capturés dans `docs/vision_produit_copilote_scenario.md`. Décisions de design verrouillées cette session :
  - **L'auteur est souverain** : sur op risquée (fusion/contradiction/suppression) le bot demande « t'es sûr ? » ; si oui **on obéit toujours + on lève une issue** (« tension assumée »), sinon on discute. Une contradiction est une *information*, pas une erreur.
  - **Commit hybride selon le risque** (direct pour le simple, confirmation pour le risqué). Entrée **chat + coller une scène**.
  - **Modèle de faits état vs événement** : relation d'état (frère de) = sans date ; événement (épouse, meurt, prend un objet) = daté/localisé → pilote les relances ET les checks temporels. **Ontologie hybride** : petit catalogue d'événements-clés (cases date/lieu/participants) + jugement LLM pour le reste.
  - **Schéma à étendre** : objets/artefacts, relations libres (non ancrées à une scène), notion de « contexte courant » — = la généralisation de A, d'où « les deux s'entraident ».

Aucun code modifié. Lien avec l'infra : A comme B reposent sur le cœur actuel (resolver/checker/extracteur) — la régression evals (40 %) est donc un **pré-requis bloquant** à investiguer avant tout build produit.

## État après la grande pause — reprise infra — 2026-06-07

Reprise du projet après ~2 mois d'inactivité (dernier commit de fond le **31/03**, dernière activité fichiers ~1er mai). Objectif de la reprise : **remettre l'infra de test/eval d'aplomb** avant de toucher au produit. Trois chantiers étaient gelés à mi-chemin, non commités, et s'étaient empilés.

### Ce qui a été remis d'aplomb

1. **Migration tests pytest → protest : finalisée et commitée** (`354bf0b`, cf. entrée dédiée plus bas). Le repo était **incohérent à froid** : `tests/session.py` (committé) importait une arbo `tests/unit` + `tests/integration` + `tests/fixtures.py` jamais trackée, pendant que les 8 anciens `test_*.py` plats + `conftest.py` (pytest) traînaient en doublon. Tout marchait *uniquement* parce que les fichiers existaient sur le disque local.

2. **Evals réparées** — elles ne démarraient plus (`ImportError`). L'API evals de protest a été **réorganisée** dans la 0.2.0 « livrée » (les evals sont passées **dans le core**, l'extra `[evals]` a disparu). Adaptation de `evals/session.py` :
   - `ModelInfo` → **`ModelLabel`** (gagne un champ `.provider`)
   - `EvalSession` **supprimé** → **`ProTestSession`** : moteur de session **unifié** tests + evals (le CLI `protest eval` charge une `ProTestSession`)
   - le **judge + le modèle** migrent de la session globale vers **chaque `EvalSuite`** (`EvalSuite("pipeline", model=…, judge=…)`)
   - `FelixJudge` était déjà conforme au protocole `Judge` (`async def judge(prompt, output_type) -> JudgeResponse`) — rien à changer.

3. **Dépendance `protest` : editable local → source git.** Passée de `{ path = "../protest", editable = true }` à `{ git = "ssh://git@github.com/renaudcepre/protest.git", tag = "protest-v0.2.0" }`. Le tag pointe sur `4b1f03b` = exactement le HEAD de la copie editable testée (**iso-code**, poussé sur `origin`). `pyproject` : `protest[evals]` → `protest`. `uv.lock` régénéré (`protest v0.2.0 (4b1f03b4)`), `uv sync` confirme l'install depuis git (plus d'« Editable project location »).

### État de santé (Python 3.14, protest 0.2.0 git, pydantic-ai 1.68)

- **Tests : 145/145 ✅** (~11-13s avec Neo4j ; 62 sans Neo4j en ~3s).
- **Evals : 34/86 (40 %)** — `-n 4`, ~423s, **$0.0076**. **Régression nette vs baseline 70 %** (60/86 au 30/03).
  - *pipeline* 12/35 : `relations_score` 1.00 et `char_extraction` OK, **mais** `bg_score` **0.00**, `group_id_recall` **0.00**, `char_id_recall` **0.05**, `date_score` 0.50.
  - *ingest* 6/8 : `char_extraction` 1.00, **`role_accuracy` 0.00**.
  - *chatbot* 16/26 : `facts_score` 0.43.
  - **Hypothèse** : ce n'est probablement **pas** une dégradation de modèle (scores à *zéro net*, pas du bruit). Le pipeline **extrait** bien les personnages mais leurs **IDs / groupes / backgrounds ne matchent plus les attendus**. Causes candidates : dérive du Qwen 2.5-7B servi par Together en 2 mois, et/ou changement de format de sortie avec pydantic-ai 1.68 / Python 3.14. Le code `felix/` n'a **pas** changé. À investiguer **eval-first**.

### Chantier « infra 3.14/evals » — non commité, sain, committable

Reste hors du commit `354bf0b` (volontairement séparé) :
- `pyproject.toml` : `requires-python >=3.14`, `torch>=2.10`, `protest` en git, `protest[evals]`→`protest`
- `uv.lock` régénéré · `evals/session.py` (fix API) · `evals/pipeline/task.py` (séparateur profil `|`→`—`, affichage des erreurs pipeline)

Nettoyages connus à faire au passage : warnings `pydantic-ai[logfire,mistral]` (extras périmés en 1.68) ; import mort `contains_expected_facts` dans `evals/session.py` (les evaluators sont attachés au niveau dataset) ; commentaire ruff `S101` « (pytest) ». Untracked à trancher : `data/scenes/education_canine_pour_auriane.md.pdf`.

### Feuille de route à la reprise

1. **Committer le chantier infra** (sécuriser) + nettoyages ci-dessus.
2. **Investiguer la régression evals** (scores à 0) — déboguer un import réel vs IDs attendus, eval-first.
3. **Prompting** (cf. entrée « Recherche & review prompting » + rapports `docs/`) : P1 few-shot non-attribution `profiler.py`, etc. — converge avec l'investigation evals.
4. **Produit** : couche **Notes / Idées**, next step naturel identifié au 25/03.

## Recherche & review prompting (état de l'art vs code) — 2026-06-06

Recherche web sur les bonnes pratiques de prompting — focus **petits modèles (7B/8B)**, **neuro-symbolique** et évaluation — puis review du code Felix. Deux rapports écrits dans `docs/` : `prompting_best_practices.md` (synthèse + sources) et `felix_prompting_review.md` (review priorisée P1→P6).

**Constat principal** : Felix est déjà un système neuro-symbolique bien décomposé (force, conforme état de l'art : pipeline découpé, pas de CoT libre, sortie structurée, vérifs symboliques post-extraction). Mais le prompting reste majoritairement **règles abstraites + instructions négatives** — le style le plus fragile pour un 7B. Le few-shot (doctrine maison) n'est appliqué que dans 2 prompts sur ~9.

**Actions identifiées (eval-first)** : P1 few-shot de non-attribution dans `profiler.py` (le maillon de la contamination LOTR, toujours 100 % abstrait) ; P2 corriger une **eval circulaire** — l'exemple #4 de `RELATION_DEDUP_PROMPT` ("companion" vs "travel companion" → merge) reproduit le cas d'échec LOTR ; P3 passer les "DO NOT REPORT" du checker en formulation positive + few-shot ; P4 reason-first dans le checker (schéma forcé ↔ tâche raisonnante) ; P5 dédup/relations génériques côté symbolique (stoplist + embedding-similarity) ; P6 hygiène LLM-as-judge (panel/rubrique, garde-fou anti-circularité). Aucun code modifié — recherche/review seulement.

## Finalisation migration tests pytest → protest (commit) — 2026-06-06

Reprise après ~5 semaines de pause. La migration des tests unitaires (cf. `JOURNAL_UNIT_PROTEST.md`, fin mars) était **écrite et fonctionnelle mais jamais commitée** : `tests/session.py` (committé) importait `tests.unit.*` / `tests.integration.*` / `tests.fixtures` qui n'étaient pas trackés, et les 8 anciens `test_*.py` plats + `conftest.py` (pytest) traînaient encore en double.

Validation avant commit : **145/145 tests passent** sous **protest 0.2.0** + **Python 3.14** (62 sans Neo4j en 3.6s, 145 complets en 20.6s). L'API de tests protest est restée rétro-compatible malgré le passage de protest 0.x → 0.2.0 (les evals ont été « livrées » dans le core, l'extra `[evals]` n'existe plus).

Nettoyage : `git add` de la nouvelle arbo `unit/`+`integration/`+`fixtures.py`, `git rm` des doublons pytest, `.protest/` + `.DS_Store` ajoutés au `.gitignore`. Chantier Python 3.14 / torch (pyproject + uv.lock + refonte API evals dans `evals/session.py`) **laissé hors de ce commit** — à committer séparément.

## Vision produit — discussion avec Felix (scenariste) — 2026-03-25

Trois couches distinctes émergent :

1. **World Model** (existant) — graphe de connaissances, source de vérité sur l'univers
   du scénario
2. **Notes / Idées** (à construire) — espace de réflexion non validé, croisable entre
   notes et avec le world model
3. **Écriture** (futur) — rédaction du scénario lui-même, exercice distinct de "décrire
   le monde"

**Concept d'arène** : notion plus riche que "location" — contexte thématique et
spatial (ex: "la piraterie" comme arène avec ses codes et personnages-types). A
modéliser quand on sera prêt.

Priorités : notes = next step naturel (low effort, high value). Écriture assistée = plan
long terme.

## Migration complète protest + scoring v2 — 2026-03-28/30

**Plus de pytest.** Tout tourne sur protest : `just test` = `protest run`, `just evals` = `protest eval`. pytest, pytest-asyncio et pytest-cov supprimés des deps.

**API protest-native** — 3 migrations successives :
1. `ProTestSession` → `EvalSession`, `add_eval_suite` → `add_suite`
2. `EvalSuite` → `ForEach` + `@session.eval()` — les evals sont des tests paramétrisés
3. Scoring v2 : evaluators retournent des dataclasses avec `Annotated[float, Metric]`, `Annotated[bool, Verdict]`, `Annotated[str, Reason]`. Les simples retournent `bool`. Plus de `dict` retour.

**Fixtures DI** pour les 3 suites — `@fixture` + `Use()`, plus de global state. `console.print` de protest pour le progress pendant l'import pipeline.

**Config multi-modèle** : Qwen 7B Together pour le pipeline, Mistral Small pour le checker (API directe, RGPD) et le chatbot (OpenRouter). Settings panel frontend simplifié en lecture seule.

**LLMJudge** protest-natif — remplace `pydantic_evals.LLMJudge`. Async, utilise Mistral Small.

86 cas total (39 pipeline, 21 ingest, 26 chatbot). Baseline : 60/86 (70%), `-n 4`, ~210s.

## Refonte evals — consolidation + checks graph-based — 2026-03-26/27

Consolidation de 6 suites pipeline en 1 (scénario Thornwall Keep + long_mission pour segmentation). Écriture du scénario unified avec intrigue polar (qui est le traître ? → ORACLE via Second Eye). Checks graph-based post-import (doublons, contradictions physiques, relations contradictoires) remplacent les checkers LLM inline. 5 cas entity-check ajoutés.

Prompts simplifiés pour compatibilité multi-modèle (÷3 en taille). Scores : Qwen 26/34, Ministral 25/34, Haiku 24/34.

## Benchmark modèles via OpenRouter — 2026-03-25

Test de Claude Haiku et Sonnet via OpenRouter (`--openrouter`). Sonnet à ~2€ pour un full run d'evals — ingérable en coût récurrent.

Résultats surprenants : **Sonnet ne bat pas le Qwen 7B** sur la plupart des suites pipeline. Le 7B est meilleur sur profiler-attribution (84% vs 53%) et segmentation (89% vs 72%). Sonnet gagne sur chatbot (73% vs 65%) grâce à un meilleur raisonnement multi-hop. Qwen3 235B via Together reste le meilleur rapport qualité/prix (87% pipeline, 96% convoi).

Conclusion : les prompts sont optimisés pour le 7B. Un modèle plus gros n'apporte pas de gain automatique sans adapter les prompts. Le 7B Together reste le default.

## Passage full anglais — 2026-03-25

Traduction de tout le contenu FR → EN : 23 scènes (data + fixtures), seed data (graph +
vectorstore), messages UI, expected values des evals, termes éphémères physiques. Motivé
par le franglais (profils EN vs scènes FR) qui cassait le consistency checker et rendait
les evals fragiles.

Scores post-traduction : 168/199 pipeline (+11 grâce aux keywords corrigés). Groups
11/11 (100%).

## Page Groupes (frontend + API) — 2026-03-25

5 endpoints API (list, create, detail, add/remove member). Frontend : liste, création,
page détail avec gestion des membres. `find_character` enrichi pour retourner les
groupes d'appartenance au chatbot.

## Consistency checker profil — 2026-03-23/25

Bouton "Vérifier" pour checker les modifications de profil contre les scènes. Approche
hybride : pré-matching textuel (n-grammes) + LLM pour les cas sans evidence.

Itérations successives :

- Diff only (ne checker que ce qui a changé, pas tout le profil)
- Suppression de `missing_evidence` — seules les contradictions comptent (le scénariste
  peut ajouter ce qu'il veut)
- `character_name` dans le payload pour éviter la confusion entre personnages
- Limites du 7B : flag des non-contradictions malgré le prompt. Dépend du passage full
  anglais pour fonctionner correctement.

## Seuil bas dedup relations — 2026-03-25

Score fuzzy < 30 → `keep_both` direct sans LLM ni clarification. "messagère" vs "
Tisserand of the Vermeil Order" (score 15) ne pose plus la question.

## Code review + refactoring — 2026-03-23

**Repository split** : `repository.py` (1021 lignes) découpé en 7 modules domaine dans
`graph/repositories/`.

**TypedDict** : 20 types pour les retours repository, `cast()` no-op runtime, zéro coût.

**Pipeline refactor** : `run_import_pipeline` décomposé en 5 sous-fonctions.
`_PipelineContext` enrichi avec `model_name`/`base_url`/`enrich_profiles` pour
simplifier les signatures.

**Quick wins** : `datetime.now(UTC)`, `Literal` pour ConsistencyIssue, embedding model
unifié, `normalize()` centralisée, `build_model` dans `llm.py`, fonctions publiques dans
`resolution.py`.

## Expansion evals + tags — 2026-03-23

+70 cas de test (129 → 199). Système de tags cross-suites (`--tag dates`,
`--tag profiling`).

## Groups/Factions — 2026-03-20

Nœud `:Group` + `MEMBER_OF`. Les collectifs (drones, pillards) sont distincts des
personnages individuels. `character_type: Literal["individual", "group"]` dans
l'extraction.

## Narrative beats pour attribution — 2026-03-18.

Extraction `subject → action → object` par scène, puis filtrage par personnage avant le
profiler. Résout les erreurs d'attribution flaky avec le 7B.

## Décomposition pipeline.py — 2026-03-19

`pipeline.py` (903 lignes) séparé en `resolution.py`, `orchestrator.py`, `pipeline.py`.
Responsabilités claires.

## Dedup relations : fuzzy + LLM + clarification — 2026-03-19/21

Pipeline 3 étages : ≥90 auto-merge, [55-90) LLM, <55 keep_both. Ajout "unsure" →
clarification utilisateur.

## Segmentation narrative — 2026-03-17

Découpage sémantique en chunks overlappants pour les fichiers longs. Liaison
`NEXT_CHUNK` dans le graphe. Idempotence re-import.

## Migration Neo4j — 2026-03-17

SQLite + Kuzu → Neo4j comme store unique. Cypher partout, async natif. Docker-compose
avec volume persistant.

## Pipeline incrémental — 2026-03-15

Check + profiling après chaque scène (plus en batch). Issues écrites en DB
immédiatement.

## Refonte evals — 2026-03-15

Exécution parallèle, Together AI comme provider cloud, 3 suites (
pipeline/ingest/chatbot), CLI unifiée. `LLMJudge` pour les cas causaux,
`RefusesToFabricate` pour les négatifs.

## Phase 0 — POC CLI — 2026-03-14

pydantic-ai + Mistral Nemo 12B + SQLite + ChromaDB. Validation que le modèle appelle les
tools correctement. Pattern `find_character` en 1 appel (le 12B ne suivait pas list→get
en 2 étapes). Support modèles locaux via LMStudio.

Leçons : le mix FR/EN dans les prompts est trop ambigu pour les petits modèles.
`TYPE_CHECKING` incompatible avec l'introspection runtime de pydantic-ai.
