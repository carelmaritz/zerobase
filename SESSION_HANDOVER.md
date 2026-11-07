# Session Handover — 2026-11-07 — H005 done; H006 (CSV and OFX import) built, awaiting Carel's real-file test

## Current state

All verified on 2026-11-07.

- **`main` at `602a2e5`** ("H006: plan agreed"), plus the commit that updated this handover. It contains H005 (merge `2a48dbb`) and pushes cleanly.
- **Branch `TASK-H006` at `1f07766`**, pushed and **not merged**. 194 tests pass on SQLite and PostgreSQL 16; ruff is clean.
- **Other branches:** `TASK-H003`, `TASK-H004` and `TASK-H005` are all fully merged and pushed. Delete them only if Carel asks.
- **Task status:**
  - Done: H000, C001, H007, H001, H002, H003, H004, H005.
  - **In progress: H006** (CSV and OFX import). Steps 1–4 are done; step 5 (Carel imports a real statement on CT 161) is pending. Details are in the "Work Completed" section of `TASKS/TASK-H006.md`.
- **Database schema:**
  - Head on `TASK-H006` is **`0007`** (`0007_imports.py`): `transactions.import_id` and the `import_mappings` table.
  - Head on `main` is `0006`.
- **GitHub CI:** status never checked (**unverified**).
- **Test deployment, CT 161** (details in `deploy/lxc/README.md` and memory `test-deployment.md`):
  - Runs **branch `TASK-H006` (`1f07766`)**, not `main`. App and database are healthy, and the database is at **`0007`**.
  - **Login:** `demo@zerobase.local` (the password was given to Carel in chat; it isn't stored anywhere).
  - **Data after Carel's H003–H005 testing** (all deliberate). Nothing has been imported yet.
    - Categories: Rent / Mortgage was merged into Holidays, Insurance renamed "Rainy Day", Groceries hidden, the Needs group deleted (its categories moved to Bills).
    - Accounts: Savings changed to type Other, and **Savings is closed**. A £1,800 transfer Savings → Current (transactions 46/47) emptied it first. Savings' starting balance (transaction 3) has the payee "Starting odd" from an edit test.
    - **Card `Visa_Starling`** (account 5, payment category 15), test transactions 48–53: -£500 starting debt, £30 on Dining out, £200 on Transport, £30 payment from Current, £10 refund to Dining out.
    - Balances: Current £5,349.01, Savings £0.00 (closed), Mortgage −£181,450.00, Visa_Starling −£690.00.
    - Ready to Assign: October £1,315.00, November and December **£815.00**. Checked again after the H006 deploy.
    - Don't wipe, reseed or restore without asking.
  - **Firewall:** the app can be reached from 192.168.1.0/24 and 192.168.2.0/24 (the WiFiman VPN). SSH is 192.168.1.0/24 only.
  - **Backups** in `/opt/zerobase/backups/`:
    - The latest is `zerobase-20261107-155225.sql.gz`, taken just before the H006 deploy (schema `0006`, card included).
    - The one before it is `zerobase-20261102-140509.sql.gz` (before H005, schema `0005`).

## Completed this session

1. **TASK-H004 (accounts), DONE**, merged as `0dd177b` on 2026-11-02. Details are in its task file.
2. **TASK-H005 (credit cards), DONE**, merged as `2a48dbb` on 2026-11-07. Plan, worked examples and details are in `TASKS/TASK-H005.md`. In short:
   - `build_budget` fills a `Ledger`; the pure `compute_budget()` / `_roll_month()` do the maths.
   - Cash is funded first, then cards in account order. Unfunded card spending is credit overspending and doesn't reduce Ready to Assign.
   - Payment categories are protected from `/categories` and from transaction pickers.
   - Carel tested it on CT 161, with the database checked after each step: starting debt, funded spending, credit overspending (amber pill and note), payment, refund and rename.
3. **TASK-H006 (CSV and OFX import), steps 1–4.** The plan was agreed on 2026-11-07, with OFX added at Carel's request. It's in "Agreed plan" in `TASKS/TASK-H006.md`.
   - **Parsing:** `src/zerobase/importer.py` is a pure module covering CSV (with a mapping), OFX 1.x/2.x and `classify()` (NEW / IMPORTED / MATCH / ERROR). Tested by 38 unit tests in `tests/test_importer.py`.
   - **Web:** `src/zerobase/routers/imports.py` handles upload → map (CSV only) → preview → confirm. The pages are `import_upload.html`, `import_map.html`, `import_preview.html` and `_import.html`. Tested by 18 tests in `tests/test_import_web.py`, including the card-payment workflow.
   - **Migration `0007`:** tested in `tests/test_migrations.py`.
   - **Deploy:** CT 161 was backed up and runs the branch.

## Next steps

1. **H006 step 5: Carel imports a real statement on CT 161.** Carel said they would get a bank download "when we do the work". Check the database after each step:
   1. Import the file into Current; check the preview's dates, totals and signs.
   2. Re-import it: everything should be "imported before".
   3. Check that any matches against typed-in transactions are sensible.

   Check that rows were added with `import_id` set and `category_id` NULL, that `import_mappings` has a row, and that Ready to Assign is unchanged.
2. **If the real file doesn't parse,** or the guessed mapping is off: add an anonymised copy as a fixture in `tests/test_importer.py`, then fix `importer.py`. The real file also decides whether QIF is needed (decision 7).
3. **Then mark H006 DONE.** Update the task file and the `TASKS.md` row in the same commit. Merge with `--no-ff` after `git pull --ff-only`, push, redeploy `main` to CT 161, and update this handover.
4. **After that:** nothing is planned yet. The next H task is done, so pick from `TASKS/TASKS.md` with Carel, e.g. M005 (transaction paging) or the open items below.

## Open decisions

- **QIF import:** only if Carel's bank offers QIF rather than OFX (H006 decision 7).
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
- **CT 161 is on a branch with migration `0007`.** Don't redeploy `main` there until H006 is merged. `main` has no revision `0007`, so its startup upgrade will most likely refuse the database (expected, not tried). To go back without merging, restore `zerobase-20261107-155225.sql.gz`, and only with Carel's OK.
- **Imports (H006):**
  - **File text between steps:** it travels in a hidden form field. The routes read their own form through `import_form`, with a 4 MB field limit; Starlette's default is 1 MB, and decoded Windows-1252 text can be longer than the upload. Uploads are capped at 1 MB (`importer.MAX_BYTES`).
  - **Import IDs:** `ofx:<FITID>` for OFX, `<date>:<amount>:<n>` for CSV. The likely-match rule also covers transactions imported in the other format.
  - **Saved settings:** `import_mappings.settings` is JSON: `{"csv": {"mapping", "header"}, "ofx": {"account_number"}}`.
  - **Deleting accounts:** a new path that deletes accounts must also delete its `ImportMapping`, because SQLite doesn't enforce the CASCADE.
  - **Tests:** Jinja escapes `'` in *variables* as `&#39;`, but not in the template's own text. Assertions must match that.
  - **`Row` and `Existing` have a field named `date`.** `importer.py` needs `from __future__ import annotations`, or the `date | None` annotation fails.
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
- **Commit attribution:** commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, plus the `Claude-Session:` line when the session gives one.
- **Pronouns:** Carel's pronouns haven't been stated, so use "they" or the name in docs. A slip in the H006 plan was corrected.
