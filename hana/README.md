# hana/ — future work, not started

Do not begin this until the Databricks build in `../databricks/` is complete and
evaluated (per `../databricks/SPEC.md` Definition of Done). Sequential, not parallel —
one complete, deployed, evaluated implementation beats two half-finished ports.

When it's time to start: port the same concept (ingestion → chunking/embedding →
retrieval → generation → deterministic scoring → eval) onto SAP BTP/HANA, using
HANA Cloud's Vector Engine in place of AI Search, and SAP AI Core / Generative AI Hub
in place of Databricks Model Serving. Ask for a spec in the same depth as
`../databricks/SPEC.md` when ready.
