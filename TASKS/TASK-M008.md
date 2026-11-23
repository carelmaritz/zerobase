# TASK-M008: Property accounts

**Status**: REVIEW
**Priority**: M - Medium
**Effort**: S - 1-2 days
**Assigned**: Claude
**Created**: 2026-11-23
**Started**: 2026-11-23
**Completed**:
**Branch**: TASK-M008
**Dependencies**: TASK-M007

---

## Objective

Let Carel record the current estimated price of a property, so it counts in net worth (TASK-M003).

---

## Background

Asked for by Carel while planning M003 (2026-11-23), "if that is not already a feature". An "Other" tracking account with "Update value" could hold it, but nothing told it apart from cash.

---

## Technical Requirements

- A **Property** account type (stored as `property`), always tracking, like the investment types. `TRACKING_KINDS` holds every always-tracking type; `INVESTMENT_KINDS` stays the three investments.
- The estimate is typed in with "Update value". No migration is needed.
- The account holds the full value; a mortgage stays in its own account.

### Success Criteria
- [x] Property can be added and is always tracking, whatever the form sends
- [x] A new estimate adds one "Market value change" row; Ready to Assign is unchanged
- [x] A budget account can't be switched to Property

### Out of Scope
- Looking up prices automatically (an outside network call).
- Linking a property to its mortgage, or showing equity.

---

## Freedom

**Free to decide**: wording, layout.

**Ask first**: any outside network call.

---

## Work Completed

2026-11-23: the type in `models.py` and `routers/accounts.py`, wording in `accounts.html`, tests in `tests/test_investments.py`.

---

## Failed Approaches

None yet.

---

*Last Updated: 2026-11-23 by Claude*
