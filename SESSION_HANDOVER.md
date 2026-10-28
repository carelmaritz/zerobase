# Session Handover — 2026-10-27 — TASK-H002 (transfers) done and merged; CT 161 back on main

## Current state

All verified on 2026-10-27 unless marked otherwise.

- **`main` at `78b477a`** ("Merge TASK-H002"), pushed, plus this handover commit. 72 tests pass on the merged code (SQLite). PostgreSQL 16 was run on `b3b3264`, the same code before the merge.
- **`main` is the only branch**, locally and on GitHub. `TASK-H002` was deleted on 2026-10-28 at Carel's request, after checking it was fully merged.
- **Task status:**
  - Done: H000, C001, H007, H001, **H002**.
  - **Next: H003** (categories).
- **Database schema head: revision `0003`** (`0003_transfers.py`, which adds `transactions.transfer_id`).
- **GitHub CI:** status never checked (**unverified**).
- **Deploy docs (2026-10-28):** `DEPLOYMENT.md` no longer claims the build is untested, and the provisioning script and `deploy/lxc/README.md` include the VPN range. `ruff check` and `ruff format --check` are clean.
- **Test deployment, CT 161** (details in `deploy/lxc/README.md` and memory `test-deployment.md`):
  - **Where:** CT 161 on prox01, 192.168.1.50. It runs **`main` (`78b477a`)**. App and database are healthy, and the database is at `0003`.
  - **Login:** `demo@zerobase.local`. Claude reset the password on 2026-10-27 at Carel's request and gave it to Carel in chat. It isn't stored in the repo or memory.
  - **Data:**
    - October Ready to Assign: **£1,315.00**.
    - Balances: Current account £3,579.01, Savings £1,800.00, Mortgage (tracking) −£181,450.00.
    - One live transfer: Current → Mortgage £1,000, IDs 44/45, category Rent / Mortgage.
    - Two old uncategorised transactions: Amazon −£23.99 and a £50 refund.
    - Don't wipe or reseed without asking.
  - **Firewall:** `/etc/nftables/zerobase.nft` lets the **app** be reached from 192.168.1.0/24 **and 192.168.2.0/24** (Carel's WiFiman VPN). Carel made this change by hand on 2026-10-27 after the classifier blocked Claude. SSH is still 192.168.1.0/24 only. The previous rules file is `/etc/nftables/zerobase.nft.bak-20261027`. `deploy/lxc/provision-zerobase.sh` generates the same rules (checked with `nft -c` on 2026-10-28).
  - **Backups** in `/opt/zerobase/backups/`. The latest is `zerobase-20261027-221954.sql.gz`, taken before the data repair described below.

## Completed this session

1. **TASK-H002 (transfers), DONE**, merged as `78b477a`. Full description in the task file's "Work Completed" section. In short:
   - A self-FK `transfer_id` links the two legs.
   - `_save()` in `routers/transactions.py` keeps both legs in step on add and edit.
   - Delete removes both legs.
   - Category rules: none for budget↔budget or tracking↔tracking. Required for budget↔tracking, and stored on the budget leg.
   - Budget↔budget legs are left out of the uncategorised count.
2. **Bug found during Carel's testing, and fixed** (`b3b3264`, with a regression test):
   - The add form came back blank after a refused save. The "Transfer to/from" picker silently reset, so a resubmitted transfer saved as a plain transaction.
   - The add form now re-shows what was typed.
3. **Data repair on CT 161**, approved by Carel:
   - During testing Carel accidentally deleted transaction 1, the Mortgage "Starting balance" of −£182,450.00 dated 2026-10-21. It was re-inserted with the same ID and values from `zerobase-20261022-115653.sql.gz`.
   - Transaction 44 (the −£1,000 that had saved as a plain transaction) was turned into a real transfer through the edit route.
4. **Carel tried every H002 flow on CT 161**: budget↔budget transfer, editing one leg, the category rule, and deleting one leg. The database and pages were checked after each step.
5. **README:** the feature list and the roadmap tick now include transfers and editing.

## Next steps

1. **TASK-H003 (categories).** It must:
   - refuse to delete the inflow category
   - handle a deleted category nulling a budget↔tracking transfer leg, which is then flagged as uncategorised (that's acceptable)
   - settle the open decision on overspending (below)
2. **After that:**
   - H004, accounts. Account deletion must handle transfer legs (see Landmines).
   - H005, credit cards. Card payments reuse transfers.
   - H006, CSV import.

## Open decisions

- **Inline category picker on transfer legs:** the budget leg of a budget↔tracking transfer still offers "Uncategorised" in the list's inline picker. If chosen, the leg is just flagged as uncategorised. It's recorded in the task file; fix it only if Carel wants it.
- **HTTPS.** The deployment is plain HTTP. Options are Home_Web_Games' proxy01 or the bundled Caddy. Not started; do it before real use, especially now that it's reachable over the VPN.
- **UI polish is deferred.** Carel wants the back end first (memory `backend-first-priority.md`).
- **H003:** whether to accept that merging categories can change past overspending (Known Issues in `TASKS/TASK-H003.md`).

## Failed approaches

- **Claude changing CT 161's firewall:** blocked by the auto-mode classifier ("Security Weaken"), even with Carel's OK in chat. Give Carel the command to run instead. Pasted one-liners can lose characters (the space in `ip saddr` vanished once), so keep `sed` patterns short.
- **Claude deleting merged branches:** blocked by the classifier ("Git Destructive") when bundled into a wrap-up. It worked when Carel asked for it directly and the merge was checked first.
- **Creating PRs from here:** `gh` isn't installed and there's no token. Merge locally with `git merge --no-ff` and push after asking, or Carel merges on GitHub.
- **Migration tests with explicit primary keys on PostgreSQL:** fixed IDs don't advance the sequence, so a later insert collides. Let the database assign IDs when anything inserts afterwards.
- **Pushing to `main` without fetching:** rejected once. Always `git pull --ff-only` first.
- **Tests:** reading `.id` on an ORM object whose row a request deleted raises `ObjectDeletedError` after `expire_all()`. Capture IDs before the request.

## Landmines

- **Task bookkeeping:** the task file is the source of truth. Any status change updates the task file **and** the `TASKS/TASKS.md` row in the same commit. One branch per task, named `TASK-XNNN`.
- **Schema changes need a migration.** Add a new revision in `src/zerobase/migrations/versions/`; `test_upgrade_reaches_head_and_matches_the_models` catches drift.
- **Transfers:**
  - Both legs point at each other through `transfer_id`. `Transaction.transfer` is **viewonly**, so set the IDs directly (`_save()` flushes, then links them).
  - **SQLite doesn't enforce FKs here**, so the app deletes the other leg. Any new delete path (H004 accounts, H006 import) must delete or unlink the other leg itself.
  - The category lives on the budget leg only.
  - `takes_category` needs `transfer.account` loaded.
- **Testing with Carel on CT 161:** check the database after each step. The UI can look right while saving the wrong thing; the plain-transaction save in item 2 of "Completed this session" was only caught that way. Read-only query: `docker compose exec -T db sh -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -c '...'"` in `/opt/zerobase`. App request logs: `docker compose logs app`.
- **Inflow category:**
  - Stored as `categories.kind = 'inflow'`, `group_id` NULL, one per user.
  - Deleting it would uncategorise all income, so H003 must refuse that.
  - `/budget/assign` returns 404 for it.
- **`inflow_category()`** only `flush()`es, so callers must commit. `_pickers()` commits on purpose, even on GET.
- **Redeploying CT 161:** `ssh root@192.168.1.50 'cd /opt/zerobase && git fetch -q origin && git checkout -q <branch> && git reset -q --hard origin/<branch> && docker compose up -d --build'`. Run `./scripts/backup.sh` first if the deploy includes a migration or data changes. Never touch other guests (VMIDs 100–160).
- **PostgreSQL tests locally:** `podman run -d --rm --name zb-pg -e POSTGRES_PASSWORD=t -e POSTGRES_DB=zb -p 55432:5432 docker.io/library/postgres:16`, then `ZEROBASE_TEST_DATABASE_URL=postgresql+psycopg://postgres:t@127.0.0.1:55432/zb .venv/bin/python -m pytest -q`.
- **Demo seed script:** don't rerun `deploy/lxc/seed_demo.py` on CT 161.
- **Known gap, not fixed:** `HEAD /` returns 405.
- **Commit attribution:** commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
