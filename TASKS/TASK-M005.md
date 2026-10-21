# TASK-M005: Transaction list paging and search

**Status**: TODO
**Priority**: M - Medium
**Effort**: S - 1-2 days
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**:
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
