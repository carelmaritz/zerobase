# TASK-H000: Initial scaffold

**Status**: DONE
**Priority**: H - High
**Effort**: M - 3-5 days
**Assigned**: Claude
**Created**: 2026-10-19
**Started**: 2026-10-19
**Completed**: 2026-10-19
**Branch**: main (commit `feb28db`)
**Dependencies**: None

---

## Objective

Stand up a working, self-hostable zero-based budgeting app with the core loop: accounts, income into Ready to Assign, monthly assignment to categories, spending, rollover and overspending.

---

## Background

Zerobase is a personal, open-source take on the YNAB method, run on your own hardware with data in your own PostgreSQL. This task records what the first commit delivered so later tasks have a baseline.

---

## Technical Requirements

### Success Criteria
- [x] Sign-up and sign-in; first account always allowed, further sign-ups only if `ZEROBASE_ALLOW_REGISTRATION=true`
- [x] Budget and tracking accounts with optional opening balance
- [x] Monthly budget view with category groups, inline (htmx) assignment, rollover and overspending
- [x] Transactions with payee, memo and category; change category after the fact; delete
- [x] Multiple users per install, fully isolated data
- [x] Docker Compose deployment with optional Caddy HTTPS proxy and a backup script
- [x] CI running ruff and pytest on SQLite and PostgreSQL, plus a Docker build

### Out of Scope

Everything on the README roadmap: editing transactions, transfers, credit cards, CSV import, category/account management, migrations, goals, scheduled transactions, reports, trusted-proxy support.

---

## Freedom

N/A (complete).

---

## Work Completed

### Files Created/Modified
- `src/zerobase/budget.py` - Envelope maths: `build_budget`, rollover, overspending, Ready to Assign
- `src/zerobase/money.py` - Parse and format amounts as integer pence
- `src/zerobase/models.py` - Users, accounts, category groups, categories, transactions, assignments
- `src/zerobase/routers/` - auth, budget, accounts, transactions
- `src/zerobase/security.py` - Argon2 hashing, in-memory login throttle
- `src/zerobase/main.py` - App factory, session middleware, same-origin check, security headers, `/healthz`
- `src/zerobase/templates/`, `static/` - Server-rendered pages, vendored htmx
- `tests/` - Unit tests for maths and money, end-to-end web tests
- `Dockerfile`, `docker-compose.yml`, `Caddyfile`, `scripts/backup.sh`, `.github/workflows/ci.yml`

### Key Decisions Made
- Money as signed integer minor units, never floats.
- Budget figures computed on read, not stored, so there is no derived state to drift.
- Overspending resets the envelope to zero next month and reduces Ready to Assign (YNAB's cash-overspending rule).
- Income is identified by convention (on-budget, no category, positive amount) rather than an explicit "Ready to Assign" category.
- Schema created with `create_all`; migrations deferred (now TASK-C001).

### Implementation Summary
See the README "How it works" and "Stack" sections.

---

## Failed Approaches

None recorded.

---

## Testing

`pytest` (SQLite) and `pytest` with `ZEROBASE_TEST_DATABASE_URL` set (PostgreSQL). Both run in CI.

---

## Next Steps

- [ ] Migrations before any schema change (TASK-C001)
- [ ] Roadmap tasks TASK-H001 to TASK-M006

---

*Last Updated: 2026-10-21 by Claude*
