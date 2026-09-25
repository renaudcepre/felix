# Profil maintenance + ingestion de fiches techniques

Branche `feat/maintenance-profile`. Cible : démo « intégration dans un RAG
documentaire » — une fiche procédure PDF devient un graphe
interrogeable, chaque fiche du graphe traçable jusqu'à sa page source.

Échantillon réel : une fiche procédure client (PDF, hors repo).
**Donnée CLIENT : jamais copiée dans le repo, jamais dans un prompt ni un test,
jamais envoyée à l'API sans accord explicite de Renaud.** Elle sert seulement de
modèle de FORME (en-tête version/créateur/valideur, liste de repères machine,
sections Boutons/Voyants/Paramètres, consignes de sécurité, unités, pied de page
répété « Page X sur N / Fait avec <outil> », beaucoup d'images non textuelles).

Univers anti-fuite ([[feedback_prompt_test_leakage]]) :
- exemples de PROMPT : presse plieuse « PL-7 » (tablier, butée arrière, pédale,
  force de pliage en tonnes, vitesse d'approche) ;
- fixtures de TEST/EVAL : sertisseuse « SX-40 » (fiche synthétique écrite pour
  l'occasion, même forme que la fiche client, contenu inventé).

## Étape 1 — Profil + chat multi-domaine (moteur)

1. `MAINTENANCE_PROFILE` (`core/profile.py`), `manages_events=False`,
   `narrative_rel=NARRATIVE_REL` (filet anti-trou de vocab).
   Types : `machine` (modele, reperes, fabricant, site) · `organe` (fonction,
   emplacement) · `commande` (nature bouton/voyant/sélecteur, role, emplacement)
   · `parametre` (unite, plage, valeur_usuelle, contrainte) · `mode`
   (description, usage) · `consigne` (texte verbatim, gravite, motif) ·
   `document` (titre, version, date_maj, auteur, valideur).
   Relations : PART_OF, CONTROLS (commande→parametre|mode|organe), INDICATES
   (commande→organe|parametre|mode), APPLIES_TO (consigne|mode|parametre|
   document→machine|organe|commande|parametre), DEPENDS_ON (parametre→parametre),
   DESCRIBED_IN (tout type→document, posée PAR LE CODE à l'ingestion).
   Règles de modélisation : valeurs/unités/plages = props VERBATIM, jamais
   calculées ; liste de repères = UNE prop `reperes`, pas N entités ; mise en
   garde / interdiction = entité `consigne` + APPLIES_TO ; boilerplate (n° de
   page, pied de page, légende d'image vide) = rien ; un paramètre répété dans
   la fiche = la MÊME entité.
   Règles de cohérence : deux sources donnent unité/plage/valeur différentes
   pour un même paramètre ; une consigne interdit ce qu'une autre recommande ;
   une valeur déclarée viole une contrainte déclarée (A ≥ B).
2. `AgentChoice` porte AUSSI `master_prompt` et `gate_prompt` (aujourd'hui
   codés en dur « scénario »). Maintenance : maître = assistant documentaire
   qui RÉPOND aux questions depuis la base (lecture seule, « pas dans la
   documentation » si absent, n'invente jamais une valeur) ; gate = « le
   message affirme-t-il un fait technique ? ». Gate construit PAR PROFIL
   (`app.state.gate_agents`), comme les autres passes.
3. Chroniqueur sauté quand `profile is None or not profile.manages_events` —
   règle systémique (un helper unique, utilisé par la route ET l'ingestion).

## Étape 2 — Ingestion de document

1. `felix/ingest/document.py` : PDF → pages (`pypdf`), nettoyage générique
   (lignes répétées sur ≥ 50 % des pages + motifs « Page X sur N »), découpage
   en blocs bornés (par page, fusion des petites, coupe des grosses), chaque bloc
   préfixé « Extrait de « titre » (page p/N) ».
2. Pipeline d'extraction PARTAGÉ route/ingestion (entités → relieur →
   [chroniqueur si events]) : un seul code, pas une copie.
3. `ingest_document(...)` : crée l'entité `document` EN CODE, passe chaque
   bloc (sans gate ni maître : un document EST du contenu), pose DESCRIBED_IN
   {page} en code pour chaque entité touchée, lance le check de cohérence.
   Retourne un résumé (entités, relations, alertes, tokens).
4. `POST /api/ingest/document` (upload + profile + project) + CLI
   `tools/ingest_doc.py` + recette `just ingest-doc`.

## Étape 3 — Front

Sélecteur de mode dans la topbar de /chat (`GET /api/atelier/profiles`,
passe `body.profile`) + bouton « Importer une fiche » (upload PDF → route
d'ingestion, affiche le résumé).

## Étape 4 — Mesure

Eval live sur la fiche synthétique SX-40 (pas la fiche client) : paramètres
avec unité verbatim, consigne en entité, CONTROLS commande→paramètre, zéro
entité boilerplate, zéro valeur calculée, DESCRIBED_IN sur 100 % des entités.

## Limites connues (à dire en démo)

- Les photos des boutons/voyants sont perdues (texte seul) : la fiche client
  est à moitié en images. Suite possible : légendes par modèle vision.
- Qualité d'extraction sur texte technique jamais mesurée avant ce chantier.
