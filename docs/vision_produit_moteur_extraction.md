# Vision produit — Moteur d'extraction texte → graphe *fiable*

> Document de **vision produit** (pas d'implémentation). 2026-06-07.
> Nom de travail : *à définir* (ex. « Veritas », « Coherent », « Felix Core »). Le nom n'engage rien ici.
> Statut : **option documentée**. Produit issu du cœur technique de Felix. Le produit « copilote scénario » (B) est traité séparément et reste la direction prioritaire — voir la dernière section.

---

## En une phrase

**On transforme du texte non structuré en graphe de connaissances — et surtout, on le rend *fiable* :** entités dédupliquées, relations non hallucinées, contradictions détectées. C'est « la couche de confiance que les outils text-to-graph actuels n'ont pas ».

---

## Contexte & origine

Felix (assistant scénario) a, sans le vouloir, produit un cœur technique réutilisable et différencié : un pipeline qui lit du texte, en extrait des entités et des relations, les range dans un graphe, **et vérifie leur cohérence**. Ce cœur n'a rien de spécifique au cinéma — il marche pour n'importe quel corpus de texte.

La question qui a déclenché cette vision : *« est-ce vendable ? »* La réponse honnête après vérification du marché : **l'extraction texte→graphe est en train de se commoditiser, mais sa fiabilité, non.** C'est là qu'est l'espace produit.

## Le problème

Extraire un graphe depuis du texte avec un LLM est devenu trivial : Microsoft GraphRAG, le [Neo4j LLM Knowledge Graph Builder](https://neo4j.com/labs/genai-ecosystem/llm-graph-builder/), LlamaIndex le font tous en quelques lignes (un LLM + un prompt → JSON → graphe).

**Mais tous héritent du plafond de qualité du LLM, et aucun ne le corrige.** La littérature 2025 est sans appel :
- l'hallucination est *« inhérente, inévitable »* aux LLM ;
- ils **inventent des relations sur des paires non reliées** — détecter l'*absence* de relation est leur point faible ([source](https://arxiv.org/pdf/2508.14391)) ;
- ils sont *« eager to find an answer »* → **sur-extraction** et doublons ;
- *« lost in the middle »* dès que le contexte grossit.

Résultat concret pour l'utilisateur de ces outils : **un graphe sale** — entités dupliquées, relations fantômes, contradictions silencieuses. Le nettoyage est manuel et ne passe pas à l'échelle. Personne ne vend la propreté.

## Pour qui

Toute équipe ou produit qui **construit un graphe de connaissances à partir de documents et ne peut pas se permettre qu'il soit faux** :
- veille / intelligence économique / due diligence (relier des acteurs, dates, faits issus de centaines de docs) ;
- recherche & synthèse documentaire ;
- conformité / juridique (traçabilité des faits, contradictions entre pièces) ;
- **mémoire long terme d'agents IA** (un graphe propre comme socle de raisonnement, là où le RAG brut dérape).

Point commun : ces gens préfèrent **moins de faits mais justes** à beaucoup de faits douteux.

## Proposition de valeur

> Tu envoies du texte. Tu reçois un graphe **+ un rapport de fiabilité** : ce qui a été fusionné, ce qui se contredit, ce qui est incertain — avec un lien vers le passage source de chaque fait.

On ne vend pas « l'extraction » (commodité). On vend **la confiance dans le graphe**.

## Le différenciateur (moat)

Trois capacités que les wrappers LLM n'ont pas, et qui existent déjà dans le cœur de Felix :

1. **Résolution d'entités** — déduplication, gestion des alias, et surtout *refus de fusionner* quand des signaux discriminants l'interdisent. « Le graphe ne se remplit pas de dix variantes de la même entité. »
2. **Détection de contradictions / cohérence** — vérifications temporelles (dates impossibles, anachronismes, ordre des événements) et factuelles (un fait nouveau contredit un fait établi). Le graphe *se souvient* et *contredit*, là où le LLM seul oublie.
3. **Architecture neuro-symbolique « extraire large, corriger ensuite »** — on laisse le LLM extraire généreusement, puis une **couche symbolique** (règles, similarité, contraintes) valide, fusionne et corrige. Cette approche coûte moins d'appels LLM pour *plus* de cohérence — c'est l'état de l'art récent ([OAK+MEND, 2026](https://arxiv.org/html/2605.29168)). C'est exactement ce que Felix fait déjà.

`Le LLM propose, le symbolique dispose.`

## Forme du produit : service / API

- **Entrée** : du texte ou des documents (un appel, un lot, ou un flux incrémental).
- **Sortie** : un graphe (entités, relations typées, événements *qui-fait-quoi-quand-où*) **+** un rapport d'*issues* (contradictions, doublons fusionnés, faits à faible confiance).
- **Agnostique au domaine** : pas de schéma figé « scénario ». Types d'entités/relations génériques, **optionnellement guidés par un schéma/ontologie fourni par le client** (« voici mes types d'entités, extrais selon ça »).
- **Incrémental & idempotent** : réinjecter des documents *met à jour* le graphe sans le polluer — la résolution d'entités garantit qu'on n'empile pas les doublons. C'est une propriété produit majeure (la plupart des outils repartent de zéro à chaque run).

## Positionnement concurrentiel

| | Ce qu'ils font | Ce qui manque | Notre angle |
|---|---|---|---|
| **GraphRAG / Neo4j LLM KG Builder / LlamaIndex** | Extraction LLM → graphe, dédup basique | Pas de couche cohérence ; sortie LLM brute déversée dans le graphe | On ajoute la **fiabilité** par-dessus la même brique |
| **NER classique (spaCy, etc.)** | Rapide, déterministe | Aucune compréhension contextuelle ; relations pauvres | LLM contextuel **+ garde-fous** symboliques |
| **Solutions internes maison** | Sur-mesure | Coûteuses à maintenir, fiabilité non outillée | Fiabilité **prête à l'emploi**, mesurable |

Message marketing en une ligne : *« GraphRAG construit le graphe. Nous, on garantit qu'il est juste. »*

## Capacités produit (niveau produit)

- Extraction d'entités **contextuelle** (le sens, pas juste les mots).
- Relations **typées** + événements (sujet → action → objet, daté/localisé).
- **Résolution / déduplication** d'entités, avec alias.
- **Rapport de cohérence** : contradictions temporelles, contradictions factuelles, doublons.
- **Score de confiance par fait**, avec **traçabilité** vers le passage source (auditable).
- **Mode incrémental** : un monde qui grandit sans se polluer.

## Ce qu'on réutilise du cœur de Felix

Conceptuellement (les détails techniques sont hors de ce document) : le pipeline d'ingestion, le graphe, la résolution d'entités et le moteur de cohérence existent déjà. Le seul vrai travail produit pour passer de Felix à ce moteur est de **« dé-spécialiser » le domaine** : ce qui est aujourd'hui pensé en *scène / personnage / époque* doit être exprimé en *document / entité / période*. **Aucun acquis n'est jeté** — on enlève l'habillage cinéma, on garde le moteur.

## Risques & questions ouvertes

- **Marché concurrentiel et qui bouge vite.** Les gros (Microsoft, Neo4j) peuvent ajouter une couche cohérence. Notre avance = avoir déjà construit le neuro-symbolique, et notre crédibilité = la **démontrer**.
- **La fiabilité doit être mesurable, pas promise.** Sans benchmark public (taux de doublons résiduels, contradictions détectées vs ratées), c'est juste un slogan. → un *banc de fiabilité* est un livrable produit, pas un détail.
- **Coût LLM par document** — à maîtriser ; l'approche « extraire large puis corriger » aide (moins d'appels que « contraindre à chaque triplet »).
- **Fork produit non tranché** : schéma générique fixe (rapide, simple) **vs** ontologie configurable par le client (puissant, vendable en entreprise, plus complexe). À décider selon la cible.
- **Go-to-market** : API *dev-first* (self-serve) **vs** entrée par un vertical (un secteur où la fiabilité a une valeur €€€ évidente).

## Métriques de succès produit

- **Taux de doublons résiduels** dans le graphe (plus bas = mieux).
- **Précision / rappel des contradictions** détectées (vs un jeu annoté).
- **Réduction du nettoyage manuel** côté client (le vrai argument de vente).
- Coût et latence par document.

## Lien avec le produit B (copilote scénario)

A et B **partagent exactement le même cœur** (extraction + graphe + cohérence) ; ils diffèrent par l'**interaction** et la **cible** :

| | A — Moteur d'extraction | B — Copilote scénario |
|---|---|---|
| Interaction | Batch / API | Conversationnel, incrémental |
| Cible | Équipes/produits (B2B) | Auteur (Felix & co.) |
| Domaine | Générique | Narratif / world-building |
| Statut | Option documentée (ce doc) | **Direction prioritaire — à discuter** |

B peut, plus tard, exposer A comme spin-off (« et si on vendait le moteur à d'autres ? »), ou A peut rester une simple option dormante. **Ce document fige A pour ne pas le perdre** ; la conversation suivante porte sur B.

---

*Décisions à reprendre quand on rouvrira A : (1) schéma fixe vs ontologie configurable, (2) API self-serve vs vertical, (3) à quoi ressemble le « banc de fiabilité » qui prouve la promesse.*
