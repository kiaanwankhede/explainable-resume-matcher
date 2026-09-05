# Progress log

Running record of what's actually been done, in the order it happened — not the
plan (`PLAN.md`), the log. Step numbers refer to `PLAN.md`. Add a new entry each
time a step is completed, skipped, or a decision/deviation is made. Never edit
past entries except to fix a factual error — append instead.

Workspace: `https://dbc-a77cb721-aa25.cloud.databricks.com`
Account: `hiteshbwankhede@gmail.com`

---

### Step 1 — Authenticate the Databricks CLI ✅
- Installed Databricks CLI v1.15.0 on Windows via `winget install Databricks.DatabricksCLI`
  (the earlier `curl | sh` instructions were Mac/Linux-only and don't apply on
  Windows `cmd.exe`/PowerShell).
- Credentials saved to `%USERPROFILE%\.databrickscfg` (`[DEFAULT]` profile, host +
  PAT) rather than session env vars, so auth persists across terminal sessions.
- Verified with `databricks current-user me` — returned a valid profile:
  - Email: `hiteshbwankhede@gmail.com`, `active: true`
  - Group membership includes **admins** — good sign for catalog-creation
    permission needed in Phase 1.
  - Entitlements: `allow-cluster-create`, `allow-instance-pool-create`.
- **Open question flagged, not yet resolved:** `SPEC.md` §7 assumes a *Free
  Edition* workspace (serverless-only, no cluster creation). This workspace's
  `allow-cluster-create` entitlement suggests it may **not** be Free Edition
  (or is a trial/other tier that also allows clusters). This matters later for:
  - Phase 8, step 80 (`environment_key`/serverless question in `job.yml`) —
    may not need the serverless-specific config at all if clusters are available.
  - Whether the Free Edition constraints in `SPEC.md` §7 (one AI Search
    endpoint, no GPU serving, etc.) still apply here.
  - **Action:** confirm workspace edition/tier before Phase 8; don't assume
    either way.
- Security note: the PAT was pasted directly into chat twice (web session, then
  screenshot). Recommended the user rotate it after setup is confirmed stable;
  not yet confirmed done.

### Step 2 — Fill workspace URL into `databricks.yml` ✅
- Set `targets.dev.workspace.host` to `https://dbc-a77cb721-aa25.cloud.databricks.com`
  in `databricks/databricks.yml`.
- Committed: `0a205e1` — "Fill in real workspace host in databricks.yml".

### Steps 3–6 — not started
- Step 3 (check Serving page for real endpoint names) — pending, needs the user
  to look at the workspace's Serving UI.
- Step 4 (update `config.yml` with real endpoint names) — blocked on step 3.
- Step 5 (confirm catalog-create permission) — likely fine given `admins` group
  membership (see step 1 note), but not explicitly tested yet
  (`databricks catalogs create --name resume_matcher_test`).
- Step 6 (download Kaggle CSV locally) — pending, manual step for the user.
