# Build plan — 100 bite-size steps

Databricks build only (per `CLAUDE.md`/`SPEC.md`). Do not reorder phases — each
one's output should be queried/confirmed before starting the next. `hana/` stays
untouched until step 100. Every step has **Why** (the reason it exists/matters)
and **How** (concretely what to run or write).

## Phase 0 — Prerequisites (1–6)

**1. Authenticate the Databricks CLI.**
- *Why:* every later step (catalog creation, running modules, deploying the bundle) goes through the CLI/SDK — nothing works without a valid auth profile.
- *How:* install the CLI, then `databricks auth login --host <workspace-url>` (or `databricks configure`), and confirm with `databricks current-user me`.

**2. Fill the real workspace URL into `databricks.yml`.**
- *Why:* the bundle needs a concrete target; the checked-in file has a placeholder.
- *How:* edit `databricks/databricks.yml`, replace `https://<your-free-edition-workspace-url>` under `targets.dev.workspace.host` with the URL used in step 1.

**3. Check the Serving page for real endpoint names.**
- *Why:* `config.yml` ships with placeholder endpoint names that likely don't exist in your workspace; SPEC §7 requires pay-per-token Foundation Model API endpoints, not custom-deployed models.
- *How:* in the workspace UI, go to **Serving**, note (or enable, under Foundation Model APIs) an embedding endpoint name and an LLM endpoint name.

**4. Update `config.yml` with those names.**
- *Why:* `chunk_embed.py`, `extract_requirements.py`, and `score.py` all read endpoint names from here; wrong names fail at call time.
- *How:* edit `models.embedding_endpoint`, `models.extraction_endpoint`, `models.generation_endpoint` in `databricks/config.yml`.

**5. Confirm you can create a catalog.**
- *Why:* Free Edition workspaces sometimes restrict catalog creation to admins — better to find out before scripting Phase 1.
- *How:* try `databricks catalogs create --name resume_matcher_test` (or check the "Create Catalog" button in Catalog Explorer), then delete the test catalog.

**6. Download the Kaggle CSV locally.**
- *Why:* SPEC §7 — outbound internet from jobs is restricted, so the Kaggle API call can't run inside Databricks; this one download has to happen on your own machine.
- *How:* find the Kaggle resume dataset (Category/Resume columns), download and unzip it to get `resume-dataset.csv`.

## Phase 1 — Unity Catalog setup (7–13)

**7. Create the catalog.**
- *Why:* everything in this project lives under one catalog per SPEC §3, keeping it isolated from other UC objects.
- *How:* `databricks catalogs create --name resume_matcher`.

**8–11. Create schemas `bronze`, `silver`, `gold`, `eval`.**
- *Why:* this is the medallion pattern the whole pipeline is built on — raw upload, chunked+embedded data, curated results, and evaluation ground truth each need clear separation for lineage and permissions.
- *How:* `databricks schemas create bronze resume_matcher`, then repeat for `silver`, `gold`, `eval` (or run `CREATE SCHEMA resume_matcher.bronze` etc. in a SQL editor).

**12. Create a UC Volume for uploads.**
- *Why:* the Kaggle CSV needs somewhere inside UC that Spark jobs can read from; Volumes are UC's managed file storage for exactly this.
- *How:* in Catalog Explorer: `resume_matcher → bronze → Volumes → Create Volume`, name it e.g. `uploads`.

**13. Upload the CSV.**
- *Why:* the one unavoidable manual step per SPEC §5.1.
- *How:* on that Volume's page, click Upload, select the local `resume-dataset.csv`, then copy the resulting path (e.g. `/Volumes/resume_matcher/bronze/uploads/resume-dataset.csv`) into `config.yml: data.raw_csv_path`.

## Phase 2 — `ingest.py` (14–24)

**14. Implement deterministic `resume_id`.**
- *Why:* re-ingesting the same CSV must never create duplicate rows (SPEC §3) — a hash of the content, not a random UUID, guarantees that.
- *How:* `uuid.uuid5(uuid.NAMESPACE_URL, raw_text)`, applied as a Spark UDF or in a pandas step.

**15. Implement the CSV read.**
- *Why:* the source data is Category/Resume columns; this becomes the DataFrame everything else operates on.
- *How:* `spark.read.csv(raw_csv_path, header=True, multiLine=True, escape='"')` — sanity-check quoting/escaping with a quick local `pandas.read_csv` first.

**16. Define/create `bronze.resumes_raw`.**
- *Why:* the concrete Delta table `ingest.py` writes to, per the SPEC §3 schema.
- *How:* `CREATE TABLE IF NOT EXISTS resume_matcher.bronze.resumes_raw (resume_id STRING, category STRING, raw_text STRING, source STRING, ingested_at TIMESTAMP) USING DELTA`.

**17. Implement `MERGE INTO`.**
- *Why:* the idempotency requirement in SPEC — re-running must not duplicate rows.
- *How:* register the incoming DataFrame as a temp view, then `MERGE INTO bronze.resumes_raw t USING updates s ON t.resume_id = s.resume_id WHEN NOT MATCHED THEN INSERT *`.

**18. Add `source`/`ingested_at` columns.**
- *Why:* `source` traces provenance if a second dataset is added later; `ingested_at` supports debugging/auditing.
- *How:* `.withColumn("source", lit("kaggle_resume_dataset")).withColumn("ingested_at", current_timestamp())`.

**19. Wire `argparse --config`.**
- *Why:* matches the CLI contract in SPEC (`python ingest.py --config config.yml`) and what the job task will invoke.
- *How:* `argparse.ArgumentParser().add_argument("--config", required=True)`, then call `ingest(args.config)`.

**20. Test locally on a ~10-row sample.**
- *Why:* CLAUDE.md explicitly requires this before wiring into the bundle job — a much cheaper feedback loop.
- *How:* `head -n 11 resume-dataset.csv > sample.csv`, point a copy of `config.yml` at it, run `python ingest.py --config sample_config.yml`, inspect with `spark.table("bronze.resumes_raw").show()`.

**21. Re-run and check idempotency.**
- *Why:* proves the MERGE logic actually works, not just "looks right on paper."
- *How:* run step 20 twice; `SELECT COUNT(*), COUNT(DISTINCT resume_id) FROM bronze.resumes_raw` must show equal counts.

**22. Run against the full CSV.**
- *Why:* moves from sample to real data before wiring into orchestration.
- *How:* point `config.yml` at the full uploaded path from step 13, run `python ingest.py --config config.yml`.

**23. Query and verify the output.**
- *Why:* CLAUDE.md's build order requires confirming each module's output before starting the next.
- *How:* `SELECT COUNT(*), COUNT(DISTINCT category) FROM resume_matcher.bronze.resumes_raw;` — row count should roughly match the CSV, category count ≤ 25.

**24. Commit + push.**
- *Why:* locks in a working checkpoint before the harder modules.
- *How:* `git add databricks/src/ingest.py && git commit -m "..." && git push`.

## Phase 3 — `chunk_embed.py` (25–34)

**25. Implement sliding-window chunking.**
- *Why:* resumes are long free text; embedding the whole document loses retrieval precision — SPEC's design note says chunk by paragraph/sentence-window.
- *How:* slide a window of `chunking.window_size` tokens with `chunking.overlap` step-back over each `raw_text`, yielding `(chunk_index, chunk_text)` pairs.

**26. Implement `chunk_id` formatting.**
- *Why:* this is the PK contract in SPEC §3, and what the MERGE in step 29 keys on.
- *How:* `f"{resume_id}::{chunk_index}"`.

**27. Wrap the embedding call in a pandas UDF.**
- *Why:* SPEC explicitly requires Spark-native parallelism here, not a Python for-loop — "the whole point of running it on Databricks."
- *How:* `@pandas_udf(ArrayType(FloatType()))` around a function that takes a `pd.Series[str]`, calls the embedding endpoint, and returns a `pd.Series[list[float]]`.

**28. Batch the embedding calls.**
- *Why:* FM API endpoints have payload/rate limits — one row per call is slow, unbounded batches can 413/429.
- *How:* inside the UDF, split the incoming series into sub-batches of ~20–50 texts per API call.

**29. `MERGE INTO silver.resume_chunks`.**
- *Why:* same idempotency requirement as ingest.
- *How:* same MERGE pattern as step 17, keyed on `chunk_id`.

**30. Wire `argparse --config`.**
- *Why:* CLI-contract consistency across modules.
- *How:* same pattern as step 19.

**31. Unit-test chunking alone.**
- *Why:* isolates chunking correctness from embedding-endpoint flakiness and cost.
- *How:* call the chunking function directly on one string; assert expected chunk count and overlap — no Spark, no endpoint involved.

**32. Smoke-test one real embedding call.**
- *Why:* confirms endpoint name/auth/payload shape before running at scale.
- *How:* call the embedding client with a single string from a notebook cell, print the returned vector's length.

**33. Run end-to-end.**
- *Why:* moves to real data.
- *How:* `python chunk_embed.py --config config.yml` against the full `bronze.resumes_raw`.

**34. Query and verify.**
- *Why:* checkpoint before `build_index.py`.
- *How:* `SELECT COUNT(*), AVG(size(embedding)) FROM resume_matcher.silver.resume_chunks;` — chunk counts should scale sensibly with resume length, embedding dims should be constant.

## Phase 4 — `build_index.py` (35–42)

**35. Implement an index-exists check.**
- *Why:* the module must be safely re-runnable — create if missing, otherwise just sync.
- *How:* Vector Search SDK's `list_indexes(endpoint_name)`, or try/except around `get_index`.

**36. Implement Delta Sync index creation.**
- *Why:* SPEC §4 specifies Delta Sync mode off `silver.resume_chunks` with the embedding source column set to `embedding`.
- *How:* `client.create_delta_sync_index(endpoint_name=..., index_name="resume_matcher.silver.resume_chunks_index", source_table_name="resume_matcher.silver.resume_chunks", pipeline_type="TRIGGERED", primary_key="chunk_id", embedding_vector_column="embedding", embedding_dimension=<dim>)`.

**37. Implement the sync trigger.**
- *Why:* a `TRIGGERED` pipeline needs an explicit sync call to pick up new rows after each `chunk_embed` run.
- *How:* `client.get_index(...).sync()`.

**38. Wire `argparse --config`** — same pattern as step 19.

**39. Run to create the index.**
- *Why:* first real creation against your data.
- *How:* `python build_index.py --config config.yml`.

**40. Confirm the index is online.**
- *Why:* index builds take time; querying before it's ready fails or returns stale/empty results.
- *How:* poll `index.describe()["status"]["ready"]`, or check the Vector Search UI page.

**41. Run a `similarity_search` smoke test.**
- *Why:* proves retrieval works end-to-end before `score.py` depends on it.
- *How:* `index.similarity_search(query_text="Java backend developer", columns=["chunk_id","chunk_text"], num_results=3)`.

**42. Commit + push.**
- *Why:* locks in two working modules before the extraction/scoring modules.
- *How:* `git add databricks/src/chunk_embed.py databricks/src/build_index.py && git commit -m "..." && git push`.

## Phase 5 — `extract_requirements.py` (43–52)

**43. Implement the `data/jds.json` loader.**
- *Why:* this file is the hand-authored source of truth for JDs.
- *How:* `json.load(open(path))`, validate the expected keys (`jd_id`, `title`, `target_category`, `raw_text`, `requirements`).

**44. Implement the `gold.jds` write.**
- *Why:* the SPEC §3 table extraction populates.
- *How:* build rows of `{jd_id, title, target_category, raw_text}`, `MERGE INTO gold.jds`.

**45. Implement the pre-structured-array parsing path.**
- *Why:* SPEC §5.2 allows skipping the LLM call for bootstrap JDs that already ship a `requirements` array.
- *How:* if `jd["requirements"]` is present, map each entry directly to a `jd_requirements` row with `requirement_id = f"{jd_id}::{n}"`, defaulting `weight` from `config.scoring`.

**46. Design the structured-output schema/prompt.**
- *Why:* needed for the LLM extraction path — the thing that actually exercises "extraction" as its own module rather than just parsing JSON.
- *How:* write a prompt requiring atomic requirements only (one skill per item), `requirement_category` restricted to `must_have`/`nice_to_have`; use the endpoint's JSON-mode/structured-output feature if available, otherwise instruct-and-parse with a retry on invalid JSON.

**47. Implement the LLM extraction call.**
- *Why:* the concrete extraction-not-RAG module SPEC calls out as its own boundary.
- *How:* call `models.extraction_endpoint` (e.g. via `mlflow.deployments.get_deploy_client("databricks").predict(endpoint=..., inputs={...})`) with the JD's `raw_text` and the prompt/schema from step 46.

**48. Validate the LLM output.**
- *Why:* structured output can still drift from the schema — never trust it blindly before writing to a gold table.
- *How:* parse the JSON, assert `requirement_category` is one of the two allowed values (skip/default otherwise), fill missing `weight` from `config.scoring`.

**49. Implement the `gold.jd_requirements` write.**
- *Why:* the SPEC §3 table.
- *How:* `MERGE INTO gold.jd_requirements` keyed on `requirement_id`.

**50. Wire `argparse --config`** — same pattern as step 19.

**51. Run the pre-structured path for all bootstrap JDs.**
- *Why:* gets the trusted, hand-authored data into the gold tables first.
- *How:* `python extract_requirements.py --config config.yml` with `data/jds.json` as shipped.

**52. Run the LLM path on at least one JD.**
- *Why:* Definition of Done requires the extraction module to be genuinely exercised via the LLM, not just JSON-parsed.
- *How:* temporarily force one JD through the LLM path (e.g. strip its `requirements` array or add a `--force-llm` flag), re-run, and diff the LLM-derived requirements against the original hand-authored ones.

## Phase 6 — `score.py`, the core RAG loop (53–66)

**53. Implement top-k retrieval.**
- *Why:* this is the "R" in RAG — the only mechanism by which requirement evidence gets found.
- *How:* `index.similarity_search(query_text=requirement_text, num_results=config.retrieval.top_k, filters={"resume_id": resume_id})`.

**54. Implement the confidence gate.**
- *Why:* SPEC §0 non-negotiable #2 — never call generation on weak evidence.
- *How:* `best = hits[0] if hits else None`; `gate_passed = best is not None and best.score >= config.retrieval.confidence_threshold`.

**55. Implement the gated-fail row.**
- *Why:* the concrete enforcement of the same non-negotiable.
- *How:* when the gate fails, return `{..., retrieved_chunk_id: None, retrieval_score: None, generated_explanation: None, meets_requirement: False}` immediately — no generation-client code runs on this path.

**56. Design the grounded-explanation prompt.**
- *Why:* SPEC is explicit — the model explains retrieved evidence, it never judges fit.
- *How:* e.g. `"Requirement: {requirement_text}\nResume excerpt: {chunk_text}\nWrite one sentence explaining how this excerpt supports the requirement, quoting the relevant part."`

**57. Implement the generation call.**
- *Why:* the only place in the codebase permitted to call this endpoint, per `score.py`'s own docstring.
- *How:* call `models.generation_endpoint` via the FM API deploy client with the prompt from step 56.

**58. Implement the gated-pass row.**
- *Why:* completes the schema when the gate passes.
- *How:* return `{..., retrieved_chunk_id: best.chunk_id, retrieval_score: best.score, generated_explanation: <model output>, meets_requirement: True}`.

**59. Enforce the null-pairing invariant in code.**
- *Why:* SPEC §3 calls this out explicitly as a data-quality invariant, not just a suggestion.
- *How:* add `assert (row["generated_explanation"] is None) == (row["retrieved_chunk_id"] is None)` before returning from `score_requirement`.

**60. Implement `aggregate_scores` as a pure function.**
- *Why:* SPEC §0 non-negotiable #3 — the final score is a deterministic weighted sum, never an LLM judgment.
- *How:* `sum(weight_for(r["requirement_category"]) * r["retrieval_score"] for r in results if r["meets_requirement"])`.

**61. Implement the weight lookup.**
- *Why:* weights are tunable via config, not hardcoded.
- *How:* `{"must_have": config.scoring.weight_must_have, "nice_to_have": config.scoring.weight_nice_to_have}[requirement_category]`.

**62. Wire the orchestration loop.**
- *Why:* `score_requirement` handles one triple; something must drive it across the full cross-product.
- *How:* for each `jd_id` in `gold.jds`, each of its rows in `gold.jd_requirements`, and each `resume_id` in `bronze.resumes_raw`, call `score_requirement(...)`.

**63. Wire the `gold.match_results` write.**
- *Why:* the SPEC table, and what `eval.py` reads from.
- *How:* collect all `score_requirement` outputs, `MERGE INTO gold.match_results`.

**64. Wire the `gold.candidate_scores` write.**
- *Why:* the SPEC table with rank, used for precision/recall in eval.
- *How:* group `match_results` by `(jd_id, resume_id)`, call `aggregate_scores`, then apply a `RANK()` window function partitioned by `jd_id` ordered by `total_score DESC`.

**65. Implement `test_confidence_gate_blocks_generation`.**
- *Why:* Definition of Done item — proves the gate is real, enforced code, not just a docstring claim.
- *How:* build a fake retrieval result with score below threshold, pass a `Mock()` generation client into `score_requirement`, assert `mock.predict.call_count == 0` and the row matches the gated-fail shape.

**66. Implement `test_aggregate_scores_is_pure`.**
- *Why:* proves determinism and the absence of a hidden model dependency.
- *How:* call `aggregate_scores(fixture_results, config)` with no client at all (or `client=None`), assert the numeric output matches a hand-computed expected value; get both tests green.

## Phase 7 — eval data + `eval.py` (67–78)

**67. Author ~50 rows in `data/eval_labels.csv`.**
- *Why:* SPEC §5.3 — these hand-labeled pairs are the ground truth `eval.py` measures against; this is explicitly a human task, not Claude's to invent.
- *How:* once step 22/23 gives real `resume_id`s, pick ~8–10 resumes per JD split across `fit`/`no_fit`/`partial_fit` per the rule in SPEC §5.3, and fill in the CSV.

**68. Author ~10 rows for `eval_evidence_labels`.**
- *Why:* needed for the faithfulness spot-check.
- *How:* for ~10 of the pairs above, read the actual resume text and write down the specific line that should support each requirement.

**69. Load both label sets into UC tables.**
- *Why:* `eval.py` reads them as Delta tables, not raw CSVs.
- *How:* `spark.read.csv("data/eval_labels.csv", header=True).write.saveAsTable("resume_matcher.eval.eval_labels")`, and the same for `eval_evidence_labels`.

**70. Implement the ranked-results pull in `compute_precision_recall`.**
- *Why:* needs the system's ranked output per JD before it can be scored against ground truth.
- *How:* for each `jd_id` in `eval_labels`, `SELECT resume_id FROM gold.candidate_scores WHERE jd_id=... ORDER BY rank LIMIT 10`.

**71. Implement precision@5.**
- *Why:* the standard IR metric SPEC asks for.
- *How:* `len(set(top5) & set(fit_resume_ids)) / 5`, averaged across JDs.

**72. Implement recall@10.**
- *Why:* same idea, at k=10, measuring coverage rather than precision.
- *How:* `len(set(top10) & set(fit_resume_ids)) / len(fit_resume_ids)`, averaged across JDs.

**73. Implement the evidence fetch in `compute_faithfulness`.**
- *Why:* needs the actual generated text before comparing it to anything.
- *How:* join `eval.eval_evidence_labels` to `gold.match_results` on `(jd_id, resume_id, requirement_id)`, pull `generated_explanation`.

**74. Implement the embedding-similarity comparison.**
- *Why:* an automatable proxy for "did the explanation actually reflect the expected evidence" — SPEC is explicit this is a signal for manual review, not a pass/fail gate.
- *How:* embed both `generated_explanation` and `expected_evidence_text` via the embedding endpoint, compute cosine similarity, average across rows.

**75. Implement `pct_requirements_gated_no_evidence`.**
- *Why:* SPEC calls this an "honesty metric" — if it's near 0%, the confidence threshold is probably too lax.
- *How:* `COUNT(retrieved_chunk_id IS NULL) / COUNT(*)` over `gold.match_results` for the eval JDs.

**76. Log every `config.yml` value as an MLflow param.**
- *Why:* CLAUDE.md non-negotiable #5.
- *How:* flatten the nested config dict (e.g. `retrieval.top_k` → `"retrieval.top_k"`), then `mlflow.log_params(flat_config)`.

**77. Log the four metrics.**
- *Why:* makes eval runs comparable over time as the threshold/weights are tuned.
- *How:* `mlflow.log_metrics({"precision_at_5":..., "recall_at_10":..., "faithfulness_mean_similarity":..., "pct_requirements_gated_no_evidence":...})`.

**78. Attach the artifact and confirm the run.**
- *Why:* lets a future reviewer inspect actual evidence trails, not just aggregate numbers.
- *How:* write `gold.match_results` (filtered to the eval JDs) to a local CSV, `mlflow.log_artifact(...)`; run `eval.py`, then check the `/resume-matcher/eval` experiment in the MLflow UI for the new run.

## Phase 8 — bundle + job wiring (79–86)

**79. Run `databricks bundle validate`.**
- *Why:* `databricks.yml`/`resources/job.yml` are checked in as unverified skeletons; validate catches syntax errors before deploy.
- *How:* `cd databricks && databricks bundle validate`.

**80. Resolve the `environment_key` question for serverless.**
- *Why:* Free Edition is serverless-only; `spark_python_task` may need an explicit serverless environment spec rather than a cluster reference.
- *How:* check the current Databricks Asset Bundle docs for serverless job-task syntax; add an `environments:` block to `job.yml` if validate/deploy errors point to it.

**81. Fix any path/schema issues.**
- *Why:* validate/deploy will surface wrong relative paths or unsupported keys.
- *How:* iterate — fix each reported error, re-run `databricks bundle validate` until clean.

**82. Deploy the bundle.**
- *Why:* uploads the code and registers the job resource in the workspace.
- *How:* `databricks bundle deploy -t dev`.

**83. Run the full DAG.**
- *Why:* proves the pipeline works as an actual Databricks Job, not just as manually-run scripts — Definition of Done requires this.
- *How:* `databricks bundle run resume_matcher_pipeline -t dev`.

**84–86. Confirm both branches and the join complete.**
- *Why:* same checkpoint discipline as earlier phases, now at the orchestration level — `ingest→chunk_embed→build_index` and `extract_requirements` should both finish before `score→eval` starts.
- *How:* watch the run in the Jobs UI (or `databricks jobs get-run <run_id>`), confirm every `task_key` shows SUCCESS in the expected order/parallelism.

## Phase 9 — Genie Agent, optional (87–93)

**87–88. Write `COMMENT ON TABLE`/`COMMENT ON COLUMN` statements.**
- *Why:* Genie reads these comments to understand the schema (SPEC §10) — write them for a recruiter, not an engineer.
- *How:* fill in `resources/table_comments.sql` for `gold.jds`, `gold.jd_requirements`, `gold.match_results`, `gold.candidate_scores` and their key columns.

**89. Apply the SQL.**
- *Why:* comments must actually be applied in the workspace before Genie can see them.
- *How:* run `table_comments.sql` in a SQL editor/notebook against the workspace.

**90. Attach a Genie Agent.**
- *Why:* the one other manual UI step SPEC explicitly allows (same category as the CSV upload).
- *How:* in the workspace, **Genie → New Agent**, add the four `gold` tables as its data source.

**91. Add example question → SQL pairs.**
- *Why:* improves Genie's accuracy on your specific schema and expected questions.
- *How:* in the Genie Agent UI, add sample questions like *"which candidates scored above 0.8 for the Java Developer role?"* with the expected SQL.

**92. Add plain-text instructions.**
- *Why:* steers Genie's behavior on domain-specific asks (e.g. explaining a non-qualifying candidate).
- *How:* add an instruction like *"when asked why a candidate didn't qualify, filter match_results on meets_requirement = false and surface generated_explanation."*

**93. Record a short demo.**
- *Why:* Definition of Done wants ≥3 example questions answered correctly, recorded.
- *How:* screen-record asking 3 example questions in the Genie chat UI and getting correct, evidence-backed answers.

## Phase 10 — README + wrap-up (94–100)

**94. Add the architecture diagram to the README.**
- *Why:* Definition of Done — a reviewer reads the README before opening any code.
- *How:* adapt the ASCII diagram from `SPEC.md` §1 into the top-level `README.md`.

**95. Report the eval numbers.**
- *Why:* turns "we tuned it and it got better" into a demonstrable, specific claim.
- *How:* pull the best MLflow run's metrics and paste precision@5/recall@10/faithfulness into the README.

**96. Write the deterministic/LLM-boundary paragraph.**
- *Why:* explicitly required by Definition of Done — explains *why* the split exists, not just that it does.
- *How:* one paragraph: what's deterministic (the confidence gate, `aggregate_scores`) vs. what calls a model (embedding, extraction, generation), and why that boundary matters for trust/auditability in a hiring-adjacent tool.

**97. Walk every Definition of Done checkbox.**
- *Why:* the final acceptance gate — also the precondition CLAUDE.md sets before `hana/` can ever be started.
- *How:* go through `SPEC.md` §11 line by line, verify and tick each `- [ ]`.

**98. Run the full test suite one final time.**
- *Why:* last correctness gate before calling the build done.
- *How:* `pytest databricks/tests -v`, confirm all green.

**99. Make a "Databricks build complete" milestone commit.**
- *Why:* marks a clean, referenceable checkpoint.
- *How:* `git add -A && git commit -m "Databricks build complete" && git push`.

**100. Confirm with the user before touching `hana/`.**
- *Why:* explicitly gated by `CLAUDE.md` and `hana/README.md` — sequential, not parallel; one complete, evaluated build beats two half-finished ports.
- *How:* ask directly; only after confirmation, request a HANA-equivalent spec at the same depth as `SPEC.md` (per `hana/README.md`).
