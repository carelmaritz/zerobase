# TASK-M003: Spending and net-worth reports

**Status**: TODO
**Priority**: M - Medium
**Effort**: M - 3-5 days
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**:
**Completed**:
**Branch**: TASK-M003
**Dependencies**: TASK-H002

---

## Objective

Add a reports page showing where money goes and how net worth changes over time.

---

## Background

All the data exists, but there's no view beyond the current month's budget. Depends on TASK-H002 so transfers aren't counted as spending or income.

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
- [ ] Figures match hand-calculated totals from test fixtures
- [ ] Transfers excluded from spending and income
- [ ] Works in light and dark colour schemes and at phone width
- [ ] Page loads in under 500 ms with 5 years of data (~10,000 transactions) on SQLite

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
- [ ] Report query functions with unit tests
### Phase 2
- [ ] SVG chart macros, reports page, navigation link

---

## Work Completed

*Fill when IN_PROGRESS or DONE.*

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [ ] Spending by category over a range spanning a year end
- [ ] Net worth includes tracking accounts
- [ ] Refunds (positive categorised amounts) reduce spending
- [ ] Empty range

---

## Related Tasks

- **Depends On**: TASK-H002
- **Blocks**: None
- **Related**: TASK-L002

---

*Last Updated: 2026-10-21 by Claude*
