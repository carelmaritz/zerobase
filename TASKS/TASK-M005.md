# TASK-M005: Transaction list paging and search

**Status**: IN_PROGRESS
**Priority**: M - Medium
**Effort**: S - 1-2 days
**Assigned**: Claude
**Created**: 2026-10-21
**Started**: 2026-11-08
**Completed**:
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
- [ ] All transactions reachable via paging
- [ ] Each filter works alone and combined
- [ ] `%` and `_` in search text are treated literally
- [ ] Filters persist after adding, editing or deleting a transaction

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

*Fill when IN_PROGRESS or DONE.*

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
