# TASK-M005: Transaction list paging and search

**Status**: DONE
**Priority**: M - Medium
**Effort**: S - 1-2 days
**Assigned**: Claude
**Created**: 2026-10-21
**Started**: 2026-11-08
**Completed**: 2026-11-08
**Branch**: TASK-M005
**Dependencies**: None

---

## Objective

Make every transaction reachable from the transactions page, and let the user find transactions by account, category, date range and payee/memo text.

---

## Background

`routers/transactions.py` caps the list at `PAGE_SIZE = 200` most recent rows with no way to see older ones. A household reaches 200 transactions in a few months, after which older transactions can't be viewed, recategorised or deleted from the UI. (Not on the README roadmap; found while reviewing the code.)

---

## Technical Requirements

- Paging: "older/newer" or numbered pages; keyset pagination on `(date, id)` preferred over OFFSET (matches the existing order and index `ix_transactions_user_date`).
- Filters as query parameters (bookmarkable): account (exists), category (including "uncategorised"), date from/to, text search on payee and memo (case-insensitive `LIKE`/`ILIKE`, escaped).
- Link from the budget page's uncategorised warning to the filtered list.
- Keep `account_id` filter behaviour and the add-transaction form working.

### Success Criteria
- [x] All transactions reachable via paging
- [x] Each filter works alone and combined
- [x] `%` and `_` in search text are treated literally
- [x] Filters persist after adding, editing or deleting a transaction

### Out of Scope

- Full-text search indexes.
- Running balance column.
- Editing transactions (TASK-H001).

---

## Freedom

**Free to decide**: Paging style, filter UI.

**Ask first**: Adding database indexes beyond what's needed for the default ordering (that needs a migration, TASK-C001).

---

## Agreed plan (2026-11-08)

Agreed with Carel: Newer/Older keyset paging, 100 rows a page. No migration: `ix_transactions_user_date` serves the `(date, id)` order.

1. **Query and paging:** one `_list_query()` with filters and keyset paging on `(date, id)` descending, 100 a page. `before=<date>:<id>` gives the next older page. `after=<date>:<id>` gives the next newer one: it's fetched in ascending order, then flipped. One extra row is fetched to tell whether there's another page. *Test:* 450 transactions, many on the same date, page through as 100/100/100/100/50 with no gaps or duplicates, both directions.
2. **Filters (query parameters, bookmarkable):** `account_id` (kept from today), `category` (an ID, or `none`), `from`, `to`, `q`. `q` is a case-insensitive `LIKE` over payee and memo, with `\`, `%` and `_` escaped. Bad values (an unknown ID, a malformed date) are ignored rather than erroring. **`category=none` uses the budget page's rule:** budget account, no category, and not a transfer between two budget accounts. *Test:* each filter alone and combined; `50%` matches literally.
3. **Filter bar:** a GET form above the list, replacing the account links. Closed accounts can be chosen. Plain UI.
4. **Budget link:** "Categorise them" goes to `/transactions?category=none&to=<last day of the viewed month>`. *Test:* the filtered count equals `uncategorised_count`.
5. **Filters kept after POST:** add, edit, delete and the no-JS category save carry the list's query string in a hidden `back` field. The redirect rebuilds `/transactions?...` from the known parameters only, so it can't be an open redirect. The page cursor is kept too. This replaces the edit page's `return_to=<account id>`. *Test:* each POST redirects back with its filters, and a 400 on add re-renders the filtered list.
6. **Bookkeeping:** tests pass on SQLite and PostgreSQL; task file, `TASKS.md`; deploy to CT 161 and Carel tries it.

**Out of scope:** new indexes, full-text search, running balance, and card payment categories as filter options (the existing picker leaves them out).

---

## Implementation Plan

### Phase 1
- [ ] Query builder with filters and keyset paging
- [ ] Template filter bar and paging links
- [ ] Redirects after POST preserve filters
- [ ] Tests

---

## Work Completed

- **Steps 1–5 done (2026-11-08):**
  - **`src/zerobase/transaction_list.py`:** `ListFilters` (parsed from the query string, or from a form's `back` field; values that don't parse are dropped), `filtered()` (the filters as one query) and `load_page()` (keyset paging, 100 a page). An unknown but well-formed ID just matches nothing.
  - **Newer from page 2:** when the newer rows don't fill a page, the real first page is shown, so the top page is always full.
  - **`routers/transactions.py`:** the list reads its filters with `ListFilters.from_params`. Add, edit, delete and the no-JS category save carry a hidden `back` field and redirect to `ListFilters.from_back(back).url()`, which is rebuilt from known parameters only. `return_to` is gone.
  - **Templates:** a GET filter bar replaces the account links. It offers closed accounts and hidden categories, but not card payment categories. Paging uses Newer/Older links.
  - **Budget:** "Categorise them" links to `?category=none&to=<last day of the month>`.
  - **Tests:** `tests/test_transaction_list.py` (9): 451 rows paged both ways, each filter alone and combined, literal `%`/`_`/`\\`, uncategorised count equal to the budget's, forms returning to the same filtered page, `back` can't leave `/transactions`, bad parameters, other users' rows. Two older tests were updated for `back`. 204 tests pass on SQLite and PostgreSQL 16.

- **Step 6 done (2026-11-08):** Carel tested on CT 161 with a 150-row CSV imported into a new account, Paging Test (account 6). It was created as a budget account by mistake and is left in place as test data. Paging over 211 rows (100/100/11) and over Paging Test alone (100/50), the budget's "Categorise them" link (162 rows in November), every filter alone and combined, and returning to the same filtered page after add, edit, cancel, delete and a category change all work. The database was checked afterwards.
- **Found on the way, fixed on this branch:** the import mapping page now guesses afresh when a CSV's header has changed (see TASK-H006). The `checking` account type is now shown as "Current account" (label only, no migration).

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [ ] 450 transactions: three pages, no duplicates or gaps, including many on the same date
- [ ] Uncategorised filter matches the budget page's uncategorised count
- [ ] Search for `50%` matches literally

---

## Related Tasks

- **Depends On**: None
- **Blocks**: None
- **Related**: TASK-H001, TASK-M006

---

*Last Updated: 2026-10-21 by Claude*
