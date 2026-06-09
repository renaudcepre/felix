# Journal de developpement — Felix

## ▶ HANDOFF (reprendre ici) — relations TYPÉES (vocab dur + domaine/portée) FAIT ; reste quick-wins (1)(2) + qualité de modélisation — 2026-06-09

**État (2026-06-09)** : **le front est passé 100 % schemaless ET 100 % papier** (deux sections ci-dessous). `/atelier → /chat`, nouvelles pages `/entities` (liste par type + fiche générique props/relations/chronologie), **tout le legacy `:Character` supprimé** (front + API + repos + ingest + agent + cli, ~85 fichiers), puis **redesign papier** des pages d'entités (`felix-fiche.css`, design system) + retrait du shell cyan résiduel (layout/navbar/settings) → toutes pages `layout:false`. Surface vérifiée end-to-end (imports, ruff sans import mort, curl entities, route SSE atelier vivante, typecheck/lint/build front verts). Moteur `core/`/`atelier/` **non touché**. **⚠ Bug visible révélé** : le bot B **invente des entités à partir de rien** (un simple « salur » a fait écrire détective/assistant/indice/bibliothèque dans le graphe) — pas un exemple recopié (rien de tel dans le code), vraie hallucination ; viole ses règles « n'écris rien si salutation / n'invente aucun fait ». **C'est le chantier `project_modeling_quality`, désormais visible grâce aux pages d'entités — prioritaire.** Les **quick-wins moteur (1)(2)(3) ci-dessous restent aussi en attente**.

**État moteur (2026-06-08)** : modèle événementiel **v0 + v1 faits**. v1 = **checker temporel « mort puis agit »** (section juste en dessous) : la chronologie ORDONNÉE des events d'une entité (`entity_timeline`) est concaténée au voisinage du juge, qui distingue désormais « agit APRÈS sa mort » (alerte) de « agit AVANT sa mort » (normal). Vérifié **déterministe** (`/tmp/check_temporal.py` 2/2, `/tmp/compare_checker.py` Small 6/6), **end-to-end** cas B vert + **e2e « Le Nadir »** 5 invariants verts. Backend Mistral **très instable ce jour** (504/503/max-retries/429/request_limit en rafale, 6 transients sur la suite eval) → cas A end-to-end non re-coché par protest (transients), mais acquis pré-fix + prouvé sur graphe fixe post-fix. Reste, par ordre :

**(1) Trous de vocab → dérive qui revient (quick-win, ~20 min, eval-first).**
- Vu sur Le Nadir : `Capitaine TRANSPORTE prototype`, `Vance AIDE intrus` (FR !), `Capitaine ORDERS Vance` (EN mais hors des 12). → ajouter `COMMANDS`, `HELPS`, `TRANSPORTS` à `SCENARIO_PROFILE.relation_vocabulary`, et une consigne « types de relation TOUJOURS en anglais ; si aucun canonique ne colle, rabats-toi sur le plus proche avant d'inventer ». Re-mesurer `rel_vocab_coverage` ; promouvoir son seuil en gate (`min_coverage` ~0.8) une fois stable. NB : `NEXT`/`INVOLVES` sont gérés en code par `add_event`, **pas** à mettre dans le vocab (le LLM ne les choisit jamais).

**(2) Le relieur re-faisait des `update_entity` — ✅ FAIT (2026-06-09).** Voir section « Qualité de modélisation : fin du churn » ci-dessous. Le relieur tourne maintenant sur `RELATION_TOOLS` (noyau − `update_entity`) → il ne PEUT plus churner les props. Couplé à la suppression de la clé `arc` et à la garde anti-écrasement d'`update_entity` (`is_correction`), le churn de propriétés est tombé à **0** sur le re-jeu « Alger ». Reste : la **sur-extraction d'entités** (et le chroniqueur qui sur-extrait parfois) — bucket parké.

**(3) v1-suite (optionnel) : généraliser la dérivation de validité d'état au-delà de la mort.**
- Le calcul d'événements vaut pour TOUT état borné (« ingénieur depuis X », « emprisonné entre Y et Z »), pas que l'état terminal mort/destruction que v1 couvre. Étendre = un état = intervalle `[event_début, event_fin]` ; « P vrai au beat N ? » = défaut(prop/relation) ± events d'ordre ≤ N. Eval-first (cf. [[feedback_tdd_evals]]). Réf. `docs/vision_produit_copilote_scenario.md`.

**(4) Relations TYPÉES + vocab DUR — ✅ enforcement au write FAIT (2026-06-09) ; refactor Cypher typé parké.** Détail : section « Relations typées par profil » ci-dessous.
- **Fait** : `relation_vocabulary` devenu **loi** vérifiée dans `add_relation` via `RelationSpec` + `Profile.validate_relation` (3 règles : vocab dur, pas de self-loop, domaine/portée **tolérant** = refus des seules violations claires). Type d'entité `groupe` ajouté (comble le « trou FLN »). Eval-first 3 niveaux (unit 36/36, sonde intégration 7/7 refus = 0 arête, e2e « Alger » = **6 bugs relationnels réglés**, 0 boucle). On garde `:REL`+`rel_type` (zéro APOC, zéro refactor Cypher).
- **Reste optionnel (phase 2, parké)** : remplacer `:REL`+`rel_type` par de **vraies relations Cypher typées** `:KNOWS`/`:OWNS` (interpolation whitelist, sûr car enum contrôlé) → lisibilité Neo4j Browser + lecteurs `all_relations`/`neighborhood` en `type(r)`. **Ne change pas la correction** (déjà acquise au write) — pur confort. Refactor borné : `core/graph.py` (writer + lecteurs + machinerie events `INVOLVES`/`NEXT`) + un poil de front.
- **Limite assumée** : la **direction entre deux entités du même type** (`école`/`cave` toutes deux `lieu` pour `PART_OF`) n'est pas déductible du typage → le check sémantique reste le filet.

**(5) Démo multi-template (parké, pour la présentation au taf).** Aujourd'hui les profils sont du **pur-Python en dur** (`core/profile.py` : `SCENARIO_PROFILE`, `CHANTIER_PROFILE` ; personas + registre `ATELIER_CHOICES` dans `atelier/agent.py`). Deux petits chantiers pour la démo :
- (a) **Externaliser les profils en fichier de conf** (YAML/JSON chargé au démarrage) → un template définissable sans toucher au code (argument démo : « les modes sont éditables »). Le docstring de `profile.py` le prévoit déjà (« structuré pour devenir un fichier éditable »).
- (b) **Sélecteur de mode au front** : `useAtelier` envoie toujours le défaut `scénario` ; ajouter un menu (topbar du chat) qui lit `GET /api/atelier/profiles` et passe `body.profile`. ~30 min. Permet de switcher scénario / chantier / **maintenance** en live.
- Profil cible démo : `MAINTENANCE_PROFILE` (~40 lignes : `piece`/`outil`/`machine`/`procedure`/`panne` ; vocab `PART_OF`/`REQUIRES`/`REPLACES`/`CAUSES` ; `manages_events=False` sauf si journal d'interventions). Zéro changement moteur (l'archi est déjà « branche-un-profil » : `AgentChoice` = profil + persona ; `CHANTIER_PROFILE` le prouve déjà).

**Pointeurs** : noyau `src/felix/core/` (graph.py `entity_timeline` + tie-break `find_node`, check.py `consistency_check` concatène la timeline + `CHECK_PROMPT` temporel, agent.py `CHRONICLE_SYSTEM_PROMPT` « mort = événement », profile.py `consistency_rules` rule 1 + `manages_events`, tools.py `add_event`/`find_non_event`, deps.py `event_seq_lock`) ; route **3 passes** `src/felix/api/routes/atelier.py` ; evals `evals/atelier/` (cas `check_death_then_act`/`check_act_then_death` A/B + `event_chrono` + `roue_de_sang`). Harness checker isolé `/tmp/check_temporal.py` (juge sur graphe fixe, 1 appel/cas — robuste aux transients) et `/tmp/compare_checker.py` (6 scénarios, non-régression faux positifs). Modèle `mistral-small-2506`. Tiering Large/Small parké ([[project_model_tiering]]).

## Slugify retire l'article de tête → fin des doublons « le pêcheur »/« pêcheur » — 2026-06-09

Fix **structurel** (model-independent : le doublon à l'article près avait persisté sur Haiku ET Sonnet). `slugify` (`src/felix/ingest/resolver.py`) retire désormais l'**article de tête** (`le/la/les/l'/un/une/des`, apostrophe droite ET typographique `’`) sur le texte normalisé → l'id s'aligne : « le pêcheur » et « pêcheur » → `pecheur` ; « l'équipe de Castan » et « équipe de Castan » → `equipe-de-castan`. Comme `add_entity` fait `entity_id = slugify(name)` puis `find_node` (slug exact), la 2e fiche est refusée (« existe déjà ») ou les MERGE concurrents collapsent sur le même id → **doublon tué à la création**.

Eval-first : `tests/unit/test_resolver.py` — l'ancien `test_slugify_special_chars` (`L'inspecteur` → `l-inspecteur-benoit`) encodait l'ancien comportement → relocalisé sur un apostrophe **milieu**-de-phrase (`Cartel d'Ophir` → `cartel-d-ophir`), + 4 tests articles (rouge constaté avant, vert après). Garde-fous : `lapin`/`larme`/`Léviathan` non rognés (l'espace après `le/la/…` et l'apostrophe pour `l'` évitent les faux positifs) ; nom réduit au seul article jamais vidé. **56/56 unit verts** ; vérifié aussi sur les vrais noms du graphe (`de`/`des`/`d'` milieu conservés).

**Caveat migration** : les fiches créées AVANT le fix gardent leur id articlé (`le-leviathan`) ; une nouvelle mention « Léviathan » → `leviathan` ne fusionnera pas par slug avec l'ancienne, mais le fallback `name CONTAINS` de `find_node` évite le vrai doublon. Sur graphe neuf, tout est cohérent.

## Coût : faux problème à l'échelle mono-user (Mistral Small = centimes) — 2026-06-09

Suite de la discussion coût (après le constat fenêtrage). **Conclusion : il n'y a quasi pas de coût à optimiser à notre échelle.** La panique venait d'avoir chiffré sur **Haiku** ($0,31 / 4 tours). Sur le défaut **Mistral Small** (~$0,1/$0,3 par M, ~10× moins cher, et **français/souverain**) : 4 tours ≈ 250k in / 7k out ≈ **$0,027** ; session 30 tours ≈ **0,20 €** ; projet 200 tours ≈ **~1,4 €**. Donc :
- **Ne PAS tenter le caching Mistral.** Bloqué des deux côtés : pydantic-ai ignore `extra_body` pour Mistral (0 usage dans `models/mistral.py` ; `_completions_create` passe une liste de params codée en dur) ; le SDK `mistralai` 1.12.4 n'a même pas `prompt_cache_key`. → il faudrait forker la couche requête de pydantic-ai (sous-classer `MistralModel`) ou réécrire la boucle tool-calling à la main. Gros taf fragile pour économiser ~0,18 € la session. **Mauvais combat.** (NB : Anthropic, lui, a un caching clé en main dans pydantic-ai — mais pas souverain.)
- **Ne PAS louer d'A100.** Usage bursty mono-user, human-in-the-loop → payer une carte 24/7 pour l'utiliser 1 % du temps est absurde.
- **Rester sur l'API Mistral Small.** Souverain (FR/EU), zéro ops, centimes la session.

**Parké (si un jour on veut du zéro-dépendance / offline) :** GPU **serverless pay-per-second** (RunPod/Modal, scale-to-zero entre sessions) plutôt qu'un GPU 24/7. Et quitte à payer un GPU, y mettre un **modèle costaud** (Qwen 32B/72B — data-souverain en self-host malgré les poids chinois), pas un 7B. Câblage Felix = **config pure** (`FLX_LLM_CHAT_BASE_URL` → `build_model` part déjà sur `OpenAIModel`, cf. `src/felix/llm.py:26-41` ; vLLM = prefix caching auto pour la vitesse). **Caveat** : le juge (`consistency_check`) fait du structured output → le laisser sur un modèle fiable ([[project_evals_model]] : Qwen 7B crashait sur la grammaire `$defs/$ref` ; à re-tester sur un Qwen plus gros). Le **M4 est hors-jeu** (trop lent, confirmé). Distinction clé actée : caching API = remise sur un compteur à tokens (galère à activer) ; self-host = pas de compteur du tout (le « préambule × N tool calls » s'évapore, c'est du GPU/h plat).

## Fenêtrage d'historique par budget de tokens — FAIT mais ⚠ N'EST PAS le levier prix — 2026-06-09

Implémenté le bornage de l'historique threadé par budget de tokens (`src/felix/api/history.py` : `estimate_tokens` + `window_history_by_tokens`, pures ; découpe en tours sur `ModelRequest`⊃`UserPromptPart` → paires tool intactes, garde les tours récents sous budget, ≥ dernier tour, no-op sous budget). Câblé dans la route (`atelier.py`, après `validate_python`, partagé passes 1 & 2 ; passe 3 = `None`) ; `FLX_HISTORY_TOKEN_BUDGET` (défaut 8000) ; nudge SYSTEM_PROMPT « historique borné → relis la base avec `find_entity` ». Eval-first : `tests/unit/test_history_window.py` 7 cas (fail-first constaté), **52/52 unit verts**. Cap **prouvé end-to-end** (replay budget=200 sur graphe space-opera : l'historique envoyé PLAFONNE à ~240 tok = budget + un tour pendant que la conversation continue sur 8 tours).

**⚠ MAIS — décevant — ÇA NE FAIT PAS BAISSER LE PRIX. C'était notre seule piste prix et elle est morte.** Mesure : **l'historique threadé est minuscule (~60 tok/tour ; ~734 tok après 10 tours)** — il faudrait **~120 tours** pour seulement atteindre le budget 8000. **Le vrai moteur de coût, ce sont les ALLERS-RETOURS D'OUTILS : à chaque tool call interne, pydantic-ai re-envoie tout (instructions + bloc DOMAINE + schémas d'outils + prompt), × 3 passes.** Preuve directe (replay budget=200, historique capé à ~240 tok) : `request_tokens` saute de **5 820** (tour à peu de tool calls) à **54 802** (tour à beaucoup de tool calls) — varie d'un facteur ~10 selon le NOMBRE de tool calls, **indépendamment de l'historique**. Donc le « 242k de Nora » que j'avais attribué au threading était en réalité du `request_tokens` (round-trips), **pas** de l'historique. J'avais mal attribué le coût dans le plan.

**Ce que le fenêtrage apporte quand même (on le garde, bas risque) :** garde-fou long-projet (évite de buter sur la limite de contexte vers ~100+ tours) + borne le payload SSE/mémoire front. Mais **ce n'est PAS un levier prix** à horizon pratique.

**Vraies pistes prix (à creuser — c'est là qu'est l'argent) :** réduire le NOMBRE d'allers-retours d'outils par tour (chaque tool call = un appel modèle qui re-paie tout le contexte) ; alléger ce qui est re-envoyé à chaque appel (instructions + schémas d'outils + bloc DOMAINE — gros et constants) ; réduire le nombre de passes (3 → ?) ou les conditionner ; tiering modèle ([[project_model_tiering]]). À noter aussi : backend Mistral toujours instable (un tour a hangé 908s pendant le check de cohérence).

## Outil rename/merge + say/do, puis run gros modèle (Haiku 4.5) — 2026-06-09

Suite « on fixe ce qu'on peut sans changer le modèle, puis on rerun sur gros modèle » (utilisateur). Calibration d'abord : **la dédup d'événements par similarité de chaîne est impossible** (token_set_ratio : paraphrases du même fait scorent 51, événements distincts sur mêmes entités scorent 71 → aucun seuil ne sépare ; « emmènent X » vs « emmènent Y » ≈90 → fusion à tort). Donc la sur-extraction du chroniqueur est **bornée modèle**, pas réparable cheap. Conclusion du tri : **les structurels étaient déjà faits** (3 commits) ; le reste est borné modèle. Deux préparatifs valaient le coup :
- **`rename_entity` (core/tools.py)** : renomme en place (migre id+name, les arêtes suivent le NŒUD) ou **FUSIONNE** si le nom cible existe déjà (`_merge_entity_into` : relations + événements rebranchés, props complétées, source `DETACH DELETE` — Cypher pur, zéro APOC sur `:REL`). Ajouté aux outils passe 1 + consigne SYSTEM_PROMPT (« nomme une entité suivie → rename, pas de doublon »). Sonde `/tmp/probe_rename.py` 7/7 (fusion le-pêcheur+Joseph → 1 Joseph héritant événement+FIGHTS+props ; renommage simple). 45/45 unit.
- **say/do** (ATELIER_PERSONA) : ne plus RÉCAPITULER les écritures (« j'ai noté X ») — la vérité = les cartes.

**Run Haiku 4.5** (chat via OpenRouter, `FLX_LLM_CHAT_MODEL`/`FLX_LLM_CHAT_BASE_URL` ; checker resté sur Mistral), mêmes 4 tours « Nora » que la passe Small. **Tout ce qui était classé « borné modèle » tombe** : relieur tire aux **4 tours** (vs 2/4 muets) ; relations riches et justes (`ALLIED_WITH`, `Veil TARGETS Nora`, **crée un groupe `l'équipe de Castan` + MEMBER_OF**, **backstory captée : `Castan KILLS le fils de Joseph`**) ; et **`rename_entity` EST utilisé** (le pêcheur → Joseph, doublon #1 mort) — l'outil marche avec un modèle assez malin.
- **Nouveau défaut** (zèle de Haiku) : doublons **à l'article près** dans un même tour (`le pêcheur`+`pêcheur`, `l'équipe`+`équipe de Castan`). Le juge les détecte mais pas d'auto-fix. → fix **model-independent** : `slugify` doit **retirer l'article de tête** (le/la/les/l'/un/une/des) → même id → fusion à la création. À FAIRE.
- **Coût/latence réels** : **$0,31 / 4 tours** (~$0,08/tour ; ~$2-3 pour 30 tours) ; 268k tok **in** / 7,8k out (très input-lourd, Haiku multiplie les tool calls) ; **26-41s/tour** (vs 8-17s Small). → argument tiering : gros modèle sur le relieur seulement.
- **Reste à voir** : run **Sonnet 4.5** (zèle/dup au sommet ?), et le fix slugify anti-article.

## Relations : exemples par type + KNOWS recadré en dernier recours (+ 2e passe dogfood) — 2026-06-09

Discussion avec l'utilisateur après la 1re passe dogfood. Deux questions de design tranchées **avec données** (micro-A/B `/tmp/exp_vocab.py` : « X surveille Y » au relieur, vocab libre vs fermé) :
- **Le vocab fermé n'est PAS responsable de l'aplatissement** : en vocab LIBRE (profile=None) Mistral Small ne produit jamais « WATCHES », il se rabat sur `KNOWS` quoi qu'il arrive. Le seul résultat juste (`TARGETS`) venait du vocab fermé. → garder la liste fermée.
- **Le vrai défaut = fragilité au rejet** (2/4 runs fermés produisaient 0 relation) + **KNOWS = attracteur fourre-tout** (vague → on s'y replie).
- **Fix (pur prompt) : champ `RelationSpec.examples`** (exemples contrastifs, rendus dans le prompt seulement — `gloss` reste court pour les messages d'enforcement) + consigne « choisis le PLUS précis » + **KNOWS placé en dernier et cadré « lien neutre SANS intention, dernier recours »** (renvois : surveiller→TARGETS, aider→ALLIED_WITH, affronter→FIGHTS) + « surveille/espionne/enquête » explicitement sous TARGETS. **Mesuré** : « X surveille Y » → `TARGETS` **3/3** (vs KNOWS/rien avant), bonne direction, zéro drop. 45/45 unit toujours verts (le gloss/examples n'affecte pas `validate_relation`).
- **Bonus, fact-check Neo4j** : « relations typées impossibles sans APOC » était une surévente. Vrai fait étroit : Cypher n'accepte pas un TYPE de relation paramétré (`-[r:$t]->`). Mais (1) **interpolation de chaîne d'un type whitelisté = sûr, sans APOC, toute version** (= la phase-2) ; (2) APOC si installé ; (3) syntaxe native `-[r:$(t)]->` en **Neo4j 5.26+** (ici 5.24.2 → pas dispo). Donc phase-2 dé-parquable quand on veut.

**2e passe dogfood (histoire « Nora / Port-Vendres / Castan », thriller, base propre).** Ce qui a CHANGÉ vs passe 1 : **les verbes chargés sortent bien quand le relieur tire** — `Nora —[TARGETS]→ Castan` (« enquête sur »), `Joseph —[FIGHTS]→ Castan` (« se venger »). Le fix vocab tient en flux. Ce qui PERSISTE (et ressort en tête) :
- **Identité/placeholders = #1, reproduit une 3e fois** : « un pêcheur sans nom » → entité `le vieux pêcheur` ; quand je le nomme **Joseph**, Felix crée un DOUBLON → **identité éclatée** (`le vieux pêcheur` porte les 2 événements + la clé USB ; `Joseph` porte `FIGHTS Castan` — aucune fiche complète). Pas de merge/rename. (Cf. Camille/Femme, Valcroze/Village.)
- **Relieur peu fiable (intermittent)** : a tiré aux tours 1 et 4, **0 relation** aux tours 2 et 3 (cohérent avec les 2/4 vides de l'A/B). Quand il se tait, les liens sont perdus ou enfouis en prop (`Veil background='homme de main de Castan'` au lieu de `MEMBER_OF/ALLIED_WITH Castan` ; `OWNS clé USB` jamais créé).
- **Dire ≠ faire (dangereux)** : Felix annonce « j'ai noté Veil / possède la clé USB » alors qu'aucune carte n'est émise — l'auteur croit la bible à jour, elle ne l'est pas (tour 2 : 0 écriture pour un tour riche).
- **Backstory perdue** : le **fils mort** de Joseph + l'accident étouffé par Castan → ni entité, ni événement, ni relation ; et « fils mort » mal lu en `traits='veuf'`.
- Mineur : Felix répète sa relance ; liste à puces collée (artefact de MON client SSE, pas Felix).
- **Priorités post-dogfood** : (1) **gestion d'identité** (placeholders → merge/rename/dedup) — de loin le plus visible et destructeur ; (2) **fiabilité du relieur** (tire 1 tour sur 2) ; (3) say/do (annonce ≠ écriture) ; (4) backstory/événements passés non captés. [[project_modeling_quality]]

## Dogfooding « à la main » : j'écris une nouvelle AVEC Felix, je note les frustrations — 2026-06-09

À la demande de l'utilisateur : utiliser Felix comme un vrai auteur (pas rejouer un scénario figé), partir d'une idée floue et l'améliorer tour par tour, en réagissant aux réponses. Outil : `/tmp/felix_chat.py` (1 tour/appel, threade l'historique via `/tmp/felix_history.json` comme le front ; rend le TEXTE de Felix + cartes + alertes). Base vidée d'abord (sinon contamination cross-histoires). 7 tours, histoire « Camille / Valcroze / l'herbier de la grand-mère ».

**MAJEUR — Identité d'entité ingérable (le thème dominant).** Idée floue → Felix réifie des PLACEHOLDERS : « une femme sans nom » → entité `Femme`, « village de montagne » → `Village de montagne`, « grand-mère » → `Grand-mère`. Quand je NOMME ensuite (Camille, Valcroze), il crée une NOUVELLE fiche au lieu de renommer → **doublons permanents** (`Femme`+`Camille`, `Village de montagne`+`Valcroze`). Pas de `merge`/`rename`/`delete` : ma correction « Valcroze EST le village de montagne » ne peut pas fusionner — Felix l'encode en prop absurde `ambiance='lieu unique'`, le doublon reste à vie. **Cascade** : Camille `LOCATED_AT` Valcroze ET Village de montagne → le juge crie bilocation = **faux positif né du doublon**. Bible finale = 7 entités dont **3 déchets**.

**MAJEUR — Relations : direction & sens des verbes chargés.** « Hervé **surveille** Camille » → écrit `Camille —[KNOWS]→ Hervé` : direction INVERSÉE + « surveille » aplati en KNOWS neutre (alors que `TARGETS` « traque/vise » collait). Relation-clé de l'intrigue, ratée et jamais rattrapée. Ironie : Felix dit « qui **la** surveille » en mots (compréhension texte > fidélité graphe).

**MOYEN — Chroniqueur sur-extrait.** « Camille trouve l'herbier » → **4 événements** quasi-identiques (#1-#4, paraphrases ; le dédoublonnage exact ne les voit pas). Pollution de timeline. (≠ d'autres tours OK à 1-2 events.)

**MOYEN — Relieur ré-émet les arêtes existantes.** `Camille KNOWS Hervé` ré-écrit chaque tour (×3 au tour 4). MERGE sauve, mais cartes bruitées + appels gâchés.

**MOYEN — Latence & coût.** Tours de 4s à **38s** (pic chroniqueur + transients) ; tokens **14k → 40k**/tour (historique + graphe relus). Longue session = cher et lent.

**MINEUR.** (a) Felix **répète mot pour mot** sa question de relance (« Que fait-elle en découvrant les annotations ? » ×3) — robotique. (b) Passe 1 annonce « je note un événement (le retour…) » mais **aucun event créé** (passe 3 ne livre pas) — dire ≠ faire. (c) `traits='partie à 18 ans'` = fait biographique calé dans `traits`.

**POSITIF (les fix récents tiennent en conditions réelles).** Correction explicite « je corrige : 52 ans, pharmacienne » → écrasement appliqué (garde `is_correction`), **zéro churn**. `traits` reste durable (« vieux taiseux »), pas de churn d'actions (chantier d'avant : tient). Question pure → **zéro écriture** + rappel EXACT sans hallucination. Typage relations tient (aucune relation absurde). Initiales/dates (« M.D. », « 3 mars 1981 ») **non réifiées**.

**Priorités qui sortent du dogfood** : (1) **gestion d'identité** = nouveau gros chantier (placeholders, `merge`/`rename`, dédoublonnage) — déclasse presque le reste tant c'est visible ; (2) **direction/sens de relation** (le relieur perd la direction et neutralise les verbes) ; (3) chroniqueur sur-extraction (paraphrases) ; (4) relance qui se répète. [[project_modeling_quality]]

## Qualité de modélisation : fin du churn de propriétés (relieur + arc + garde anti-écrasement) — 2026-06-09

Chantier `project_modeling_quality`, mesuré sur « Alger 1957 » (graphe propre, 12 beats). **Symptôme** : la fiche d'un personnage finissait avec une PROPRIÉTÉ écrasée par l'action du dernier beat (`arc = « écrit une lettre d'adieu »`), perdant le durable. **Cause racine** : la passe 1 (entités) n'a PAS `add_event` → son seul exutoire pour « ce qui se passe » est `update_entity` sur une prop ; et le relieur (passe 2, tous outils) re-updatait par-dessus. **Décisions actées avec l'utilisateur** : (1) la trajectoire vit dans la CHRONOLOGIE (pas de prop `arc`) ; (2) garde anti-écrasement au write ; (3) sur-extraction d'entités parquée pour plus tard.

Trois leviers, **eval-first**, validés par re-jeux successifs (métrique = nb de cartes « Entité mise à jour ») :
- **Relieur sans `update_entity`** (`RELATION_TOOLS` = noyau − update_entity ; garde `add_entity` en backfill). Tue le DOUBLEMENT (item 2 du HANDOFF). Structurel — le piège « boucle sur outil manquant » concernait le retrait d'`add_entity`, pas d'`update_entity`. Test : `update_entity ∉ RELATION_TOOLS`.
- **Suppression de la clé `arc`** des `personnage` + règle « l'évolution se lit dans la chronologie ; n'allonge JAMAIS `traits` avec une action » (few-shot concret : « sourit », « rouge de colère » → événement, cf. [[feedback_prompt_engineering]]). Test : `'arc' ∉ keys`.
- **Garde anti-écrasement** : `plan_property_update(existing, props, is_correction)` (fonction PURE, testée) partitionne en {appliqué, bloqué} — on n'écrase une valeur existante non-vide QUE si `is_correction=True` (correction explicite de l'auteur, cf. SYSTEM_PROMPT règle 4). `update_entity` gagne le param `is_correction` + message guidant si bloqué (pas d'exception → pas de boucle ModelRetry). Même patron que l'enforcement des relations (Option 2).

**Churn mesuré (re-jeux « Alger »)** : ~38 cartes update (avant) → 18 (relieur+arc) → 11 (+few-shot, mais `traits` écrasé → durable détruit) → **0** (+garde). Fiches finales PROPRES : Laurent `traits='Cheveux gris, parle arabe', background='Né à Oran', age='40 ans'` (durable préservé ; « sourit amèrement » = l'événement #25), Dubois `traits='Colonial pur suif'`, Marcel `background="fils d'un légionnaire"`. Trajectoire dans les événements (Laurent : 21). Relations toujours typées-correctes (Option 2 tient). Run 135s, 1 alerte juge (vs 3).

**Eval-first, 3 niveaux** : unit déterministe (`tests/unit/test_modeling_quality.py`, 9 cas : clés perso, outils relieur, partition d'update — **fail-first vérifié**, 45/45) ; sonde d'intégration (`/tmp/probe_update_guard.py` : écrasement refusé = valeur INCHANGÉE en base, correction appliquée, clé nouvelle appliquée) ; e2e re-jeu (churn 0, durable préservé).

**Limites / reste (parké)** : (a) **sur-extraction d'entités** encore présente (`armes`, `tableau noir`, doublon `mot`/`morceau de papier`) — bucket parké ; (b) le **chroniqueur sur-extrait** parfois (6-8 events sur un beat introspectif, vs « 1-3 max ») ; (c) un fait durable NOUVEAU post-création passe par une nouvelle clé (OK), mais un enrichissement formulé comme écrasement est bloqué (friction mineure, redirigée par le message). `plan_property_update` est générique (vaut pour tout profil).

## Relations typées par profil : vocab dur + domaine/portée (Option 2 — enforcement au write) — 2026-06-09

Suite de l'item (4) du HANDOFF, partie « enforcement à l'écriture » (la plus rentable). Le `relation_vocabulary` du profil passe de **suggestion molle** du prompt à **loi vérifiée dans `add_relation`**, **sans APOC ni refactor Cypher** (on garde `:REL`+`rel_type`). Plan validé avec l'utilisateur avant de coder ; refus = message **guidant** (pas d'exception → pas de boucle ModelRetry).

- **Modèle (`core/profile.py`).** `relation_vocabulary: tuple[tuple,...]` → `tuple[RelationSpec,...]` où `RelationSpec(name, gloss, subjects, objects, allow_self=False)` porte le typage domaine/portée. Nouvelle méthode `Profile.validate_relation(rel_type, subject_type, object_type, *, same_node) -> str|None` — **3 règles** : (1) `rel_type ∈ vocab` sinon refus (profil sans vocab = tout permis → rétrocompat `CHANTIER_PROFILE`) ; (2) pas de boucle `a==b` si `not allow_self` ; (3) domaine/portée. **Règle 3 TOLÉRANTE** (schemaless) : on ne refuse que les violations **claires** — une extrémité d'un type **connu du domaine** (`known_entity_types` = types déclarés ∪ types cités dans les specs ∪ `evenement`) mais hors-liste → refus ; un type **inconnu** improvisé par le modèle (ex. `langue`) → **toléré**, pas de sur-rejet. Helper `_or_types` pour des messages lisibles.
- **Enforcement (`core/tools.py` `add_relation`).** Après résolution `find_non_event` des deux extrémités, appel `profile.validate_relation(...)` **AVANT le MERGE** ; si message → **return du message** (aucune écriture, aucune exception → l'agent rejoue avec un type/sens valides ; même pattern que la garde « type réservé » d'`add_entity`).
- **Typage du profil scénario** (12 specs, validé utilisateur) : `LOCATED_AT`→lieu ; `OWNS`→objet ; `KNOWS` P→P ; `MEMBER_OF`→**groupe** ; `ALLIED_WITH`/`FIGHTS`/`TARGETS` P,G→P,G ; `KILLS`→P,objet ; `CREATES`→objet,événement ; `CAUSES`→événement ; `PART_OF` L,O,G ; `WITNESSES`→objet,événement. **Nouveau type d'entité `groupe`** ajouté à `SCENARIO_PROFILE.entity_types` (sans lui `MEMBER_OF→groupe` serait mort — c'était le « trou FLN » : le FLN n'avait jamais d'entité). `evenement` figure dans des specs mais **jamais atteint via `add_relation`** (`find_non_event` l'exclut) — cohérence conceptuelle seulement.
- **Eval-first, 3 niveaux.** (1) **Unit déterministe** `tests/unit/test_relation_typing.py` (12 cas, ni LLM ni Neo4j ; branché `tests/unit/suite.py` + `tests/session.py`) : **fail-first** (`AttributeError: validate_relation`) → **36/36 vert**. (2) **Sonde d'intégration** `/tmp/probe_enforcement.py` (pilote `add_relation` sur Neo4j ensemencé, sans LLM) : les 5 cas refusés écrivent **0 arête**, les 2 valides 1 → prouve que le refus **BLOQUE l'écriture** (≠ « le modèle a deviné bon »). (3) **End-to-end** : re-jeu « Alger 1957 » (12 beats, base vide, code frais) — **les 6 bugs relationnels disparus** (self-loop `PART_OF`, `LOCATED_AT`/`TARGETS`→objet, `WITNESSES`→lieu, `PART_OF` inversé), FLN modélisé `[groupe]`, plus de faux type `langue`, **0 boucle / 0 freeze** (209s ; +22s vs run buggé = coût des rejouages guidants). `registre LOCATED_AT cave` désormais dans le bon sens (objet→lieu), `WITNESSES` toujours sur objet.
- **Reste / limites.** Phase 2 (vraies relations Cypher typées via interpolation whitelist) **parquée** — gain = lisibilité Neo4j Browser + lecteurs `type(r)`, **pas** la correction (acquise au write). **Direction same-type** (`école`/`cave` `PART_OF`) non bordable par types seuls → check sémantique reste le filet. Les alertes du **juge** (beats 9/12 : « agit après arrestation ») relèvent d'une autre couche (précision du juge), hors Option 2. Le **churn d'`update_entity arc=…`** à chaque beat reste l'item (2). `RUF003` pré-existant (un `×` dans un commentaire d'`add_event`) laissé tel quel (hors scope).

## Chat « utilisable » (2/2) : moins d'appels juge + parallélisation = fin des gros blancs — 2026-06-09

Suite directe du diagnostic (section ci-dessous). Le « gros blanc » de fin de tour = le checker qui appelait le juge **une fois par entité touchée, en série**. Deux leviers, **eval-first** :

- **Scoping (moins d'appels).** Nouveau `deps.check_candidates` (core/deps.py) : sous-ensemble de `touched_ids` où une contradiction est POSSIBLE ce tour — peuplé par `add_relation` (les 2 extrémités), `add_event` (participants/lieu), `update_entity` **seulement si écrasement** (`replaced`). PAS `add_entity` (création additive), PAS les nœuds événement (jamais sujets). La route (`_consistency_alerts`) itère `check_candidates` au lieu de `touched_ids`. Les checks prouvés (temporel « mort puis agit », spatial) sont tous portés par une relation/événement → couverts. **Tradeoff acté** : on laisse tomber le check de divergence purement additive sur prop (le `check_contradiction` flaky) — « les contradictions vivent dans les relations » (utilisateur). Réversible (ajouter `update_entity` sans la garde `replaced`).
- **Parallélisation (moins d'attente).** Les juges des candidats tournent en `asyncio.gather` (`return_exceptions=True`) → le blanc passe de Σ(appels) à max(appels). Sûr sur Mistral Small (5M tok/min).
- **Eval-first** : `/tmp/test_check_scope.py` (déterministe, sans LLM — appelle les tools directement, asserte `check_candidates`) : **fail-first** (AttributeError) → vert après (`{borin, le-baron, salle}`, **event-N exclus**, création/additif exclus). `consistency_check` **inchangé** → les cas `check_*` (qui l'appellent en direct avec un id explicite) ne régressent pas.
- **Mesuré (graphe propre, beat Marlowe/Vera, 2 rel + events)** : gap check **13,4s → 5,3s** (séquentiel → parallèle), tour total **23s → 16,5s** ; et ça scale avec le nombre de candidats. Route OK de bout en bout. Refactor route au passage : helper `stream_pass` (closure) pour les 3 passes → corrige un PLR0912/0913 introduit par le fix progression.
- **Reste** : si encore lent sur de gros beats, dédup des voisinages qui se recouvrent (1 check par composante connexe) ; et le fond = qualité de modélisation / relations typées ([[project_modeling_quality]]).

## Chat « utilisable » : progression en live + diagnostic des retries — 2026-06-09

Retour utilisateur : « le chat n'est pas utilisable — je vois quand il a ajouté / quand c'est fini, mais PAS pendant ; et j'ai des milliers de retry ».

- **Diagnostic des retries (pas de boucle, c'est du volume × rate-limit).** Mesuré sur graphe propre : 1 message simple = **15,7s**, 0 erreur. La structure d'appels est lourde : **3 passes/tour** (entités → relieur → chroniqueur, chacune une boucle agentique) **+ le checker qui appelle le juge UNE FOIS PAR ENTITÉ touchée** (`for touched in deps.touched_ids`, chacun envoyant le voisinage) → **~20-30 appels LLM/tour**. Avec une clé Mistral rate-limitée (429, retries HTTP 3-5× chacun) **et un graphe pollué à 28 entités** (3 histoires empilées → contextes gonflés), ça cascade en « milliers » ressentis. `just db-clean` enlève l'amplificateur graphe. Le gros temps **silencieux** = le checker en fin de tour (~8s sur un beat simple, bien plus si beaucoup d'entités touchées).
- **Quick win — progression visible (route + front).** `atelier.py` : émission d'événements SSE **`phase`** (`Felix écrit… / relie les fiches… / note les événements… / vérifie la cohérence…`) ; et les passes 2/3 passent de `await sub_agent.run()` à `sub_agent.iter()` pour **vider leurs cartes EN LIVE** (au lieu d'un dump à la fin). Front : `useAtelier` gère `phase` (ref exposée, posée sur `phase`, vidée sur `text`/`done`), `chat.vue` l'affiche près de l'indicateur de frappe (`.phase-label` mono, thème papier). Protocole SSE rétro-compatible (nouvel event ignoré par anciens clients). Comportement GRAPHE inchangé (mêmes tools/passes, `iter` ≡ `run`). Vérifié : import-sanity OK, typecheck/lint front verts, smoke SSE live (phases à 0/6,3/10,8/11,9s, done 17,7s).
- **Reste (pistes de fond, pas faites)** : réduire le volume d'appels — surtout **batcher / restreindre le juge** (1 appel par entité touchée = le pire multiplicateur) ; éventuellement alléger/fusionner des passes. Et le scoping par histoire (cf. [[project_modeling_quality]]).

## Pages d'entités en design system papier (au lieu du thème cyan) — 2026-06-09

Retour utilisateur juste après la bascule : les pages d'entités **reprenaient l'ancien thème cyan** (`@nuxt/ui` `UCard`/`UBadge`/`.tape-effect`, « ancien design moche ») au lieu du **design system papier** (celui de `/chat` + `resources/design-system/`). J'avais fait ce choix parce que les pages vivaient sous le layout `default` (cyan, `AppNavbar`). Reprise complète sur le papier.

- **Source = le bundle** `resources/design-system/project/` : `felix.css` (tokens + `.btn`/`.badge`/`.input`/`.mono-avatar`) + **`Fiche personnage.html`** (la maquette exacte de fiche : `.fbar`, `.char-head`, `.card`, `.rel-row`, `.fiche-foot`) + `fiche-app.jsx`/`felix-ui.jsx` (structure + composant `Mono` = avatar rond, fontSize = size×0.42).
- **`felix-fiche.css`** (nouveau, importé dans `main.css`) : thème papier **scopé `.felix-fiche`** (tokens littéraux → indépendant du cyan, comme `felix-atelier.css`). Classes : `.fbar`/`.back-link`/`.fbar-brand`, `.fwrap`, `.mono-avatar`(+`.neutral`), `.ent-head`/`.ent-name`/`.ent-tags`, `.badge`(+`.badge-rel`/`.cap`), `.card`/`.card-title`, `.prop-grid` (clé/valeur lecture seule), `.rel-row`/`.rel-dir`(flip pour `in`), `.chrono-row`, `.fiche-foot`, `.filter-row`/`.chip`, `.ent-grid`/`.ent-card`.
- **Pages** (`layout:false`, wrapper `.felix-fiche`) : liste = topbar papier (back-link « Retour au chat » + brand) + chips de filtre par type + grille `EntityCard` ; fiche = en-tête monogramme + badge type, carte **Propriétés** (props libres en `<dl>` clé/valeur), carte **Relations** (rangées liées + flèche de direction `out`/`in`), carte **Chronologie** (#ordre + resume), `.fiche-foot`. Read-only et **schemaless** : on porte l'esthétique de la maquette (qui était un formulaire `:Character` figé) sans réintroduire de schéma.
- **Retrait du shell cyan orphelin** (toutes les pages sont désormais `layout:false`) : `layouts/default.vue` + `AppNavbar.vue`, et `SettingsPanel.vue` + `useSettings.ts` (panneau **lecture-seule** du modèle actif, info dispo via `/api/health`/env — réajouter en papier si besoin). `main.css` : retrait des utilitaires cyan morts (`.aged-texture`/`.tape-effect`/`.handwritten-note`/`.era-*`) ; **gardé** le bloc `@theme felix-*` (mappé `primary:'felix'` dans `app.config.ts`, encore lu par `@nuxt/ui`/`UApp`).
- **Vérif** : `typecheck` vert, `lint` 0 erreur (1 warning `v-html` pré-existant), **`nuxi build` prod OK** (✨ Build complete), dev server 3007 répond.
- **Au passage, bug produit révélé** (cf. HANDOFF ⚠) : maintenant qu'on VOIT ce que le bot écrit, on a constaté qu'un simple « salur » lui a fait **inventer un scénario de détective** et l'écrire dans le graphe. Hallucination réelle (rien de tel dans les prompts) → chantier `project_modeling_quality` priorisé.

## Bascule du front sur le schemaless — /chat + pages d'entités + purge totale du legacy — 2026-06-09

Le produit était **schizophrène** : deux modèles disjoints dans la même base Neo4j. Le legacy `:Character/:Location/:Scene/:RELATED_TO` (pipeline d'import, routes `/api/characters`…, tout le front dashboard/fiches) et le schemaless `:GenEntity/:REL` du copilote (bot B) — les pages « Personnages » ne voyaient **rien** de ce que le copilote créait (elles lisaient `:Character`, vide côté atelier). Décision actée avec l'utilisateur : **basculer 100 % schemaless** et **supprimer tout le legacy**. Exécuté en **2 commits** (bâtir le neuf, puis retirer le mort), l'app jamais cassée entre les deux.

- **Commit 1 — le neuf.** API lecture schemaless : `GET /api/entities?type=…` (liste, événements exclus) + `GET /api/entities/{id}` (fiche : props libres + relations hors machinerie `INVOLVES`/`NEXT`/`LOCATED_AT` + chronologie ordonnée). `core/graph.py` : `entity_events(driver, ref)` (rows `{ordre, resume}`) factorisé, `entity_timeline` s'appuie dessus (DRY). Modèles `Entity*` (`api/models.py`). Front : `/atelier → /chat` (l'ancien chat Q&A legacy supprimé), pages `/entities` (liste filtrable par type, onglets dérivés des données, deep-link `?type=`) + **fiche générique** (`<dl>` clé/valeur, relations liées, chronologie) **robuste à une structure non garantie**. `useEntities`/`useEntity`, `types/entities.ts`, `EntityCard`. Navbar recâblée (Chat/Personnages/Lieux/Objets/Entités), accueil → redirect `/chat`.
- **Commit 2 — purge (~85 fichiers).** Backend : `agent/` (chatbot lecture-seule legacy), routes `characters/chat/checks/groups/locations/timeline/export/ingest`, `graph/repositories/` + `graph/{checks,consistency,formatters,writer,seed}`, tout `ingest/` **sauf** `resolver.py`+`utils.py` (slugify/normalize, utilisés par `core/`), `cli.py`. Front : pages/composants/composables/`types/index.ts` legacy. Tuyauterie : `main.py` (routes + lifespan épurés : plus de `create_agent`/`ImportState`), `api/deps.py` (réduit aux deps atelier+entities), `api/models.py` (→ `ChatRequest` + `Entity*`), `graph/driver.py setup_constraints` (→ `genentity_id_unique` seule ; les contraintes legacy déjà en base restent inertes), `pyproject` (scripts `felix`/`felix-export` retirés, ignores morts), `justfile` (`evals`/`export` retirés). **Tests/evals legacy retirés aussi** (ils testaient du code supprimé) : `evals/{session,task,evaluators,ingest,pipeline,chatbot}`, `tests/integration/` + `tests/fixtures.py` + `test_segmenter` ; **conservés** `evals/atelier/`, `evals/generic/`, `tests/unit/{test_resolver,test_vectorstore}` (recâblés sans le bind Neo4j legacy).
- **Vérif (surface conservée, end-to-end).** `import felix.api.main` + sessions eval/test conservées OK ; `ruff check src evals tests` → **aucun F401/import mort** (le reste = motifs ruff pré-existants : TC001 sur les deps FastAPI, E402 `setup_logfire` avant imports, etc.) ; `curl` liste/filtre/fiche/404 OK sur « Le Nadir » (Vance : prop `role`, relations `FIGHTS`, chronologie #3→#12) ; **route SSE `/api/atelier/chat` vivante** post-purge (`text`→`usage`→`history`→`done`) ; front **typecheck vert** (16 erreurs → 0 : legacy supprimé + `AtelierIcon` durci sous `noUncheckedIndexedAccess` via un `FALLBACK` typé) et **lint 0 erreur** (1 warning `v-html` pré-existant). Moteur `core/`/`atelier/` **non touché** → pas de régression engine ; `e2e-atelier` (≈40 appels Mistral, instable) **non rejoué**, jugé inutile vu le diff (smoke SSE 1 appel + import-sanity suffisent).
- **Reste** : quick-wins moteur (vocab relations, relieur) et qualité de modélisation Mistral Small ([[project_modeling_quality]]) inchangés, toujours en attente. Deep-link par id depuis les cartes tool du chat (`AtelierMessage` pointe `/entities` générique pour l'instant) — amélioration future.

## Modèle événementiel v1 : checker temporel « mort puis agit » — 2026-06-08

v0 stocke les events ordonnés (`ordre`+`NEXT`). v1 leur donne un **usage** : un sens du temps pour le checker de cohérence. Principe acté avec l'utilisateur (« un état a un début et une fin ») : on ne **tamponne pas** la validité des états, on la **dérive** en donnant au juge la chronologie ordonnée de l'entité (calcul d'événements / fluents). **Eval-first**, et le TDD a **recadré le plan en cours de route**.

- **Le pivot (eval-first qui corrige l'hypothèse).** Cas A/B = même graphe final, **ordre des events inversé** : A « mort #1 puis agit #2 » (attendu alerte), B « agit #1 puis mort #2 » (attendu silence). Hypothèse de départ : « A échoue faute de chronologie ». **Faux** : A **passait déjà** (le juge triait les resumes en NL). Le vrai défaut était B en **FAUX POSITIF** : sur un voisinage non trié, le juge voyait « mort + action » coexister et alertait sans regarder l'ordre. Diagnostic isolé et déterministe via `/tmp/check_temporal.py` (le juge sur graphe fixe, 1 appel/cas) : **baseline 1/2** (A=alerte ✓, B=alerte ✗). La valeur de v1 n'est donc pas d'obtenir A mais d'**éliminer le faux positif B**.
- **Le cœur : une CHRONOLOGIE ordonnée injectée au juge.** Nouveau `entity_timeline(driver, ref)` (graph.py) : résout le sujet via `find_non_event` (un event n'est jamais sujet d'une chronologie, juste un maillon), puis requête **ciblée/indexée/triée** (`MATCH (ev:evenement)-[:INVOLVES]->(t {id}) RETURN ev.ordre, ev.resume ORDER BY ev.ordre`), rendue `#k : resume`. `consistency_check` la **concatène** au `neighborhood(ref)` (compose, pas de mutation ; pas de nouveau placeholder ; `""` si aucun event → contexte inchangé, auto-désactivation sans gate profil).
- **Wording exploitant l'ordre.** `CHECK_PROMPT` : la ligne temporelle générique devient « le sujet AGIT de lui-même à un event d'ordre SUPÉRIEUR à sa mort = contradiction ; ordre INFÉRIEUR ou ÉGAL = NORMAL, ne signale pas ; sans chronologie, statut terminal + nouvelle action = suspect ». Garde anti-faux-positif ajoutée : « un mort peut RESTER SUJET PASSIF (corps retrouvé, enterré, vengé, épave examinée) — seul son AGIR PROPRE après sa fin est impossible ; flash-back assumé non plus ». `SCENARIO_PROFILE.consistency_rules` rule 1 reformulée dans le même sens (« ne peut plus AGIR » vs « rester sujet passif »).
- **Mort = événement (fiabilise la dérivation).** `CHRONICLE_SYSTEM_PROMPT` : « une mort/destruction/fin EST un événement — relie la victime via add_event, pour qu'elle prenne son rang » + exemple Borin. Sans ça la mort risquerait de n'être qu'un prop `statut='mort'` sans `ordre`. L'e2e confirme : « L'intrus tue le technicien » est bien chroniqué comme event.
- **Bug latent attrapé (Plan agent).** `find_node("borin")` matchait aussi l'event « le Baron abat **Borin** » (name CONTAINS) → `LIMIT 1` sans tri pouvait rendre l'event → mauvais sous-graphe au check. **Durci** avec un tie-break `ORDER BY` (id-exact d'abord, puis non-événement) — strictement bénéfique pour tous les appelants (`find_entity`, dup-check `add_entity`, `update_entity`, `neighborhood`), et déterministe.
- **Vérif.** `check_temporal.py` **1/2 → 2/2** post-fix (B faux positif éliminé, A conservé). `compare_checker.py` **Small 6/6** inchangé (aucun piège à faux positif réveillé : Rust+AWS, '45'→'45 ans', couleur d'yeux, gros voisinage 3 villes). `check_act_then_death` **end-to-end vert** (extraction réelle → chroniqueur crée l'event de mort #3 → timeline triée → juge conclut « #1#2 avant #3 → cohérent »), `check_compatible_no_alert` vert. **e2e « Le Nadir »** : 5 tours, 0 erreur, 5 invariants verts (le prompt chroniqueur modifié ne régresse pas l'hygiène). **Backend Mistral en rafale de transients** (504/503/`exceeded max retries`/429/`request_limit 50`) → 6 échecs runtime sur la suite eval lourde (3 passes × 2 beats = grosse surface), **aucune régression** : chaque composant repasse isolément, et le cas A reste corroboré (baseline pré-fix + graphe fixe post-fix). Diff minimal : graph.py +48, check.py +20, dataset.py +47, agent.py +6, profile.py +6.

## Tiering modèle (Small vs Large) : testé, Small partout — 2026-06-08

Question parkée (`project_model_tiering`) tranchée **eval-driven** : faut-il un modèle plus fort par feature ? Câblé `build_checker_model()` dans `core/check.py` (au lieu de `build_chat_model()`) → le checker lit `FLX_LLM_CHECKER_MODEL` indépendamment de l'extraction (décou­plage propre, **neutre** : `.env` garde le checker en Small). Puis mesuré.

- **Large sur l'extraction (e2e Le Nadir, pacé)** : timeline cohérente (11 events, 0 doublon, 0 relation entité↔event — les invariants tiennent sur les DEUX modèles, nos fixes sont structurels), mais **nommage verbeux** (« Intrus du Nadir » → pire pour la résolution), et surtout **mur de rate-limit** : `429 Rate limit exceeded` dès le tour 2 (les passes font ~10-15 appels/tour ; Large throttlé bien en dessous de Small 5M tok/min). Pacing 65s/tour obligatoire. Coût 5-10×.
- **Large sur le checker (test contrôlé, 6 scénarios graphe-fixe)** : vrais positifs (alibi spatial, mort-puis-agit) + pièges à faux positifs (Rust+AWS, '45'→'45 ans', ajout neutre, **gros voisinage 3 villes** = la plaie historique) → **Small 6/6, Large 6/6**. Large n'apporte **rien** ; le prompt-engineering (reason-first, « différent ≠ incompatible ») a déjà mis Small au niveau.
- **Décision** : Small (`mistral-small-2506`) **partout**. Garder le câblage `build_checker_model` comme option dormante (tiering = un env var si un cas futur le justifie). Vérif : checker via la nouvelle voie passe `-k check` 2/2.

## E2E route atelier (SSE in-process) + Le Nadir validé sur code frais — 2026-06-08

Les evals protest **shuntent la route** (`run_atelier_case` appelle `agent.run()` direct) → les bugs de câblage (3 passes, chroniqueur sans `message_history`, ordre des events SSE) leur échappent. Nouveau harness `evals/atelier/e2e.py` (`just e2e-atelier`) : joue « Le Nadir » multi-tours contre la **vraie route SSE**, **in-process** (httpx ASGITransport sur l'app FastAPI → code TOUJOURS à jour, pas de serveur à relancer), re-injecte le `history` SSE au tour suivant comme le front, puis **asserte les invariants** (events bornés < 3×tours, 0 doublon de resume, 0 relation entité↔event, ordres distincts/complets, Vance=personnage), **exit 1** si cassé.

**Validation décisive** : sur code frais, « Le Nadir » 5 tours → **7-9 events** (contre **63** en live), 0 doublon, 0 relation entité↔event, intrus créé comme personnage. Confirme que les 63 events du test live = **fantôme du code stale** (le serveur tournait le chroniqueur AVEC historique, fix round 1 pas rechargé) — les fixes round 1/2 tiennent de bout en bout. Reste cosmétique (round 3) : typage variable (« Le Nadir » lieu/objet selon run), quasi-doublon d'entité (« cadavre » / « cadavre du technicien »), et resserrage fin de la sur-extraction. Garde notée en mémoire `reference_e2e_atelier`.

## Modèle événementiel — bugfixes live round 2 (relations vers events, doublons) — 2026-06-08

2e test live « Le Nadir » → graphe inspecté : **63 events pour ~6 tours**, 3 familles de bugs.

- **Relations entité↔ÉVÉNEMENT (corruption).** `add_relation` (relieur) résolvait ses extrémités via `find_node`, qui matche les nodes evenement → `vance -[FIGHTS]-> event-11`, `event-33 -[KNOWS]-> capitaine`, `event-35 -[OWNS]-> combinaison`. **Fix** : helper `find_non_event` (exclut `entity_type='evenement'`), utilisé par `add_relation` (2 extrémités) ET `add_event` (participants, en remplacement de la requête inline). Un événement ne se relie qu'via add_event (INVOLVES/NEXT/LOCATED_AT). Garde : evaluator `relations_skip_events` (gate) + set `ENTITY_ONLY_RELS`.
- **Events en double.** Le chroniqueur appelle add_event 2× pour la même action dans une réponse → `add_event` **dédup par resume** (skip si un event au resume identique existe déjà). Garde : `events_distinct`.
- **Volume (63) = en partie STALE.** Le serveur tournait encore le chroniqueur AVEC historique (le fix `message_history=None` de round 1 n'était pas rechargé) → re-chroniquage à chaque tour. **Restart `felix-api` requis** pour charger le fix.
- **Reste (round 3, eval-first sur données fraîches).** Sur-extraction PAR TOUR : chaque sous-clause devient un event, et les « Vance réalise que… / comprend que… » (pensées) sont traités comme des actions → resserrer `CHRONICLE_SYSTEM_PROMPT` (max strict, exclure les états mentaux, garder les actions externes). Intrus décrit indirectement jamais créé comme `personnage` (trou de passe 1). Le Nadir typé `objet` au lieu de `lieu`.
- **Vérif** : `event_chrono` + `event_no_bleed` verts (`rels_clean_ok=✓`, `distinct=1.0`, `stray=0`) ; `find_node` matchait bien un node evenement, `find_non_event` non (déterministe).

## Modèle événementiel — bugfixes du test live « Le Nadir » — 2026-06-08

Test live du v0 par l'utilisateur → 3 bugs que l'eval propre (`event_chrono`, 3 actions nettes) ne montrait pas. Reproduits via un cas plus dur (`event_no_bleed` : 1 tour DESCRIPTIF puis 1 tour à événements, le scénario réel de l'utilisateur).

- **Bug 1 — re-chroniquage de l'historique (doublons cross-tour).** Le chroniqueur recevait l'historique de conversation (Option B) → au tour 2 il recréait des événements du tour 1 (« Vance patrouille » ×3, absents du tour 2). **Fix** : le chroniqueur tourne **sans `message_history`** (route + harness eval) — il ne chronique que le beat courant et (re)découvre les entités via le graphe. Bug **structurel** : il ne peut plus re-chroniquer ce qu'il ne voit pas.
- **Bug 2 — auto-INVOLVES (mon code, déterministe).** `add_event` résolvait les participants via `find_node`, qui matche n'importe quelle `GenEntity` — y compris le node événement qu'on vient de créer (même nom) → INVOLVES event→lui-même. Prouvé déterministe (find_node renvoie le node evenement). **Fix** : résolution des participants restreinte aux entités **non-événement** (`entity_type <> 'evenement'`), jamais soi-même.
- **Bug 3 — participants dupliqués** (« Le Nadir, Le Nadir »). **Fix** : dédup des participants résolus (set d'ids). NB : l'acteur manquant (IA de bord non créée en entité) reste un trou de passe 1, secondaire.
- **Eval-first** : bug 2 prouvé déterministe (find_node direct) ; bugs 1/3 = variance LLM (le cas tombait parfois sur le chemin propre) → cas `event_no_bleed` + evaluators `involves_only_entities` (aucun INVOLVES vers un event) et `events_distinct` (pas de resume en double) comme garde. **Après fix : `event_no_bleed` vert ×2** (`chain_len=2`, `distinct=1.0`, `involves_clean=✓`), `event_chrono` non-régressé (`chain_len=5`). Backend Mistral très instable ce jour (400/503/request_limit sur retries) → 2 échecs runtime transients entre les passes propres (17 appels = pas une boucle), pas des régressions.

## Modèle événementiel v0 : nodes `evenement` ordonnés (état vs événement) — 2026-06-08

Le test live « Le Nadir » montrait les ACTIONS écrasées dans une prop mutable du perso (chronologie perdue, seul le dernier geste survit). v0 du modèle événementiel, **eval-first**, ontologie et topologie tranchées avec l'utilisateur.

- **Ontologie** : un ÉVÉNEMENT = une action qui SE PASSE à un instant (« tire », « le réacteur explose ») ; un ÉTAT = ce qui TIENT (« est ingénieure », « a un bras mécanique »). Test opérationnel (trouvé par l'utilisateur) = **« quand ? »** : réponse = un instant → événement ; absurde (ça tient) → état. Conséquence (calcul d'événements) : un état est un **intervalle borné par des événements** → on stocke les events (les bornes) et on dérivera la validité d'état en **v1**, sans rien tamponner maintenant. Anti-explosion (« le moindre verbe est un event ? ») : le chroniqueur ne parse pas chaque verbe, il **RÉSUME** le beat en 1-3 actions-clés.
- **Mécanisme** : tool déterministe `add_event(resume, participants, lieu)` (core/tools.py) → node `:GenEntity {entity_type:'evenement', resume, ordre}`, id `event-{ordre}` (**pas** de slug : deux actions proches ne doivent pas fusionner), `ordre` auto-incrémenté **EN CODE** (neuro-symbolique, pas le LLM), chaîne `NEXT` depuis l'event précédent, `INVOLVES`/`LOCATED_AT` vers participants/lieu existants. **Lock `event_seq_lock`** (sur le deps) : pydantic-ai exécute les `add_event` d'une même réponse **en parallèle** → sans lock, `max(ordre)+1` concurrent collisionne sur le même id (bug attrapé en eval : `ConstraintValidationFailed event-1`).
- **Topologie 3 passes** (choix utilisateur, cohérent « petits appels spécialisés ») : passe 1 entités/état durable → passe 2 relieur (relations) → passe 3 **chroniqueur** (événements). Chroniqueur = agent à outils **restreints** (lecture + `add_event`) + `CHRONICLE_SYSTEM_PROMPT` (résumé 1-3 events, few-shot état-vs-événement). Pas de boucle sur outil manquant (le piège du relieur restreint) car `add_event` **absorbe** les participants absents (retour normal).
- **Coordination (crainte de l'utilisateur, confirmée puis réglée au niveau DONNÉES)** : passe 1/relieur fabriquaient des entités-événement parasites (`sabotage-du-vaisseau`, sans `ordre`, hors chaîne). 1er correctif (retrait du type `evenement` du profil + règle positive « une action n'est NI prop NI entité ») a réduit mais pas éliminé (revenu par variance en suite). **Correctif robuste** : `Profile.manages_events` + **garde dans `add_entity`** qui refuse de créer une entité `evenement` quand le domaine gère la chronologie (retour normal → pas de boucle). Scopé scénario (générique `profile=None` et chantier `manages_events=False` intacts). Résultat : `stray_events=0`, stable.
- **Eval-first** : cas `event_chrono` (3 beats d'action Vance). Evaluators `graph_has_events` (recall des actions parmi les nodes evenement), `events_ordered` (**gate = la colonne `ordre`+`NEXT`** ; les strays = métrique `stray_events` **non-bloquante**, pour suivre la dérive de coordination sans flaker l'eval du modèle), `events_involve`. **Baseline** (code actuel) : `event_count=0`, actions perdues en relations `TARGETS`/`KNOWS`. **Après** : `event_recall=1.0`, chaîne ordonnée complète (`chain_len=5`), `involve=1.0`, `stray=0`. Câblé **route SSE** (3e passe non-streamée → une seule bulle, usage sommé) + **harness eval** (3 `.run()`/beat sur le même deps). Refactor au passage : boucle de check extraite en `_consistency_alerts` (PLR0912).
- **v1 documenté (pas fait)** : dériver la validité des états (checker « mort puis agit »). Quick-wins restants : (2) vocab `COMMANDS/HELPS/TRANSPORTS`, (3) relieur qui re-update.

## Extraction de relations : vocab canonique anglais + 2e passe « relieur » (décompo) — 2026-06-08

L'eval `roue_de_sang` a montré les relations comme dimension faible (`rel_recall` ~0.6, noms qui dérivent). Plan en 3 phases, **eval-first**, décompo en sous-agents assumée par l'utilisateur.

- **Phase 0 — baseline** (`/tmp/measure_relations.py`, 3 beats fixes, N runs) : recall **0.52**, dérive ~totale (off_vocab ~1.0, noms FR libres `decouvre`/`porte les preuves`/`draine l'essence vitale`…), **2 runs sur 5 à zéro relation** (sous-extraction extrême).
- **Phase 1 — vocab canonique EN + règle renforcée.** Nouveau champ `Profile.relation_vocabulary: tuple[(PRÉDICAT_EN, glose_FR)]` rendu dans `render_prompt_block`/`render_schema_hint` ; `SCENARIO_PROFILE` = 12 prédicats `UPPER_SNAKE` (`LOCATED_AT, MEMBER_OF, OWNS, KNOWS, ALLIED_WITH, FIGHTS, KILLS, CREATES, TARGETS, CAUSES, PART_OF, WITNESSES`). Règle 3 du `SYSTEM_PROMPT` renforcée (relier APRÈS les entités). Docstring `add_relation` → types canoniques. Nouvel evaluator `rel_vocab_coverage` (métrique de dérive, non-gating). **Résultat : off_vocab 1.0 → 0.0 (dérive réglée), mais recall ~0.44 (sous-extraction persiste)** — split prévu.
- **Phase 2 — sous-agent « relieur » (2e passe).** `create_core_agent` accepte `tools=` et `system_prompt=` (rétro-compatibles). `build_relation_agent` + `RELATION_PERSONA` + `RELATION_SYSTEM_PROMPT` (discipline focalisée relations). Préconstruit par profil (`app.state.relation_agents`, `RelationAgentsDep`). Route : 2e passe en **`.run()` non streamée** après l'agent d'entités (cartes seules via `deps.ui_events` partagé → **une seule bulle**, usage sommé, history = agent d'entités seul). Eval task : 2 `.run()`/beat sur le même `deps` (Option B : historique d'avant-beat partagé). **Piège résolu** : relieur d'abord restreint aux outils lecture+`add_relation` → il bouclait en erreur (« Exceeded max retries ») quand le texte mentionnait une entité ratée par la passe 1 (il tentait `add_entity` non outillé). Fix : **noyau complet** + discipline qui priorise les relations et autorise le backfill d'entité. **Résultat : recall 0.44 → 0.80, 0 run à zéro relation**, off_vocab ~0.18 (un run anomal).
- **Infra** : `.env` pinné `mistral-small-2506` (5M tok/min, 20.83 req/s — le `latest`→2603 throttlé à 100k causait les 429). Mistral instable ce jour (503/504 transitoires) → scripts de mesure rendus résilients (retry 5xx).
- **Vérif : suite atelier 13/13 verte** (roue_de_sang inclus, `rel_recall` ≥0.8). 2 corrections d'eval au passage : `entity_unique` passé en match exact puis restreint aux 2 leads (« Baron Arkham » a une forme variable qui faisait flaker l'exact) ; message de `explicit_correction_overwrites` désambiguïsé (le « son » orphelin faisait créer une entité bidon « alibi »). Les échecs intermittents observés = transients Mistral (« Tool exceeded max retries »), pas des régressions (chaque cas repasse seul).
- **Reste** : seuil `relations_present` aspirationnel 0.8 (atteint) ; verrue type `organisation/faction` (Milice=lieu) toujours hors-scope ; tiering modèle parké (cf. mémoire).

## Eval scénario multi-beats « La Roue de Sang » (extraction cumulative + résolution) — 2026-06-08

Le harness atelier était mono-tour. Étendu pour jouer un **scénario complet beat par beat** sur le même graphe (comme l'usage réel « je raconte au fil de l'eau »), ce qui teste ce qu'aucun cas ne testait : l'**extraction cumulative** et la **résolution d'entité** (Silas = 1 nœud sur 7 tours, pas un doublon).

- **Harness** (`evals/atelier/task.py`) : `run_atelier_case` accepte `inputs["beats"]` (liste de messages joués en séquence, historique threadé `result.all_messages()`, pas de wipe entre beats). Sémantique mono-tour préservée (`beats = [message]`). `AtelierRunResult` expose désormais `entities` (tous types) + `relations` en plus de `characters`.
- **Evaluators** (`evaluators.py`) : `graph_has_entities` (recall sur toutes entités), `entity_unique` (chaque protagoniste = exactement 1 nœud → LE test de résolution), `relations_present` (paires from→to souples, sens ignoré). Recalls souples (seuils 0.8 / 0.6) pour absorber la variance ; `entity_unique` strict.
- **Cas `roue_de_sang`** : les 7 beats du scénario steampunk noir (Silas/Éléonore/Arkham/Athanor…). Vérifie recall entités ≥0.8, unicité Silas/Éléonore/Arkham, relations clés ≥0.6.
- **Run réel : 1/1 vert.** Le 429 initial venait du modèle : `.env` était sur `mistral-small-latest` → résout vers `2603` (100k tok/min) ; un run threadé fait ~85k tokens → plafond frôlé. **Pinné `.env` sur `mistral-small-2506`** (5M tok/min, 20.83 req/s — cohérent avec la direction « beaucoup de petits appels parallèles »). Re-run : `entity_recall=1.0`, résolution OK, `rel_recall` 0.6-0.8.
- **Bug d'evaluator corrigé** : `entity_unique` matchait en sous-chaîne → « Supérieur de Silas » comptait comme un 2ᵉ « Silas » (faux positif, même travers que le checker). Passé en **match exact** (nom/id normalisé, noms canoniques). Silas/Éléonore/Arkham = 1 nœud chacun confirmé. Seuil `relations_present` gardé **aspirationnel à 0.8** (l'extraction de relations est la dimension faible ~60-80 % ; cible à atteindre en améliorant, pas à baisser — prochain chantier).
- **Verrues confirmées par le run** (cibles qualité suivantes) : Milice du Cuivre typée `lieu` (manque type `organisation/faction`) ; dérive des relations (`se_rend_chez`/`se_rend_à`/`infiltre`/`atteint`/`duel`…) ; `alibi` détourné en statut ; conflation `Silas sacrifie → cœur de la victime` (alors qu'il sacrifie son bras) ; slugify casse sur la ligature œ (`c-ur-mecanique-aux-runes`). Mono-tour (`create_simple`) 1/1 après refactor.

## Bornage scénario : retrait du multi-profil front + passe overwrite-vs-add — 2026-06-08

Décision actée (cf. mémoire direction produit) : **borner le produit au scénario**, garder le moteur schemaless + `SCENARIO_PROFILE` + le check, abandonner l'ambition agnostique.

- **Front débarrassé du multi-templates** : sélecteur de profil retiré de `atelier.vue` (topbar + handlers + CSS), refs `profile/profiles/loadProfiles/setProfile` retirées de `useAtelier.ts`, le POST n'envoie plus `profile` → `ChatRequest.profile` défaut « scenario ». Backend (`ATELIER_CHOICES`, `GET /profiles`, modes chantier/none) **conservé** comme outil d'eval/preuve. eslint clean, curl sans `profile` OK.
- **Passe qualité modélisation, eval-first** (overwrite vs add — la vraie perte de donnée scénario ; le « sur-usage de role » était surtout un artefact chantier/contamination, éteint par le bornage). Baseline mesuré (`/tmp/measure_overwrite.py`, N=6×2 formulations) : l'agent ne faisait **jamais** « garde l'ancien + ajoute le nouveau » (0/12) — soit il écrase, soit il ignore. **Cause** : la règle 2 (réutilise les clés existantes) primait sur la règle 4 → réutilise `alibi` donc remplace. **Fix** : `SYSTEM_PROMPT` règle 4 rendue opérationnelle (« nouvelle clé, ceci PRIME sur la règle 2 ») + exemple concret (few-shot alibi/témoin) dans `SCENARIO_PROFILE.modeling_rules`. **Résultat** : formulation impérative 0/6 → **6/6** add correct.
- **Evals** : 2 nouveaux cas (`diverge_adds_keeps_old`, `explicit_correction_overwrites`) + evaluator `char_props` (sous-chaînes attendues/interdites dans les props d'un perso). Atelier **12/12** (et `check_contradiction` devient fiable : garder les deux valeurs rend la contradiction visible). Generic 15/17 = haut de la bande de variance, pas de régression.
- **Reste connu** : la formulation narrative/ouï-dire (« un témoin jure l'avoir vu à Lyon ») est **sous-extraite** (0/6 : garde l'alibi mais n'écrit pas le témoignage) — bug distinct de l'overwrite, non traité ici.

## Checker : carte lisible (message court) + dédup, et graphe remis à zéro — 2026-06-07

Suite au test live de l'atelier : le checker de cohérence marchait (il attrapait bien les contradictions sémantiques), mais l'UX était mauvaise — la carte « Incohérence possible » affichait le **CoT brut** du judge (« 1. Analyse… 2. Comparaison… 4. Conclusion ») et la **même** contradiction apparaissait en **double** (une carte par entité touchée, voisinages qui se recouvrent).

- **`CheckVerdict` + prompt** (`core/check.py`) : ajout d'un champ `message` (défaut `""`) **après** `contradiction` — donc généré une fois le verdict posé (reason-first préservé : `reason` reste le brouillon interne, jamais affiché). Le prompt demande, si contradiction, UNE phrase concrète pour l'auteur, sans numérotation ni jargon (« écriture récente », « propriété »…). Live : « Renaud est interdit de parler de la fête du choux mais explique à Sarah qu'il y est allé. » (89 car).
- **Route** (`api/routes/atelier.py`) : la carte affiche `message` (`reason` en filet de secours) ; **dédup** par tour (`set` sur le texte normalisé) → une seule carte par contradiction distincte.
- **Vérif** : evals atelier 10/10 (le seul fail transitoire = variance agent qui *écrase* l'alibi au lieu de l'ajouter → plus de contradiction à voir ; repassé 1/1 au rejeu). Hot reload `fastapi dev`, pas de restart.
- **Régression corrigée** : la variable locale ajoutée s'appelait `body`, qui shadowait le paramètre de requête `body` de la route → `UnboundLocalError` à chaque tour (« cannot access local variable 'body' »). Renommée `alert_body`. Pyright l'avait signalé, balayé à tort avec le bruit d'imports. Re-vérifié en live (HTTP) : `text/usage/history/done`, plus d'`event: error`.
- **Précision resserrée (faux positif)** : le juge sonnait sur Atn-tech « spécialisée en Rust » → « gère l'OBS avec AWS/Kube » (overwrite de l'agent), alors que les deux peuvent coexister. Le `CHECK_PROMPT` confondait « valeur remplacée » et « valeurs incompatibles ». Reformulé : ne signaler que si deux faits ne peuvent pas être vrais ENSEMBLE pour le même sujet (interdiction violée, deux lieux au même instant, états exclusifs…) ; « différent ≠ incompatible », une MAJ vers une valeur qui pourrait coexister n'est pas un conflit. **Piège évité** : une 1ʳᵉ version trop stricte (« ne signaler que si impossible ») tuait les vrais positifs (violer une interdiction n'est pas « impossible »). Banc de précision (`/tmp/check_precision.py`) 4/4 : Atn-tech non, choux oui, Marseille∧Lyon oui, ajout d'âge non. Evals atelier `-k check` 2/2. NB : la cause amont reste l'agent qui **écrase** au lieu d'ajouter (perte de l'info Rust) → chantier modélisation à froid.
- **Graphe remis à zéro** (demande explicite) : contaminé par les tests successifs (types `plante` reliquats, props `role`/`intervenant` chantier sur des `personnage` scénario). Repartir propre, un domaine à la fois, pour juger le modèle sans le bruit. Reste à attaquer **à froid** : la sur-utilisation de `role` par le modèle (« chien » → `role='chien'`), vrai sujet de qualité de modélisation (few-shot / `modeling_rules`).

## Fix « réponse coupée » de l'atelier = DEUX bugs front, pas le SSE — 2026-06-07

Symptôme rapporté : réponses Felix « coupées / pas finies » dans `/atelier`. Deux bugs distincts, le premier masquait le second.

**Le SSE est innocenté (3 preuves)** : (1) au niveau pydantic-ai, `stream_text(delta=True)` == `run.result.output` au caractère près ; (2) capture des **octets SSE bruts sur HTTP** → texte complet, flux terminé par `event: done`, tous les chunks `text` présents ; (3) `apiStreamBase` tape le backend en direct (pas via le `devProxy`). La repro décisive : le SSE contenait **3 events `text`** mais le front n'en affichait **qu'un**.

**Bug n°1 — rendu markdown garbled.** `AtelierMessage.vue` rendait le body via un `split(/(\*[^*]+\*)/g)` maison écrit pour les *titres d'œuvres* en italique (un seul `*`). Felix répond en **`**gras**`** : la regex appaire les `**` **en quinconce** et **écrase les `\n`**. Retracé → reproduit le copier-coller utilisateur (`*Cathia : - Propriétés*`) mot pour mot. 0 caractère perdu, mais illisible. **Fix** : rendu via `marked` (`{breaks,gfm}`) + `v-html`, comme `ChatMessage.vue` legacy ; CSS `.felix-text` étendu (strong, em doré, listes, code, blockquote) en thème papier.

**Bug n°2 — LA vraie troncature (réactivité Vue), démasquée par le fix n°1.** Le composable accumule le texte via `current.body += sse.data`, mais `append()` renvoyait l'objet **brut** poussé dans le tableau, pas le **proxy réactif**. Mutation brute = aucune dépendance déclenchée ; avec un `:key` stable, l'enfant `AtelierMessage` (computed sur `props.msg.body`) **ne re-render qu'au 1ᵉ chunk** → figé sur le premier event `text`. Prouvé avec `@vue/reactivity` : brut → `childRenders:1` (vide) ; proxy → `chunk1+chunk2+chunk3`. **Fix** d'une ligne : `append()` retourne `messages.value[len-1]` (le proxy). Le `messages.value = [...]` du case `text` devient redondant (gardé, inoffensif, prouvé compatible). Bug **préexistant** au fix n°1 — le garbling le camouflait.

**Note modélisation (question « FastAPI devrait être un node ? »)** : oui, idéalement techno = `:GenEntity` avec relations (`X -utilise-> FastAPI`). Ne s'est pas produit car le domaine *projet logiciel* était testé sous le profil **scénario** (types personnage/lieu/événement/objet, aucune case techno) dont les `modeling_rules` poussent à mettre les caractéristiques en propriété → FastAPI noyé dans un `background`. Pour ce contenu : mode **noyau nu** (laisse émerger un type `technologie`) ou profil dédié. Conforte l'intérêt du sélecteur de profil.

**Vérif** : eslint clean (1 warning `v-html` attendu, identique à ChatMessage) · rendu `marked` validé en CLI (bold/listes/paragraphes) · diagnostic SSE concluant.

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
