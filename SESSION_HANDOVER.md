# Session Handover — 2026-11-02 — TASK-H004 (accounts) done and merged; CT 161 on main

## Current state

All verified on 2026-11-02.

- **`main` at `0dd177b`** ("Merge TASK-H004"). It and branch `TASK-H004` are both pushed. 106 tests pass on SQLite and PostgreSQL 16.
- **Branches:** `main`, plus `TASK-H003` and `TASK-H004` (both fully merged and pushed; delete only if Carel asks).
- **Task status:**
  - Done: H000, C001, H007, H001, H002, H003, **H004**.
  - **Next: H005** (credit cards). Not planned yet.
- **Database schema head: revision `0005`** (`0005_manage_accounts.py`): adds `accounts.closed` and changes `transactions.account_id` to `ON DELETE RESTRICT`.
- **GitHub CI:** status never checked (**unverified**).
- **Test deployment, CT 161** (details in `deploy/lxc/README.md` and memory `test-deployment.md`):
  - Runs **`main` (`0dd177b`)**. App and database are healthy, and the database is at `0005` (checked: the FK's `confdeltype` is `r`).
  - **Login:** `demo@zerobase.local` (the password was given to Carel in chat; it isn't stored anywhere).
  - **Data after Carel's H003 and H004 testing** (all deliberate):
    - Categories: Rent / Mortgage was merged into Holidays, Insurance renamed "Rainy Day", Groceries hidden, the Needs group deleted (its categories moved to Bills).
    - Accounts: Savings changed to type Other, and **Savings is closed**. A £1,800 transfer Savings → Current (transactions 46/47) emptied it first. Savings' starting balance (transaction 3) has the payee "Starting odd" from an edit test.
    - Balances: Current £5,379.01, Savings £0.00 (closed), Mortgage −£181,450.00.
    - November Ready to Assign **£815.00**.
    - Don't wipe, reseed or restore without asking.
  - **Firewall:** the app can be reached from 192.168.1.0/24 and 192.168.2.0/24 (the WiFiman VPN). SSH is 192.168.1.0/24 only.
  - **Backups** in `/opt/zerobase/backups/`. The latest is `zerobase-20261102-095819.sql.gz`, taken just before the H004 deploy (it has schema `0004`, and Savings is open at £1,800).

## Completed this session

1. **TASK-H004 (accounts), DONE**, merged as `0dd177b`. Full description in the task file's "Work Completed" section. In short:
   - `/accounts/{id}/edit` to change the name and type. Budget/tracking stays fixed.
   - `/accounts/{id}/close`: close only at a zero balance, reopen any time.
   - `/accounts/{id}/delete`: only when the account has no transactions.
   - Closed accounts are left out of the pickers unless already selected. `_validate()` refuses a closed account on either leg unless the edited transaction already used it.
2. **Carel tested on CT 161**, with the database checked afterwards: change of type, closing refused at a non-zero balance, adding and deleting an empty account, the transfer, closing at zero, and editing in a closed account. Ready to Assign stayed £815.00. Not tried there, but covered by the automated tests: refusing a new transaction in a closed account, and reopening.
3. README feature list and roadmap updated.

## Next steps

1. **TASK-H005 (credit cards).** Read `TASKS/TASK-H005.md` and plan it with Carel before coding (the `task-planning` skill).
   - Card payments reuse transfers.
   - It needs system categories that can't be deleted. The H003 routes only manage `kind == 'standard'`, so a new `kind` is already excluded.
   - A credit card will be a new account kind. The H004 edit route only allows `ACCOUNT_KINDS` and keeps budget/tracking fixed; decide whether changing to or from "credit card" is allowed.
2. **After that:** H006, CSV import.

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
- **Tests: checking for `value="<id>"` across a whole page** gives false matches, because account and category IDs overlap. Slice out the specific `<select>` first, as `account_pickers()` in `tests/test_accounts.py` does.
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
- **Accounts (H004):**
  - `transactions.account_id` is RESTRICT, so a new path that deletes accounts must check for transactions first.
  - Closed accounts are still returned by `account_balances()` and `_pickers()`. Filtering happens in the templates (`_macros.html`, `transactions.html`, `accounts.html`), so a new picker must do the same.
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
