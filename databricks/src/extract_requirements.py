"""
extract_requirements.py — gold.jds, gold.jd_requirements

Per SPEC.md §4. Reads data/jds.json. For each JD, one LLM call
(config.yml: models.extraction_endpoint) with a structured-output schema forcing
list[{requirement_text, requirement_category, weight}].

This is extraction, explicitly NOT part of the RAG loop in score.py — keep it in
this separate module so the deterministic/LLM boundary (SPEC.md §0) stays visible
in the repo structure, not just in prose.

Note: data/jds.json ships with pre-structured `requirements` arrays for bootstrap
JDs. Exercise the actual LLM extraction path on at least one JD (re-derive from
raw_text) rather than only ever parsing the pre-structured array — see SPEC.md
§5.2 and the Definition of Done.

CLI: python extract_requirements.py --config config.yml
"""


def extract_requirements(config_path: str) -> None:
    """
    Read data/jds.json, extract/validate requirements, write to gold.jds and
    gold.jd_requirements. See SPEC.md §3 for target schemas.
    """
    raise NotImplementedError("TODO: implement per SPEC.md §4")


if __name__ == "__main__":
    raise NotImplementedError("TODO: argparse --config, call extract_requirements()")
