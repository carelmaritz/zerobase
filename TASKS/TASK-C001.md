# TASK-C001: Database migrations (Alembic)

**Status**: IN_PROGRESS
**Priority**: C - Critical
**Effort**: M - 3-5 days
**Assigned**: Claude
**Created**: 2026-10-21
**Started**: 2026-10-21
**Completed**:
**Branch**: TASK-C001
**Dependencies**: None

---

## Objective

Introduce versioned schema migrations with Alembic so that an existing install can be upgraded in place without losing data, and so every later schema change ships as a reviewed migration.

---

## Background

`main.py` calls `Base.metadata.create_all(engine)` on startup. That creates missing tables but never alters existing ones, so the first column added to any table will break or silently diverge on existing installs. The README warns users not to rely on in-place upgrades until this lands.

Almost every roadmap feature needs a schema change (transfer links, hidden/closed flags, import IDs, targets, schedules, cleared status), so this task blocks TASK-H002 to TASK-H006, TASK-M001, TASK-M002 and TASK-M006.

---

## Technical Requirements

- Alembic added as a runtime dependency; migration scripts packaged inside `src/zerobase/` so they ship in the Docker image (`pip install .` only installs the package).
- A baseline revision that reproduces the current schema exactly.
- A constraint **naming convention** on `Base.metadata` (`ix`, `uq`, `ck`, `fk`, `pk`), set before the baseline is generated. Unnamed constraints are painful to alter later, especially on SQLite.
- `render_as_batch=True` so ALTERs work on SQLite (dev and tests).
- The app upgrades the database to head on startup, replacing `create_all`. Must be safe if two processes start at once (Postgres advisory lock, or document single-instance only).
- No pre-migration installs exist (decision 2026-10-21, see Key Decisions). If the app finds application tables but no `alembic_version`, it refuses to start with a clear message explaining dump/restore, rather than stamping or touching the data.
- The database URL comes from `Settings`, not a hard-coded `alembic.ini` value.

### Success Criteria
- [ ] Fresh database: app starts, tables are created via migrations, `alembic_version` is at head.
- [ ] Database with app tables but no `alembic_version`: app refuses to start with a clear message, data untouched.
- [ ] A test asserts migrations at head match the models (`alembic check` or `compare_metadata`) on SQLite and PostgreSQL in CI.
- [ ] A test runs upgrade to head then downgrade to base on an empty database.
- [ ] README: in-place upgrade warning removed; "how to add a migration" added to Development; backup-before-upgrade advice added.

### Out of Scope

- Any actual schema change beyond the naming convention (each feature task brings its own migration).
- Changing test fixtures away from `create_all` for speed, unless trivial. Unit tests may keep using `create_all`; the drift test above guards correctness.
- Automatic pre-migration backups.

---

## Freedom

**Free to decide**: Directory layout for migrations, whether upgrade runs in the lifespan hook or a small entrypoint step, test structure.

**Ask first**: Adding any dependency other than Alembic, anything that drops or rewrites existing data.

---

## Implementation Plan

### Phase 1: Set up
- [ ] Add `alembic` to dependencies; `alembic init` inside the package; wire `env.py` to `Base.metadata` and `Settings.database_url`
- [ ] Add naming convention to `Base` in `db.py`
- [ ] Autogenerate baseline; review it by hand against `models.py`

### Phase 2: Startup
- [ ] Replace `create_all` in `lifespan` with upgrade-to-head
- [ ] Refuse to start on a pre-Alembic database (tables but no `alembic_version`)
- [ ] Concurrency guard or documented single-instance assumption

### Phase 3: Tests, CI, docs
- [ ] Drift test and up/down test, both backends
- [ ] README updates
- [ ] Manually: fresh Docker deployment reaches head; restart is a no-op

---

## Work Completed

*Fill when IN_PROGRESS or DONE.*

### Key Decisions Made
- 2026-10-21: No existing installs with data (first deployment is still to come), so constraint-naming option (c) chosen: the naming convention applies from the baseline, and pre-Alembic databases are refused rather than stamped. Decided with the user.

---

## Failed Approaches

None yet.

---

## Testing

### Test Strategy
Automated drift and up/down tests on both backends in CI, plus a manual upgrade of a real database populated by the current scaffold.

### Test Cases
- [ ] Fresh SQLite and PostgreSQL databases reach head
- [ ] Database with app tables but no `alembic_version` is refused, row counts unchanged
- [ ] Models and migrations agree (no autogenerate diff)
- [ ] Downgrade to base succeeds

---

## Installation/Deployment

**Deployment Steps**:
1. Run `./scripts/backup.sh`
2. `docker compose up -d --build`
3. Check logs for the migration message

**Verification**:
- [ ] `/healthz` returns ok; `SELECT version_num FROM alembic_version` shows head

---

## Known Issues & Gotchas

- [x] Constraint names: databases created by `create_all` would have database-default names (e.g. `accounts_user_id_fkey`) that differ from the convention. Resolved: no such installs exist; option (c) chosen (see Key Decisions).
- [ ] SQLite cannot ALTER most things; batch mode recreates tables. Fine for tests and dev, but keep migrations simple.
- [ ] `func.extract` and boolean handling already differ between SQLite and Postgres; run the drift test on both.

---

## Rollback Plan

**Steps**:
1. Restore the pre-upgrade backup (`gunzip -c backups/<file>.sql.gz | docker compose exec -T db psql -U zerobase zerobase`)
2. Deploy the previous image

**Validation**:
- App starts and budget figures match those before the upgrade

---

## Related Tasks

- **Depends On**: None
- **Blocks**: TASK-H002, TASK-H003, TASK-H004, TASK-H005, TASK-H006, TASK-M001, TASK-M002, TASK-M006
- **Related**: TASK-H000

---

## References

- Alembic: https://alembic.sqlalchemy.org/
- SQLAlchemy constraint naming conventions: https://docs.sqlalchemy.org/en/20/core/constraints.html#constraint-naming-conventions

---

*Last Updated: 2026-10-21 by Claude*
