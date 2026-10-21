# TASK-H001: Edit transactions

**Status**: TODO
**Priority**: H - High
**Effort**: S - 1-2 days
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**:
**Completed**:
**Branch**: TASK-H001
**Dependencies**: None

---

## Objective

Let the user edit every field of an existing transaction (date, account, payee, memo, category, outflow/inflow) instead of having to delete and re-enter it.

---

## Background

Today a transaction can only have its category changed (`POST /transactions/{id}/category`) or be deleted. Typos in amount or date mean delete and re-add. Editing needs no schema change, so it can start before TASK-C001.

---

## Technical Requirements

- An edit form for one transaction: either an inline htmx row swap on the transactions page or a separate edit page. Must work without JavaScript as a plain form post (the app's existing pattern).
- Validation identical to adding a transaction. Extract the parsing in `add_transaction` (date range, outflow xor inflow, non-zero amount, category ownership, trimming lengths) into a shared helper used by both routes.
- Moving a transaction to a tracking account clears its category (same rule as today's add and set-category routes).
- Ownership checks on the transaction, the target account and the category, as elsewhere.
- After saving, return to the same transactions view (keep `account_id` filter if one was active).

### Success Criteria
- [ ] Every field can be edited and the change is reflected in account balances and the budget view
- [ ] Invalid input re-shows the form with an error and changes nothing
- [ ] Editing another user's transaction returns 404
- [ ] Moving a categorised transaction to a tracking account clears its category
- [ ] Add and edit share one validation helper

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
- [ ] Extract transaction-form parsing into a helper returning either a validated value object or an error message
- [ ] Switch `add_transaction` to it; existing tests must still pass

### Phase 2: Edit
- [ ] GET edit form, POST update route
- [ ] Template changes (edit link or button per row)
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
- [ ] Edit amount: account balance and category activity change accordingly
- [ ] Edit date across a month boundary: activity moves months, rollover recalculated
- [ ] Change outflow to inflow on an uncategorised transaction: it becomes income and Ready to Assign rises
- [ ] Invalid date, both amounts, zero amount: 400 with message, row unchanged
- [ ] Other user's transaction: 404

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
