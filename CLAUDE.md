# Instructions for Claude Code

Read `databricks/SPEC.md` in full before writing or modifying any code. It is the
authoritative spec — architecture, data model, module contracts, and non-negotiables.

## Current phase

Databricks build only. The `hana/` folder is a placeholder for later — do not start work
there until explicitly told the Databricks build is complete and evaluated.

## Build order — do not skip ahead

Work one module at a time, in this order, confirming each works before starting the next:

1. Unity Catalog setup (catalog + bronze/silver/gold/eval schemas) — SPEC.md §3
2. `src/ingest.py` only — SPEC.md §4. Test against a small local sample (~10 rows) before
   wiring into the bundle job.
3. `src/chunk_embed.py` — SPEC.md §4
4. `src/build_index.py` — SPEC.md §4
5. `src/extract_requirements.py` — SPEC.md §4
6. `src/score.py` — SPEC.md §4. Read SPEC.md §0 again before writing this one specifically.
7. `src/eval.py` — SPEC.md §4
8. Wire `resources/job.yml` and confirm `databricks bundle run` executes the full DAG.
9. `resources/table_comments.sql` + Genie Agent (optional) — SPEC.md §10

Do not build steps 3–7 in parallel or all at once. Stop and confirm each step's output
(query the resulting table) before moving on.

## Non-negotiables — SPEC.md §0

1. This is RAG, not a scoring script — retrieval AND generation, both required.
2. Never let the LLM hallucinate support for a requirement — the confidence gate blocks
   the generation call, not just the final answer.
3. Scoring (`aggregate_scores`) is deterministic — no model calls, ever. See the stub in
   `src/score.py` and the test in `tests/test_scoring.py`.
4. Everything is code except two explicitly-flagged manual steps (SPEC.md §5.1, §10).
5. Every value in `config.yml` must be a logged MLflow param on every eval run.

## Before you start

Confirm with the user:
- Databricks CLI is authenticated (`databricks current-user me` succeeds)
- Real model-serving endpoint names for `config.yml` (do not use the placeholder names
  as-is — check what's actually available in Serving on their workspace)
- `data/jds.json` has been filled in with real JDs (this is a human task, not yours to invent)
