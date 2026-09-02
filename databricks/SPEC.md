# Explainable Resume ↔ JD Matcher — Databricks Build Spec

Hand this to Claude Code as the implementation brief. It defines every data contract, module boundary, and business rule precisely enough that implementation shouldn't require guessing. Drop it in the repo root as `SPEC.md` (or fold into `CLAUDE.md`).

## 0. Non-negotiables (read before implementing anything)

1. **This is RAG, not a scoring script.** Retrieval pulls evidence; a generation step turns that evidence into a grounded explanation. If a code path skips the LLM generation call and just surfaces the raw chunk, it's not done.
2. **Never let the LLM hallucinate support for a requirement.** If retrieval doesn't clear the confidence threshold, the requirement is marked unmet — no generation call happens, no explanation is fabricated.
3. **Scoring is deterministic.** The final numeric score is a plain weighted sum, computed in code, never asked of an LLM.
4. **Everything is code, nothing is clicked.** No manual notebook-UI steps except the one unavoidable one (§5.1).
5. **Free Edition constraints are real constraints, not suggestions** — see §7.

---

## 1. Architecture

```
┌─────────────┐
│  Kaggle CSV  │ (manual upload once — see §5.1)
└──────┬──────┘
       ▼
┌─────────────────┐
│ bronze.resumes_raw│  ingest.py
└──────┬───────────┘
       ▼
┌───────────────────┐
│ silver.resume_chunks│  chunk_embed.py — chunk + call embedding endpoint
└──────┬─────────────┘
       ▼
┌───────────────────┐
│ AI Search index     │  build_index.py — synced off resume_chunks
└─────────────────────┘

┌──────────────┐
│ data/jds.json │ (hand-authored — see §5.2)
└──────┬────────┘
       ▼
┌───────────────────────┐
│ gold.jds + jd_requirements│  extract_requirements.py — LLM extraction
└──────┬─────────────────┘
       ▼
┌────────────────────────────────────────────────────┐
│  score.py — the RAG loop, per (jd, resume, requirement):        │
│  retrieve top-k chunks → confidence gate →                       │
│  [pass] generate grounded explanation (LLM)  [fail] mark unmet    │
│  → deterministic weighted aggregation → gold.match_results        │
└──────┬───────────────────────────────────────────────┘
       ▼
┌───────────────────┐
│ eval.py — precision@5/recall@10 vs eval.eval_labels, logged to MLflow │
└─────────────────────┘
```

---

## 2. Repo layout (Databricks Asset Bundle)

```
resume-matcher/
├── databricks.yml                 # bundle root config
├── config.yml                     # all tunable params (§8)
├── data/
│   ├── jds.json                   # 5–6 hand-written JDs (§5.2)
│   └── eval_labels.csv            # 50 hand-labeled pairs (§5.3)
├── src/
│   ├── ingest.py
│   ├── chunk_embed.py
│   ├── build_index.py
│   ├── extract_requirements.py
│   ├── score.py
│   └── eval.py
├── resources/
│   ├── job.yml                    # task DAG (§9)
│   └── table_comments.sql         # gold-schema metadata for the Genie Agent (§10, optional)
└── tests/
    └── test_scoring.py            # unit tests for the deterministic aggregator
```

---

## 3. Data model

Catalog: `resume_matcher` (Unity Catalog). Schemas: `bronze`, `silver`, `gold`, `eval`.

### `bronze.resumes_raw`
| column | type | notes |
|---|---|---|
| resume_id | string (PK) | `uuid5` of raw_text, deterministic so re-ingestion is idempotent |
| category | string | one of the 25 Kaggle categories |
| raw_text | string | |
| source | string | constant `"kaggle_resume_dataset"` |
| ingested_at | timestamp | |

### `silver.resume_chunks`
| column | type | notes |
|---|---|---|
| chunk_id | string (PK) | `f"{resume_id}::{chunk_index}"` |
| resume_id | string (FK) | |
| chunk_text | string | |
| chunk_index | int | |
| embedding | array\<float\> | populated by `chunk_embed.py`, this is the column AI Search syncs on |

*(No separate section-parsing table — the Kaggle rows are already scoped to one category/role, and forcing a hard experience/skills/education split on free-text resumes adds parsing risk for no eval benefit at this stage. Chunk by paragraph/sentence-window instead. Revisit only if evidence quality in eval looks section-confused.)*

### `gold.jds`
| column | type | notes |
|---|---|---|
| jd_id | string (PK) | slug, e.g. `"java-developer"` |
| title | string | |
| target_category | string | must match a `bronze.resumes_raw.category` value — this is what makes eval labeling possible |
| raw_text | string | |

### `gold.jd_requirements`
| column | type | notes |
|---|---|---|
| requirement_id | string (PK) | `f"{jd_id}::{n}"` |
| jd_id | string (FK) | |
| requirement_text | string | atomic — one skill/qualification per row, never a compound clause |
| requirement_category | string | enum: `must_have` \| `nice_to_have` |
| weight | float | must_have default 1.0, nice_to_have default 0.4 (tune in `config.yml`) |

### `gold.match_results`
| column | type | notes |
|---|---|---|
| result_id | string (PK) | |
| jd_id, resume_id, requirement_id | string (FK) | |
| retrieved_chunk_id | string, nullable | null if confidence gate failed |
| retrieval_score | float, nullable | |
| generated_explanation | string, nullable | **null iff retrieved_chunk_id is null** — enforce this invariant in code |
| meets_requirement | boolean | |
| scored_at | timestamp | |

### `gold.candidate_scores`
| column | type | notes |
|---|---|---|
| jd_id, resume_id | string | |
| total_score | float | sum of `weight * retrieval_score` over met requirements |
| rank | int | rank within `jd_id`, computed at query time or materialized per run |

### `eval.eval_labels`
| column | type | notes |
|---|---|---|
| eval_id | string (PK) | |
| resume_id, jd_id | string | |
| human_label | string | enum: `fit` \| `partial_fit` \| `no_fit` |
| labeled_by | string | your name/id |
| labeled_at | timestamp | |

### `eval.eval_evidence_labels`
For faithfulness checking on a ~10-pair subset.
| column | type | notes |
|---|---|---|
| eval_id | string | |
| resume_id, jd_id, requirement_id | string | |
| expected_evidence_text | string | the specific resume line a human says supports this requirement |
| notes | string, nullable | |

---

## 4. Module specs

### `src/ingest.py`
- **Input:** path to the manually-uploaded CSV in the UC Volume (`config.yml: data.raw_csv_path`).
- **Output:** writes/merges into `bronze.resumes_raw`.
- **Behavior:** read CSV (`Category`, `Resume`) → compute deterministic `resume_id` → `MERGE INTO` (idempotent — safe to re-run).
- **CLI:** `python ingest.py --config config.yml`

### `src/chunk_embed.py`
- **Input:** `bronze.resumes_raw`.
- **Output:** `silver.resume_chunks`.
- **Behavior:** chunk each `raw_text` (sliding window, params in `config.yml: chunking.window_size` / `chunking.overlap`) → batch-call the embedding endpoint (`config.yml: models.embedding_endpoint`) → write chunks + embeddings.
- **Parallelism:** use a pandas UDF over a Spark DataFrame, not a Python for-loop — this is the whole point of running it on Databricks instead of a laptop script.
- **Idempotency:** `MERGE INTO` on `chunk_id`.

### `src/build_index.py`
- **Input:** `silver.resume_chunks`.
- **Output:** one AI Search index, `resume_matcher.silver.resume_chunks_index`.
- **Behavior:** create index if not exists (Delta Sync mode, off `silver.resume_chunks`, embedding source column = `embedding`); trigger a sync on each run. See §7 for Free Edition endpoint constraints.

### `src/extract_requirements.py`
- **Input:** `data/jds.json`.
- **Output:** `gold.jds`, `gold.jd_requirements`.
- **Behavior:** for each JD, one LLM call (`config.yml: models.extraction_endpoint`) with a structured-output schema forcing `list[{requirement_text, requirement_category, weight}]`. This is extraction, explicitly **not** part of the RAG loop — keep it in its own module so the boundary in §0.1 stays visible in the repo structure, not just in prose.

### `src/score.py` — the core RAG loop
- **Input:** `gold.jd_requirements`, the AI Search index.
- **Output:** `gold.match_results`, `gold.candidate_scores`.
- **Per (jd, resume, requirement):**
  1. `hits = index.similarity_search(requirement_text, num_results=config.retrieval.top_k, filter={"resume_id": resume_id})`
  2. `best = hits[0] if hits else None`
  3. **Confidence gate:** if `best is None or best.score < config.retrieval.confidence_threshold` → write a row with `retrieved_chunk_id=null`, `generated_explanation=null`, `meets_requirement=false`. **Do not call the generation model.**
  4. **Generation (only on gate pass):** call the LLM (`config.yml: models.generation_endpoint`) with the requirement text + retrieved chunk text, prompted to produce one grounded sentence citing the chunk — never asked to judge fit, only to explain the retrieved evidence.
  5. Write the row with `meets_requirement=true`.
- **Aggregation (separate function, no LLM call):** `total_score = Σ (weight * retrieval_score)` over requirements where `meets_requirement=true`, per `(jd_id, resume_id)`, written to `gold.candidate_scores`.
- **This file should have two clearly separated functions** — `score_requirement(...)` (the per-requirement RAG loop above) and `aggregate_scores(...)` (pure, deterministic, no I/O to a model endpoint) — so the deterministic/LLM boundary is enforced by the module's own structure, not just convention.

### `src/eval.py`
- **Input:** `gold.candidate_scores`, `eval.eval_labels`, `eval.eval_evidence_labels`.
- **Output:** MLflow run with logged metrics (§10).
- **Behavior:**
  - Precision@5 / recall@10: for each `jd_id` in `eval_labels`, take the system's top-5/top-10 ranked resumes from `candidate_scores`, compare against `human_label == "fit"` as ground truth.
  - Faithfulness spot-check: for each row in `eval_evidence_labels`, fetch the corresponding `gold.match_results.generated_explanation` and compute embedding similarity against `expected_evidence_text` — log the mean, but this metric is a signal for you to manually review, not a fully automated pass/fail.

---

## 5. Data creation

### 5.1 Resume corpus (one manual step, everything else is code)
Free Edition restricts outbound internet from notebooks (see §7), so the Kaggle API call won't work from inside the job. Download `resume-dataset.csv` from Kaggle locally once, then upload it into a UC Volume through the workspace UI (`Catalog → resume_matcher → bronze → Volumes → upload`). Record the resulting path in `config.yml: data.raw_csv_path`. Everything downstream (`ingest.py` onward) is code and reruns without touching the UI again.

### 5.2 Job descriptions — `data/jds.json`
Pick 5–6 of the 25 Kaggle categories. For each, write a JD as atomic requirements, matching the `gold.jd_requirements` schema directly:
```json
{
  "jd_id": "java-developer",
  "title": "Java Developer",
  "target_category": "Java Developer",
  "raw_text": "...",
  "requirements": [
    {"requirement_text": "3+ years of experience with Java", "requirement_category": "must_have"},
    {"requirement_text": "Familiarity with CI/CD pipelines", "requirement_category": "must_have"},
    {"requirement_text": "Exposure to cloud platforms, AWS preferred", "requirement_category": "nice_to_have"}
  ]
}
```
`extract_requirements.py` can either parse the pre-structured `requirements` array directly (skip the LLM call for these bootstrap JDs) or re-derive it from `raw_text` via the LLM as a way of testing the extraction module itself — do the latter at least once so the extraction path is actually exercised before you rely on it for a 7th JD later.

### 5.3 Eval labels — `data/eval_labels.csv`
~50 pairs across your 5–6 JDs (≈8–10 per JD), three-way split:
- **fit** — resume's `category` equals the JD's `target_category`
- **no_fit** — resume from an unrelated category (negative control)
- **partial_fit** — resume from an adjacent/related category — the genuinely hard cases

For ~10 of these pairs, additionally fill `eval_evidence_labels` with the specific line you believe should support each requirement.

---

## 6. `config.yml`

```yaml
data:
  raw_csv_path: /Volumes/resume_matcher/bronze/uploads/resume-dataset.csv

chunking:
  window_size: 400        # tokens
  overlap: 50

models:
  embedding_endpoint: databricks-gte-large-en     # or current FM API embedding model
  extraction_endpoint: databricks-claude-endpoint  # structured JD parsing
  generation_endpoint: databricks-claude-endpoint  # grounded explanation generation

retrieval:
  top_k: 3
  confidence_threshold: 0.72   # tune during eval, log every value tried in MLflow params

scoring:
  weight_must_have: 1.0
  weight_nice_to_have: 0.4

catalog:
  name: resume_matcher
```
Every parameter above must be an MLflow **logged param** on every eval run — that's what makes "we tuned the threshold to X and precision moved from Y to Z" a demonstrable claim instead of an assertion.

---

## 7. Free Edition constraints — implementation notes

- **AI Search:** one endpoint, one search unit. Fine — this project needs exactly one index. Don't design for multiple indexes.
- **Model serving:** limited active endpoints, no GPU serving, no provisioned throughput. Use pay-per-token Foundation Model API endpoints for embedding/extraction/generation, not a custom-deployed model.
- **Outbound internet:** restricted to trusted domains unless LinkedIn-verified. Confirmed impact: the Kaggle download (§5.1). Everything else in this spec only talks to Databricks-internal services, so it's unaffected.
- **Jobs:** max 5 concurrent tasks per account — irrelevant here since the DAG in §9 runs sequentially.
- **Apps:** up to 3, auto-stop after 24h idle, restart anytime — fine for a demo app you spin up before an interview and restart as needed.

---

## 8. Orchestration — `resources/job.yml`

Sequential DAG, one task per module, in this order:
```
ingest → chunk_embed → build_index
                              ↘
extract_requirements ──────────→ score → eval
```
`extract_requirements` has no dependency on the chunking branch and can run in parallel with it; `score` depends on both `build_index` and `extract_requirements`.

---

## 9. MLflow eval tracking

- **Experiment:** `/resume-matcher/eval`
- **Params logged per run:** every value in `config.yml` (flatten the dict).
- **Metrics logged per run:** `precision_at_5`, `recall_at_10`, `faithfulness_mean_similarity`, `pct_requirements_gated_no_evidence` (this last one is a useful honesty metric — if it's near 0%, your confidence threshold is probably too low and you're generating explanations for weak matches).
- **Artifacts:** the full `gold.match_results` for the eval JDs, as a CSV, attached to the run — so a reviewer (or you, months later) can inspect actual evidence trails, not just the aggregate numbers.

---

## 10. Optional layer — Genie Agent for recruiter-facing querying

**What it adds:** a natural-language chat interface over the `gold` tables, so someone can ask *"which candidates scored above 0.8 for the Java Developer role?"* or *"why didn't candidate X qualify on cloud experience?"* and get a SQL-backed, tabular answer — no custom code, no MCP server. This is complementary to the RAG matcher, not a replacement: Genie doesn't do the matching, it lets you interrogate the results afterward. It's also a second, genuinely different Databricks-native AI pattern (structured NL-to-SQL vs. unstructured RAG) in the same project — worth calling out explicitly as two distinct agent patterns, one build.

**Setup:**
- Attach a Genie Agent to `gold.jds`, `gold.jd_requirements`, `gold.match_results`, `gold.candidate_scores`.
- Add table/column comments via `COMMENT ON` DDL, checked into the repo as `resources/table_comments.sql` — this is what Genie reads to understand your schema, and it's the part of setup you can keep in code.
- Add a handful of example question → SQL pairs and plain-text instructions in the Genie Agent UI, e.g.: *"when asked why a candidate didn't qualify, filter match_results on meets_requirement = false and surface generated_explanation."*

**Honest exception to "everything is code":** the Genie Agent itself — its curated table list, example SQL, instructions — is configured through the Genie UI, the same way the AI Search endpoint is a Databricks-managed resource rather than something you fully define in a bundle. Keep the underlying comments and example SQL in the repo so the agent is reproducible from documented steps even though the final attach-step is manual — same spirit as the one CSV upload in §5.1.

**Demo path:** use the Genie Agent standalone (its own chat UI in the workspace) for a screen-recording, or wire it into the same Databricks App you're already building, via the AppKit `genie` plugin + `GenieChat` component — one plugin registration server-side, one component on the page.

**Pricing note:** Genie Agent usage is free through January 31, 2027. Don't bake a permanent "free" claim into the README — check current pricing before anyone reads it after that date.

**Resume line:** *"Added a Genie Agent over the matching results, giving recruiters a natural-language query interface backed by governed Unity Catalog metadata — a second, complementary agent pattern alongside the RAG-based matching engine."*

---

## 11. Definition of done

- [ ] `ingest.py` through `build_index.py` run end-to-end on the uploaded CSV with zero manual steps.
- [ ] `score.py` never calls the generation endpoint when the confidence gate fails — assert this invariant in `tests/test_scoring.py`, not just by inspection.
- [ ] `eval.py` produces a logged MLflow run with precision@5, recall@10, and the faithfulness metric, against the full 50-pair label set.
- [ ] At least one JD's requirements were extracted via the LLM path (not just hand-authored), so `extract_requirements.py` is actually exercised.
- [ ] `resources/job.yml` runs as a Databricks Job end-to-end via `databricks bundle run`, not by manually running notebooks.
- [ ] README documents: the architecture diagram, the eval numbers from your best run, and one paragraph on the deterministic/LLM boundary decisions and why they're there — this is what a reviewer reads before opening code.
- [ ] *(Optional, §10)* Genie Agent attached to the `gold` schema, `table_comments.sql` checked into the repo, and at least 3 example questions answered correctly in a recorded demo.
