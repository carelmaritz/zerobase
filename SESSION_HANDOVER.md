# Session Handover — 2026-10-22 — Task system, C001 migrations, H007 explicit income, H001 edit transactions, first test deployment

## Current state

All verified at the end of this session unless marked otherwise.

- **Checked out: `TASK-H001`**, pushed to `origin/TASK-H001`. Working tree clean apart from this file (committed on the same branch).
  - TASK-H001 (edit transactions) is **REVIEW**. Carel tried it on the test deployment and said "Perfect", but has **not yet asked for it to be merged**. Ask before merging.
  - Commits ahead of `main`: `e87d15f` (mark in progress), `6863237` (the feature), `ecb9e88` (related task files and README roadmap), then this handover.
- **`main` at `6c8d609`** (test-deployment scripts), identical to `origin/main`. It includes TASK-C001 (merged as `68ca576`), TASK-H007 (merged as `41f808e`) and `deploy/lxc/`. `TASK-H001` branched from `41f808e`, so it doesn't contain `deploy/lxc/` until it's merged.
- **Database schema head: revision `0002`** (`src/zerobase/migrations/versions/0002_inflow_category.py`). TASK-H001 has no schema change.
- **Tests:** 56 pass on SQLite and on PostgreSQL 16 at `ecb9e88`'s code (`6863237`; the later commit is docs only). `ruff check` and `ruff format --check` are clean.
- **GitHub CI:** status never checked. `gh` isn't installed, so this is **unverified**.
- **Merged branches still on GitHub:** `add-task-tracking`, `TASK-C001` and `TASK-H007`. Carel can delete them.
- **Test deployment** (details in memory `test-deployment.md`):
  - **Where:** LXC **CT 161 `zerobase` on prox01**, 192.168.1.50, http://zerobase.port115.com or http://192.168.1.50. Plain HTTP, LAN only (nftables inside the CT), root SSH key-only from lnx02.
  - **What it runs:** branch **`TASK-H001` at `6863237`**, not `main`. It's healthy and the DB is at `0002`.
  - **Data:** demo user `demo@zerobase.local`. The password isn't recorded in the repo; Carel has it. Carel has since added data of their own: October Ready to Assign was **£1,315.00** at last check, and there's an uncategorised £50 "refund" dated 2026-10-21. Don't reseed or wipe it without asking.
  - **Backups:** in `/opt/zerobase/backups/` on the CT: `zerobase-20261021-123818.sql.gz` (after seeding) and `zerobase-20261021-172711.sql.gz` (just before migration 0002).

## Completed this session

1. **Task system.** `TASKS/` folder with the index at **`TASKS/TASKS.md`** (not the repo root) and one file per task. Created H000 (done) through L002, plus H007.
2. **TASK-C001 (database migrations), DONE.**
   - Alembic is set up with a naming convention in `db.py`, `migrate.py`, `src/zerobase/migrations/` and baseline `0001`.
   - The app upgrades the database to head on startup under a PostgreSQL advisory lock.
   - It refuses a database that has tables but no `alembic_version`.
   - Verified on SQLite, PostgreSQL and the real deployment.
3. **First test deployment** on Proxmox. Verified:
   - container healthy with no restarts
   - fresh-database migration
   - data survives a restart and a CT reboot
   - `scripts/backup.sh` works
   - Ready to Assign matched the hand calculation (£315.00 for October before Carel's additions)
4. **TASK-H007 ("Inflow: Ready to Assign" category), DONE.**
   - Decision: option B, YNAB style (rationale in `TASKS/TASK-H007.md`).
   - Migration 0002 converted the live demo data with Ready to Assign unchanged (verified: September £3,295.00, October £315.00).
5. **TASK-H001 (edit transactions), REVIEW.**
   - Separate edit page: `GET`/`POST /transactions/{id}/edit`.
   - Add and edit share `_validate()` and the `transaction_fields` macro.
   - `return_to` keeps the account filter through the edit.
   - Smoke-tested on the deployment (re-saving the same values left everything unchanged).
6. **Related task files updated for H001:** L001, H002, M006 and the README roadmap.
7. **Test-deployment scripts saved in the repo** (on `main`): `deploy/lxc/provision-zerobase.sh` (builds CT 161; default branch `main`), `deploy/lxc/seed_demo.py` (updated for the inflow category) and `deploy/lxc/README.md`. The seed script was verified against a local instance: October Ready to Assign came out at £315.00, as on the original demo.

## Next steps

1. **Ask Carel whether to merge TASK-H001.** If yes, in one commit on the branch set Status DONE and Completed in `TASKS/TASK-H001.md` and move the row to the Completed archive in `TASKS/TASKS.md`. Then `git checkout main && git merge --no-ff TASK-H001`, run the tests, push, and switch CT 161 to `main` (command under Landmines). Done when `main` contains H001 and the CT reports `main`'s head.
2. **TASK-H002 (transfers).** It's unblocked now that C001 and H007 are done. The task file says **ask first about the schema shape** (see Open decisions). Then follow its plan: migration, `build_budget` uncategorised exclusion for budget-to-budget legs, create/edit/delete keeping both legs in sync (extend `edit_transaction`/`delete_transaction`). Done when its success criteria pass on SQLite and PostgreSQL and on the CT.
3. **Remove the stale warnings in `DEPLOYMENT.md`** (line 5, "container build has **not** yet been run on a real Docker host", and line ~267). They're no longer true: the build ran on CT 161 on 2026-10-21. Small docs commit.
4. **After that, in priority order:** H003 (categories; must protect the inflow category), H004 (accounts), H005 (credit cards, needs H002), H006 (CSV import).

## Open decisions

- **H002 schema shape** (the task file says ask first). Options:
  - a self-referencing `transfer_id` FK on `transactions`
  - a shared transfer group key
  - a separate `transfers` table

  No leaning recorded yet. Credit card payments (H005) must be able to reuse it.
- **HTTPS.** The deployment is plain HTTP on the LAN. Options: Home_Web_Games' proxy01, or the bundled Caddy. Not started; do it before real use.
- **UI polish is deferred.** Carel: back end first, and the plain UI is fine for testing (memory `backend-first-priority.md`). Don't propose visual work until Carel raises it.
- **H003:** whether to accept that merging categories can change past overspending (Known Issues in `TASKS/TASK-H003.md`).

## Failed approaches

- **Creating PRs from here:** `gh` isn't installed and there's no token. The workflow that works: Carel merges on GitHub, or Claude merges locally with `git merge --no-ff` and pushes, after asking.
- **Migration tests with explicit primary keys on PostgreSQL:** inserting a `categories` row with a fixed `id` doesn't advance the sequence, so the migration's own insert collided (`UniqueViolation pk_categories`). Let the database assign IDs in migration tests (see `tests/test_migrations.py::test_0002_...`).
- **Pushing to `main` without fetching:** rejected once because Carel had merged PR #1 and edited `DEPLOYMENT.md` on GitHub. Always `git pull --ff-only` before merging into `main`.

## Landmines

- **Task bookkeeping:** the task file is the source of truth. Any status change updates the task file **and** the `TASKS/TASKS.md` row in the same commit. One branch per task, named `TASK-XNNN`.
- **Schema changes need a migration:** the app migrates on start. Every model change needs a new revision in `src/zerobase/migrations/versions/` (`alembic revision --autogenerate -m ...` with the root `alembic.ini`). `test_upgrade_reaches_head_and_matches_the_models` fails if the models and migrations drift.
- **Inflow category:**
  - It's `categories.kind = 'inflow'` with `group_id` NULL, one per user, named "Ready to Assign" and shown as "Inflow: Ready to Assign".
  - It's left out of pickers by the inner join on `CategoryGroup`, so templates get it separately as `inflow`.
  - `transactions.category_id` is `ON DELETE SET NULL`, so deleting it would uncategorise all income. H003 must refuse that.
  - `/budget/assign` returns 404 for it.
- **`inflow_category()`** (`budget.py`) is get-or-create and only `flush()`es, so callers must commit. `_pickers()` in `routers/transactions.py` commits on purpose, even on GET.
- **Income rule:** income is the inflow category, either sign. A blank category means uncategorised (both directions) and counts nowhere. Budget-to-budget transfer legs will have no category, so H002 must exclude them from the uncategorised warning.
- **Redeploying CT 161** (also in `deploy/lxc/README.md` on `main`): `ssh root@192.168.1.50 'cd /opt/zerobase && git fetch -q origin && git checkout -q <branch> && git reset -q --hard origin/<branch> && docker compose up -d --build'`. Run `./scripts/backup.sh` first if the deploy includes a migration. Compose leaves the app container alone when the image hasn't changed; that's normal. Never touch other guests on the cluster (VMIDs 100–160).
- **PostgreSQL tests locally:** `podman run -d --rm --name zb-pg -e POSTGRES_PASSWORD=t -e POSTGRES_DB=zb -p 55432:5432 docker.io/library/postgres:16`, then `ZEROBASE_TEST_DATABASE_URL=postgresql+psycopg://postgres:t@127.0.0.1:55432/zb .venv/bin/python -m pytest -q`.
- **Demo seed script:** `deploy/lxc/seed_demo.py` needs registration open and an empty target. Don't rerun it on CT 161, where the demo user already exists and Carel has added data.
- **Known gap, not fixed:** `HEAD /` returns 405.
- **Commit attribution:** commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
