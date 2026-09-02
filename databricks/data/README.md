# data/

- **jds.json** — one example entry (Java Developer) is filled in as a template. Add
  4–5 more role entries in the same shape (SPEC.md §5.2) — this is a human task, write
  the atomic requirements yourself, don't let a model invent the bootstrap set. Pick
  `target_category` values that exist in the Kaggle dataset's 25 categories, since
  eval labeling in eval_labels.csv depends on that match.
- **eval_labels.csv** — header only right now. Fill in ~50 rows (SPEC.md §5.3) after
  `ingest.py` has run at least once, so you have real `resume_id` values to reference
  (resume_id is a deterministic uuid5 of the raw resume text, computed in ingest.py —
  you can't know it in advance).
- **The Kaggle CSV itself does NOT go in this folder.** It's uploaded once, manually,
  to a Unity Catalog Volume — see SPEC.md §5.1 and §7. This folder only holds
  hand-authored data that's small enough to check into git.
