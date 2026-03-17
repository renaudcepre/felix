# Plan : Evals du pipeline d'import

## Objectif

Tester la qualité réelle du pipeline (extraction, profiling, checker) avec un vrai LLM,
en important des scènes courtes à ground truth connu, en exportant le résultat,
puis en passant l'export à des évaluateurs heuristiques et à un LLM judge.

---

## Structure des fichiers

```
evals/
  fixtures/
    01_signal.txt        # scène 1 : 2 personnages, lieu, date claire
    02_rapport.txt       # scène 2 : 1 nouveau perso + Irina, même lieu
    03_intrusion.txt     # scène 3 : contradiction narrative (Yuna sait ce qu'elle ne devrait pas savoir)
  expected.py            # constantes ground truth
  conftest.py            # session fixture : run pipeline réel une fois, yield export dict
  evaluators.py          # évaluateurs heuristiques (sans LLM)
  judge.py               # LLM judge pydantic-ai (extraction + profiling)
  test_heuristics.py     # tests rapides (no LLM, marqués automatiquement)
  test_judge.py          # tests avec judge LLM (marqués @pytest.mark.eval)
```

---

## Fixtures scènes (genre SF, ~120 mots chacune)

### 01_signal.txt
```
STATION HELIOS-3 — SALLE DE CONTRÔLE — 12 MARS 2157

Irina Voss lève les yeux de son terminal. Les données d'émission du satellite DR-7
ne correspondent plus aux paramètres nominaux : une anomalie fréquentielle de 3,2 Hz
est apparue à 04h17 TU.

"Kofi, tu as vu ça ?" lance-t-elle à son collègue.

Kofi Adu s'approche, les doigts volant sur le clavier. "Signal non répertorié.
Ça ressemble à un écho de surface... mais la source est à 400 kilomètres d'altitude."

Irina note l'heure dans son journal de bord et déclenche le protocole d'alerte.
C'est la première fois en dix-huit mois qu'un signal non identifié traverse les filtres
de la station.
```

### 02_rapport.txt
```
STATION HELIOS-3 — SALLE DE COMMANDEMENT — 13 MARS 2157

Commandant Chen Wei écoute le rapport d'Irina sans l'interrompre.

"Vous êtes sûre que ce n'est pas un artefact de calibration ?" demande-t-il enfin.

"Certaine. J'ai fait tourner la vérification trois fois." Irina pose son terminal sur
la table. "Le signal correspond à une signature de propulsion que je n'ai jamais vue
dans les archives."

Chen Wei se lève. "Je préviens le centre de contrôle de Nairobi. Vous et Kofi,
vous continuez la surveillance. Personne d'autre n'est au courant pour l'instant."

Irina acquiesce. En quinze ans de carrière dans l'observation spatiale, elle n'avait
jamais vu Chen Wei perdre son calme — et là, il était clairement inquiet.
```

### 03_intrusion.txt (contradiction narrative)
```
STATION HELIOS-3 — SALLE DE CONTRÔLE — 15 MARS 2157

Yuna Park arrive à la station : c'est son premier jour en poste, elle vient tout juste
de débarquer. Elle découvre Irina Voss penchée sur son terminal.

"Le signal a repris ?" demande Yuna.

Irina se retourne, surprise. "Comment vous savez pour le signal ?
Ça fait quarante-huit heures que tout est classifié."

Yuna sourit. "Les murs ont des oreilles, même dans l'espace."

La situation est étrange : Yuna est décrite comme nouvelle recrue arrivant pour la
première fois, mais elle semble déjà informée d'un incident classifié que seuls Irina,
Kofi et le commandant Chen Wei devaient connaître.
```

---

## Ground truth (`expected.py`)

```python
EXPECTED_CHARACTER_IDS = {"irina-voss", "kofi-adu", "chen-wei", "yuna-park"}
EXPECTED_LOCATION_SUBSTRINGS = ["helios", "commandement"]
EXPECTED_SCENE_COUNT = 3
EXPECTED_IRINA_FRAGMENT_COUNT = 3     # présente dans les 3 scènes
EXPECTED_MIN_ISSUES = 1               # contradiction Yuna détectée
EXPECTED_IRINA_BACKGROUND_KEYWORDS = ["quinze", "carr", "observation", "ans"]
EXPECTED_MIN_RELATIONS = 1            # au moins une relation extraite
```

---

## Évaluateurs heuristiques (`evaluators.py`)

```python
@dataclass
class EvalResult:
    name: str
    passed: bool
    score: float  # 0.0–1.0
    details: str = ""

def eval_scenes_stored(export) -> EvalResult
def eval_characters_found(export) -> EvalResult      # ratio found/expected
def eval_irina_fragments(export) -> EvalResult       # ≥ EXPECTED_IRINA_FRAGMENT_COUNT
def eval_timeline_populated(export) -> EvalResult    # toutes scènes ont un event + date
def eval_issue_detected(export) -> EvalResult        # ≥ 1 issue contradiction/missing_info
def eval_profile_grounded(export) -> EvalResult      # background Irina contient keywords
def eval_relations_present(export) -> EvalResult     # ≥ 1 relation dans character_relations
```

---

## LLM judge (`judge.py`)

### Modèles de sortie

```python
class ExtractionScore(BaseModel):
    summary_faithfulness: int    # 1-5 : le résumé reflète le texte source ?
    characters_completeness: int # 1-5 : tous les persos pertinents extraits ?
    characters_accuracy: int     # 1-5 : noms/rôles corrects ?
    justification: str

class ProfilingScore(BaseModel):
    groundedness: int            # 1-5 : les infos du profil sont dans le texte ?
    completeness: int            # 1-5 : les infos disponibles ont été capturées ?
    no_hallucination: bool       # aucun fait inventé ?
    justification: str
```

### Agents

```python
async def judge_scene_extraction(
    scene_text: str,
    scene_export: dict,
    model_name: str | None,
    base_url: str | None,
) -> ExtractionScore

async def judge_character_profiling(
    char_name: str,
    scene_texts: list[str],
    profile_export: dict,
    model_name: str | None,
    base_url: str | None,
) -> ProfilingScore
```

---

## conftest.py (session fixture)

```python
@pytest.fixture(scope="session")
def pipeline_export(tmp_path_factory):
    """Run le pipeline réel une seule fois. Skippé si le modèle n'est pas dispo."""
    import asyncio, shutil
    fixtures_dir = Path(__file__).parent / "fixtures"
    scenes_dir = tmp_path_factory.mktemp("scenes")
    for f in fixtures_dir.glob("*.txt"):
        shutil.copy(f, scenes_dir / f.name)

    async def _run() -> dict:
        db = await init_db(":memory:")
        collection = chromadb.Client().get_or_create_collection("eval_scenes")
        progress = ImportProgress()
        await run_import_pipeline(
            str(scenes_dir), db, collection,
            model_name=settings.llm_model,
            base_url=settings.llm_base_url,
            progress=progress,
            enrich_profiles=True,
        )
        export = { ... toutes les tables ... }
        await db.close()
        return export

    try:
        return asyncio.run(_run())
    except Exception as e:
        pytest.skip(f"Modele indisponible: {e}")
```

---

## Exécution

```bash
# Tests heuristiques seuls (rapides, no LLM)
uv run pytest evals/test_heuristics.py -v

# Tous les evals (avec LLM judge)
uv run pytest evals/ -v -m eval

# Tout (heuristiques + judge)
uv run pytest evals/ -v
```

---

## Ce qui ne change pas

- `pyproject.toml` : ajouter marqueur `eval` dans `[tool.pytest.ini_options]`
- `evals/**` déjà dans ruff per-file-ignores (T201)
- `testpaths = ["tests"]` reste inchangé (evals ne tournent pas avec `pytest` seul)
