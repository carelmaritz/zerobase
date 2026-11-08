# TASK-M006: Cleared status and reconciliation

**Status**: IN_PROGRESS
**Priority**: M - Medium
**Effort**: M - 3-5 days
**Assigned**: Claude
**Created**: 2026-10-21
**Started**: 2026-11-08
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

## Agreed plan (2026-11-08)

### Decisions (agreed with Carel)

1. **The adjustment is always in Inflow: Ready to Assign** on a budget account (cards included), and has no category on a tracking account, like YNAB. It can be recategorised afterwards with Edit. No category picker.
2. **Imported rows start cleared**, and a typed-in transaction becomes cleared when an import matches it.
3. **Each transfer leg has its own status** (each bank clears its side).
4. **Changing only the category** of a reconciled transaction (the inline picker) needs no confirmation: it doesn't change the balance.

### Steps, each with its completion test

1. **Migration `0008`:** `transactions.status` (`uncleared` | `cleared` | `reconciled`, default `uncleared`, NOT NULL) and `accounts.reconciled_on` (date, nullable). *Test:* upgrade and downgrade on SQLite and PostgreSQL; the model check passes.
2. **Clear toggle:** a "C" column on the list. htmx switches uncleared ↔ cleared in place; without JS it posts and returns to the same filtered page. Reconciled rows show a lock instead. *Test:* the toggle saves, refuses a reconciled row and another user's row.
3. **Balances:** cleared, uncleared and total per account on the Accounts page, and on the transactions list when filtered to one account. *Test:* the figures add up across mixed statuses.
4. **Reconcile:** a page reached from the account's Manage page, where you enter the bank balance. If it equals the cleared balance, all cleared rows become reconciled and `reconciled_on` = today. If not, the difference is shown with "Create adjustment and reconcile": one transaction "Reconciliation balance adjustment", dated today, status reconciled, in Inflow (budget) or no category (tracking). *Tests:* matching; positive and negative difference with the Ready to Assign effect; a tracking account; a card; exactly one adjustment even if posted twice; another user's account 404.
5. **Reconciled guard:** edit and delete of a reconciled row need `confirm_reconciled=1`, enforced on the server; otherwise the edit form is shown again with the warning, and delete is refused with a message. The edit page gets a Status field (the manual undo). *Test:* each path with and without the confirmation.
6. **Import:** rows added by an import are `cleared`; a matched typed-in row becomes `cleared` (a reconciled one stays reconciled). *Test:* in `tests/test_import_web.py`.
7. **Bookkeeping:** tests on SQLite and PostgreSQL, task file, `TASKS.md`, README; back up CT 161, deploy, Carel tests.

**Out of scope:** undoing a whole reconciliation in one go, filtering the list by status, statement matching.

---

## Implementation Plan

### Phase 1
- [ ] Migration and model; cleared toggle; account balance breakdown
### Phase 2
- [ ] Reconcile flow and adjustment
- [ ] Reconciled-edit guard in `edit_transaction` (`POST /transactions/{id}/edit`, TASK-H001)

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
