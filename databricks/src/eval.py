"""
eval.py — MLflow-tracked evaluation against hand-labeled ground truth.

Per SPEC.md §4 and §9. Reads gold.candidate_scores, eval.eval_labels,
eval.eval_evidence_labels. Logs a run to the /resume-matcher/eval experiment.

Params logged: every value in config.yml, flattened.
Metrics logged: precision_at_5, recall_at_10, faithfulness_mean_similarity,
pct_requirements_gated_no_evidence.
Artifact logged: the full gold.match_results for the eval JDs, as CSV.

CLI: python eval.py --config config.yml
"""


def compute_precision_recall(config_path: str) -> dict:
    """
    For each jd_id in eval.eval_labels: take the system's top-5/top-10 ranked
    resumes from gold.candidate_scores, compare against human_label == "fit"
    as ground truth. Return {"precision_at_5": ..., "recall_at_10": ...}.
    """
    raise NotImplementedError("TODO: implement per SPEC.md §4")


def compute_faithfulness(config_path: str) -> float:
    """
    For each row in eval.eval_evidence_labels: fetch the corresponding
    gold.match_results.generated_explanation, compute embedding similarity
    against expected_evidence_text. Return the mean. This is a signal for
    manual review, not a fully automated pass/fail — say so in the README
    when you report it.
    """
    raise NotImplementedError("TODO: implement per SPEC.md §4")


def run_eval(config_path: str) -> None:
    """
    Orchestrate the above, log everything to MLflow per SPEC.md §9.
    """
    raise NotImplementedError("TODO: implement per SPEC.md §9")


if __name__ == "__main__":
    raise NotImplementedError("TODO: argparse --config, call run_eval()")
