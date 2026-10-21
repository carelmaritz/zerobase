# TASK-H006: CSV import

**Status**: TODO
**Priority**: H - High
**Effort**: L - 1-2 weeks
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**:
**Completed**:
**Branch**: TASK-H006
**Dependencies**: TASK-C001

---

## Objective

Import transactions from a bank's CSV export into an account, with column mapping, a preview, and duplicate detection so re-importing an overlapping statement doesn't double-count.

---

## Background

Manual entry is the only way to record transactions today. Every UK bank offers CSV export, and the column layouts differ (single signed amount vs separate money-in/money-out columns, `DD/MM/YYYY` vs ISO dates, header rows, trailing balance columns).

---

## Technical Requirements

- Upload a CSV (size limit, e.g. 2 MB) for a chosen account.
- **Mapping step**: pick which column is date, payee, memo, and either amount (signed) or outflow + inflow; pick date format; option to flip the sign; skip header rows. Remember the mapping per account (schema) for next time.
- **Preview step**: show parsed rows, highlight errors and likely duplicates, let the user untick rows. Nothing is written until confirmed.
- **Duplicate detection**: an `import_id` on transactions (schema), derived from account + date + amount + occurrence count of that combination within the file (YNAB's approach), unique per account. Also flag likely matches against manually entered transactions (same account, amount, date within a few days).
- Imported transactions are uncategorised unless a later payee-rule feature assigns them; they appear in the existing uncategorised warning.
- Amounts parsed with `money.parse_money` (pence, never floats). Handle UTF-8 with BOM and common encodings.
- Use the stdlib `csv` module; no new dependency expected.

### Success Criteria
- [ ] Import a file with a signed amount column and one with separate in/out columns
- [ ] Re-importing the same file adds nothing; importing an overlapping file adds only new rows
- [ ] Two identical real transactions on the same day (e.g. two £3 coffees) are both imported
- [ ] Bad rows reported in preview, not silently dropped
- [ ] Mapping remembered per account
- [ ] Migration up/down tested

### Out of Scope

- OFX/QFX/QIF formats (possible follow-up).
- Direct bank connections / open banking.
- Payee rename and auto-categorisation rules (possible follow-up).
- Matching imported rows to scheduled transactions (TASK-M002) or transfers (TASK-H002).

---

## Freedom

**Free to decide**: Where preview state lives between steps (re-upload, hidden form field, or a short-lived server-side store), UI layout.

**Ask first**: Any new dependency (e.g. a charset-detection library), storing uploaded files on disk.

---

## Implementation Plan

### Phase 1: Parsing core
- [ ] Pure parsing module: CSV text + mapping -> list of parsed rows or row errors; unit tests with fixtures from several real bank formats (anonymised)
- [ ] `import_id` generation and duplicate detection, unit-tested

### Phase 2: Schema and flow
- [ ] Migration: `transactions.import_id` (unique per account), saved mappings per account
- [ ] Upload, map, preview, confirm routes and templates

### Phase 3: Tests
- [ ] End-to-end import, re-import, overlap

---

## Work Completed

*Fill when IN_PROGRESS or DONE.*

---

## Failed Approaches

None yet.

---

## Testing

### Test Cases
- [ ] UK date format `31/01/2026`, ISO, and ambiguous `01/02/2026` with explicit format choice
- [ ] Amount formats: `-12.34`, `12.34 DR`, `"1,234.56"`, separate in/out columns with blanks
- [ ] UTF-8 BOM header
- [ ] Empty file, header only, wrong column count rows
- [ ] File over the size limit rejected

---

## Security Considerations

- Enforce upload size limit before reading the whole body into memory.
- Treat file content as untrusted: escape everything in the preview (Jinja autoescape covers this; don't mark anything `|safe`).
- The account ID in the form must be ownership-checked.

---

## Known Issues & Gotchas

- [ ] Banks change export layouts; saved mappings may stop matching. Detect a header mismatch and send the user back to mapping.
- [ ] Some banks export pending transactions that later change amount or date; duplicate detection by import_id will treat them as new.

---

## Related Tasks

- **Depends On**: TASK-C001
- **Blocks**: None
- **Related**: TASK-H001, TASK-H002, TASK-M002, TASK-M006, TASK-L002

---

*Last Updated: 2026-10-21 by Claude*
