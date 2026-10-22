# TASK-H002: Transfers between accounts

**Status**: IN_PROGRESS
**Priority**: H - High
**Effort**: M - 3-5 days
**Assigned**: Claude
**Created**: 2026-10-21
**Started**: 2026-10-22
**Completed**:
**Branch**: TASK-H002
**Dependencies**: TASK-C001, TASK-H007

---

## Objective

Record moving money between two of the user's accounts as a single linked transfer, with correct envelope behaviour, instead of as two unrelated transactions that distort income and spending.

---

## Background

Today, moving £500 from current account to savings must be entered as an outflow and an inflow. After TASK-H007 neither leg counts as income, but both are flagged as **uncategorised**, and nothing links them. Before TASK-H007 the inflow leg even counted as income.

YNAB rules this task should follow:
- **Budget to budget**: no category, no effect on Ready to Assign or any envelope. Only account balances change.
- **Budget to tracking** (e.g. paying the mortgage or moving to an investment account): money leaves the budget, so the budget-side leg **needs a category** and counts as spending. The tracking leg has no category.
- **Tracking to budget**: money enters the budget; the budget-side leg needs a category, usually "Inflow: Ready to Assign" (or e.g. a refund category).
- **Tracking to tracking**: balances only.

---

## Technical Requirements

- Schema (migration): a link between the two legs, e.g. `transfer_id` on `transactions` (self-referencing FK to the other leg) or a shared transfer group key. Both legs belong to the same user.
- Creating, editing and deleting a transfer always keeps both legs consistent (amounts equal and opposite, same date), in one database transaction.
- `budget.build_budget` must exclude budget-to-budget transfer legs from the **uncategorised** warning. They have no category, so (after TASK-H007) they already stay out of income and envelopes.
- UI: a "Transfer to/from" choice in the add-transaction form (YNAB shows transfers as payees "Transfer: Savings"). The transaction list shows the other account.
- Category on a transfer leg is only allowed on the budget side of a budget/tracking transfer, and required there.

### Success Criteria
- [ ] Budget-to-budget transfer: account balances change, Ready to Assign and all envelopes unchanged, no uncategorised warning
- [ ] Budget-to-tracking transfer with category: envelope activity reduced, tracking balance increased
- [ ] Deleting either leg deletes both
- [ ] Editing amount or date on one leg updates the other
- [ ] Cannot create a transfer to an account owned by another user, or to the same account
- [ ] Migration up and down tested

### Out of Scope

- Credit card payment logic (TASK-H005), though the data model must allow it to reuse transfers.
- Scheduled transfers (TASK-M002).
- Matching imported transactions to existing transfers (TASK-H006).
- Converting existing pairs of transactions into transfers.

---

## Freedom

**Free to decide**: UI layout, route names, how the paired leg is displayed.

**Ask first**: The schema shape (self-FK vs group key vs a separate `transfers` table).

**Settled 2026-10-22**: a self-referencing `transfer_id` on `transactions`; each leg points at the other.

---

## Implementation Plan

### Phase 1: Model and maths
- [ ] Migration adding the transfer link
- [ ] Update the `build_budget` uncategorised query to ignore budget-to-budget transfer legs
- [ ] Unit tests in `test_budget.py` for all four account combinations

### Phase 2: Create, edit, delete
- [ ] Create route and form changes
- [ ] Delete and edit keep both legs in sync: extend `edit_transaction` and `delete_transaction` in `routers/transactions.py` (TASK-H001), reusing `_validate()`

### Phase 3: Web tests
- [ ] End-to-end tests for each combination and for isolation between users

---

## Work Completed

*Fill when IN_PROGRESS or DONE.*

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [ ] All four account-type combinations, checking Ready to Assign, envelope activity and balances
- [ ] Edit and delete propagate to both legs
- [ ] Transfer spanning a month end (same date on both legs, so no split)
- [ ] Cross-user account ID rejected

---

## Security Considerations

- Both account IDs ownership-checked; the paired leg must never point at another user's row.

---

## Known Issues & Gotchas

- [ ] Budget-to-budget legs have no category, so the uncategorised count must explicitly exclude them.
- [ ] `ondelete` behaviour of the link: deleting one leg must not leave an orphan pointing nowhere.
- [ ] Deleting an account (TASK-H004) that has transfers must handle the other account's legs.

---

## Related Tasks

- **Depends On**: TASK-C001, TASK-H007
- **Blocks**: TASK-H005, TASK-M003
- **Related**: TASK-H001, TASK-H004, TASK-H006, TASK-M002

---

## Notes

Settled 2026-10-21: income is explicit via an "Inflow: Ready to Assign" category, done first as TASK-H007.

---

*Last Updated: 2026-10-21 by Claude*
