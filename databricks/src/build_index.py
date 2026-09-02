"""
build_index.py — AI Search index over silver.resume_chunks

Per SPEC.md §4 and §7 (Free Edition: one AI Search endpoint, one search unit —
design for exactly one index, not multiple).

Creates the index if it doesn't exist (Delta Sync mode, off silver.resume_chunks,
embedding source column = embedding), triggers a sync on each run.

CLI: python build_index.py --config config.yml
"""


def build_index(config_path: str) -> None:
    """
    Create/sync resume_matcher.silver.resume_chunks_index off silver.resume_chunks.
    """
    raise NotImplementedError("TODO: implement per SPEC.md §4")


if __name__ == "__main__":
    raise NotImplementedError("TODO: argparse --config, call build_index()")
