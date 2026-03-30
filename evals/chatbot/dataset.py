"""Chatbot eval dataset — Felix chat agent (WWII thriller story)."""

from __future__ import annotations

from protest import ForEach
from protest.evals import EvalCase

from evals.evaluators import contains_expected_facts, llm_judge, refuses_to_fabricate

chatbot_cases = ForEach(
    [
        # --- lookup ---
        EvalCase(
            name="lookup_character",
            inputs="Who is Marie Dupont?",
            expected="Marie, Resistance, 1940s, courier",
            evaluators=[contains_expected_facts],
        ),
        EvalCase(
            name="lookup_pierre",
            inputs="Who is Pierre Renard?",
            expected="Pierre, Renard, arrest, 1942",
            evaluators=[contains_expected_facts],
        ),
        EvalCase(
            name="lookup_location",
            inputs="Describe the Lyon safehouse.",
            expected="Lyon Safe House, Lyon, Resistance",
            evaluators=[contains_expected_facts],
        ),
        # --- coherence ---
        EvalCase(
            name="coherence_marie_sarah",
            inputs="Is it consistent for Marie to meet Sarah in March 1942?",
            expected="Sarah, March 1942, Lyon",
            evaluators=[contains_expected_facts],
        ),
        EvalCase(
            name="coherence_pierre_november",
            inputs="Where was Pierre in November 1942?",
            expected="Pierre, November 1942, arrest",
            evaluators=[contains_expected_facts],
        ),
        # --- semantic ---
        EvalCase(
            name="semantic_identity",
            inputs="Find scenes where someone discovers a secret identity.",
            expected="042, identity, Laforge",
            evaluators=[contains_expected_facts],
        ),
        EvalCase(
            name="semantic_archives",
            inputs="What happens in the archives?",
            expected="Julien, Paris, document",
            evaluators=[contains_expected_facts],
        ),
        EvalCase(
            name="semantic_rafle",
            inputs="Find scenes related to the roundups.",
            expected="raid, Vichy, 1942",
            evaluators=[contains_expected_facts],
        ),
        # --- cross-era ---
        EvalCase(
            name="cross_era_benoit_julien",
            inputs="What is the connection between Benoit in the 1940s and the documents Julien finds?",
            expected="Benoit, schedule, raid, Julien, documents",
            evaluators=[contains_expected_facts],
        ),
        EvalCase(
            name="cross_era_marie_timeline",
            inputs="What was Marie's role between January and November 1942?",
            expected="Marie, 1942, courier, cell",
            evaluators=[contains_expected_facts],
        ),
        # --- causal ---
        EvalCase(
            name="causal_marie_leader",
            inputs="What pushed Marie to take over the cell?",
            expected="Pierre arrested in 1942, Marie takes over the resistance cell",
            evaluators=[
                llm_judge(
                    rubric="The response explains that Marie took over the resistance cell following Pierre Renard's arrest in 1942."
                )
            ],
        ),
        EvalCase(
            name="causal_benoit_protection",
            inputs="How did Benoit's actions protect Pierre's cell?",
            expected="Benoit passes information to Pierre to protect the resistance cell",
            evaluators=[
                llm_judge(
                    rubric="The response explains that Benoit Laforge, acting as a double agent, transmitted intelligence (schedules, plans) to Pierre Renard's resistance cell."
                )
            ],
        ),
        EvalCase(
            name="causal_julien_discovery",
            inputs="Why is Julien searching the archives in 1970?",
            expected="",
            evaluators=[refuses_to_fabricate],
        ),
        EvalCase(
            name="causal_chain_benoit_to_julien",
            inputs="Trace the causal chain between Benoit's double game in 1942 and Julien's discovery 30 years later.",
            expected="Benoit transmits in 1942, documents survive, Julien discovers them in the archives",
            evaluators=[
                llm_judge(
                    rubric="The response traces a causal chain: Benoit's 1942 intelligence transmissions → documents/information preserved → Julien's discovery in archives decades later."
                )
            ],
        ),
        # --- prop tracking ---
        EvalCase(
            name="prop_carbone_origin",
            inputs="Who created the carbon copy mentioned in the 1942 archives?",
            expected="Benoit,schedule,raid",
            evaluators=[contains_expected_facts],
        ),
        EvalCase(
            name="prop_carbone_rediscovery",
            inputs="When and where does the carbon copy reappear after 1942?",
            expected="Julien,1974,archives",
            evaluators=[contains_expected_facts],
        ),
        EvalCase(
            name="prop_carbone_full_trace",
            inputs="Trace the roundup document from its creation to its rediscovery.",
            expected="Benoit creates the carbon copy in 1942, Julien finds it in the archives in 1974",
            evaluators=[
                llm_judge(
                    rubric="Response traces the document from Benoit's clandestine carbon copy in 1942 to Julien's discovery in the Paris Tribune archives in 1974, identifying Benoit as the origin."
                )
            ],
        ),
        # --- information asymmetry ---
        EvalCase(
            name="asym_julien_henriblanc",
            inputs="When Julien meets Henri Blanc in June 1974, does he know it's Benoit Laforge?",
            expected="Julien does not know that Henri Blanc is Benoit Laforge at the time of their meeting",
            evaluators=[
                llm_judge(
                    rubric="Response correctly states that Julien does not yet know Henri Blanc is Benoit Laforge at the time of their June 1974 meeting."
                )
            ],
        ),
        EvalCase(
            name="asym_marie_benoit_july42",
            inputs="By July 1942, does Marie already know Benoit is a double agent?",
            expected="",
            evaluators=[refuses_to_fabricate],
        ),
        EvalCase(
            name="asym_who_knows_june42",
            inputs="In June 1942, who knows that Benoit is passing information to the Resistance?",
            expected="Pierre,Benoit",
            evaluators=[contains_expected_facts],
        ),
        # --- alias resolution ---
        EvalCase(
            name="alias_inspecteur_laforge",
            inputs="Who is Inspector Laforge?",
            expected="Benoit,Laforge,double agent",
            evaluators=[contains_expected_facts],
        ),
        EvalCase(
            name="alias_henri_blanc",
            inputs="Who is Henri Blanc?",
            expected="Benoit,1974,alias",
            evaluators=[contains_expected_facts],
        ),
        EvalCase(
            name="alias_le_fantome",
            inputs="Who is Le Fantome?",
            expected="",
            evaluators=[refuses_to_fabricate],
        ),
        # --- negative ---
        EvalCase(
            name="negative_car_color",
            inputs="What color is Marie's car?",
            expected="",
            evaluators=[refuses_to_fabricate],
        ),
        EvalCase(
            name="negative_julien_brother",
            inputs="Who is Julien's brother?",
            expected="",
            evaluators=[refuses_to_fabricate],
        ),
        EvalCase(
            name="negative_unknown_person",
            inputs="Who is Francois Moreau?",
            expected="",
            evaluators=[refuses_to_fabricate],
        ),
    ]
)
