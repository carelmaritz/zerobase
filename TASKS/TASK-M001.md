# TASK-M001: Targets and goals

**Status**: TODO
**Priority**: M - Medium
**Effort**: L - 1-2 weeks
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**:
**Completed**:
**Branch**: TASK-M001
**Dependencies**: TASK-C001

---

## Objective

Let the user set a target on a category and see how much still needs assigning this month to stay on track, with a one-click "assign what's needed".

---

## Background

The budget view shows assigned, activity and available, but nothing says what a category *should* have. YNAB's targets turn the monthly assigning session into "fund what's underfunded".

---

## Technical Requirements

Target types (start with these; YNAB has more):
- **Monthly amount**: assign £X every month (e.g. Groceries £400).
- **Target balance**: have £X available, no date (e.g. Emergency fund £3,000).
- **Target balance by date**: have £X available by a month; needed per month = remaining / months left (e.g. Holidays £1,200 by July).

Requirements:
- Schema: a `targets` table (category, type, amount, optional target month), one target per category.
- Pure function computing **underfunded** for a category in a month from target + assigned + available. Unit-tested.
- Budget view: progress indicator and "needs £X" per category; total underfunded for the month.
- Quick assign: "Assign underfunded" per category and for all, limited by Ready to Assign (decide what happens when there isn't enough).

### Success Criteria
- [ ] Each target type shows correct underfunded amounts across several months, including after overspending and rollover
- [ ] Quick-assign never assigns more than Ready to Assign without the user choosing to
- [ ] Targets deleted with their category (or moved on reassignment, coordinate with TASK-H003)
- [ ] Migration up/down tested

### Out of Scope

- Weekly/yearly repeating targets, "needed for spending" with refill/set-aside variants.
- Debt payoff targets.
- Notifications.

---

## Freedom

**Free to decide**: UI for setting targets, visual style of progress.

**Ask first**: Adding more target types than the three above, behaviour of quick-assign when Ready to Assign is short.

---

## Implementation Plan

### Phase 1
- [ ] Define the maths for each type with worked examples in this file; unit tests first
- [ ] Migration and model

### Phase 2
- [ ] Set/edit/remove target UI
- [ ] Budget view indicators and totals
- [ ] Quick-assign routes (htmx, reuse OOB update pattern from `_budget_oob.html`)

---

## Work Completed

*Fill when IN_PROGRESS or DONE.*

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [ ] Monthly target, partially assigned
- [ ] Balance-by-date target, months left = 1 and target month already passed
- [ ] Target balance reached by rollover alone: underfunded = 0
- [ ] Quick-assign all with insufficient Ready to Assign

---

## Related Tasks

- **Depends On**: TASK-C001
- **Blocks**: None
- **Related**: TASK-H003

---

*Last Updated: 2026-10-21 by Claude*
