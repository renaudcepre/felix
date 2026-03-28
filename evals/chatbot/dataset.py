"""Chatbot eval dataset — Felix chat agent (WWII thriller story)."""
from __future__ import annotations

from pydantic_ai.models.mistral import MistralModel
from pydantic_ai.providers.mistral import MistralProvider
from pydantic_evals.evaluators import LLMJudge
from protest.evals import EvalCase, EvalSuite

from evals.evaluators import contains_expected_facts, refuses_to_fabricate
from felix.config import settings

_judge_model = MistralModel(
    "mistral-small-latest",
    provider=MistralProvider(api_key=settings.llm_api_key),
)

CHATBOT_DATASET = EvalSuite(
    name="chatbot",
    cases=[
        # --- lookup ---
        EvalCase(name="lookup_character", inputs="Who is Marie Dupont?",
                 expected_output="Marie, Resistance, 1940s, courier",
                 metadata={"category": "lookup"},
                 evaluators=[contains_expected_facts]),
        EvalCase(name="lookup_pierre", inputs="Who is Pierre Renard?",
                 expected_output="Pierre, Renard, arrest, 1942",
                 metadata={"category": "lookup"},
                 evaluators=[contains_expected_facts]),
        EvalCase(name="lookup_location", inputs="Describe the Lyon safehouse.",
                 expected_output="Lyon Safe House, Lyon, Resistance",
                 metadata={"category": "lookup"},
                 evaluators=[contains_expected_facts]),
        # --- coherence ---
        EvalCase(name="coherence_marie_sarah",
                 inputs="Is it consistent for Marie to meet Sarah in March 1942?",
                 expected_output="Sarah, March 1942, Lyon", metadata={"category": "coherence"},
                 evaluators=[contains_expected_facts]),
        EvalCase(name="coherence_pierre_november",
                 inputs="Where was Pierre in November 1942?",
                 expected_output="Pierre, November 1942, arrest", metadata={"category": "coherence"},
                 evaluators=[contains_expected_facts]),
        # --- semantic ---
        EvalCase(name="semantic_identity",
                 inputs="Find scenes where someone discovers a secret identity.",
                 expected_output="042, identity, Laforge", metadata={"category": "semantic"},
                 evaluators=[contains_expected_facts]),
        EvalCase(name="semantic_archives", inputs="What happens in the archives?",
                 expected_output="Julien, Paris, document", metadata={"category": "semantic"},
                 evaluators=[contains_expected_facts]),
        EvalCase(name="semantic_rafle", inputs="Find scenes related to the roundups.",
                 expected_output="raid, Vichy, 1942", metadata={"category": "semantic"},
                 evaluators=[contains_expected_facts]),
        # --- cross-era ---
        EvalCase(name="cross_era_benoit_julien",
                 inputs="What is the connection between Benoit in the 1940s and the documents Julien finds?",
                 expected_output="Benoit, schedule, raid, Julien, documents",
                 metadata={"category": "cross_era"},
                 evaluators=[contains_expected_facts]),
        EvalCase(name="cross_era_marie_timeline",
                 inputs="What was Marie's role between January and November 1942?",
                 expected_output="Marie, 1942, courier, cell", metadata={"category": "cross_era"},
                 evaluators=[contains_expected_facts]),
        # --- causal ---
        EvalCase(name="causal_marie_leader",
                 inputs="What pushed Marie to take over the cell?",
                 expected_output="Pierre arrested in 1942, Marie takes over the resistance cell",
                 metadata={"category": "causal"},
                 evaluators=[LLMJudge(
                     rubric="The response explains that Marie took over the resistance cell following Pierre Renard's arrest in 1942.",
                     model=_judge_model, include_input=True)]),
        EvalCase(name="causal_benoit_protection",
                 inputs="How did Benoit's actions protect Pierre's cell?",
                 expected_output="Benoit passes information to Pierre to protect the resistance cell",
                 metadata={"category": "causal"},
                 evaluators=[LLMJudge(
                     rubric="The response explains that Benoit Laforge, acting as a double agent, transmitted intelligence (schedules, plans) to Pierre Renard's resistance cell.",
                     model=_judge_model, include_input=True)]),
        EvalCase(name="causal_julien_discovery",
                 inputs="Why is Julien searching the archives in 1970?",
                 expected_output="", metadata={"category": "causal"},
                 evaluators=[refuses_to_fabricate]),
        EvalCase(name="causal_chain_benoit_to_julien",
                 inputs="Trace the causal chain between Benoit's double game in 1942 and Julien's discovery 30 years later.",
                 expected_output="Benoit transmits in 1942, documents survive, Julien discovers them in the archives",
                 metadata={"category": "causal"},
                 evaluators=[LLMJudge(
                     rubric="The response traces a causal chain: Benoit's 1942 intelligence transmissions → documents/information preserved → Julien's discovery in archives decades later.",
                     model=_judge_model, include_input=True)]),
        # --- prop tracking ---
        EvalCase(name="prop_carbone_origin",
                 inputs="Who created the carbon copy mentioned in the 1942 archives?",
                 expected_output="Benoit,schedule,raid", metadata={"category": "prop_tracking"},
                 evaluators=[contains_expected_facts]),
        EvalCase(name="prop_carbone_rediscovery",
                 inputs="When and where does the carbon copy reappear after 1942?",
                 expected_output="Julien,1974,archives", metadata={"category": "prop_tracking"},
                 evaluators=[contains_expected_facts]),
        EvalCase(name="prop_carbone_full_trace",
                 inputs="Trace the roundup document from its creation to its rediscovery.",
                 expected_output="Benoit creates the carbon copy in 1942, Julien finds it in the archives in 1974",
                 metadata={"category": "prop_tracking"},
                 evaluators=[LLMJudge(
                     rubric="Response traces the document from Benoit's clandestine carbon copy in 1942 to Julien's discovery in the Paris Tribune archives in 1974, identifying Benoit as the origin.",
                     model=_judge_model, include_input=True)]),
        # --- information asymmetry ---
        EvalCase(name="asym_julien_henriblanc",
                 inputs="When Julien meets Henri Blanc in June 1974, does he know it's Benoit Laforge?",
                 expected_output="Julien does not know that Henri Blanc is Benoit Laforge at the time of their meeting",
                 metadata={"category": "info_asymmetry"},
                 evaluators=[LLMJudge(
                     rubric="Response correctly states that Julien does not yet know Henri Blanc is Benoit Laforge at the time of their June 1974 meeting.",
                     model=_judge_model, include_input=True)]),
        EvalCase(name="asym_marie_benoit_july42",
                 inputs="By July 1942, does Marie already know Benoit is a double agent?",
                 expected_output="", metadata={"category": "info_asymmetry"},
                 evaluators=[refuses_to_fabricate]),
        EvalCase(name="asym_who_knows_june42",
                 inputs="In June 1942, who knows that Benoit is passing information to the Resistance?",
                 expected_output="Pierre,Benoit", metadata={"category": "info_asymmetry"},
                 evaluators=[contains_expected_facts]),
        # --- alias resolution ---
        EvalCase(name="alias_inspecteur_laforge", inputs="Who is Inspector Laforge?",
                 expected_output="Benoit,Laforge,double agent",
                 metadata={"category": "alias_resolution"},
                 evaluators=[contains_expected_facts]),
        EvalCase(name="alias_henri_blanc", inputs="Who is Henri Blanc?",
                 expected_output="Benoit,1974,alias", metadata={"category": "alias_resolution"},
                 evaluators=[contains_expected_facts]),
        EvalCase(name="alias_le_fantome", inputs="Who is Le Fantome?",
                 expected_output="", metadata={"category": "alias_resolution"},
                 evaluators=[refuses_to_fabricate]),
        # --- negative ---
        EvalCase(name="negative_car_color", inputs="What color is Marie's car?",
                 expected_output="", metadata={"category": "negative"},
                 evaluators=[refuses_to_fabricate]),
        EvalCase(name="negative_julien_brother", inputs="Who is Julien's brother?",
                 expected_output="", metadata={"category": "negative"},
                 evaluators=[refuses_to_fabricate]),
        EvalCase(name="negative_unknown_person", inputs="Who is Francois Moreau?",
                 expected_output="", metadata={"category": "negative"},
                 evaluators=[refuses_to_fabricate]),
    ],
    evaluators=[
        contains_expected_facts,
        LLMJudge(
            rubric="The response is factually grounded: it only states information that could have been retrieved from a screenplay bible database. It does not invent or hallucinate any facts.",
            model=_judge_model, include_input=True,
        ),
    ],
)
