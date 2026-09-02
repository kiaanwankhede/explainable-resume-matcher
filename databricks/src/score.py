"""
score.py — the core RAG loop and deterministic aggregation.

Per SPEC.md §4 and the non-negotiables in §0. This module is DELIBERATELY split
into two functions with different rules — do not merge them, do not let
aggregate_scores call a model, do not let score_requirement skip the gate.

Writes to gold.match_results and gold.candidate_scores.

CLI: python score.py --config config.yml
"""


def score_requirement(jd_id: str, resume_id: str, requirement_id: str, config) -> dict:
    """
    The RAG loop for one (jd, resume, requirement) triple. This is the ONLY
    function in the codebase permitted to call the generation model endpoint.

    1. Retrieve top-k chunks from the AI Search index for this requirement,
       filtered to this resume_id (config.retrieval.top_k).
    2. CONFIDENCE GATE: if the best hit is None or its score is below
       config.retrieval.confidence_threshold — return a row with
       retrieved_chunk_id=None, generated_explanation=None,
       meets_requirement=False. Do NOT call the generation endpoint. This
       invariant is asserted in tests/test_scoring.py — do not weaken it to
       make a test pass.
    3. Otherwise, call config.models.generation_endpoint with
       (requirement_text, retrieved_chunk_text), prompted to produce ONE
       grounded sentence citing the chunk. The model explains retrieved
       evidence — it does not judge fit, and it is never invoked without a
       retrieved chunk to ground it.
    4. Return a dict matching the gold.match_results schema (SPEC.md §3).
    """
    raise NotImplementedError("TODO: implement per SPEC.md §4 and §0")


def aggregate_scores(match_results_for_candidate: list[dict], config) -> float:
    """
    PURE function. No model calls, no network calls, no exceptions to this rule.

    total_score = sum(weight * retrieval_score) over rows where
    meets_requirement is True. weight comes from config.scoring
    (weight_must_have / weight_nice_to_have) keyed off the requirement's
    requirement_category.

    See tests/test_scoring.py::test_aggregate_scores_is_pure — this function
    must produce correct output even with every model client set to None.
    """
    raise NotImplementedError("TODO: implement per SPEC.md §4")


if __name__ == "__main__":
    raise NotImplementedError(
        "TODO: argparse --config; orchestrate score_requirement() over every "
        "(jd, resume, requirement) combination, write gold.match_results, then "
        "call aggregate_scores() per (jd, resume) and write gold.candidate_scores"
    )
