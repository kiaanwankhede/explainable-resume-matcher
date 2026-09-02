"""
Unit tests for src/score.py's non-negotiables (SPEC.md §0, Definition of Done item 2).

These two tests are the ones that must exist and pass before score.py is considered
done — not optional coverage, the actual proof that the deterministic/LLM boundary
is real in code, not just in the docstrings.
"""


def test_confidence_gate_blocks_generation():
    """
    Given a retrieval result below config.retrieval.confidence_threshold,
    score_requirement() must NOT call the generation endpoint, and must return
    retrieved_chunk_id=None, generated_explanation=None, meets_requirement=False.

    Implementation approach: mock/stub the model-serving client passed into
    score_requirement(), assert its generation-call method has zero invocations
    for a synthetic low-score retrieval result.
    """
    raise NotImplementedError("TODO: implement — see SPEC.md Definition of Done, item 2")


def test_aggregate_scores_is_pure():
    """
    aggregate_scores() must produce correct output with no model or network
    clients available at all — pass None or an unmocked/unreachable client and
    confirm it still works, proving it never actually calls one.
    """
    raise NotImplementedError("TODO: implement — see SPEC.md §4, src/score.py")
