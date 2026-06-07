# Bonnes pratiques de prompting — état de l'art (synthèse)

> Rapport de recherche, 2026-06-06. Sources web citées en fin de document.
> Périmètre demandé : prompting en général, **petits modèles (7B/8B)**, approches **neuro-symboliques**, et évaluation.
> Pendant pratique pour Felix : voir [`felix_prompting_review.md`](felix_prompting_review.md).

---

## TL;DR — les 10 principes qui ressortent

1. **Sur petit modèle, le prompt est un hyperparamètre de premier ordre.** Un bon prompt fait gagner ~10–12 points d'accuracy à un Llama-3.1-8B / Mistral-7B — l'équivalent d'un saut d'un ordre de grandeur en paramètres, à coût quasi nul.
2. **Few-shot > zero-shot, surtout en domaine spécifique.** Même *un seul* exemple (k=1) bat systématiquement le zero-shot. Les règles abstraites ne suffisent pas aux petits modèles ; les exemples sont leurs « images valant mille mots ».
3. **Le Chain-of-Thought *dégrade* les modèles < 10B.** Ils produisent des chaînes fluides mais illogiques → plus d'hallucination, moins de précision. CoT n'aide que les très gros modèles (ordre 100B) ou via distillation/fine-tuning dédié.
4. **Décomposer en une tâche par appel.** Un prompt = un sous-problème réduit l'hallucination et le hors-sujet ; gains massifs mesurés (jusqu'à ×2 d'accuracy). Bonus : chaque étape peut être remplacée par une fonction symbolique.
5. **Sorties structurées (JSON schema / constrained decoding) = fiabilité de format à 100 %…** mais elles peuvent **coûter jusqu'à 27 points de raisonnement** si elles forcent la réponse *avant* tout raisonnement. Règle : *raisonner d'abord, structurer ensuite*.
6. **Formuler en positif, pas en négatif.** « Don't do X » déclenche le « pink elephant problem » : le modèle doit d'abord se représenter X. « Always lowercase names » bat « don't uppercase names » de façon mesurable.
7. **Champs optionnels plutôt que champs forcés.** Un champ requis dans un schéma pousse à halluciner une valeur quand l'info est absente. Rendre `null`/optionnel ce qui peut manquer.
8. **Neuro-symbolique : laisser le LLM extraire largement, puis corriger par le symbolique** (« better later than sooner »). Un graphe/ontologie valide la cohérence (contraintes domaine-portée), corrige par inversion/substitution/typage, et tranche les ambiguïtés — moins d'appels LLM, plus de cohérence.
9. **LLM-as-judge : biais connus** (verbosité, position, auto-préférence). Mitiger par randomisation d'ordre, rubriques explicites, et **panels multi-juges** (un seul juge est statistiquement instable).
10. **Structurer le prompt** : rôle explicite, sections délimitées (Markdown/XML), 3–5 exemples canoniques et divers, instructions spécifiques plutôt que vagues.

---

## 1. Petits modèles (7B/8B) — le prompt comme levier principal

Le constat le plus solide : **les petits modèles bénéficient *disproportionnellement* d'un bon prompt.** Là où un gros modèle « pardonne » un prompt médiocre, un 7B/8B s'effondre ou excelle selon la formulation.

- Gains rapportés de **~10–12 points d'accuracy** sur Llama-3.1-8B et Mistral-7B avec un meilleur prompt — « ce qu'un petit modèle obtient par un prompt soigné exigerait sinon un ordre de grandeur de paramètres en plus ».
- L'optimisation de prompt *consciente de la taille du modèle* (« model-size-aware ») peut améliorer l'accuracy de 8–12 % **et** réduire les tokens de 70–80 %.
- Pratique : traiter le prompt comme un **hyperparamètre de premier ordre**, à itérer/optimiser avant d'envisager un modèle plus gros.

**Implication clé** : sur un 7B/8B, on ne « décrit » pas la tâche, on la **montre** et on la **découpe**.

## 2. Few-shot / In-Context Learning (ICL)

- **Few-shot = ICL** : le modèle apprend des exemples du prompt sans mise à jour de poids.
- Le few-shot bat le zero-shot de façon **consistante**, et l'écart se creuse sur les **tâches de domaine** (jargon, schéma de sortie précis, conventions métier) — précisément là où le zero-shot décroche.
- Même **k=1** (un exemple) apporte un gain net ; inutile d'en mettre 20.
- Côté Anthropic : **3–5 exemples canoniques et divers**, enveloppés dans des balises (`<example>`), pour que le modèle les distingue des instructions.

**Coût caché à connaître** : un exemple few-shot enseigne *une distribution*. Si les exemples couvrent toujours le même sous-cas, le modèle généralise mal au reste — et si un exemple reproduit un cas de test, l'évaluation devient **circulaire** (cf. §9 et la review Felix).

## 3. Chain-of-Thought (CoT) sur petits modèles — attention

Résultat contre-intuitif mais robuste dans la littérature :

- **Le CoT standard dégrade les modèles < ~10B.** Ils écrivent des raisonnements « fluents but illogical » → l'accuracy descend *sous* le prompting standard.
- Le gain du CoT est **proportionnel à la taille** : il n'apparaît nettement qu'autour de ~100B.
- Sur petit modèle, CoT augmente l'hallucination (génération fluide mais fausse).
- **Ce qui marche quand même** : variantes spécialisées (ex. *Trace-of-Thought* pour ~7B), distillation/fine-tuning sur des CoT auto-construits, ou — plus simple — **décomposer la tâche** (§4) au lieu de demander un raisonnement libre.

**Implication** : pour un 7B, préférer *des étapes externes orchestrées* à *un raisonnement interne libre*.

## 4. Décomposition de tâches (Decomposed Prompting)

Un prompt = un sous-problème. C'est l'alternative « système » au CoT interne, et elle est particulièrement adaptée aux petits modèles.

- Gains mesurés : JEEBench ~10 % → ~22 % ; GSM8K 36 % (CoT) → 50,6 % (décomposé) ; MultiArith 78 % → 95 %.
- « Focaliser le modèle sur un seul sous-objectif réduit l'hallucination et le hors-sujet. »
- **Modularité** : chaque sous-prompt s'optimise séparément, se re-décompose, ou **se remplace par un modèle entraîné ou une fonction symbolique** — c'est le pont naturel vers le neuro-symbolique (§8).

## 5. Sorties structurées & constrained decoding

- **Mécanisme** : le décodage contraint masque en temps réel les tokens qui violeraient le schéma → conformité de format **garantie**, sans retries ni post-parsing.
- **Bénéfice pipeline** : dans un système multi-étapes, chaque donnée est « exactement où elle doit être » → robustesse globale.
- **Le piège majeur** : forcer un schéma peut **dégrader le raisonnement jusqu'à 27 points** (benchmarks math), car le modèle doit émettre la réponse *avant* d'avoir raisonné. Pour la classification pure, les contraintes aident ; pour le raisonnement multi-étapes, elles peuvent nuire.
- **Bonnes pratiques** :
  - *Reason first* : prévoir un champ « raisonnement/justification » **avant** les champs de décision, ou faire le raisonnement dans un appel séparé.
  - **Un schéma par tâche** ; au-delà de ~50 champs, scinder en plusieurs extractions (les gros schémas dégradent la qualité).
  - **Champs optionnels** si l'info peut manquer → évite l'hallucination de remplissage.
  - Garder des **chemins défensifs** (try/except, fallback) malgré la garantie de format (timeouts, dépassement de contexte).

## 6. Instructions négatives vs positives

- **Pink elephant problem** (théorie du processus ironique) : « ne fais pas X » oblige d'abord à se représenter X, ce qui *augmente* sa probabilité de surgir.
- Mesuré : « always lowercase names » > « don't uppercase names » ; « only use real data » > « don't use mock data ».
- Techniquement : un prompt négatif baisse *un peu* la proba des tokens indésirables ; un prompt positif **augmente activement** la proba des tokens désirés.
- Les instructions négatives **augmentent le risque de confusion et d'hallucination**, surtout sur petit modèle.

**Nuance** : une *liste d'exclusions* peut rester utile pour cadrer un périmètre — mais mieux vaut la convertir en **définition positive du périmètre + exemples** de ce qui est attendu/rejeté.

## 7. Neuro-symbolique : LLM + graphe de connaissances

C'est l'axe le plus directement applicable à un projet « extraction → graphe → vérifications ».

- **Pourquoi un graphe/ontologie** : il adresse les défauts structurels des LLM — opacité, hallucination (faits fabriqués), incohérence. Les LLM « as KG constructors » sous-performent en domaine spécifique et inventent des faits.
- **Pattern gagnant — « Better Later Than Sooner » (OAK+MEND)** : *ne pas* injecter l'ontologie dans le prompt d'extraction. Extraire en domaine ouvert, **puis** valider/corriger symboliquement.
  - **Efficacité** : 59 % du coût en tokens d'une approche « contrainte pendant l'extraction », pour **96,8 % de cohérence des triplets** (vs 77,4 %).
  - **Techniques de correction symbolique** :
    - *contraintes domaine-portée* + règles de qualificateurs détectent les violations ;
    - *inversion sujet-objet* quand l'inversion satisfait la contrainte ;
    - *substitution de prédicat* par similarité d'embedding ;
    - *raffinement de type* (ajout des types manquants) — « ajouter les types d'entité et les propager à tous les triplets corrige plusieurs violations en **un seul appel LLM** ».
  - **Effet de bord mesuré** : l'extraction libre produit des **prédicats redondants** (même info, formulations différentes) → la couche symbolique doit dédupliquer. (Écho direct au problème « relations dupliquées » de Felix.)
- **GraphRAG** (Microsoft) : interroger un KG pour ancrer les réponses → cohérence et explicabilité accrues.
- **Modèles** : les modèles *de raisonnement* préservent mieux la fidélité sémantique à travers les corrections ; les petits modèles « gonflent » certaines métriques via des artefacts (multiplicité d'arêtes).

**Principe à retenir** : *le LLM propose, le symbolique dispose.* L'extraction reste large et tolérante ; la rigueur (cohérence, dédup, typage, contradictions) vit dans la couche graphe, pas dans le prompt.

## 8. LLM-as-judge (évaluation par LLM)

- **Biais documentés** : verbosité (préfère les réponses longues), position (préfère ce qui vient en premier), auto-préférence (préfère ses propres sorties), préférence pour le format « autoritaire/bien mis en forme ».
- **Stabilité** : même un juge SOTA fluctue de ~0,03 (jusqu'à ~0,2 pour les *petits* juges) selon des perturbations mineures → un **juge unique est statistiquement insuffisant**.
- **Mitigations** :
  - randomiser l'ordre des candidats, mélanger les rubriques ;
  - termes de débiaisage explicites dans le prompt du juge ;
  - **panels multi-juges** (moyenne sur des tendances diverses) ;
  - rubriques structurées plutôt que prompting ad hoc.

**Implication** : pour des evals automatisées sur petit modèle-juge, préférer des **évaluateurs déterministes/symboliques** quand c'est possible, et réserver le LLM-juge aux jugements vraiment sémantiques (avec rubrique + idéalement panel).

## 9. Structure générale du prompt (synthèse Anthropic & co.)

- **Rôle explicite** dans le system/instructions : oriente fortement ton et expertise (« You are a … specialized in … »).
- **Sections délimitées** : Markdown headers ou balises XML (`<instructions>`, `<context>`, `<input>`, `<example>`) pour que le modèle ne confonde pas consignes, contexte et données.
- **Spécificité** : instructions détaillées > requêtes vagues ; **une tâche à la fois**.
- **Exemples** : 3–5, divers et canoniques, balisés.
- **Montrer le format de sortie** attendu explicitement.

---

## Tableau de synthèse — technique × adapté aux petits modèles ?

| Technique | Petit modèle (7B/8B) | Remarque |
|---|---|---|
| Few-shot (k=1–5) | ✅ fortement | Le levier n°1 ; éviter que les exemples = cas d'eval |
| Règles abstraites seules | ⚠️ faible | Mal suivies sans exemples |
| CoT interne libre | ❌ contre-productif | Dégrade < 10B ; préférer la décomposition |
| Décomposition (1 tâche/appel) | ✅ fortement | Réduit hallucination ; ouvre la porte au symbolique |
| Sortie structurée (schema) | ✅ pour format / ⚠️ pour raisonnement | « Reason first » ; champs optionnels |
| Instructions négatives | ⚠️ à convertir en positif | Pink elephant ; ↑ hallucination |
| Validation symbolique post-extraction | ✅✅ | Rigueur hors du prompt ; corrige en 1 appel |
| Température basse (0–0.1) | ✅ extraction | Cohérent avec la déterminisme voulu |
| LLM-as-judge mono-juge | ⚠️ instable | Panel + rubrique + randomisation |

---

## Sources

**Petits modèles & prompt comme hyperparamètre**
- [Promptomatix: An Automatic Prompt Optimization Framework (arXiv)](https://arxiv.org/pdf/2507.14241)
- [Prompt Engineering in 2025: Latest Best Practices — Aakash G](https://www.news.aakashg.com/p/prompt-engineering)
- [Prompt engineering best practices 2025 — CodeSignal](https://codesignal.com/blog/prompt-engineering-best-practices-2025/)
- [EffGen: Small Language Models as Capable Autonomous Agents (arXiv)](https://arxiv.org/pdf/2602.00887)

**Few-shot / ICL**
- [Zero-Shot vs Few-Shot Prompting — Shelf.io](https://shelf.io/blog/zero-shot-and-few-shot-prompting/)
- [Shot-Based Prompting — Learn Prompting](https://learnprompting.org/docs/basics/few_shot)
- [In-Context Learning — Ludwig](https://ludwig.ai/latest/user_guide/llms/in_context_learning/)
- [Zero-Shot and Few-Shot Learning with Reasoning LLMs — MachineLearningMastery](https://machinelearningmastery.com/zero-shot-and-few-shot-learning-with-reasoning-llms/)

**Chain-of-Thought & taille de modèle**
- [Chain-of-Thought Prompting Elicits Reasoning in LLMs — Wei et al. (arXiv)](https://arxiv.org/pdf/2201.11903)
- [Towards Better Chain-of-Thought Prompting Strategies: A Survey (arXiv)](https://arxiv.org/pdf/2310.04959)
- [Chain of Thought Prompting — Vellum](https://www.vellum.ai/blog/chain-of-thought-prompting-cot-everything-you-need-to-know)

**Décomposition de tâches**
- [Decomposed Prompting: A Modular Approach (arXiv 2210.02406)](https://arxiv.org/pdf/2210.02406)
- [LLM-Based Prompted Decomposition — EmergentMind](https://www.emergentmind.com/topics/llm-based-prompted-decomposition)
- [DecomP — Learn Prompting](https://learnprompting.org/docs/advanced/decomposition/decomp)

**Sorties structurées / constrained decoding**
- [Introducing Structured Outputs in the API — OpenAI](https://openai.com/index/introducing-structured-outputs-in-the-api/)
- [Structured outputs — BentoML LLM Inference Handbook](https://bentoml.com/llm/model-interaction/structured-outputs)
- [Reliable JSON from Any LLM: Pydantic + Zod — TECHSY](https://techsy.io/en/blog/llm-structured-outputs-guide)
- [PARSE: LLM-Driven Schema Optimization for Reliable Entity Extraction (arXiv)](https://arxiv.org/html/2510.08623v1)
- [Grammar-Constrained Generation — TianPan](https://tianpan.co/blog/2026-04-16-grammar-constrained-generation-output-reliability)

**Instructions négatives vs positives**
- [The Pink Elephant Problem — eval.16x.engineer](https://eval.16x.engineer/blog/the-pink-elephant-negative-instructions-llms-effectiveness-analysis)
- [Why Positive Prompts Outperform Negative Ones — Gadlet](https://gadlet.com/posts/negative-prompting/)
- [Best practices for LLM prompt engineering — Palantir](https://www.palantir.com/docs/foundry/aip/best-practices-prompt-engineering)

**Neuro-symbolique / KG**
- [Better Later Than Sooner: Ontology-grounded Post-extraction Correction (OAK+MEND, arXiv 2605.29168)](https://arxiv.org/html/2605.29168)
- [HyDRA: Hybrid-Driven Reasoning Architecture for Verifiable Knowledge Graphs (arXiv)](https://arxiv.org/pdf/2507.15917)
- [GraphMERT: Distillation of Reliable Knowledge Graphs (arXiv)](https://arxiv.org/pdf/2510.09580)
- [Neuro-Symbolic AI: Foundations & Applications — Ajith Prabhakar](https://ajithp.com/2025/07/27/neuro-symbolic-ai-multimodal-reasoning/)
- [Neuro-symbolic AI — metaphacts](https://blog.metaphacts.com/neuro-symbolic-ai-the-key-to-truly-intelligent-systems)

**LLM-as-judge**
- [From Generation to Judgment: Opportunities and Challenges of LLM-as-a-judge (arXiv 2411.16594)](https://arxiv.org/pdf/2411.16594)
- [Bias in the Loop: Auditing LLM-as-a-Judge for Software Engineering (arXiv)](https://arxiv.org/html/2604.16790v1)
- [CyclicJudge: Mitigating Judge Bias (arXiv)](https://arxiv.org/pdf/2603.01865)
- [LLM-as-a-Judge Evaluation — EmergentMind](https://www.emergentmind.com/topics/llm-as-a-judge-evaluations)

**Structure de prompt (Anthropic & co.)**
- [Prompting best practices — Claude API Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [Effective context engineering for AI agents — Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Anthropic's Interactive Prompt Engineering Tutorial — GitHub](https://github.com/anthropics/prompt-eng-interactive-tutorial)
