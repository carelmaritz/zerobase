# TASK-H002: Transfers between accounts

**Status**: DONE
**Priority**: H - High
**Effort**: M - 3-5 days
**Assigned**: Claude
**Created**: 2026-10-21
**Started**: 2026-10-22
**Completed**: 2026-10-27
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
- [x] Budget-to-budget transfer: account balances change, Ready to Assign and all envelopes unchanged, no uncategorised warning
- [x] Budget-to-tracking transfer with category: envelope activity reduced, tracking balance increased
- [x] Deleting either leg deletes both
- [x] Editing amount or date on one leg updates the other
- [x] Cannot create a transfer to an account owned by another user, or to the same account
- [x] Migration up and down tested

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
- [x] Migration adding the transfer link
- [x] Update the `build_budget` uncategorised query to ignore budget-to-budget transfer legs
- [x] Unit tests in `test_budget.py` for all four account combinations

### Phase 2: Create, edit, delete
- [x] Create route and form changes
- [x] Delete and edit keep both legs in sync: extend `edit_transaction` and `delete_transaction` in `routers/transactions.py` (TASK-H001), reusing `_validate()`

### Phase 3: Web tests
- [x] End-to-end tests for each combination and for isolation between users

---

## Work Completed

- Migration `0003_transfers.py`: `transactions.transfer_id`, a nullable self-FK (`ON DELETE SET NULL`, indexed). Each leg points at the other. Downgrade drops the link and keeps both legs as plain transactions.
- `models.py`: `Transaction.transfer` (read-only relationship) and `takes_category` (a budget leg, unless the other leg is also on budget).
- `budget.build_budget`: the uncategorised count skips legs whose other leg is in a budget account. A budget leg of a budget/tracking transfer with no category is still flagged.
- `routers/transactions.py`: a `transfer_account_id` form field. `_validate()` checks ownership (404) and that the two accounts differ, and applies the category rules: none for budget-budget or tracking-tracking, required for budget/tracking, and always stored on the budget leg whichever side the form was filled from. `_save()` is shared by add and edit: it creates, updates or (when the transfer account is cleared) deletes the other leg in the same commit. Delete removes both legs. The inline category route uses `takes_category`.
- Templates: "Transfer to/from" picker in the shared form fields. The list shows "Transfer to/from <account>" before the payee and "Transfer" instead of a category picker for budget-budget legs.
- Tests: 5 budget tests (four combinations, plus a flagged uncategorised budget-to-tracking leg), 9 web tests, 1 migration test with data. 71 pass on SQLite and PostgreSQL 16.
- Fix found while Carel tested on CT 161: after a refused save, the add form came back blank, so the Transfer to/from picker reset and a resubmitted transfer saved as a plain transaction. The add form now re-shows what was typed, as edit does (`b3b3264`, with a test).
- Tried by Carel on CT 161 (2026-10-27): budget-to-budget transfer, editing one leg, the category rule on a transfer to the mortgage, and deleting one leg. Database and pages checked after each step.
- Not enforced: the inline category picker on the budget leg of a budget/tracking transfer still offers "Uncategorised"; such a leg is then flagged like any uncategorised transaction.

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [x] All four account-type combinations, checking Ready to Assign, envelope activity and balances
- [x] Edit and delete propagate to both legs
- [x] Transfer spanning a month end (same date on both legs, so no split)
- [x] Cross-user account ID rejected

---

## Security Considerations

- Both account IDs ownership-checked; the paired leg must never point at another user's row.

---

## Known Issues & Gotchas

- [x] Budget-to-budget legs have no category, so the uncategorised count must explicitly exclude them.
- [x] `ondelete` behaviour of the link: deleting one leg must not leave an orphan pointing nowhere.
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

*Last Updated: 2026-10-27 by Claude*
