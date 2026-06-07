# Journal de developpement — Felix

## Sélecteur de profil dans l'UI + preuve du schéma émergent sans instruction — 2026-06-07

Pour *tester* la claim centrale (« sans instruction de domaine, le modèle suit-il une structure ? ») directement à l'écran, on ajoute un **sélecteur de profil** dans la topbar de `/atelier` : **Scénario / Chantier / Aucun (noyau nu)**. Le mode « Aucun » fait tourner `create_core_agent()` sans profil ni persona de domaine — il garde seulement les tools + la discipline schemaless (`SYSTEM_PROMPT`), qui est le *moteur*, pas une instruction de domaine. Un 2ᵉ profil concret (`CHANTIER_PROFILE`, gestion de travaux) est ajouté pour que le sélecteur démontre le multi-domaine, pas juste avec/sans.

- **Backend** : registre `AgentChoice` (clé/label/profil/persona) dans `atelier/agent.py` ; agents pré-construits par profil (`app.state.atelier_agents`, `AtelierAgentsDep`) ; `ChatRequest.profile` ; `GET /api/atelier/profiles` ; la route `/chat` résout le profil par requête (deps **et** `consistency_check` utilisent `choice.profile`). `create_atelier_agent()` garde sa signature (défaut scénario) pour les evals.
- **Front** : sélecteur câblé (`useAtelier.profile/profiles/setProfile`) ; changer de mode repart d'une conversation neuve (l'historique d'un agent — tools/prompt — n'est pas interchangeable).
- **Décision assumée** : le mode « Aucun » garde une persona *neutre, sans contenu de domaine* (« tiens une base, consulte-la avant de répondre ») pour rester utilisable (relecture), sinon le test paraîtrait pire qu'il n'est.

**Preuve live (smoke SSE, mode `none`, domaine inconnu des profils = des plantes)** : tour 1 → crée `Monstera` **type `plante`** `{date_achat:'mars 2024', exposition:'mi-ombre'}` ; tour 2 → crée `Ficus` en **réutilisant le même type ET les mêmes clés**. Donc **le schéma émergent ne dépend pas du profil** : la discipline vient du noyau, le profil ne fait que canonicaliser/biaiser. Réponse empirique à la question : oui, sans instruction, il invente une structure cohérente et la tient.

**Vérif** : `just test` 145/145 · ruff sans nouvelle erreur (drift pré-existant seulement) · eslint clean · smoke SSE `GET /profiles` + `/chat` en modes `none` et `scenario`.

## Promotion du noyau générique + bascule du bot B sur le checker — 2026-06-07

Suite directe de l'expérience « generic-core » (validée 15/17, checks 6/6) : on **promeut le prototype** `evals/generic/proto.py` en package `src/felix/core/` et on fait **basculer le bot B (atelier) dessus**, checker de cohérence câblé à chaque écriture. Décisions actées : `:GenEntity` pur (aucun pont avec le vieux monde `:Character` — l'app cyan, l'ingest, le chatbot legacy restent intouchés, `era` meurt avec le nouveau monde) ; profil de domaine en **données Python** (`Profile`/`EntityType`, `frozen`, migrable plus tard vers un fichier de la couche auto-apprenante) ; pas de YAML, un seul profil câblé en dur. Mené en **5 commits, un par étape, vérif à chaque pas**.

- **Étape 1 — noyau `src/felix/core/`** (`deps`, `models`, `graph`, `tools`, `agent`, `check`, `profile`, `__init__`). Inversion de dépendance : `GenericDeps` devient la **classe racine**, `atelier/deps.py` et `models.py` la ré-exportent (compat des imports route/api). `touched_ids: set[str]` ajouté à `GenericDeps`, alimenté par les 3 tools d'écriture. Contrainte `genentity_id_unique` sur `:GenEntity`. Profil = 3 rendus (`render_prompt_block` ≤12 lignes pour le system prompt, `render_schema_hint` pour `describe_schema` sur base vide, `render_check_rules` pour le `CHECK_PROMPT` via placeholder `{domain_rules}`). **Garde-fou de non-régression vérifié au caractère près : `CHECK_PROMPT.format(domain_rules="")` est identique à `proto.CHECK_PROMPT`** → le check générique ne bouge pas tant qu'aucun profil n'est passé. 145/145 tests.
- **Étape 2 — `evals/generic` sur `felix.core`**, `proto.py` supprimé. **15/17, checks 6/6** — score identique à avant promotion (les 2 fails = variance Mistral Small). La promotion est neutre sur le noyau.
- **Étape 3 — bascule du bot B**. `create_atelier_agent() = create_core_agent(profile=SCENARIO_PROFILE, persona=<posture FR>)`. `atelier/tools.py` (`add_character`/`list_characters`) supprimé ; seed et lecture des evals atelier passent à `:GenEntity {entity_type:'personnage'}`, lecture **filtrée** sur `personnage` (un « lieu » créé en passant ne fausse plus `graph_char_count`). **Régression attrapée par le gate, et corrigée ici comme prévu** : le noyau a 5 tools mais ne sait pas *énumérer* (`find_entity` = une entité, `describe_schema` = types/comptes/clés **sans les noms**) → le cas `read_list` échouait (l'agent ne pouvait pas lister « Jean ET Camille »). Fix : **`list_entities`** (l'équivalent générique de l'ancien `list_characters`) ajouté au noyau mais **enregistré seulement pour l'agent atelier** — le noyau générique reste à 5 tools (expérience gelée), l'atelier en a 6. **8/8** (= la seule déviation au plan « 5 tools », assumée et documentée).
- **Étape 4 — checker câblé (route SSE + front)**. La route construit `GenericDeps(profile=SCENARIO_PROFILE)` ; après la boucle agent (ordre **tool/text → usage → history → alert? → done**), `consistency_check` sur chaque entité touchée, contradiction → event SSE `alert` `{kind, title:"Incohérence possible", body:reason, status:"open"}`. Bloc **best-effort** (try/except + `logger.exception`) : une panne du judge ne bloque jamais `done`. Front : `case 'alert'` dans `useAtelier` (le rendu terracotta `AtelierMessage` et les handlers resolve/status préexistaient). **Vérifié end-to-end (smoke SSE réel)** : contradiction spatiale Marseille/Lyon détectée, **règles du profil citées par le judge** (`render_check_rules` en prod), ordre `history < alert < done`.
- **Étape 5 — cas d'eval du checker** (suite atelier, 10 cas). `task.py` rejoue `consistency_check` quand le cas fournit `check` (champ `alert: dict|None`) ; seed généralisé (`_seed_entities`, accepte `entity_type`/`props`, compat `{name,background}`). Évaluateur `alert_emitted(expected)` (dataclass à champs uniques — piège protest). 2 cas : contradiction → alerte, fait additif → pas d'alerte. **10/10.**

**Observations honnêtes** :
1. **Le checker signale aussi l'écrasement destructeur d'une propriété.** Le 1er jet du cas « compatible » (déjeuner le 14 vs alibi le 12) a *échoué* : l'agent, par discipline de réutilisation de clés, a écrasé `alibi='…Marseille le 12'` par `alibi='déjeuner au Vesuvio le 14'` (un déjeuner n'est pas un alibi !). Le judge a alors **correctement** signalé un remplacement par valeur incompatible. Ce n'est pas un bug du checker — c'est le filet qui marche dans les deux sens (déjà noté à l'étape « échelle »). Le cas compatible utilise donc un ajout pur (un âge) ; le cas date-différente/même-lieu reste couvert côté generic.
2. **Variance Mistral Small confirmée, sans régression.** Sur du code agent **byte-identique** (diff `agent/check/graph` = 0 ligne depuis l'étape 2 ; `list_entities` non enregistré dans `create_core_agent`), `just evals-generic` a donné **15 → 13 → 14/17** sur trois runs. Le bruit vient des cas « liberté de modélisation » (`noir_create`, `scale_long_conversation`) et de `scale_check_big_no_false_positive` (anti-faux-positif à gros voisinage = le cas le plus dur, « la plaie historique »). La suite atelier — le gate de production — est **stable à 10/10**.
3. **Verrue UX v0 à dédupliquer plus tard** : une écriture qui touche plusieurs entités (relation → `from` + `to`) lance le check sur chacune ; une même incohérence peut donc émettre **2 cartes alerte** (observé au smoke test). Comportement littéral du plan (« pour chaque id touché »), dédup laissée à une itération future.

**État final** : `just test` 145/145 · `just evals-atelier` 10/10 (8 comportements + 2 checker) · `just evals-generic` 13-15/17 (variance, checks 5-6/6, aucune régression du code promu) · smoke SSE de bout en bout OK. Le « scénario » est désormais **le premier profil d'un noyau réutilisable**, plus une implémentation. Restent ouverts : la couche 3 (profil auto-apprenant, cf. section generic-core), la dédup des alertes, et la fiche personnage atelier (le lien « Voir la fiche » est un placeholder).

## Expérience « generic-core » : le schemaless tient-il ? — 2026-06-07

Question posée (discussion produit) : plutôt que des tools spécifiques (`add_character`, `era` hardcodé…), un **noyau générique schemaless** où le LLM construit le schéma au fil de la conversation — entités/props/relations libres, discipline assurée par l'introspection (`describe_schema`) — fonctionnerait-il ? Si oui, le « scénario » ne serait qu'un **profil de domaine** posé sur un noyau réutilisable (gestion de travaux, etc.). Tranché **eval-first** : prototype complet dans `evals/generic/` (rien dans `src/felix`) — 5 tools génériques (`describe_schema`, `find_entity`, `add_entity`, `update_entity`, `add_relation`, nœuds `:GenEntity` + relations `:REL {rel_type}`), agent agnostique, et check de cohérence « voisinage 1-hop + judge », **zéro sémantique de domaine**. 13 cas sur **3 domaines** (montage d'abri bois, polar, WW2) : extraction, discipline de réutilisation de clés (intra-conversation ET depuis un seed découvrable uniquement via `describe_schema`), contradictions (directe, via relation ×2) et **miroir anti-faux-positif**. `just evals-generic`.

**Résultat : 12/13 (92 %), stable sur 2 runs (même unique fail), ~$0.007/run.**
- **Q1 discipline du schéma émergent : OUI.** `date_achat`/`date_capture`/`alibi` réutilisées depuis le seed (le test décisif — la clé n'est pas dans l'historique de conversation), types d'entités cohérents, clé partagée intra-conversation. Zéro synonyme créé sur tous les runs.
- **Q2 multi-domaine : OUI.** Même code, même prompt, 3 domaines.
- **Q3 check sans sémantique : OUI — mais 0/3 au round 1, 4/4 au round 2.** Deux findings de design majeurs :
  1. **Le check doit voir le DELTA, pas l'état final** : au round 1, l'agent *écrasait* l'alibi contradictoire de Marco via `update_entity` → état final auto-cohérent → judge aveugle. Fix : `write_log` (ancienne → nouvelle valeur) injecté dans le contexte du check. (= l'intuition initiale « l'état + la chose à y ajouter » était la bonne formulation.)
  2. **Reason-first + classes de contradictions** : `CheckVerdict.reason` AVANT `contradiction` (leçon P4), classes génériques (conflit de valeurs, impossibilité temporelle « agir après destruction/mort », spatiale « plus grand que le support », états exclusifs), et calibrage du doute (« n'invente pas de scénario improbable pour réconcilier » — au round 1 le judge voyait les dates du pont effondré et rationalisait « peut-être une erreur de saisie »).
- Seul fail (stable) : « Léa est un témoin » → `role='témoin'` non enregistré (extraction partielle ; `alibi` et le type sont, eux, bien réutilisés). **Pas une dérive de schéma.** Cas dur conservé tel quel.
- Piège protest découvert : deux evaluators d'un même cas ne peuvent pas émettre le même nom de score → une dataclass à champs uniques par evaluator.

**Verdict** : l'hypothèse schemaless est **validée empiriquement à l'échelle testée** (petits graphes). Architecture cible esquissée : noyau générique + « profils » de domaine déclaratifs (types/clés canoniques + règles de cohérence) — le profil n'est pas ce qui *permet* le check générique, c'est ce qui le rendra rapide/fiable à plus grande échelle. Décision produit (promouvoir le noyau, faire de « scénario » le premier profil) : ouverte.

### Round « échelle » (même session, suite)

4 cas ajoutés (17 total) : contradiction noyée dans **14 voisins** (~40 props) + son miroir, **schéma riche** (la bonne clé parmi ~20, 4 types), **conversation de 8 tours** (références partielles « Santi », correction utilisateur en cours de route). **Run final : 15/17 (88 %)**, les 6 checks de cohérence passent tous — needle-in-haystack compris.

**Enseignements (4 runs, ~$0.01/run)** :
1. **La liberté de modélisation est LA source n°1 de variance** — pas la discipline de clés (stable à 100 % partout). L'alibi devient tantôt une prop, tantôt une relation vers une entité « mère de Marco » ; l'interview tantôt relation, tantôt événement. Rien de faux, mais imprévisible → c'est l'argument *empirique* central pour le **profil de domaine** (canonicaliser : « un alibi est une prop `alibi` du personnage »).
2. **Écritures zélées de l'agent** : il a écrasé l'alibi d'un personnage avec un fait tiers (déjeuner→alibi), changé la catégorie d'un club en « restaurant » parce qu'on y déjeune. Règle de provenance ajoutée au prompt (« une info divergente s'AJOUTE, seule une correction explicite remplace ») — aide, ne suffit pas. En produit : c'est le **commit hybride** de la vision B (confirmation sur update) qui couvre ça.
3. **Le check attrape aussi les bêtises de l'agent** : le « faux positif » du round 3 était un VRAI positif sur l'écrasement fautif du point 2 — le filet de sécurité marche dans les deux sens (incohérences de l'auteur ET erreurs d'écriture du bot).
4. **Le judge devenu rigoureux refuse les contradictions sous-déterminées** : « chez sa mère à Marseille » vs « au Vesuvio » n'est pas démontrable si le Vesuvio n'a pas d'adresse — il l'a dit explicitement. Pas un défaut : ça pointe l'UX Intervieweur (« où se trouve le Vesuvio ? »).
5. **UX validée par les données : messages courts et atomiques** — les cas atomiques sont stables à ~100 %, le multi-faits ambigu fait diverger la modélisation ; nommer le champ (« son alibi : … ») fiabilise. Le produit devra guider l'utilisateur à découper son propos.

Fails restants (stables, compris, conservés comme cas durs) : `noir_key_reuse_schema` (« est un témoin » → `role` non enregistré, extraction partielle) ; `scale_long_conversation` (alibi modélisé en relation plutôt qu'en prop → cf. enseignement 1). Fixes d'eval en route : `_match` préfère le match exact (sinon « marco » attrapait « frere-de-marco-santi »), cas `check_direct_noir` sous-déterminé corrigé (Vesuvio localisé).

**Idée actée pour la couche 3 — profil auto-apprenant** : le LLM fait grandir le profil à l'usage (à la façon d'une mémoire d'agent) — **cristallisation du jugement en règle**. Quand le check découvre par raisonnement une contradiction d'une classe non couverte (ex. « événement avant la naissance d'un participant »), il émet une `regle_candidate` structurée en plus du verdict ; validation par l'auteur (carte UI, souveraineté) puis append au profil avec provenance (exemple d'origine). Même mécanisme pour promouvoir une clé récurrente en clé canonique, et pour figer une décision de modélisation (alibi = prop). Effet : le raisonnement coûteux se paie une fois, devient check symbolique ensuite — le système gagne en fiabilité ET en coût avec l'usage. Pièges identifiés (≈ hygiène d'une mémoire d'agent) : calibrage du niveau d'abstraction (un fait n'est pas une règle), empoisonnement silencieux par une mauvaise règle (d'où la validation), croissance non bornée (jardinage/dédup). Possible parce que **le profil est un fichier de données, pas du code**. Séquencement : (1) commit de l'état actuel, (2) promotion du noyau + profil statique v0 « scénario » (mort de `era`), (3) auto-apprentissage.

## Bot B v0 : module atelier + evals dédiées + câblage /atelier — 2026-06-07

Le bot B existe et la coquille `/atelier` lui parle. Reprise **à zéro sur les trois fronts** (décisions actées en session) : module backend neuf, session d'evals séparée, front câblé en SSE structuré. L'ancien chatbot (`felix/agent/`, `/chat`, evals legacy) **intact** — référence vivante.

- **Backend `src/felix/atelier/`** : agent pydantic-ai (Mistral via `build_chat_model`, temp 0.1) + 2 tools — `add_character` (slugify partagé avec le pipeline + anti-doublon par MERGE, cf. `create_character` ajouté au repository) et `list_characters`. **Parti pris : tout en français** (prompt + docstrings de tools), l'inverse du bot A full-EN — Mistral est natif FR, les evals trancheront. Les tools poussent des **cartes UI structurées** (`ToolCard`, alignées sur `AtelierMsg`) dans `AtelierDeps.ui_events`, drainées par la route.
- **Evals `evals/atelier/`** : **session protest séparée** (`just evals-atelier`), 8 cas, wipe+seed du graphe avant chaque cas (lock asyncio — ne pas lancer en même temps que `just evals`). Evaluators symboliques sur l'état du graphe (matching d'IDs souple, leçon des faux négatifs pipeline) + cartes + réponse. **Baseline : 8/8 (100 %), 11s, $0.0011** — créations, slug `marie-lavalle`, anti-doublon, zéro write sur smalltalk, lecture. Piège protest rencontré : `TaskResult[X]` sous `TYPE_CHECKING` → `Any[...]` → `get_type_hints_compat` rend `{}` → aucune injection DI ; importer au runtime.
- **Route `POST /api/atelier/chat`** (SSE) : events `text` (deltas) / `tool` (carte JSON) / `usage` / `history` / `done` / `error`. Pattern `agent.iter()` + drainage des cartes entre les nodes → ordre naturel carte-puis-confirmation.
- **Front** : `useAtelier.ts` (réutilise `parseSSE.ts`) ; `atelier.vue` débarrassé du scripté (seed/canned/followMap), handlers choice/alert conservés (renvoient la décision comme message en attendant le câblage checker). FelixJudge extrait vers `evals/_judge.py` (partagé).
- **Vérifié** : tests 145/145, evals atelier 8/8, build prod web OK, eslint clean, **bout en bout au navigateur** (Playwright) : création → carte + streaming visible ; « Bonjour » → zéro write ; multi-tours → Inès créée, Tomas non dupliqué (message_history OK).

**Observations** : (1) le background d'Inès recopie la méta-phrase de l'auteur (« Elle est nouvelle dans l'histoire ») — few-shot à prévoir dans le tool, bon prochain cas d'eval ; (2) `just test` wipe la base partagée → la cohabitation dev/evals/tests deviendra un sujet quand B écrira de vraies données (option namespace écartée au MVP).

**Prochain pas** : enrichir le périmètre tools (update de fiche, relations) avec leurs cas d'eval, puis poser le checker à chaque écriture (cartes `alert`).

## Front : page « atelier » (le bot B) portée React→Vue — 2026-06-07

Première brique UI de B : le **chat** du design Claude Design, porté du proto **React (CDN+Babel)** vers **Nuxt 4 / Vue 3**. Décision produit : on **refait une page neuve** plutôt que re-skinner l'existant ; l'app cyan reste comme **référence vivante** (rien jeté). Route dédiée **`/atelier`** (`layout: false`), isolée du thème cyan. **`/atelier` est désormais la référence canonique du « design system chatbot »** — on itère dessus (câblage backend plus tard).

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
