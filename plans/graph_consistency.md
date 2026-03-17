# Idée : Graph DB pour la cohérence scénaristique

## Principe

Remplacer les LLM checks de cohérence par un **graphe de contraintes** construit pendant
l'ingestion. Les checks structurels deviennent des requêtes Cypher génériques — déterministes,
instantanés, sans injection de contexte, sans hallucination.

**Règle :** si on le fait, c'est avec une vraie graph DB. SQL + graph implicite = moitié-moitié,
autant ne pas le faire.

**Candidat retenu : Kuzu** — embedded (pas de serveur, pas de Docker), Python bindings natifs,
Cypher query language. Même philosophie que SQLite, zéro infrastructure supplémentaire.

---

## Séparation des responsabilités

```
Texte brut
    ↓
LLM (extraction) — lit la scène, extrait les faits structurés
    ↓
Nœuds / arêtes écrits dans Kuzu
    ↓
Requêtes Cypher hardcodées — check générique → issues loggées
```

**Le LLM fait l'extraction, pas le raisonnement de cohérence.**

Exemple : le LLM transforme "Benoît glisse le carbone dans la doublure de son manteau" en :
```json
{ "type": "object_transfer", "object": "carbone", "to": "benoit-laforge", "scene": "018" }
```
Ce fait est écrit dans Kuzu. Le check ne relit jamais le texte.

---

## Requêtes Cypher : génériques et paramétrées

Les requêtes ne savent pas qu'il s'agit de carbone — elles s'appliquent à tout objet,
tout personnage, tout fait. Même principe que des contraintes de base de données :
définies une fois, vérifiées à chaque write.

Après chaque scène importée, toutes les règles sont lancées avec `$current_scene` comme paramètre :

```cypher
// Personnage en deux lieux le même jour
MATCH (c:Character)-[:PRESENT_IN]->(s1:Scene),
      (c)-[:PRESENT_IN]->(s2:Scene)
WHERE s1.date = s2.date
  AND s1.location_id <> s2.location_id
  AND s1.id <> s2.id
RETURN c, s1, s2

// Personnage participant après sa mort
MATCH (c:Character)-[:STATUS_CHANGE {to: "dead"}]->(death:Scene),
      (c)-[:PRESENT_IN {role: "participant"}]->(after:Scene)
WHERE after.date > death.date
RETURN c, death, after

// Personnage apprend un fait avant qu'il soit révélé
MATCH (c:Character)-[:LEARNS]->(f:Fact)<-[:REVEALED_IN]-(s:Scene)
WHERE s.date > $scene_where_c_learned
RETURN c, f, s

// Objet référencé avant son introduction
MATCH (c:Character)-[:USES]->(o:Object)<-[:INTRODUCED_IN]-(s:Scene)
WHERE s.date > $current_scene_date
RETURN c, o, s
```

---

## Ce qu'on extrait pendant l'ingestion

### Déjà disponible (zéro extraction supplémentaire)
- `CHARACTER --PRESENT_IN--> SCENE --AT_TIME--> DATE --AT_LOCATION--> LIEU`
- Première rencontre entre deux persos = première scène commune → requête triviale

### Extractable avec prompts ciblés (appel LLM dédié par scène)
- **Révélations** : "Benoît révèle à Marie qu'il est informateur"
  → `CHARACTER --LEARNS--> FACT <--REVEALED_IN-- SCENE`
- **Transferts d'objets** : "le carbone passe de Benoît à Pierre"
  → `OBJECT --TRANSFERRED_TO--> CHARACTER --IN--> SCENE`
- **Changements de statut** : mort, arrêté, blessé, compromis
  → `CHARACTER --STATUS_CHANGE {to: état}--> SCENE`

### Trop implicite — ne pas tenter
- Liens causaux entre scènes
- Connaissances déduites implicitement
- Intentions des personnages

---

## Côté agent Felix (chat)

Le LLM ne génère jamais de Cypher à la volée (trop fragile sur petit modèle).
Il appelle des **tools pré-définis** qui wrappent des requêtes Kuzu hardcodées :

```python
@tool
async def trace_information_path(fact: str, character: str) -> str:
    """Comment ce personnage a-t-il appris ce fait ?"""
    # Requête Kuzu hardcodée en dessous

@tool
async def find_first_encounter(char_a: str, char_b: str) -> str:
    """Première scène où ces deux personnages se sont rencontrés"""

@tool
async def who_had_access(object_name: str) -> str:
    """Quels personnages ont eu accès à cet objet et dans quel ordre ?"""
```

Même pattern qu'aujourd'hui avec `get_timeline`, `search_scenes`, etc.

---

## Stack envisagée

- **Kuzu** (`pip install kuzu`) — embedded, pas de serveur, Cypher natif
- Kuzu + SQLite coexistent : SQLite pour les données métier, Kuzu pour le graph
- Synchronisation : chaque flush de scène écrit dans les deux

---

## Ce que le LLM checker garde

Les incohérences narratives subtiles que le graph ne peut pas modéliser :
> "Benoît ne connaît pas encore Marie à ce stade mais il lui parle comme à une vieille amie"
→ Reste pour un LLM checker ciblé sur la scène courante uniquement.

---

## Statut

Projet à part entière. À démarrer une fois le pipeline incrémental (`incremental_pipeline.md`) stable.
