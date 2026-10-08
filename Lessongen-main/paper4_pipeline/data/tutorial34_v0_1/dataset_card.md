# Dataset Card: tutorial34-v0.1-dev

## Purpose

Validate the shared input contract and observable execution paths of tutorial 3 and tutorial 4 before larger experiments.

## Composition

- 5 base lesson-design tasks;
- 2 language variants per task (`zh`, `en`);
- 10 records, all in the `dev` split;
- 5 local, project-authored reference fixtures;
- complete expected-outline, factual-anchor, and risk-point annotations.

## Intended uses

- deterministic dry runs;
- prompt and node integration tests;
- Autonomous versus HITL workflow checks;
- trace, human-review, and output-schema validation.

## Prohibited claims

Results on this dataset must not be presented as statistically significant model-quality evidence. The source fixtures are intentionally concise engineering inputs rather than authoritative curriculum documents.

## Next release gate

Before adding a frozen test split, each task must receive subject-matter review, traceable source metadata, copyright review, and a second-person bilingual consistency check.
