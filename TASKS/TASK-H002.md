# TASK-H002: Transfers between accounts

**Status**: TODO
**Priority**: H - High
**Effort**: M - 3-5 days
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**:
**Completed**:
**Branch**: TASK-H002
**Dependencies**: TASK-C001

---

## Objective

Record moving money between two of the user's accounts as a single linked transfer, with correct envelope behaviour, instead of as two unrelated transactions that distort income and spending.

---

## Background

Today, moving £500 from current account to savings must be entered as an outflow and an inflow. With no category, the inflow counts as **income** (Ready to Assign goes up by £500) and the outflow is flagged as **uncategorised spending**. Both are wrong.

YNAB rules this task should follow:
- **Budget to budget**: no category, no effect on Ready to Assign or any envelope. Only account balances change.
- **Budget to tracking** (e.g. paying the mortgage or moving to an investment account): money leaves the budget, so the budget-side leg **needs a category** and counts as spending. The tracking leg has no category.
- **Tracking to budget**: money enters the budget; the budget-side leg is income (or categorised, e.g. a refund).
- **Tracking to tracking**: balances only.

---

## Technical Requirements

- Schema (migration): a link between the two legs, e.g. `transfer_id` on `transactions` (self-referencing FK to the other leg) or a shared transfer group key. Both legs belong to the same user.
- Creating, editing and deleting a transfer always keeps both legs consistent (amounts equal and opposite, same date), in one database transaction.
- `budget.build_budget` must exclude budget-to-budget transfer legs from **income** and from the **uncategorised outflow** count. This is the critical correctness change, since today any uncategorised positive on-budget transaction is treated as income.
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

**Ask first**: The schema shape (self-FK vs group key vs a separate `transfers` table) and whether to introduce an explicit "Ready to Assign" inflow category at the same time (see Notes).

---

## Implementation Plan

### Phase 1: Model and maths
- [ ] Migration adding the transfer link
- [ ] Update `build_budget` income and uncategorised queries to ignore transfer legs where appropriate
- [ ] Unit tests in `test_budget.py` for all four account combinations

### Phase 2: Create, edit, delete
- [ ] Create route and form changes
- [ ] Delete and edit keep both legs in sync (coordinate with TASK-H001's edit route)

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

- [ ] The income rule in `build_budget` (no category + positive + on-budget) will misclassify transfer inflows unless the query explicitly excludes them. Same for the uncategorised outflow count.
- [ ] `ondelete` behaviour of the link: deleting one leg must not leave an orphan pointing nowhere.
- [ ] Deleting an account (TASK-H004) that has transfers must handle the other account's legs.

---

## Related Tasks

- **Depends On**: TASK-C001
- **Blocks**: TASK-H005, TASK-M003
- **Related**: TASK-H001, TASK-H004, TASK-H006, TASK-M002

---

## Notes

Design question to settle before starting: income is currently identified implicitly (no category + positive). YNAB instead has an explicit "Inflow: Ready to Assign" category, which makes negative adjustments to Ready to Assign possible (e.g. a budget account opened while overdrawn) and makes "uncategorised" unambiguous. Transfers, credit cards and CSV import all get simpler if income is explicit. Worth deciding once for all three.

---

*Last Updated: 2026-10-21 by Claude*
