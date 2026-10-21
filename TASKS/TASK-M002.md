# TASK-M002: Scheduled and recurring transactions

**Status**: TODO
**Priority**: M - Medium
**Effort**: L - 1-2 weeks
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**:
**Completed**:
**Branch**: TASK-M002
**Dependencies**: TASK-C001

---

## Objective

Let the user schedule transactions (one-off future or repeating: weekly, monthly, yearly, etc.) that are entered automatically on their due date, and see what's upcoming.

---

## Background

Rent, salary and subscriptions repeat on predictable dates. Entering them by hand each time is tedious and they're easy to forget.

---

## Technical Requirements

- Schema: `scheduled_transactions` with the same fields as a transaction (account, payee, memo, category, amount, optional transfer target) plus frequency and next due date.
- Frequencies: once, weekly, every 2 weeks, monthly, every N months, yearly. Monthly on the 31st falls back to the month's last day.
- **Materialisation**: due schedules become real transactions without a background worker. Recommended: materialise lazily per user at the start of authenticated requests (cheap query on next-due date), idempotent so concurrent requests don't double-enter. Alternative: a periodic task in the lifespan.
- Future scheduled transactions do **not** affect the budget until they are entered.
- UI: list of scheduled transactions; add/edit/delete; "upcoming" section on the transactions page; "enter now" and "skip next".

### Success Criteria
- [ ] A monthly schedule produces exactly one transaction per month, including after the app was off for several months (catches up)
- [ ] Two concurrent requests don't double-enter
- [ ] Month-end dates handled (31st -> 28/29/30)
- [ ] Skip and enter-now work
- [ ] Migration up/down tested

### Out of Scope

- Matching imported CSV rows to scheduled ones (follow-up to TASK-H006).
- Email or push reminders.
- Variable-amount schedules.

---

## Freedom

**Free to decide**: Lazy vs periodic materialisation (record the choice and why), UI layout.

**Ask first**: Adding a scheduler or task-queue dependency, running a second container.

---

## Implementation Plan

### Phase 1
- [ ] Pure date-recurrence function (next occurrence after a date) with thorough unit tests
- [ ] Migration and model

### Phase 2
- [ ] Idempotent materialisation (e.g. row lock on the schedule, or a unique key on schedule + occurrence date)
- [ ] CRUD UI and upcoming list

---

## Work Completed

*Fill when IN_PROGRESS or DONE.*

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [ ] Recurrence: monthly on 31st across Feb in leap and non-leap years; weekly across year end
- [ ] Catch-up after 3 missed months
- [ ] Schedule for a closed account (TASK-H004): pause, don't enter
- [ ] Scheduled transfer creates both legs (if TASK-H002 is done)

---

## Known Issues & Gotchas

- [ ] "Today" depends on timezone; the server's date may differ from the user's. Decide on server-local date for now and note it.

---

## Related Tasks

- **Depends On**: TASK-C001
- **Blocks**: None
- **Related**: TASK-H002, TASK-H004, TASK-H006

---

*Last Updated: 2026-10-21 by Claude*
