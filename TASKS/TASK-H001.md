# TASK-H001: Edit transactions

**Status**: DONE
**Priority**: H - High
**Effort**: S - 1-2 days
**Assigned**: Claude
**Created**: 2026-10-21
**Started**: 2026-10-21
**Completed**: 2026-10-22
**Branch**: TASK-H001
**Dependencies**: None

---

## Objective

Let the user edit every field of an existing transaction (date, account, payee, memo, category, outflow/inflow) instead of having to delete and re-enter it.

---

## Background

Today a transaction can only have its category changed (`POST /transactions/{id}/category`) or be deleted. Typos in amount or date mean delete and re-add. Editing needs no schema change.

---

## Technical Requirements

- An edit form for one transaction: either an inline htmx row swap on the transactions page or a separate edit page. Must work without JavaScript as a plain form post (the app's existing pattern).
- Validation identical to adding a transaction. Extract the parsing in `add_transaction` (date range, outflow xor inflow, non-zero amount, category ownership, trimming lengths) into a shared helper used by both routes.
- Moving a transaction to a tracking account clears its category (same rule as today's add and set-category routes).
- Ownership checks on the transaction, the target account and the category, as elsewhere.
- After saving, return to the same transactions view (keep `account_id` filter if one was active).

### Success Criteria
- [x] Every field can be edited and the change is reflected in account balances and the budget view
- [x] Invalid input re-shows the form with an error and changes nothing
- [x] Editing another user's transaction returns 404
- [x] Moving a categorised transaction to a tracking account clears its category
- [x] Add and edit share one validation helper

### Out of Scope

- Transfers (TASK-H002). If a transfer concept exists by the time this lands, editing a transfer leg is handled there.
- Bulk edit, split transactions, undo.
- Paging or search on the transaction list (TASK-M005).
- Fixing the bare 404 on a foreign category ID (TASK-L001).

---

## Freedom

**Free to decide**: Inline row vs separate page, route names, template structure, whether the existing set-category route is kept or folded into edit.

**Ask first**: Any schema change, new JavaScript beyond htmx attributes.

---

## Implementation Plan

### Phase 1: Shared validation
- [x] Extract transaction-form parsing into a helper returning either a validated value object or an error message
- [x] Switch `add_transaction` to it; existing tests must still pass

### Phase 2: Edit
- [x] GET edit form, POST update route
- [x] Template changes (edit link or button per row)
- [x] Tests

---

## Work Completed

Chose a separate edit page over an inline row: works without JavaScript, needs no new htmx behaviour, and keeps UI work minimal (back end first).

- `routers/transactions.py`: `TransactionForm` (raw fields, built by the `_form` dependency) and `_validate()` returning a `ValidTransaction` or an error message, used by both add and edit. `_pickers()` gathers accounts and categories for both forms. New `GET /transactions/{id}/edit` and `POST /transactions/{id}/edit`; a `return_to` account ID carries the list filter through and back.
- `deps.py`: `owned_transaction()`.
- Templates: `transaction_fields` macro shared by the add form and the new `transaction_edit.html`; an Edit link on each row. On error the edit form re-shows what was typed.
- The inline set-category route is kept: it's the quick way to categorise from the list.
- Tests: 7 web tests (form prefill, every field incl. a month change, inflow category, move to tracking, four kinds of invalid input, return-to filter, other user's transaction and account). 56 pass on SQLite and PostgreSQL 16.

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [x] Edit amount: account balance and category activity change accordingly
- [x] Edit date across a month boundary: activity moves months, rollover recalculated
- [x] Change a transaction's category to "Inflow: Ready to Assign": it becomes income and Ready to Assign rises
- [x] Invalid date, both amounts, zero amount: 400 with message, row unchanged
- [x] Other user's transaction: 404

---

## Security Considerations

- All IDs in the form (transaction, account, category) must be ownership-checked.
- Same-origin middleware already covers the new POST route.

---

## Related Tasks

- **Depends On**: None
- **Blocks**: TASK-M006 (cleared status edits build on this)
- **Related**: TASK-H002, TASK-L001, TASK-M005

---

*Last Updated: 2026-10-21 by Claude*
