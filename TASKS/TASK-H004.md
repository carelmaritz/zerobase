# TASK-H004: Manage accounts

**Status**: TODO
**Priority**: H - High
**Effort**: S - 1-2 days
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**:
**Completed**:
**Branch**: TASK-H004
**Dependencies**: TASK-C001

---

## Objective

Let the user rename accounts, change their type, close and reopen them, and delete accounts that were created by mistake.

---

## Background

Accounts can only be created today. The README roadmap lists "close accounts" alongside category management; it is split out here because it is smaller and independent.

Note: `transactions.account_id` is `ON DELETE CASCADE`, so deleting an account today (if a route existed) would silently delete all its transactions and change the budget.

---

## Technical Requirements

- **Rename** and change **kind** (checking, savings, cash, other).
- **Close** (schema: `closed` flag): hidden from the account picker and the main list, shown under "Closed accounts". YNAB requires a zero balance to close; do the same, and point the user at a balance adjustment if not zero.
- **Reopen** a closed account.
- **Delete** only if the account has no transactions. Otherwise offer close.
- Switching an account between budget and tracking is **not** allowed after creation (it would rewrite history: categorised transactions would drop out of envelopes). YNAB doesn't allow it either.

### Success Criteria
- [ ] Rename and kind change persist
- [ ] Closing requires a zero balance; closed accounts disappear from pickers but their history still counts in the budget
- [ ] Delete refused when transactions exist
- [ ] Ownership checks; migration up/down tested

### Out of Scope

- Balance adjustment / reconciliation transactions (TASK-M006).
- Credit card account type (TASK-H005).
- Handling transfers into a deleted account (deletion is refused when transactions exist, so this doesn't arise).

---

## Freedom

**Free to decide**: UI layout, route names.

**Ask first**: Allowing budget/tracking switching, changing the cascade on `transactions.account_id`.

---

## Agreed plan (2026-11-02)

Decisions from Carel:
- `transactions.account_id` changes from `ON DELETE CASCADE` to `RESTRICT` (same approach as H003's category FK).
- Existing transactions in a closed account **stay editable**, even if an edit makes the balance non-zero again (the Closed accounts list then shows it). **New** transactions, or transfers, into a closed account are refused by the server.

Steps, each with its completion test:
1. **Migration `0005`**: `accounts.closed` (default false), and the RESTRICT FK change. Done when: up/down works, the drift test passes on SQLite and PostgreSQL, and a test (with `PRAGMA foreign_keys` on for SQLite, as in `tests/test_categories.py`) shows the database refuses to delete an account with transactions.
2. **Edit**: `/accounts/{id}/edit` with name (1–80 characters) and kind. Budget/tracking is shown but can't be changed. Done when: changes persist, bad input is refused, and another user's account gets a 404.
3. **Close and reopen**: only at a zero balance. Otherwise refuse, giving the balance and suggesting a transaction or transfer to clear it. Closed accounts appear under "Closed accounts" on the Accounts page, and their history stays viewable through `/transactions?account_id=`. Done when: a non-zero balance is refused, and the budget figures are identical before and after closing.
4. **Delete**: only with no transactions; otherwise refuse and offer close. Done when: both cases are tested.
5. **Pickers and validation**: closed accounts are left out of the account and transfer pickers, except the one an edited transaction already uses (the same pattern as hidden categories in `_macros.html`). `_validate()` in `routers/transactions.py` refuses a closed account on either leg unless the transaction already used it.
6. **Tests and bookkeeping**: ownership checks on every route; the task file, `TASKS.md` and README. Then deploy to CT 161 (backup first) for Carel to test.

Checked before planning: with RESTRICT on these FKs, PostgreSQL 16 still deletes a whole user cascade cleanly.

## Implementation Plan

### Phase 1
- [ ] Migration: `closed` flag
- [ ] Rename/kind edit route and form
- [ ] Close/reopen with zero-balance check
- [ ] Delete when empty
- [ ] Filter closed accounts from transaction-form pickers

### Phase 2
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
- [ ] Close with non-zero balance refused
- [ ] Closed account's past transactions still count in budget figures
- [ ] Delete with transactions refused; delete empty account works
- [ ] Other user's account: 404

---

## Related Tasks

- **Depends On**: TASK-C001
- **Blocks**: None
- **Related**: TASK-H002, TASK-H003, TASK-H005, TASK-M006

---

*Last Updated: 2026-11-02 by Claude*
