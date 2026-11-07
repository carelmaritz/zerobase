# Session Handover — 2026-11-07 — TASK-H005 (credit cards) done and merged; CT 161 on main

## Current state

All verified on 2026-11-07.

- **`main` at `2a48dbb`** ("Merge TASK-H005"), plus the commit that updated this handover. `main` and branch `TASK-H005` are pushed. 137 tests pass on SQLite and PostgreSQL 16; ruff is clean.
- **Branches:** `main`, plus `TASK-H003`, `TASK-H004` and `TASK-H005` (all fully merged and pushed; delete only if Carel asks).
- **Task status:**
  - Done: H000, C001, H007, H001, H002, H003, H004, **H005**.
  - **Next: H006** (CSV import). Not planned yet.
- **Database schema head: revision `0006`** (`0006_credit_cards.py`): adds `category_groups.kind` and `categories.account_id` (unique, RESTRICT).
- **GitHub CI:** status never checked (**unverified**).
- **Test deployment, CT 161** (details in `deploy/lxc/README.md` and memory `test-deployment.md`):
  - Runs **`main` (`2a48dbb`)**. App and database are healthy, and the database is at `0006`. Later commits that only touch this handover aren't deployed, and don't need to be.
  - **Login:** `demo@zerobase.local` (the password was given to Carel in chat; it isn't stored anywhere).
  - **Data after Carel's H003, H004 and H005 testing** (all deliberate):
    - Categories: Rent / Mortgage was merged into Holidays, Insurance renamed "Rainy Day", Groceries hidden, the Needs group deleted (its categories moved to Bills).
    - Accounts: Savings changed to type Other, and **Savings is closed**. A £1,800 transfer Savings → Current (transactions 46/47) emptied it first. Savings' starting balance (transaction 3) has the payee "Starting odd" from an edit test.
    - **Card `Visa_Starling`** (account 5, payment category 15), test transactions 48–53: -£500 starting debt, £30 on Dining out, £200 on Transport, £30 payment from Current, £10 refund to Dining out.
    - Balances: Current £5,349.01, Savings £0.00 (closed), Mortgage −£181,450.00, Visa_Starling −£690.00.
    - Ready to Assign: October £1,315.00, November and December **£815.00**.
    - Transport shows −£80.90 of credit overspending in November. The Visa_Starling payment line has £109.10 available and £580.90 needed.
    - Don't wipe, reseed or restore without asking.
  - **Firewall:** the app can be reached from 192.168.1.0/24 and 192.168.2.0/24 (the WiFiman VPN). SSH is 192.168.1.0/24 only.
  - **Backups** in `/opt/zerobase/backups/`. The latest is `zerobase-20261102-140509.sql.gz`, taken just before the H005 deploy (it has schema `0005` and no card).

## Completed this session

1. **TASK-H004 (accounts), DONE**, merged as `0dd177b` on 2026-11-02. Details are in its task file.
2. **TASK-H005 (credit cards), DONE**, merged as `2a48dbb` on 2026-11-07. Plan, worked examples and details are in `TASKS/TASK-H005.md`. In short:
   - **Maths:** `build_budget` fills a `Ledger` of plain sums, and the pure `compute_budget()` / `_roll_month()` do the maths. `tests/test_card_maths.py` holds the plan's worked examples.
   - **Rules:** cash spending is funded first, then cards in account order. Funded card spending moves to the card's payment category. Unfunded card spending is credit overspending and doesn't reduce Ready to Assign. Starting debt doesn't touch Ready to Assign.
   - **Protection:** payment categories can't be managed on `/categories` or chosen for a transaction. Renaming, closing or deleting the card handles them. The credit card type is fixed once the account is created.
   - **Tests:** `tests/test_cards.py` and `test_0006_adds_card_links_and_a_user_still_deletes_on_postgres` in `tests/test_migrations.py`.
3. **Carel tested H005 on CT 161**, with the database checked afterwards: starting debt, funded spending, credit overspending (including the amber pill and note), a payment, a refund and a rename. Not tried there, but covered by the automated tests: the server refusing a type change, refusing a payment category on a transaction, and closing or deleting a card.
4. `/budget` with 5,000 transactions over 3 years and two cards takes about 70 ms on local PostgreSQL (measured 2026-11-02 with a throwaway script).

## Next steps

1. **TASK-H006 (CSV import).** Read `TASKS/TASK-H006.md` and plan it with Carel before coding (the `task-planning` skill).
   - Any delete path must delete or unlink a transfer's other leg itself.
   - Decide how imported rows on a credit card are handled. A payment category can't be chosen for a transaction, and card payments must be transfers.

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
- **Credit cards (H005):**
  - `build_budget()` must keep payment categories out of `category_ids`. They come from `ledger.payment_categories`, and a category passed both ways would be rolled twice.
  - Starting debt is a card transaction in the card's own payment category. It's debt, not activity.
  - A refund lowers the debt and the payment category's Available by the same amount, so the amount needed doesn't change.
  - A card's edit page only offers the "Credit card" type. That's deliberate: the type is fixed.
  - **Known edges, left alone:** editing the starting debt to a positive amount doesn't reach Ready to Assign, and a transfer from a card to a budget account (a cash advance) counts as reversing a payment.
  - **SQLite with foreign keys switched on refuses to delete a user** because of the RESTRICT keys. This predates H005. The app never switches them on in SQLite, and PostgreSQL cascades cleanly, so that test runs on PostgreSQL only.
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
- **Testing with Carel on CT 161:** check the database after each step. The UI can look right while saving the wrong thing; an earlier bug in saving plain transactions was only caught that way. Read-only query: `docker compose exec -T db sh -c "psql -U \$POSTGRES_USER -d \$POSTGRES_DB -c '...'"` in `/opt/zerobase`. App request logs: `docker compose logs app`.
- **Inflow category:**
  - Stored as `categories.kind = 'inflow'`, `group_id` NULL, one per user.
  - Deleting it would uncategorise all income, so the H003 routes refuse it (404).
  - `/budget/assign` returns 404 for it.
- **`inflow_category()`** only `flush()`es, so callers must commit. `_pickers()` commits on purpose, even on GET.
- **Redeploying CT 161:** `ssh root@192.168.1.50 'cd /opt/zerobase && git fetch -q origin && git checkout -q <branch> && git reset -q --hard origin/<branch> && docker compose up -d --build'`. Run `./scripts/backup.sh` first if the deploy includes a migration or data changes. Never touch other guests (VMIDs 100–160).
- **PostgreSQL tests locally:** `podman run -d --rm --name zb-pg -e POSTGRES_PASSWORD=t -e POSTGRES_DB=zb -p 55432:5432 docker.io/library/postgres:16`, then `ZEROBASE_TEST_DATABASE_URL=postgresql+psycopg://postgres:t@127.0.0.1:55432/zb .venv/bin/python -m pytest -q`.
- **Demo seed script:** don't rerun `deploy/lxc/seed_demo.py` on CT 161.
- **Known gap, not fixed:** `HEAD /` returns 405.
- **App port on CT 161:** the app is published on port 80, so checks from the CT against `127.0.0.1:8000` get connection refused.
- **`TASKS/TASKS.md`:** its Quick Reference says to move finished tasks to the archive table, but H002–H005 are still marked DONE in the High Priority table. Tidy them together if Carel wants it.
- **Commit attribution:** commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
