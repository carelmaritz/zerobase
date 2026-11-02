# Session Handover — 2026-11-02 — TASK-H003 (categories) done and merged; CT 161 on main

## Current state

All verified on 2026-11-02.

- **`main` at `19ed610`** ("Merge TASK-H003"), pushed. 92 tests pass on SQLite and PostgreSQL 16.
- **Branches:** `main`, plus `TASK-H003` (fully merged and pushed; delete only if Carel asks).
- **Task status:**
  - Done: H000, C001, H007, H001, H002, **H003**.
  - **Next: H004** (accounts).
- **Database schema head: revision `0004`** (`0004_manage_categories.py`): adds `categories.hidden` and changes `transactions.category_id` to `ON DELETE RESTRICT`.
- **GitHub CI:** status never checked (**unverified**).
- **Test deployment, CT 161** (details in `deploy/lxc/README.md` and memory `test-deployment.md`):
  - Runs **`main` (`19ed610`)**. App and database are healthy, and the database is at `0004`. The app container wasn't recreated by the final deploy because the image didn't change; it runs the same code from the H003 deploy.
  - **Login:** `demo@zerobase.local` (the password was given to Carel in chat; it isn't stored anywhere).
  - **Data after Carel's H003 testing** (all deliberate):
    - Rent / Mortgage was merged into Holidays, and Insurance renamed "Rainy Day".
    - Groceries is hidden. The Needs group was deleted, and its categories moved to Bills.
    - November Ready to Assign **£815.00**, total Available £4,538.00. October Ready to Assign £1,315.00.
    - Balances unchanged: Current £3,579.01, Savings £1,800.00, Mortgage −£181,450.00.
    - Transfer 44/45 (Current → Mortgage £1,000) is now in Holidays.
    - Two uncategorised transactions: Amazon −£23.99 and a £50 refund.
    - Don't wipe, reseed or restore without asking.
  - **Firewall:** the app can be reached from 192.168.1.0/24 and 192.168.2.0/24 (the WiFiman VPN). SSH is 192.168.1.0/24 only.
  - **Backups** in `/opt/zerobase/backups/`. The latest is `zerobase-20261102-092603.sql.gz`, taken before the H003 deploy and before Carel's testing (it still has Rent / Mortgage).

## Completed this session

1. **TASK-H003 (categories and groups), DONE**, merged as `19ed610`. Full description in the task file's "Work Completed" section. In short:
   - A `/categories` page to rename, reorder, move between groups, hide or unhide, and delete.
   - Delete merges the category into another one (`budget.merge_category`), adding assignments in the same month together.
   - The confirm page previews Ready to Assign for the current month (`build_budget(..., merge=...)`, worked out in memory).
   - Hidden categories still count. They're listed under "Hidden categories" on the budget page and left out of the pickers unless already selected.
   - The inflow category gets a 404 on all of these routes.
2. **Carel's decisions (2026-11-02):** the RESTRICT foreign key, and allowing merges that cancel past overspending, shown in the preview.
3. **Carel tested on CT 161, with the database checked after each step:** hide, merge (the preview showed £315.00 → £815.00, which was correct), rename, reorder, moving between groups, deleting a group. Renaming and reordering a **group** weren't tried there; the automated tests cover them.
4. README feature list and roadmap updated.

## Next steps

1. **TASK-H004 (accounts). Planned and approved by Carel on 2026-11-02; not started, and there's no branch yet.**
   - The plan and decisions are in `TASKS/TASK-H004.md` under "Agreed plan (2026-11-02)". Create branch `TASK-H004` from `main`, then start with migration `0005` (step 1).
   - Both "ask first" items are settled:
     - The foreign key on `transactions.account_id` changes from `CASCADE` to `RESTRICT`.
     - Existing transactions in a closed account stay editable. New transactions or transfers into a closed account are refused.
   - An account can be deleted only when it has no transactions. That means the transfer-leg problem can't come up: an account with transfers has transactions.
   - Done when the success criteria in the task file pass on SQLite and PostgreSQL, the change is deployed to CT 161 (back up first: `0005` is a migration), and Carel has tested it with the database checked after each step.
2. **After that:**
   - H005, credit cards. Card payments reuse transfers. It needs system categories that can't be deleted; the H003 routes only manage `kind == 'standard'`.
   - H006, CSV import.

## Open decisions

- **Inline category picker on transfer legs:** the budget leg of a budget↔tracking transfer still offers "Uncategorised" in the list's inline picker. If chosen, the leg is just flagged as uncategorised. It's recorded in the task file; fix it only if Carel wants it.
- **HTTPS.** The deployment is plain HTTP. Options are Home_Web_Games' proxy01 or the bundled Caddy. Not started; do it before real use, especially now that it's reachable over the VPN.
- **UI polish is deferred.** Carel wants the back end first (memory `backend-first-priority.md`).

## Failed approaches

- **Claude changing CT 161's firewall:** blocked by the auto-mode classifier ("Security Weaken"), even with Carel's OK in chat. Give Carel the command to run instead. Pasted one-liners can lose characters (the space in `ip saddr` vanished once), so keep `sed` patterns short.
- **Claude deleting merged branches:** blocked by the classifier ("Git Destructive") when bundled into a wrap-up. It worked when Carel asked for it directly and the merge was checked first.
- **Creating PRs from here:** `gh` isn't installed and there's no token. Merge locally with `git merge --no-ff` and push after asking, or Carel merges on GitHub.
- **Migration tests with explicit primary keys on PostgreSQL:** fixed IDs don't advance the sequence, so a later insert collides. Let the database assign IDs when anything inserts afterwards.
- **Worry that RESTRICT breaks deleting a user (checked 2026-11-02, it doesn't):** on PostgreSQL 16, deleting a user still cascades through categories, accounts and transactions with RESTRICT foreign keys between them, and RESTRICT still blocks deleting a category directly. No need for NO ACTION instead, and no route deletes users anyway.
- **Pushing to `main` without fetching:** rejected once. Always `git pull --ff-only` first.
- **Tests:** reading `.id` on an ORM object whose row a request deleted raises `ObjectDeletedError` after `expire_all()`. Capture IDs before the request.

## Landmines

- **Task bookkeeping:** the task file is the source of truth. Any status change updates the task file **and** the `TASKS/TASKS.md` row in the same commit. One branch per task, named `TASK-XNNN`.
- **Schema changes need a migration.** Add a new revision in `src/zerobase/migrations/versions/`; `test_upgrade_reaches_head_and_matches_the_models` catches drift.
- **Transfers:**
  - Both legs point at each other through `transfer_id`. `Transaction.transfer` is **viewonly**, so set the IDs directly (`_save()` flushes, then links them).
  - **SQLite doesn't enforce FKs here**, so the app deletes the other leg. Any new delete path (e.g. H006 import) must delete or unlink the other leg itself. H004 sidesteps this: it only deletes accounts with no transactions.
  - The category lives on the budget leg only.
  - `takes_category` needs `transfer.account` loaded.
- **Categories (H003):**
  - Deleting a category goes through `merge_category()`, or `db.delete` only when `category_in_use()` is false. PostgreSQL refuses anything else (RESTRICT); SQLite doesn't enforce foreign keys.
  - `build_budget()` returns hidden categories in `view.hidden`, not in the groups. Any new total must include both.
  - On the original demo data, November's Ready to Assign was £1,000 below October's because of an October overspend. That's the overspending rule, not a bug.
- **Read-only budget checks on CT 161:** run `build_budget` in `docker compose exec -T app python -` with `make_session_factory(make_engine(get_settings().database_url))`, then `db.rollback()`.
- **Testing with Carel on CT 161:** check the database after each step. The UI can look right while saving the wrong thing; the plain-transaction save in item 2 of "Completed this session" was only caught that way. Read-only query: `docker compose exec -T db sh -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -c '...'"` in `/opt/zerobase`. App request logs: `docker compose logs app`.
- **Inflow category:**
  - Stored as `categories.kind = 'inflow'`, `group_id` NULL, one per user.
  - Deleting it would uncategorise all income, so the H003 routes refuse it (404).
  - `/budget/assign` returns 404 for it.
- **`inflow_category()`** only `flush()`es, so callers must commit. `_pickers()` commits on purpose, even on GET.
- **Redeploying CT 161:** `ssh root@192.168.1.50 'cd /opt/zerobase && git fetch -q origin && git checkout -q <branch> && git reset -q --hard origin/<branch> && docker compose up -d --build'`. Run `./scripts/backup.sh` first if the deploy includes a migration or data changes. Never touch other guests (VMIDs 100–160).
- **PostgreSQL tests locally:** `podman run -d --rm --name zb-pg -e POSTGRES_PASSWORD=t -e POSTGRES_DB=zb -p 55432:5432 docker.io/library/postgres:16`, then `ZEROBASE_TEST_DATABASE_URL=postgresql+psycopg://postgres:t@127.0.0.1:55432/zb .venv/bin/python -m pytest -q`.
- **Demo seed script:** don't rerun `deploy/lxc/seed_demo.py` on CT 161.
- **Known gap, not fixed:** `HEAD /` returns 405.
- **Commit attribution:** commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
