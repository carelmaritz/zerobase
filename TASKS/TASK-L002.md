# TASK-L002: Data export

**Status**: TODO
**Priority**: L - Low
**Effort**: S - 1-2 days
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**:
**Completed**:
**Branch**: TASK-L002
**Dependencies**: None

---

## Objective

Let each user download their own data as CSV: all transactions, and the budget (assigned/activity/available per category per month).

---

## Background

`scripts/backup.sh` dumps the whole database, which suits the operator but not an individual user wanting their own data in a spreadsheet. Self-hosting is about owning your data; export also makes leaving easy. Not on the README roadmap.

---

## Technical Requirements

- `GET /export/transactions.csv` and `GET /export/budget.csv`, signed-in user's data only.
- Amounts as plain decimals (`money.plain_money`), ISO dates, UTF-8 with header row.
- Guard against CSV formula injection: prefix cells starting with `=`, `+`, `-`, `@`, tab or CR with `'` in text fields (payee, memo, names), not in numeric amount columns.
- Streamed response so large exports don't load everything into memory.

### Success Criteria
- [ ] Exports open cleanly in a spreadsheet and round-trip totals match the app
- [ ] Payee `=HYPERLINK(...)` is exported inert
- [ ] Another user's data never appears

### Out of Scope

- Import of this format (TASK-H006 handles bank CSVs).
- JSON/full-fidelity export, scheduled exports.

---

## Freedom

**Free to decide**: Column set, file naming, where the links live in the UI.

**Ask first**: Nothing expected.

---

## Implementation Plan

### Phase 1
- [ ] Export routes with streaming CSV writer and injection guard
- [ ] Links on accounts or a settings page
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
- [ ] Two users: each export contains only their rows
- [ ] Formula-injection payee
- [ ] Budget export totals equal the budget page for a sample month

---

## Security Considerations

- Formula injection (see above); user scoping.

---

## Related Tasks

- **Depends On**: None
- **Blocks**: None
- **Related**: TASK-H006, TASK-M003

---

*Last Updated: 2026-10-21 by Claude*
