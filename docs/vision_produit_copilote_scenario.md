# Vision produit — Copilote de world-building conversationnel

> **Vision produit + design d'interaction** (pas d'implémentation). 2026-06-07.
> Nom de travail : *Felix* (le copilote). **Direction prioritaire.**
> Cœur technique partagé avec le produit A — voir `vision_produit_moteur_extraction.md`.

---

## En une phrase

Un copilote avec qui l'auteur **construit la bible de son univers en parlant** : il décrit, le bot range dans le graphe, **relance pour combler les trous**, et veille à la **cohérence en temps réel** — sans jamais lui retirer le dernier mot.

---

## Contexte & origine

Felix est né comme assistant scénario. Le détour par « import batch de scènes existantes » puis par « moteur générique (A) » a servi à isoler le cœur réutilisable. Mais le **but réel** n'a jamais changé : aider un auteur (Felix, le scénariste) à **tenir son monde cohérent pendant qu'il l'invente**.

Insight clé du recadrage : l'import batch suppose un scénario *déjà écrit*. La vraie valeur est **en amont**, au moment de la création, quand le monde se construit et que les contradictions naissent.

## Le problème

Un récit multi-époques, multi-personnages devient vite ingérable : qui sait quoi, qui était où, qui est mort quand, quel objet est passé dans quelles mains. La « bible » dans un doc texte ne tient pas — et un LLM seul **oublie** (pas de mémoire fiable, *lost in the middle*). **Un graphe, lui, se souvient et contredit.**

## Pour qui

Felix d'abord (scénariste, thriller multi-époques). Puis, même besoin : romanciers, maîtres de jeu / JDR, créateurs de séries, world-builders.

## Proposition de valeur

> Tu inventes en parlant. L'outil tient ta bible cohérente à ta place, et te prévient quand tu te contredis — **sans t'empêcher de le faire exprès.**

## L'expérience : la boucle

Posture du bot : **Intervieweur** (il enregistre *et* relance).

```
auteur : "ça se passe en 1944, sur un porte-avion"
   └─ set_contexte(date=1944, lieu="porte-avion")  → "ok, c'est noté"
   └─ relance : "qui était présent ?"

auteur : "Jean transporte la relique maya"
   ├─ add_personnage("Jean")     → resolver : déjà connu ? fusion / création
   ├─ add_objet("relique maya")  → nouvelle entité
   ├─ add_evenement(Jean —transporte→ relique, lieu+date = contexte courant)
   │     └─ checker : contredit un fait connu ?
   └─ "noté : Jean transporte la relique maya, porte-avion, 1944.
        Il l'a depuis quand ?"   ← relance pilotée par le type d'événement
```

## Les tools du chat

L'agent passe de **lecture seule** à **lecture + écriture** :

| Lecture (existe déjà) | Écriture (nouveau) |
|---|---|
| `find_personnage`, `find_lieu`, `get_timeline`, `search` | `add_personnage`, `add_lieu`, `add_objet`, `add_relation`, `add_evenement`, `set_contexte`, `merge` / `rename` / `delete` |

**Chaque écriture passe par `resolver` (dédup/alias) puis `checker` (cohérence)** avant confirmation. C'est ce qui distingue B d'un simple chatbot scriptable.

## Principe directeur : l'auteur est souverain

| Type d'action | Comportement |
|---|---|
| Ajout simple (perso, lieu, date) | écrit direct + résumé |
| Op risquée (fusion, **contradiction**, suppression) | le bot demande « t'es sûr ? » |
| → l'auteur confirme | **on obéit toujours** + on lève une *issue* |
| → l'auteur hésite | on discute / on corrige |

Commit : **hybride selon le risque** (direct pour le simple, confirmation pour le risqué).

> **Une contradiction n'est pas une erreur, c'est une information.** Un auteur plante des contradictions exprès (flashback, narrateur non fiable, twist, retcon). Le bot ne les bloque jamais : il les **enregistre comme *tensions assumées*** que l'auteur peut rouvrir plus tard (« ces 5 trucs que j'ai tordus volontairement — toujours OK ? »). Aucun outil text-to-graph ne fait ça, parce qu'aucun n'est pensé *pour un auteur*. **C'est l'angle de B.**

## Modèle de faits : états vs événements

L'auteur pose deux natures de faits, et le bot doit les distinguer :

- **Relation d'état** — permanente, sans date. *« Jean est le frère de Marie »* → le bot ne demande pas « quand ? ».
- **Événement** — daté (et souvent localisé). *« Jean épouse Marie »*, *« Jean meurt »*, *« Jean prend la relique »* → le bot **relance** pour les cases manquantes (date, lieu, témoins).

Ce typage est **le moteur de deux features à la fois** : il pilote les relances de l'Intervieweur *et* il rend les checks de cohérence temporelle possibles (on ne vérifie une date que sur ce qui a une date).

**Ontologie : hybride.** Un petit **catalogue d'événements-clés** (naissance, mort, mariage, rencontre, déplacement, prise/perte d'objet…) avec leurs **cases attendues** (date, lieu, participants) ; pour tout le reste, le bot **juge à la volée**. Assez de structure pour le checker, assez de souplesse pour ne pas brider l'auteur.

## Ce que ça change dans le modèle du monde

Trois évolutions de schéma, qui sont **exactement la « dé-spécialisation » décrite pour A** — d'où « les deux projets s'entraident » :

1. **Nouveaux types d'entité** : objets/artefacts (la relique maya), organisations/factions — au-delà de *personnage / lieu*.
2. **Relations libres**, non ancrées à une scène (*« frère de »* n'appartient à aucune scène).
3. **Notion de « contexte courant »** (focus temps + lieu) dans la conversation, auquel se rattachent par défaut les faits situés.

## Modes d'entrée

- **Chat incrémental** (principal) — on construit en parlant.
- **Coller une scène** — réutilise l'extracteur batch existant → le bot **propose un lot d'ajouts** que l'auteur valide. (Pont direct vers le pipeline actuel.)

## Différenciateur

C'est le **seul text-to-graph pensé pour un auteur** : contradiction = information (pas erreur), relances intelligentes pilotées par l'ontologie, mémoire fiable du monde. Les outils « A-like » visent un graphe propre *pour la machine* ; B vise l'**assistance créative pour un humain**.

## Risques & questions ouvertes

- **Pré-requis bloquant : le cœur doit marcher.** B repose sur `resolver` + `checker` + extracteur — or les evals sont retombées à **40 %** (régression à investiguer, cf. JOURNAL). **On stabilise le cœur avant de bâtir B dessus.**
- **Granularité du checker** : aujourd'hui il raisonne par *scène*. B a besoin d'un check **par fait/événement** au moment de l'écriture. À concevoir.
- **Contenu du catalogue d'événements de départ** : lequel, avec quelles cases ? À définir.
- **Petit modèle (7B/8B)** : la qualité du *tool-calling* et du jugement état/événement est incertaine sur petit modèle → few-shot indispensable (cf. `felix_prompting_review.md`, P1).
- **Latence/coût** : un tour de chat = plusieurs appels (tool-use + checks). À surveiller pour rester fluide et conversationnel.

## Lien avec le produit A

| | A — Moteur d'extraction | B — Copilote (ce doc) |
|---|---|---|
| Interaction | Batch / API | Conversationnel, incrémental |
| Cible | Équipes / produits (B2B) | Auteur (Felix & co.) |
| Domaine | Générique | Narratif / world-building |
| Contradiction | À nettoyer | À **assumer** (info créative) |
| Statut | Option parkée | **Prioritaire** |

Même cœur (extraction + résolution + cohérence + ontologie). Construire B fait avancer A « gratuitement » ; A pourra plus tard exposer le cœur en service.

## Du design au build (feuille de route, pas du code)

1. **Stabiliser le cœur** — investiguer la régression evals (pré-requis).
2. **Définir le catalogue d'événements** de départ + leurs cases.
3. **Étendre le schéma** — objets, relations libres, contexte courant.
4. **Ajouter les write-tools** au chat agent, chacun wrappé `resolver` → `checker`.
5. **Eval-first** — une eval de *conversation* : séquence d'énoncés → graphe attendu + contradictions attendues. (Conforme à la doctrine TDD-evals.)
