# Session Handover — 2026-10-27 — TASK-H002 (transfers) built and deployed; waiting for Carel to try it

## Current state

All verified on 2026-10-27 unless marked otherwise.

- **Active branch: `TASK-H002`**, pushed and identical to `origin/TASK-H002` (`ab9b8b5`, plus this handover commit). It hasn't been merged. `main` is unchanged at `95bfd51`. There's no PR, because `gh` isn't installed (see Failed approaches).
- **Task status:**
  - Done: H000, C001, H007, H001.
  - **H002 is IN_PROGRESS** (task file and `TASKS/TASKS.md` row). The code is complete. It is done once Carel has tried it on CT 161.
- **Database schema head: revision `0003`** (`src/zerobase/migrations/versions/0003_transfers.py`), which adds `transactions.transfer_id`.
- **Tests:** 71 pass on SQLite and PostgreSQL 16 at `ab9b8b5`, run on 2026-10-22. `ruff check` and `ruff format --check` are clean.
- **GitHub CI:** status never checked (**unverified**).
- **Test deployment** (details in `deploy/lxc/README.md` and memory `test-deployment.md`):
  - **Where:** LXC **CT 161 `zerobase` on prox01**, 192.168.1.50, http://zerobase.port115.com or http://192.168.1.50. Plain HTTP, LAN only, root SSH key-only from lnx02.
  - **What it runs:** branch **`TASK-H002` (`ab9b8b5`)**. App and database are healthy, and the database is at `0003`.
  - **Data:** demo user `demo@zerobase.local`, whose password only Carel has, plus data Carel added.
    - 41 transactions, none of them transfers yet (Carel hasn't tried the feature).
    - October Ready to Assign was £1,315.00 before H002. It wasn't re-checked after the deploy because that needs a login.
    - Don't reseed or wipe the data without asking.
  - **Backups** in `/opt/zerobase/backups/`. The latest is `zerobase-20261022-115653.sql.gz`, taken just before migration 0003.

## Completed this session

1. **H002 schema decision:** option 1, a self-referencing `transfer_id`. Carel chose it, and it's recorded under Freedom in `TASKS/TASK-H002.md`.
2. **TASK-H002 implemented** (commit `ab9b8b5`). Full description in the task file's "Work Completed" section. In short:
   - **Migration 0003:** nullable self-FK on `transactions.transfer_id`, indexed, `ON DELETE SET NULL`.
   - **Models:** `Transaction.transfer` (read-only relationship) and `takes_category`.
   - **`build_budget`:** the uncategorised count skips legs whose other leg is in a budget account.
   - **`routers/transactions.py`:**
     - a `transfer_account_id` field
     - category rules in `_validate()`: none for budget↔budget or tracking↔tracking; required for budget↔tracking, and stored on the budget leg
     - a new `_save()` shared by add and edit, which creates, updates or deletes the other leg
     - delete removes both legs
   - **UI:** a "Transfer to/from" picker, and the list shows "Transfer to/from X".
   - **Tests:** 15 new (5 budget, 9 web, 1 migration).
3. **README:** the feature list now includes editing and transfers. "Not there yet" no longer lists them.
4. **Deployed `TASK-H002` to CT 161**, with a backup taken first. Verified: healthy, at `0003`, 41 transactions all unlinked.

## Next steps

1. **Wait for Carel to try transfers on CT 161** (ask if they haven't said). Useful checks:
   - October Ready to Assign is still £1,315.00
   - a Current→Savings transfer leaves Ready to Assign unchanged
   - a budget→tracking transfer needs a category
2. **Then close H002**, in one commit on `TASK-H002`:
   - set the task file to DONE, with a Completed date
   - update the `TASKS/TASKS.md` row
   - tick "Transfers between accounts" in the README roadmap (`README.md` ~line 135)

   Then `git pull --ff-only` on `main` and merge, with Carel's OK. Carel either merges on GitHub or Claude runs `git merge --no-ff` and pushes. Redeploy CT 161 on `main` and delete the branch with approval.
3. **Remove the stale warnings in `DEPLOYMENT.md`** (line 5 and ~line 267, "container build has **not** yet been run on a real Docker host"). The build has run on CT 161 since 2026-10-21. This is a small docs commit.
4. **After that, in priority order:**
   - H003, categories. It must protect the inflow category. It must also handle a deleted category nulling a budget↔tracking transfer leg, which is then flagged as uncategorised (that's acceptable).
   - H004, accounts. Its task file says deleting an account with transactions is refused, so transfers into a deleted account can't arise.
   - H005, credit cards. Card payments reuse the H002 transfers.
   - H006, CSV import.

## Open decisions

- **Inline category picker on transfer legs:** the budget leg of a budget↔tracking transfer still offers "Uncategorised" in the list's inline picker. The form refuses a blank category there, but the inline picker allows it, and the leg is then just flagged as uncategorised. Not raised with Carel as a question; fix it only if they want it.
- **HTTPS.** The deployment is plain HTTP on the LAN. Options are Home_Web_Games' proxy01 or the bundled Caddy. Not started; do it before real use.
- **UI polish is deferred.** Carel wants the back end first, and the plain UI is fine for testing (memory `backend-first-priority.md`).
- **H003:** whether to accept that merging categories can change past overspending (Known Issues in `TASKS/TASK-H003.md`).

## Failed approaches

- **Creating PRs from here:** `gh` isn't installed and there's no token. The workflow that works: Carel merges on GitHub, or Claude merges locally with `git merge --no-ff` and pushes, after asking.
- **Migration tests with explicit primary keys on PostgreSQL:** inserting a `categories` row with a fixed `id` doesn't advance the sequence, so a later insert collides. Let the database assign IDs when anything inserts afterwards. The 0003 test uses fixed IDs safely because nothing inserts after them.
- **Pushing to `main` without fetching:** rejected once because Carel had edited on GitHub. Always `git pull --ff-only` first.
- **Test bug to avoid:** reading `.id` on an ORM object whose row a request deleted raises `ObjectDeletedError` after `expire_all()`. Capture IDs before the request.

## Landmines

- **Task bookkeeping:** the task file is the source of truth. Any status change updates the task file **and** the `TASKS/TASKS.md` row in the same commit. One branch per task, named `TASK-XNNN`.
- **Schema changes need a migration.** The app migrates on start. Add a new revision in `src/zerobase/migrations/versions/`; `test_upgrade_reaches_head_and_matches_the_models` catches drift.
- **Transfers (H002):**
  - Both legs point at each other through `transfer_id`. `Transaction.transfer` is **viewonly**, so set the IDs directly. `_save()` flushes so both legs have IDs, then links them.
  - **SQLite doesn't enforce FKs here** (no `PRAGMA foreign_keys`), so the app, not the database, deletes the other leg. Any new code path that deletes transactions (H004 accounts, H006 import) must delete or unlink the other leg itself.
  - The category lives on the budget leg only. The edit form shows `transaction.category_id or other.category_id`.
  - `takes_category` needs `transfer` and `transfer.account` loaded. The list joinedloads them; elsewhere they lazy-load.
- **Inflow category:**
  - Stored as `categories.kind = 'inflow'`, `group_id` NULL, one per user.
  - It's left out of pickers by the inner join on `CategoryGroup`.
  - Deleting it would uncategorise all income (`ON DELETE SET NULL`), so H003 must refuse that.
  - `/budget/assign` returns 404 for it.
- **`inflow_category()`** only `flush()`es, so callers must commit. `_pickers()` commits on purpose, even on GET.
- **Redeploying CT 161:** `ssh root@192.168.1.50 'cd /opt/zerobase && git fetch -q origin && git checkout -q <branch> && git reset -q --hard origin/<branch> && docker compose up -d --build'`. Run `./scripts/backup.sh` first if the deploy includes a migration. Never touch other guests on the cluster (VMIDs 100–160).
- **PostgreSQL tests locally:** `podman run -d --rm --name zb-pg -e POSTGRES_PASSWORD=t -e POSTGRES_DB=zb -p 55432:5432 docker.io/library/postgres:16`, then `ZEROBASE_TEST_DATABASE_URL=postgresql+psycopg://postgres:t@127.0.0.1:55432/zb .venv/bin/python -m pytest -q`.
- **Demo seed script:** don't rerun `deploy/lxc/seed_demo.py` on CT 161.
- **Known gap, not fixed:** `HEAD /` returns 405.
- **Commit attribution:** commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
