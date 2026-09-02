# explainable-resume-matcher

An explainable, evidence-citing resume-to-JD matching RAG pipeline, built twice on purpose:
once on Databricks (current phase), later ported to SAP BTP/HANA — same concept, two enterprise
data platforms, to demonstrate platform versatility rather than a single-stack toy.

## Structure

- `databricks/` — current build. Start here. `databricks/SPEC.md` is the authoritative spec.
- `hana/` — future port. Do not start until the Databricks build is complete and evaluated
  (see `databricks/SPEC.md` §11, Definition of Done).

## For Claude Code

Read `CLAUDE.md` first.
