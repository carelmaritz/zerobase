# TASK-H003: Manage categories and groups

**Status**: TODO
**Priority**: H - High
**Effort**: M - 3-5 days
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**:
**Completed**:
**Branch**: TASK-H003
**Dependencies**: TASK-C001

---

## Objective

Let the user rename, reorder, move, hide and delete categories and category groups without corrupting budget history or Ready to Assign.

---

## Background

Today categories and groups can only be added. New users get a default set (`DEFAULT_CATEGORIES` in `budget.py`) that they cannot tailor.

Naive deletion is dangerous with the current foreign keys:
- `transactions.category_id` is `ON DELETE SET NULL`. A deleted category's **positive** transactions would become **income** and its negative ones **uncategorised spending**, changing Ready to Assign and history.
- `assignments.category_id` is `ON DELETE CASCADE`. Deleting assignments returns that money to Ready to Assign for every past month.

So deletion must reassign, the way YNAB does: "Move this category's transactions and available balance to...".

---

## Technical Requirements

- **Rename** category and group (same 1-60 character rule as creation).
- **Reorder** within a group and reorder groups. No drag-and-drop JS required; up/down buttons are fine (CSP allows only same-origin scripts, and htmx is already vendored).
- **Move** a category to another group.
- **Hide** a category (schema: `hidden` flag): not shown in the budget view or category pickers, but history and maths unaffected. Show hidden categories on request and allow unhide.
- **Delete** a category: requires choosing a target category. Its transactions and assignments move to the target in one database transaction. Assignments for the same month are summed into the target's existing assignment (the `uq_assignment_cat_month` constraint). A category with no transactions or assignments can be deleted without a target.
- **Delete** a group: only when empty, or by moving its categories to another group first.
- Change the FK on `transactions.category_id` away from silent `SET NULL` (e.g. `RESTRICT`), so the database itself refuses an unsafe delete.

### Success Criteria
- [ ] Rename, reorder and move are reflected in the budget view and the category picker
- [ ] Hidden categories disappear from views but Ready to Assign and other envelopes are unchanged
- [ ] Deleting a category with reassignment leaves Ready to Assign and total Available unchanged for every month
- [ ] Database-level guard against deleting a category that still has transactions
- [ ] All operations ownership-checked; migration up/down tested

### Out of Scope

- Targets and goals (TASK-M001).
- System categories for credit card payments (TASK-H005), though the design should leave room for categories the user cannot delete.
- Bulk recategorisation of transactions outside the delete flow.
- Closing accounts (TASK-H004).

---

## Freedom

**Free to decide**: UI (an "edit categories" mode on the budget page vs a separate page), route names, how reorder is implemented.

**Ask first**: Hard-delete vs hide-only if the reassignment maths turns out to be messy, the FK change.

---

## Implementation Plan

### Phase 1: Non-destructive edits
- [ ] Rename, reorder, move for categories and groups
- [ ] Migration: `hidden` flag; hide/unhide; filter hidden from budget view and pickers

### Phase 2: Delete with reassignment
- [ ] Merge logic (transactions, assignments with month collision summing) as a function in `budget.py` or a service module, unit-tested
- [ ] Delete routes and confirmation UI
- [ ] FK change migration

### Phase 3: Tests
- [ ] Invariant tests: Ready to Assign and totals unchanged across delete-with-reassign for several months

---

## Work Completed

*Fill when IN_PROGRESS or DONE.*

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [ ] Delete category A into B where both have an assignment in the same month: B's assignment becomes the sum
- [ ] Delete category with overspending in a past month: Ready to Assign unchanged after merge (check the overspend rule still yields the same result, since merging can cancel out one category's overspending with another's surplus; see Known Issues)
- [ ] Hide a category with money in it: shown somewhere so money isn't "lost" from view
- [ ] Reorder persists across reloads

---

## Known Issues & Gotchas

- [ ] Merging two categories can change history: if A was overspent in March and B had a surplus, after the merge March is no longer overspent, so Ready to Assign goes **up**. YNAB accepts this. Decide whether to accept it (and tell the user) or block it.
- [ ] Hiding a category that still has Available money: YNAB warns about this. At minimum show a notice.

---

## Related Tasks

- **Depends On**: TASK-C001
- **Blocks**: None
- **Related**: TASK-H004, TASK-H005, TASK-M001

---

*Last Updated: 2026-10-21 by Claude*
