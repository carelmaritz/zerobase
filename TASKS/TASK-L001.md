# TASK-L001: Form validation loose ends

**Status**: TODO
**Priority**: L - Low
**Effort**: S - 1-2 days
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**:
**Completed**:
**Branch**: TASK-L001
**Dependencies**: None

---

## Objective

Give the user a clear message wherever a form currently fails silently or returns a bare error page.

---

## Background

Found while reviewing the scaffold:

1. `add_transaction` (`routers/transactions.py`) wraps `owned_category(...)` in `try/except ValueError` meant to show "Choose a valid category." But `owned_category` raises `HTTPException(404)`, so a category ID that exists but belongs to someone else (or was just deleted in another tab) returns a bare 404 instead of the form with an error. Only non-numeric input reaches the friendly message.
2. `add_group` and `add_category` (`routers/budget.py`) silently ignore an empty or over-60-character name and redirect back with no message. `add_category` also silently ignores a group ID that isn't the user's.
3. `set_category` returns a bare 400/404 for bad IDs. For an htmx request the user sees nothing happen.

None of these lose data; they're confusing.

---

## Technical Requirements

- (1) Catch the not-found case and show the form error, or check ownership without raising.
- (2) Show an error on the budget page (the `_page` helper already supports `error`).
- (3) For htmx requests return something the page can display, or keep the select's previous value.

### Success Criteria
- [ ] Each case above shows a human-readable message and changes nothing
- [ ] Tests for each case

### Out of Scope

- Redesigning error display generally.
- Anything in TASK-H001's shared validation helper (if H001 lands first, fix (1) there instead and note it here).

---

## Freedom

**Free to decide**: Wording, exact mechanism.

**Ask first**: Nothing expected.

---

## Implementation Plan

### Phase 1
- [ ] Fix (1), (2), (3) with tests

---

## Work Completed

*Fill when IN_PROGRESS or DONE.*

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [ ] Post a transaction with another user's category ID: 400 with message
- [ ] Add a category with a blank name: error shown
- [ ] Add a category to another user's group: error or 404, nothing created

---

## Related Tasks

- **Depends On**: None
- **Blocks**: None
- **Related**: TASK-H001, TASK-H003

---

*Last Updated: 2026-10-21 by Claude*
