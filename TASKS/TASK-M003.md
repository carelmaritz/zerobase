# TASK-M003: Spending and net-worth reports

**Status**: IN_PROGRESS
**Priority**: M - Medium
**Effort**: M - 3-5 days
**Assigned**: Claude
**Created**: 2026-10-21
**Started**: 2026-11-23
**Completed**:
**Branch**: TASK-M003
**Dependencies**: TASK-H002, TASK-M008

---

## Objective

Add a reports page showing where money goes and how net worth changes over time.

---

## Background

All the data exists, but there's no view beyond the current month's budget. Depends on TASK-H002 so transfers aren't counted as spending or income.

---

## Agreed with Carel (2026-11-23)

1. Market value changes affect only net worth. Starting balances aren't income.
2. Starting balances get a real marker (`transactions.is_starting`, migration `0012`); existing rows are matched by payee. CT 161's "Starting odd" row (3) needs a one-off fix, only with Carel's OK.
3. Budget-to-tracking transfers are neither income nor spending: a separate "Moved to tracking accounts" column, net of money coming back.
4. Uncategorised rows are left out, with a note and link. They count in net worth.
5. Net worth is split per account and month end: below zero is debt; otherwise investments, or cash and other. Carel then asked for property (TASK-M008), which Claude made its own part.

Charts are server-drawn SVG, as below; Carel was told and didn't object. Reconciliation adjustments count as income, as in the budget. The current month's net worth is as of today; its income and spending cover the whole month.

---

## Technical Requirements

Reports, each over a selectable date range (default: last 12 months):
- **Spending by category / group**: totals and monthly breakdown (table plus bar chart).
- **Income vs spending**: per month, with net.
- **Net worth**: sum of all account balances (budget and tracking) at each month end.

Constraints:
- Strict CSP (`script-src 'self'`): no CDN. Prefer server-rendered inline SVG charts from Jinja (no JS at all). A vendored chart library is acceptable only if SVG becomes unwieldy.
- Queries scoped to the user; aggregate in SQL, not by loading every transaction.
- Every chart has an accessible table alongside it.

### Success Criteria
- [x] Figures match hand-calculated totals from test fixtures
- [x] Transfers excluded from spending and income
- [ ] Works in light and dark colour schemes and at phone width
- [x] Page loads in under 500 ms with 5 years of data (~10,000 transactions) on SQLite

### Out of Scope

- Age of money.
- Exporting reports (TASK-L002 covers raw data export).
- Custom report builder.

---

## Freedom

**Free to decide**: Chart rendering approach within the CSP, layout.

**Ask first**: Adding a JS chart library (must be vendored with licence).

---

## Implementation Plan

### Phase 1
- [x] Report query functions with unit tests
### Phase 2
- [x] SVG chart macros, reports page, navigation link

---

## Work Completed

2026-11-23 (branch `TASK-M003`): migration `0012`, `reports.py` (figures), `charts.py` (SVG geometry), `routers/reports.py`, `reports.html`, the menu link, and `tests/test_reports.py`. 377 pass on SQLite (1 skipped), 378 on PostgreSQL. 10,000 rows over five years took about 100 ms on SQLite.

**Not done:** looking at the page (light, dark, phone), code review, testing by Carel on CT 161.

---

## Failed Approaches

- **Rendering the page in a headless Chromium container (root, `--no-sandbox`):** blocked by the auto-mode classifier. Not worked around.

---

## Testing

### Test Cases
- [x] Spending by category over a range spanning a year end
- [x] Net worth includes tracking accounts
- [x] Refunds (positive categorised amounts) reduce spending
- [x] Empty range

---

## Related Tasks

- **Depends On**: TASK-H002, TASK-M008 (the branch is built on TASK-M008)
- **Blocks**: None
- **Related**: TASK-L002

---

*Last Updated: 2026-11-23 by Claude*
