# TASK-H003: Manage categories and groups

**Status**: IN_PROGRESS
**Priority**: H - High
**Effort**: M - 3-5 days
**Assigned**: Claude
**Created**: 2026-10-21
**Started**: 2026-11-02
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
- `transactions.category_id` is `ON DELETE SET NULL`. A deleted category's transactions would all become **uncategorised**, dropping out of the budget and changing history. The built-in "Inflow: Ready to Assign" category (TASK-H007) must never be renamed, moved, hidden or deleted: deleting it would uncategorise all income.
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
- [x] Rename, reorder and move are reflected in the budget view and the category picker
- [x] Hidden categories disappear from views but Ready to Assign and other envelopes are unchanged
- [x] Deleting a category with reassignment leaves total Available unchanged for every month, and Ready to Assign too unless the merge cancels past overspending (accepted by Carel on 2026-11-02; the confirm page previews the change)
- [x] Database-level guard against deleting a category that still has transactions
- [x] All operations ownership-checked; migration up/down tested

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
- [x] Rename, reorder, move for categories and groups
- [x] Migration: `hidden` flag; hide/unhide; filter hidden from budget view and pickers

### Phase 2: Delete with reassignment
- [x] Merge logic (transactions, assignments with month collision summing) as a function in `budget.py` or a service module, unit-tested
- [x] Delete routes and confirmation UI
- [x] FK change migration

### Phase 3: Tests
- [x] Invariant tests: Ready to Assign and totals unchanged across delete-with-reassign for several months

---

## Work Completed

Branch `TASK-H003`. Decisions from Carel (2026-11-02): FK changed to RESTRICT; merges that change past overspending are allowed, with a preview.

- **Migration `0004_manage_categories.py`**: adds `categories.hidden` (default false) and changes `transactions.category_id` from `ON DELETE SET NULL` to `RESTRICT`. Downgrade reverses both. The drift test was checked to fail if the FK's `ondelete` is wrong.
- **`budget.py`**:
  - `build_budget()` puts hidden categories in `BudgetView.hidden` instead of their group. They still count in every total.
  - `build_budget(..., merge=(source_id, target_id))` is an in-memory dry run of a merge, used for the preview. It writes nothing, so no savepoints are involved.
  - `merge_category(db, source, target)` moves transactions, sums assignments for the same month (and drops one that sums to zero), then deletes the source. The caller commits.
  - `category_in_use()` reports whether any transaction or assignment uses a category.
- **`routers/categories.py`** and the `/categories` page ("Edit categories" link on the budget page):
  - Rename categories and groups, move them up or down, move a category to another group, hide or unhide.
  - Delete a group only when it's empty.
  - Delete a category: if it's unused, straight away. Otherwise you pick a target on `/categories/{id}/delete`, see a preview of Ready to Assign for the current month, then confirm.
  - The inflow category gets a 404 everywhere here, as a source or a target. Everything is ownership-checked.
- **Pickers**: `category_options` leaves hidden categories out, except the one already selected.
- **Budget page**: a collapsible "Hidden categories" table shows their figures (read-only). Hiding a category with money in it shows a notice.
- **Tests**: 6 new in `tests/test_budget.py` (hide, merge, the invariants across 4 months, the overspending preview) and 14 in `tests/test_categories.py` (routes, ownership, inflow protection, the database-level RESTRICT guard). 92 pass on SQLite and on PostgreSQL 16.

Not done yet: Carel testing on CT 161.

Notes:
- The preview shows Ready to Assign for the **current month** only. A changed overspend in an earlier month carries through to every later month, so the current month shows the effect.
- On SQLite, FKs aren't enforced (no `PRAGMA foreign_keys`), so RESTRICT only guards PostgreSQL in practice. The guard test switches the pragma on for SQLite.
- You can't assign to a hidden category from the budget page; unhide it first.

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [x] Delete category A into B where both have an assignment in the same month: B's assignment becomes the sum
- [x] Delete category with overspending in a past month: Ready to Assign unchanged after merge (check the overspend rule still yields the same result, since merging can cancel out one category's overspending with another's surplus; see Known Issues)
- [x] Hide a category with money in it: shown somewhere so money isn't "lost" from view
- [x] Reorder persists across reloads

---

## Known Issues & Gotchas

- [x] **Decided 2026-11-02 (Carel): accept and show it.** Merging two categories can change history: if A was overspent in March and B had a surplus, after the merge March is no longer overspent, so Ready to Assign goes **up**. YNAB accepts this. Decide whether to accept it (and tell the user) or block it.
- [x] Hiding a category that still has Available money: YNAB warns about this. At minimum show a notice. (Done: a notice after hiding, and hidden categories are listed under "Hidden categories" on the budget page.)

---

## Related Tasks

- **Depends On**: TASK-C001
- **Blocks**: None
- **Related**: TASK-H004, TASK-H005, TASK-M001

---

*Last Updated: 2026-11-02 by Claude*
