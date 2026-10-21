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

*Last Updated: 2026-10-21 by Claude*
