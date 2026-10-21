# TASK-M006: Cleared status and reconciliation

**Status**: TODO
**Priority**: M - Medium
**Effort**: M - 3-5 days
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**:
**Completed**:
**Branch**: TASK-M006
**Dependencies**: TASK-C001, TASK-H001

---

## Objective

Let the user mark transactions as cleared (seen on the bank statement) and reconcile an account: confirm the cleared balance matches the bank, lock those transactions, and create an adjustment if it doesn't match.

---

## Background

YNAB's reconciliation is how users keep the app honest against reality. Without it, small errors drift into the budget unnoticed. Not on the README roadmap; proposed because it's central to the YNAB method.

---

## Technical Requirements

- Schema: transaction status `uncleared | cleared | reconciled`.
- Toggle cleared on the transactions list (htmx, like the category picker).
- Account shows cleared balance, uncleared balance and total.
- **Reconcile** flow: user enters the bank's balance; if it equals the cleared balance, mark all cleared as reconciled; if not, offer to create a "Reconciliation balance adjustment" transaction for the difference (on budget: in "Inflow: Ready to Assign", affecting Ready to Assign like YNAB does).
- Reconciled transactions warn before edit or delete.
- CSV import (TASK-H006) may mark imported rows cleared.

### Success Criteria
- [ ] Toggle cleared persists
- [ ] Reconcile with matching balance marks cleared as reconciled
- [ ] Reconcile with a difference creates exactly one adjustment and then reconciles
- [ ] Editing a reconciled transaction requires confirmation
- [ ] Migration up/down tested

### Out of Scope

- Statement import or matching.
- Undo reconciliation (beyond editing status manually).

---

## Freedom

**Free to decide**: UI, warning style for reconciled edits.

**Ask first**: Whether the user may pick a different category for the adjustment.

---

## Implementation Plan

### Phase 1
- [ ] Migration and model; cleared toggle; account balance breakdown
### Phase 2
- [ ] Reconcile flow and adjustment
- [ ] Reconciled-edit guard in the TASK-H001 edit route

---

## Work Completed

*Fill when IN_PROGRESS or DONE.*

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [ ] Positive and negative adjustments; check Ready to Assign effect
- [ ] Reconcile tracking account (adjustment has no category)
- [ ] Other user's account: 404

---

## Related Tasks

- **Depends On**: TASK-C001, TASK-H001
- **Blocks**: None
- **Related**: TASK-H002, TASK-H004, TASK-H006

---

*Last Updated: 2026-10-21 by Claude*
