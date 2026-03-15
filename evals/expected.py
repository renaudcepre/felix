from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Personnages attendus (IDs slugifiés)
EXPECTED_CHARACTER_IDS = {"irina-voss", "kofi-adu", "chen-wei", "yuna-park"}

# Irina est présente dans les 3 scènes
IRINA_ID = "irina-voss"
EXPECTED_IRINA_FRAGMENT_COUNT = 3

# Lieux : au moins "helios" doit être dans un des noms de lieu
EXPECTED_LOCATION_SUBSTRINGS = ["helios"]

EXPECTED_SCENE_COUNT = 3

# Après profiling, le background d'Irina doit refléter sa carrière (scène 02)
# On cherche des sous-chaînes dans le texte lowercasé
EXPECTED_IRINA_BACKGROUND_KEYWORDS = ["quinze", "15", "carri", "observ", "spatial"]
EXPECTED_IRINA_BACKGROUND_KEYWORDS_MIN_MATCH = 2  # au moins 2 sur 5

# Scène 3 : contradiction narrative (Yuna sait ce qu'elle ne devrait pas)
EXPECTED_MIN_ISSUES = 1

# Au moins une relation extraite
EXPECTED_MIN_RELATIONS = 1
