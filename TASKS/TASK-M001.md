# TASK-M001: Targets and goals

**Status**: DONE
**Priority**: M - Medium
**Effort**: L - 1-2 weeks
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**: 2026-11-09
**Completed**: 2026-11-11
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
- [x] Each target type shows correct underfunded amounts across several months, including after overspending and rollover
- [x] Quick-assign never assigns more than Ready to Assign without the user choosing to
- [x] Targets deleted with their category (or moved on reassignment, coordinate with TASK-H003)
- [x] Migration up/down tested

### Out of Scope

- Weekly/yearly repeating targets, "needed for spending" with refill/set-aside variants.
- Debt payoff targets.
- Notifications.

---

## Freedom

**Free to decide**: UI for setting targets, visual style of progress.

**Ask first**: Adding more target types than the three above, behaviour of quick-assign when Ready to Assign is short.

---

## Agreed Plan (2026-11-09)

Carel's decisions:
1. **Ready to Assign short:** quick-assign assigns what's left. One category gets `min(needed, Ready to Assign)`. "Assign all" funds categories in budget order until Ready to Assign reaches £0, then stops and says which weren't fully funded. It never pushes Ready to Assign below £0.
2. **Monthly amount = "set aside £X"**: assign £X every month, whatever rolled over. Leftovers build up.
3. **Merge (H003):** if the category merged into has a target, keep it and drop the source's. If it has none, it takes the source's target.
4. **Hidden categories** keep their targets, but "Assign all" skips them.

Claude's calls:
- Card payment categories (and the inflow category) can't have targets. Payment categories already show "needed".
- **Ready to Assign cap = the lowest Ready to Assign from the month shown to the last month with income or assignments.** An assignment in October also reduces November's Ready to Assign. If November is lower, capping by October's figure alone would push November negative.
- The schema has one target per category (unique `category_id`), with `ON DELETE CASCADE`. Delete paths also remove it themselves, because SQLite doesn't enforce foreign keys here.

### The maths (pence; A = assigned this month, V = available at the end of the month)

- **Monthly £X:** needs `max(0, X − A)`.
  - £400 with A = 0: needs £400. A = 150: needs £250. A = 500: needs £0. Overspending or leftovers from earlier months make no difference.
- **Balance £T:** needs `max(0, T − V)`.
  - £3,000 with V = 1,200: needs £1,800.
  - V = 3,000 from rollover alone: needs £0.
  - Overspent, V = −50: needs £3,050.
- **Balance £T by month D:** `start = V − A` (the balance before this month's assigning, after this month's activity). `left = months from the month shown to D, inclusive, at least 1`. `share = ceil((T − start) / left)`, and it needs `max(0, share − A)`.
  - £1,200 by Jul 2027, viewing Nov 2026 with start £300: 9 months left, share £100. A = 0: needs £100. A = 40: needs £60.
  - Viewing Jul 2027 with start £1,100: 1 month left, needs £100.
  - Viewing Aug 2027 (D has passed), start £1,100: needs the whole £100.
  - £1,000 over 3 months from 0: share £333.34 (rounded up to the penny).
  - Start ≥ T: needs £0.

Progress shown: monthly is A / X; the two balance types are V / T.

---

## Implementation Plan

### Phase 1
- [x] Define the maths for each type with worked examples in this file; unit tests first
- [x] Migration and model

### Phase 2
- [x] Set/edit/remove target UI
- [x] Budget view indicators and totals
- [x] Quick-assign routes (htmx, reuse OOB update pattern from `_budget_oob.html`)

---

## Work Completed

2026-11-09 (branch `TASK-M001`):
- **Migration `0009`:** `targets` table, one per category (`uq_targets_category_id`), CASCADE with the category. The `Target` model and the kind constants (`MONTHLY`, `BALANCE`, `BY_DATE`) are in `models.py`.
- **Maths:** `budget.underfunded()`, tested with the worked examples above in `tests/test_target_maths.py`. `build_budget()` sets `line.target` and `line.underfunded`. `view.underfunded` totals the visible categories.
- **Merge and delete:** `merge_category()` keeps the target category's own target, or moves the source's. Deleting an unused category deletes its target explicitly.
- **Target page:** `routers/targets.py` and `templates/target.html`, at `GET/POST /categories/{id}/target` and `POST .../target/delete`. Standard categories only (others return 404).
- **Budget page:** each line has a progress bar with "£A of £T", "needs £X" and an "Assign £X" button, or a "Set a target" link. Above the table is "Underfunded this month" with "Assign all underfunded".
- **Quick-assign:** `POST /budget/fund` (one category) and `POST /budget/fund-all`, via `budget.fund()` and `budget.assign_cap()`. The htmx response is `_budget_oob.html` with `inputs=True`, so the assigned inputs are swapped too.
- **Tests:** `tests/test_targets.py`, plus the `0009` test in `tests/test_migrations.py`.

Fixes from Carel's testing:
- The "by" month was an `<input type="month">`, which Carel's browser couldn't type into or pick from. It's now two dropdowns, Month and Year (this year plus ten).
- At Carel's suggestion, the month and year fields show only when "by a month" is chosen. This is CSS `:has()`, not JavaScript; browsers without `:has()` always show the fields.

**Tested by Carel on CT 161 (2026-11-10 to 11), with the database checked after each step:**
- Monthly target and quick-assign.
- Balance targets: already funded, raised above the balance, and on an overspent category.
- By-month target: £133.34 a month over 9 months.
- Assign all stopping at Ready to Assign £0.
- October blocked by November's £0 (the later-month limit).
- Removing a target.
- Merge: the destination category's target is kept.

Hidden categories: a hidden category's target stays, but the budget's hidden table shows no target or button. Unhide the category to fund it (as for assigning).

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [x] Monthly target, partially assigned
- [x] Balance-by-date target, months left = 1 and target month already passed
- [x] Target balance reached by rollover alone: underfunded = 0
- [x] Quick-assign all with insufficient Ready to Assign

---

## Related Tasks

- **Depends On**: TASK-C001
- **Blocks**: None
- **Related**: TASK-H003

---

*Last Updated: 2026-11-09 by Claude*
