# TASK-M002: Scheduled and recurring transactions

**Status**: DONE
**Priority**: M - Medium
**Effort**: L - 1-2 weeks
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**: 2026-11-11
**Completed**: 2026-11-13
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
- [x] A monthly schedule produces exactly one transaction per month, including after the app was off for several months (catches up)
- [x] Two concurrent requests don't double-enter
- [x] Month-end dates handled (31st -> 28/29/30)
- [x] Skip and enter-now work
- [x] Migration up/down tested

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

### Annual bills in the budget (Carel, 2026-11-11)

Carel subscribes to Dropbox and Amazon Prime yearly and wants the budget to save up for them.

Carel's decisions:
- **A yearly repeating target and a shortcut on schedules.**
  - The by-month target (M001) gets **"repeat every year"** (`targets.repeats`). This was out of scope in M001; Carel has now asked for it.
  - A yearly schedule with a category gets a **"Save up for this in [category]"** tick (`scheduled_transactions.save_up`). Saving the schedule with it ticked creates or replaces that category's target: by a month, repeating, with the amount set to the schedule's outflow and the month set to the month of its next due date.
- **One category per annual bill** (e.g. "Dropbox", "Amazon Prime"). A category keeps at most one target; no change to M001's design.

The maths for a repeating target (pence). T is the amount, D the target month of the year, and the month shown is m:
- `due` = the first month ≥ m that falls in month D. `left` = months from m to `due`, inclusive (1 to 12).
- `start` = the balance at the **start** of m, before this month's assigning and spending (`V − A − activity`). Non-repeating by-month targets use `V − A`. The difference means paying the bill in its due month doesn't make the category look underfunded again.
- `share = ceil((T − start) / left)`, and it needs `max(0, share − A)`.
- Examples:
  - Dropbox £120 due in March, viewed in April with £0: due next March, 12 months left, needs £10.
  - Viewed in March with £110 carried in: needs £10.
  - In March, after paying £120: `start` is still £110 and A = £10, so it needs £0.
  - Viewed in April after paying: the balance is £0, so it needs £10 again (12 months to the next March).
- **Known edge:** if the bill is paid a month early (posted in February for a March renewal), March's `start` drops and March shows the whole amount as needed. That's acceptable; fix it only if it bites.

The tick when the category already has a different target: the form says it will be replaced.

## Implementation Plan

### Phase 1
- [x] Pure date-recurrence function (next occurrence after a date) with thorough unit tests
- [x] Migration and model

### Phase 2
- [x] Idempotent materialisation (e.g. row lock on the schedule, or a unique key on schedule + occurrence date)
- [x] CRUD UI and upcoming list

---

## Work Completed

2026-11-11 (branch `TASK-M002`):
- **Migration `0010`:**
  - The `scheduled_transactions` table.
  - `transactions.schedule_id` and `scheduled_for`, unique together (`uq_transactions_schedule_occurrence`).
  - `targets.repeats`.
- **Dates:** `schedules.following()` and `occurrences()`, tested in `tests/test_schedule_dates.py`. The units are `once`, `week`, `month` and `year`, each × `interval`.
- **Shared code:** `entry.py` now holds the transaction form's checks and save (`validate_transaction`, `save_transaction`), moved out of `routers/transactions.py` so schedules enter rows the same way.
- **Entering:**
  - `schedules.enter_due()` runs from `deps.current_user` on every authenticated request.
  - Each schedule gets a `FOR UPDATE` lock and a savepoint. Dates already entered are passed over; the unique key catches only a true race (tested on PostgreSQL with two sessions).
  - Paused schedules (closed account) stay due.
  - The notice uses the session key `scheduled_entered`. It's shown by `templating.render` on the next full page.
- **Scheduled page:** `routers/scheduled.py`, `scheduled.html`, `scheduled_edit.html` and `_schedule_fields.html`. "Enter now" dates the row today, with `scheduled_for` set to the due date. There's a "Scheduled" link in the top bar.
- **Upcoming:** on the transactions page, the next 30 days (`schedules.upcoming()`), filtered to the account when the list is.
- **Categories and accounts:** `category_in_use()` counts schedules, and `merge_category()` moves them. Deleting an account deletes its schedules (either side), through `delete_schedule()`, which clears `schedule_id` on rows already entered.
- **Annual bills:**
  - `budget.target_due()`, and `underfunded(..., repeats=, activity=)`. Tested in `tests/test_target_maths.py`.
  - The target form has "Repeat every year". The budget shows "by Mar 2027 (every year)".
  - On yearly schedules, the "Save up" tick calls `schedules.apply_save_up()` on save.
- **Tests:** `tests/test_schedules.py`, plus the `0010` test in `tests/test_migrations.py`.

Bug found in Claude's own review before testing: editing a schedule's next date back past rows it had already entered would have hit the unique key on every request, so the schedule would never move on. Fixed by passing over dates already entered, with a test.

2026-11-13: Carel tested on CT 161 (iPad); all five steps were checked in the database.
1. Monthly Phone Bill from 1 Sep caught up 3 rows (uncleared, linked by date).
2. Weekly Coffee: Upcoming listed it; Enter now ×3 dated today with the right `scheduled_for`; Skip on Phone Bill moved Dec → Jan with no row.
3. Yearly Dropbox £119.88 with Save up: target `by_date`, `repeats`, Mar 2027. November needs £23.98 (5 months); December £29.97 (4 months, November unfunded, as designed). Editing the next date moved the target date with it.
4. Save up on a monthly schedule is refused with the message.
5. Deleting Phone Bill kept its 3 rows, unlinked.

Found while testing: a new schedule's date defaults to today, and today counts as due, so saving enters it at once (a stray Dropbox row this way, deleted by Carel). Works as agreed; a possible small follow-up.

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [x] Recurrence: monthly on 31st across Feb in leap and non-leap years; weekly across year end
- [x] Catch-up after 3 missed months
- [x] Schedule for a closed account (TASK-H004): pause, don't enter
- [x] Scheduled transfer creates both legs (if TASK-H002 is done)

---

## Known Issues & Gotchas

- [x] "Today" depends on timezone; the server's date may differ from the user's. Decide on server-local date for now and note it.

---

## Related Tasks

- **Depends On**: TASK-C001
- **Blocks**: None
- **Related**: TASK-H002, TASK-H004, TASK-H006

---

*Last Updated: 2026-11-13 by Claude*
