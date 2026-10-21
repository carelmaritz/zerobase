# TASK-H007: Explicit "Inflow: Ready to Assign" category

**Status**: DONE
**Priority**: H - High
**Effort**: S - 1-2 days
**Assigned**: Claude
**Created**: 2026-10-21
**Started**: 2026-10-21
**Completed**: 2026-10-21
**Branch**: TASK-H007
**Dependencies**: TASK-C001

---

## Objective

Mark income explicitly with a built-in "Inflow: Ready to Assign" category, as YNAB does, instead of treating every uncategorised positive transaction as income.

---

## Background

Today `build_budget` treats an on-budget transaction with **no category and a positive amount** as income. That causes problems that get worse with each core feature:

- A refund or reimbursement entered without a category silently becomes income. Uncategorised outflows get a warning; uncategorised inflows can't, because they are indistinguishable from income.
- **Transfers (TASK-H002)**: the inflow leg of a budget-to-budget transfer has no category, so it would count as income.
- **CSV import (TASK-H006)**: imported rows arrive uncategorised, so every imported inflow would hit Ready to Assign before review.
- Negative income (salary correction, an account opened while overdrawn) can't be recorded: it shows up as an uncategorised outflow.

Decision (2026-10-21, with the user): option B, an explicit inflow category, done as its own task before TASK-H002. Alternative considered: an `is_income` flag or `kind` column on transactions. Rejected because two fields would then decide where money goes.

---

## Technical Requirements

- Schema (migration 0002): `categories.kind` (`standard` default, `inflow`), and `categories.group_id` nullable. The inflow category has no group.
- Every user has exactly one inflow category: created at registration, created for existing users by the migration, and fetched with a get-or-create helper so code never assumes it exists.
- Migration backfills: existing on-budget transactions with no category and a positive amount move to the user's inflow category, so Ready to Assign is unchanged for existing data. Downgrade reverses it.
- `build_budget`: income = on-budget transactions in the inflow category, **any sign**. A blank category means uncategorised, flagged for **inflows and outflows**, and not counted anywhere.
- The inflow category never appears in the budget grid and cannot have money assigned to it.
- Transaction form and the inline category picker offer "Inflow: Ready to Assign" at the top. Opening balances of budget accounts go into it automatically (either sign).

### Success Criteria
- [x] Income in the inflow category reaches Ready to Assign; an uncategorised inflow does not, and is flagged
- [x] A negative inflow reduces Ready to Assign
- [x] Inflow category hidden from the budget grid; assigning to it is refused
- [x] New users get the category; opening balances use it
- [x] Migration backfills existing income, leaves Ready to Assign unchanged, and downgrades cleanly; tested on SQLite and PostgreSQL

### Out of Scope

- Renaming, hiding or deleting categories in general (TASK-H003, which must protect the inflow category).
- Credit card payment categories (TASK-H005), though `kind` leaves room for them.
- Transfers (TASK-H002).

---

## Freedom

**Free to decide**: Helper and column names, how the uncategorised warning is worded, where the option sits in the picker.

**Ask first**: Letting users rename the inflow category, or having more than one.

---

## Implementation Plan

### Phase 1: Model and maths
- [x] Model changes and migration 0002 with backfill
- [x] Get-or-create helper; seed at registration
- [x] `build_budget` income and uncategorised changes

### Phase 2: Web
- [x] Picker option, opening balances, refuse assignment to inflow, form hint, uncategorised warning wording
- [x] README: how to record income

### Phase 3: Tests
- [x] Budget unit tests, web tests, migration backfill test

---

## Work Completed

- `models.py`: `Category.kind` (`standard`/`inflow`, server default `standard`), `group_id` nullable, `is_inflow` property.
- `migrations/versions/0002_inflow_category.py`: adds the column, makes `group_id` nullable (batch mode for SQLite), inserts a "Ready to Assign" inflow category per user, moves on-budget uncategorised positive transactions into it. Downgrade reverses all of it.
- `budget.py`: `inflow_category()` get-or-create helper, called from `seed_default_categories`. `build_budget` splits per-category totals into income (inflow category, any sign) and activity; uncategorised now counts both directions and reports outflow and inflow totals separately (`uncategorised_outflow`, `uncategorised_inflow` replace `uncategorised_total`). The inflow category is left out of the grid.
- Routes: budget-account opening balances go into the inflow category; `/budget/assign` returns 404 for it; the transactions page passes it to the picker (committing in case the helper had to create it).
- Templates: "Inflow: Ready to Assign" option second in every category picker; new form hint; uncategorised warning now says "N uncategorised transactions (£x out, £y in) not counted in your budget yet".
- Tests: 4 new or rewritten budget tests, 1 web test (registration, three kinds of opening balance, picker, uncategorised inflow, refused assignment), 1 migration test (backfill across two users, outflow, categorised refund, tracking account; then downgrade). 49 pass on SQLite and PostgreSQL 16.

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [x] Income, uncategorised inflow, negative inflow, uncategorised outflow
- [x] Assign to inflow category returns 404
- [x] Opening balance on budget account (positive and negative) lands in Ready to Assign; on a tracking account it has no category
- [x] Migration from 0001 with existing data: income moved, outflows and tracking rows untouched; downgrade restores NULLs

---

## Installation/Deployment

The app upgrades the database on start. The test deployment (CT 161) has demo data, which the migration converts. Back up first as usual.

---

## Known Issues & Gotchas

- [ ] `transactions.category_id` is `ON DELETE SET NULL`: if the inflow category were ever deleted, all income would become uncategorised. Nothing can delete categories today; TASK-H003 must refuse it.
- [ ] Downgrade turns negative inflows into uncategorised outflows, which is how the old model sees them anyway.

---

## Rollback Plan

Downgrade to 0001 (`alembic downgrade 0001`) and deploy the previous image. Income rows go back to having no category.

---

## Related Tasks

- **Depends On**: TASK-C001
- **Blocks**: TASK-H002
- **Related**: TASK-H003, TASK-H005, TASK-H006, TASK-M006

---

*Last Updated: 2026-10-21 by Claude*
