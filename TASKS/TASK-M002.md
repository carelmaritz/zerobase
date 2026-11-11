# TASK-M002: Scheduled and recurring transactions

**Status**: IN_PROGRESS
**Priority**: M - Medium
**Effort**: L - 1-2 weeks
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**: 2026-11-11
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

## Agreed Plan (2026-11-11)

Carel's decisions:
1. **Timing:** due schedules are entered when the user opens the app. That happens at the start of any authenticated request, with a cheap check on the earliest `next_due`. There's no background job and no second container.
2. **Editing:** editing a schedule changes every future occurrence. Rows already entered are ordinary transactions, edited one at a time. For a one-off difference, use "Enter now" and then edit the row, or "Skip next". There's no per-occurrence exceptions table.
3. **Missed dates:** each one is entered with its own due date (3 missed months → 3 rows). A notice says "N scheduled transactions entered".
4. **Status:** entered rows start uncleared (M006).

Settled by the task file or follow from earlier tasks:
- **Budget:** future schedules don't affect the budget, Ready to Assign or M001's `assign_cap()` until entered.
- **Closed account:** a schedule on a closed account (either side of a transfer) is paused. It isn't entered, and it isn't advanced.
- **Transfers:** a scheduled transfer enters both legs through the existing transfer code. The category goes on the budget leg only, as now.
- **"Today":** the server's local date (UK on CT 161).
- **"Once":** a one-off schedule is deleted after it's entered.
- **Imports:** entered rows have no `import_id`, so H006's likely-match rule can stamp them, avoiding duplicates.

Claude's calls (free to decide):
- **No double entry:** `transactions` gets `schedule_id` (SET NULL) and `scheduled_for` (the occurrence date), with a unique key on (`schedule_id`, `scheduled_for`). The rows are inserted and `next_due` advanced in one database transaction. If a concurrent request gets there first, the unique key fails, and that request rolls back and moves on.
- **Frequencies:** once, weekly, every 2 weeks, monthly, every N months, yearly. Monthly and yearly keep the original day (`day_of_month`) and use the month's last day when it doesn't exist (31st → 30th → 28th or 29th → back to the 31st).
- **Catch-up is capped** at 100 occurrences per schedule per request, so a weekly schedule set in 1990 can't flood a single request. The rest is entered on the next request.
- **UI:**
  - A "Scheduled" page to list, add, edit and delete schedules, with "Enter now" and "Skip next".
  - An "Upcoming" section on the transactions page with the next 30 days.
  - Plain styling (back end first).

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

*Last Updated: 2026-11-11 by Claude*
