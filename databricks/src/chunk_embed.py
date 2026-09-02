"""
chunk_embed.py — silver.resume_chunks

Per SPEC.md §4. Chunks each bronze.resumes_raw.raw_text (sliding window, params in
config.yml: chunking.window_size / chunking.overlap), batch-calls the embedding
endpoint (config.yml: models.embedding_endpoint), writes chunks + embeddings.

Use a pandas UDF over a Spark DataFrame for parallelism — not a Python for-loop.
This is the whole point of running it on Databricks instead of a laptop script.

Idempotent — MERGE INTO on chunk_id.

CLI: python chunk_embed.py --config config.yml
"""


def chunk_embed(config_path: str) -> None:
    """
    Read bronze.resumes_raw, chunk + embed, MERGE INTO silver.resume_chunks.
    See SPEC.md §3 for the target schema.
    """
    raise NotImplementedError("TODO: implement per SPEC.md §4")


if __name__ == "__main__":
    raise NotImplementedError("TODO: argparse --config, call chunk_embed()")
