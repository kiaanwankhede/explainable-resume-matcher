# Build plan — 100 bite-size steps

Databricks build only (per `CLAUDE.md`/`SPEC.md`). Do not reorder phases — each
one's output should be queried/confirmed before starting the next. `hana/` stays
untouched until step 100.

## Phase 0 — Prerequisites (1–6)
1. Authenticate the Databricks CLI; confirm `databricks current-user me` succeeds.
2. Fill the real Free Edition workspace URL into `databricks.yml: targets.dev.workspace.host`.
3. Check the workspace's Serving page for available Foundation Model API endpoints.
4. Replace the placeholder endpoint names in `config.yml: models.*` with real ones.
5. Confirm you have permission to create a catalog in Unity Catalog.
6. Download `resume-dataset.csv` from Kaggle locally (manual — Free Edition blocks outbound internet from jobs).

## Phase 1 — Unity Catalog setup (7–13)
7. Create catalog `resume_matcher`.
8. Create schema `bronze`.
9. Create schema `silver`.
10. Create schema `gold`.
11. Create schema `eval`.
12. Create a UC Volume under `bronze` for uploads.
13. Upload `resume-dataset.csv` to that volume via the workspace UI; record the path in `config.yml: data.raw_csv_path`.

## Phase 2 — `ingest.py` (14–24)
14. Implement deterministic `resume_id` (uuid5 of raw_text).
15. Implement CSV read (Category, Resume columns) via Spark.
16. Define/create the `bronze.resumes_raw` table per SPEC §3.
17. Implement `MERGE INTO` keyed on `resume_id`.
18. Add `source` constant + `ingested_at` timestamp columns.
19. Wire `argparse --config` in `__main__`.
20. Test `ingest()` locally against a ~10-row sample CSV.
21. Re-run against the same sample; confirm no duplicate rows (idempotency).
22. Run `ingest.py` against the full uploaded CSV.
23. Query `bronze.resumes_raw`; confirm row count and schema match SPEC §3.
24. Commit + push working `ingest.py`.

## Phase 3 — `chunk_embed.py` (25–34)
25. Implement sliding-window chunking (`chunking.window_size`/`overlap` from config).
26. Implement `chunk_id` formatting (`{resume_id}::{chunk_index}`).
27. Wrap the embedding endpoint call in a pandas UDF (not a Python for-loop).
28. Batch rows per UDF call to respect endpoint limits.
29. Implement `MERGE INTO silver.resume_chunks` keyed on `chunk_id`.
30. Wire `argparse --config`.
31. Unit-test the chunking function alone (no embedding call) on one sample resume.
32. Smoke-test one real embedding call against the configured endpoint.
33. Run `chunk_embed.py` end-to-end against `bronze.resumes_raw`.
34. Query `silver.resume_chunks`; confirm embeddings are populated and chunk counts look sane.

## Phase 4 — `build_index.py` (35–42)
35. Implement an index-exists check for `resume_matcher.silver.resume_chunks_index`.
36. Implement Delta Sync index creation (embedding source column = `embedding`).
37. Implement a sync-trigger call for an already-existing index.
38. Wire `argparse --config`.
39. Run `build_index.py` to create the index.
40. Confirm the index reaches "online"/ready state.
41. Run one manual `similarity_search` as a smoke test.
42. Commit + push working `chunk_embed.py` + `build_index.py`.

## Phase 5 — `extract_requirements.py` (43–52)
43. Implement the `data/jds.json` loader.
44. Implement `gold.jds` write.
45. Implement the pre-structured-`requirements`-array parsing path.
46. Design the structured-output schema/prompt for LLM extraction from `raw_text`.
47. Implement the LLM extraction call against `models.extraction_endpoint`.
48. Validate LLM output: enforce `requirement_category` enum, apply default weights.
49. Implement `gold.jd_requirements` write.
50. Wire `argparse --config`.
51. Run extraction via the pre-structured path for all bootstrap JDs.
52. Run extraction via the LLM path on at least one JD; diff against the hand-authored version.

## Phase 6 — `score.py`, the core RAG loop (53–66)
53. Implement top-k retrieval against the AI Search index, filtered by `resume_id`.
54. Implement the confidence-gate check (best hit `None` or score below threshold).
55. Implement the gated-fail row (nulls, `meets_requirement=False`) — no model call.
56. Implement the grounded-explanation prompt (requirement_text + chunk_text → one sentence).
57. Implement the generation call against `models.generation_endpoint`.
58. Implement the gated-pass row (`meets_requirement=True`).
59. Enforce in code: `generated_explanation is null` iff `retrieved_chunk_id is null`.
60. Implement `aggregate_scores()` as a pure function (Σ weight × retrieval_score).
61. Implement per-requirement weight lookup from `config.scoring`.
62. Wire `__main__` to loop over every (jd, resume, requirement) triple.
63. Wire the `gold.match_results` write.
64. Wire the `gold.candidate_scores` write (with rank).
65. Implement `test_confidence_gate_blocks_generation` with a mocked generation client.
66. Implement `test_aggregate_scores_is_pure` with `client=None`; get both tests green.

## Phase 7 — eval data + `eval.py` (67–78)
67. Author ~50 rows in `data/eval_labels.csv` (fit/no_fit/partial_fit) using real `resume_id`s from `bronze.resumes_raw`.
68. Author ~10 rows for `eval.eval_evidence_labels` with expected evidence text.
69. Load both label sets into `eval.eval_labels` / `eval.eval_evidence_labels`.
70. Implement `compute_precision_recall()`: pull top-5/top-10 ranked resumes per `jd_id`.
71. Implement precision@5 against `human_label == "fit"`.
72. Implement recall@10 against `human_label == "fit"`.
73. Implement `compute_faithfulness()`: fetch matching `generated_explanation` per evidence-label row.
74. Implement embedding-similarity scoring vs. `expected_evidence_text`.
75. Implement the `pct_requirements_gated_no_evidence` metric.
76. Log every flattened `config.yml` value as an MLflow param.
77. Log all four metrics to the run.
78. Attach the `gold.match_results` CSV artifact; run `eval.py` and confirm a run lands in `/resume-matcher/eval`.

## Phase 8 — bundle + job wiring (79–86)
79. Run `databricks bundle validate` against `databricks.yml`/`resources/job.yml`.
80. Resolve whether `spark_python_task` needs an explicit `environment_key` on serverless.
81. Fix any path/schema issues `validate` surfaces.
82. Deploy the bundle to the `dev` target.
83. Run the full DAG (`databricks bundle run resume_matcher_pipeline`).
84. Confirm the `ingest → chunk_embed → build_index` branch completes.
85. Confirm `extract_requirements` completes in parallel with that branch.
86. Confirm `score → eval` complete after both branches; check the job run UI for success.

## Phase 9 — Genie Agent, optional (87–93)
87. Write `COMMENT ON TABLE` statements for all four `gold` tables.
88. Write `COMMENT ON COLUMN` statements for key columns, in recruiter-readable language.
89. Apply `table_comments.sql` against the workspace.
90. Attach a Genie Agent to the four `gold` tables via the UI.
91. Add 3+ example question → SQL pairs in the Genie UI.
92. Add plain-text instructions (e.g. how to explain a non-qualifying candidate).
93. Record a short demo answering 3 example questions correctly.

## Phase 10 — README + wrap-up (94–100)
94. Add the architecture diagram to the top-level README.
95. Report the eval numbers from your best MLflow run in the README.
96. Write the deterministic/LLM-boundary paragraph in the README.
97. Walk every checkbox in `SPEC.md` §11 (Definition of Done) and confirm each one.
98. Run the full test suite (`pytest databricks/tests`) one final time, all green.
99. Make a "Databricks build complete" milestone commit.
100. Confirm with the user before starting anything in `hana/` — only then draft its port spec.
