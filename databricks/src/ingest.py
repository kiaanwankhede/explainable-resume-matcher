"""
ingest.py — bronze.resumes_raw

Per SPEC.md §4. Reads the manually-uploaded Kaggle CSV from a Unity Catalog Volume
(path in config.yml: data.raw_csv_path), computes a deterministic resume_id
(uuid5 of raw_text), and MERGEs into bronze.resumes_raw.

Must be idempotent — safe to re-run without creating duplicate rows.

CLI: python ingest.py --config config.yml
"""


def ingest(config_path: str) -> None:
    """
    Read the raw CSV (columns: Category, Resume), compute resume_id, MERGE INTO
    bronze.resumes_raw. See SPEC.md §3 for the target schema.
    """
    raise NotImplementedError("TODO: implement per SPEC.md §4")


if __name__ == "__main__":
    raise NotImplementedError("TODO: argparse --config, call ingest()")
