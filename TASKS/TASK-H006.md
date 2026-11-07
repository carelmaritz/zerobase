# TASK-H006: CSV and OFX import

**Status**: IN_PROGRESS
**Priority**: H - High
**Effort**: L - 1-2 weeks
**Assigned**: Claude
**Created**: 2026-10-21
**Started**: 2026-11-07
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

- QIF, unless Carel's bank only offers that; Microsoft Money's own `.mny` files (see the draft plan, decision 7).
- Direct bank connections / open banking.
- Payee rename and auto-categorisation rules (possible follow-up).
- Matching imported rows to scheduled transactions (TASK-M002) or transfers (TASK-H002).

---

## Freedom

**Free to decide**: Where preview state lives between steps (re-upload, hidden form field, or a short-lived server-side store), UI layout.

**Ask first**: Any new dependency (e.g. a charset-detection library), storing uploaded files on disk.

---

## Agreed plan (2026-11-07)

Approved by Carel on 2026-11-07, with OFX (Microsoft Money format) added at Carel's request. Carel will provide a real bank download for the fixtures when the work reaches the parsers; that also settles whether QIF is needed.

### Decisions

1. **Preview state lives in a hidden form field.** The uploaded text is carried in the page through mapping, preview and confirm. Each step parses it again, and confirm validates it again, so a tampered page can only affect the user's own import. Nothing is stored on the server and there's nothing to clean up. **This caps uploads at 1 MB**, because Starlette refuses form fields larger than that. A year of statements is typically well under that (a few hundred bytes per row). The alternative is a short-lived drafts table, which is more code plus expiry.
2. **Likely duplicates of hand-entered transactions are matched, not imported.** A match is a transaction in the same account with no `import_id`, the same amount, and a date up to 3 days away; each one is matched at most once, to the closest date. By default the imported row isn't added. Instead, the existing transaction gets the row's `import_id`, so later imports skip it too. Ticking "import as new" overrides this. (YNAB also matches; the alternative is to only flag the row.)
3. **Credit cards and transfers get no special handling.** Imported rows are uncategorised. A card payment row (an inflow on the card) can't take the payment category. Instead, the user edits it into a transfer from Current, which the edit page already supports. That creates the Current leg with no `import_id`. When Current's statement is imported later, decision 2 matches that leg instead of duplicating it. Automatic transfer matching stays out of scope.
4. **No "undo import".** The preview, with a sign-flip option and totals, is the guard. Batch undo would need an import-batch table; it's a possible follow-up.
5. **Encodings:** UTF-8 (with or without BOM), falling back to Windows-1252, which is how a `£` usually arrives in UK exports. No new dependency.
6. **Test fixtures:** made-up CSV files in common UK layouts:
   - a signed amount column
   - separate paid-in and paid-out columns
   - a `DR`/`CR` suffix
   - `01 Jan 2026` dates
   - a trailing balance column

   They aren't copied from any particular bank. Anonymised real exports from Carel's banks would be better, if available.
7. **Microsoft Money format (added 2026-11-07 at Carel's request):** OFX, which UK banks often label as "Microsoft Money".
   - Both versions are handled: OFX 1.x (SGML) and 2.x (XML), read with a small stdlib parser of the `<STMTTRN>` blocks. No new dependency.
   - There's no mapping step: an OFX file names its own fields.
   - QIF (the older "Quicken/Money" download) is included only if one of Carel's banks offers it rather than OFX.
   - Money's own `.mny` data file is out of scope: it's a proprietary encrypted database.

### Parsing rules

The rules below are for CSV. OFX has its own subsection after them.

- **Mapping:**
  - Columns are chosen by position.
  - Dates use one of `DD/MM/YYYY`, `YYYY-MM-DD`, `MM/DD/YYYY`, `DD-MM-YYYY` or `DD Mon YYYY`. The format is guessed from the file, and the user confirms it.
  - The amount is either one signed column or separate out and in columns. There's an option to flip the sign, and the number of header rows to skip.
- **Amounts:** `12.34 DR` and `(12.34)` are read as negative, and `CR` as positive. Everything then goes through `money.parse_money`.
- **Row errors:** a row with a bad date, a bad amount, a zero amount or the wrong column count is shown in the preview with the reason, and can't be ticked. Blank rows are skipped silently.
- **Text fields:** the payee is cut to 100 characters and the memo to 255, as in the transaction form.
- **`import_id`:** `"{date}:{amount}:{n}"`, where `n` counts the repeats of that date and amount within the file, so two £3 coffees on the same day get `:1` and `:2`. It's unique per account, and re-importing or overlapping files skips IDs that are already present.
- **Account:** it must be owned by the user and open. A tracking account's rows get no category, as with typed entries.

#### OFX

- **Fields:**
  - `DTPOSTED` gives the date, from its first 8 digits.
  - `TRNAMT` is already signed; it goes through `parse_money`.
  - `NAME` (or `PAYEE/NAME`) is the payee and `MEMO` the memo.
  - `FITID` is the bank's own ID for the transaction.
- **`import_id` = `"ofx:{FITID}"`.** A bank's ID is more reliable than date, amount and count, so OFX re-imports are exact.
- **Account number check:** the file's `ACCTID` is saved with the account's import settings. A different number next time is shown as a warning in the preview, in case the wrong account was chosen.
- **Mixing formats in one account:** CSV and OFX IDs never match each other. The likely-match rule (decision 2) therefore also covers transactions imported in the *other* format, so switching formats flags overlaps instead of doubling them.
- **Detection:** the extension (`.ofx`, `.qfx`, `.csv`) or the content (`OFXHEADER:` or `<OFX>`) decides the parser.

### Schema (migration `0007`)

- `transactions.import_id`: nullable string, `UniqueConstraint(account_id, import_id)`. Both PostgreSQL and SQLite allow many NULLs.
- `import_mappings`: `account_id` unique (FK → accounts, CASCADE), `user_id`, the `settings` as JSON text, and the header row (CSV) or `ACCTID` (OFX) seen last. A different header next time sends the user back to the mapping step. Deleting an empty account also deletes its mapping in code, because SQLite doesn't enforce the cascade here.

### Flow

1. **`GET /accounts/{id}/import`:** the upload form, linked from the account's page.
2. **`POST /accounts/{id}/import`:** checks `Content-Length` and reads at most 1 MB + 1 byte, then decodes the file.
   - If the header matches the saved mapping, it goes straight to the preview; otherwise to the mapping form, guessed from the header.
3. **`POST /accounts/{id}/import/preview`:** shows the rows with their status: new, already imported, likely match (with the existing transaction shown), or error. It also shows totals in and out and the date range.
4. **`POST /accounts/{id}/import/confirm`:**
   - Parses and checks for duplicates again, then inserts the ticked rows and stamps the matches, all in one commit.
   - Saves the mapping.
   - Redirects to the account's transactions, with "Imported N, matched M, skipped K already imported".

### Steps, each with its completion test

1. **Parser (pure module `importer.py`):** CSV text plus a mapping gives parsed rows or row errors, and the date format guess. Done when unit tests cover every case in "Test Cases" below.
1b. **OFX parser** (same module): OFX text gives the same parsed rows, plus the account number. Done when unit tests pass on 1.x SGML (unclosed tags) and 2.x XML samples, a Windows-1252 file, and a file with no transactions.
2. **Duplicate and match logic (pure):** IDs, skipping existing IDs, and the manual-match rule. Done when unit tests cover re-import, overlap, the two-coffees case and closest-date matching.
3. **Migration `0007`:** done when up/down and the drift test pass on SQLite and PostgreSQL.
4. **Routes and templates (plain UI):** done when web tests cover:
   - an import with each amount layout, and an OFX import
   - an OFX re-import adds nothing, and an account-number mismatch warns
   - re-import adds nothing
   - an overlapping file adds only the new rows
   - a saved mapping is reused
   - a changed header goes back to mapping
   - the size limit
   - a foreign account (404) and a closed account
5. **Bookkeeping and deploy:** tests pass on PostgreSQL; update the task file, `TASKS.md` and README. Back up CT 161, deploy, and have Carel import a real statement, with the database checked afterwards.

### Out of scope (beyond the list above)

- Undoing an import.
- Payee rules and auto-categorisation.
- Matching transfers automatically.
- QIF, unless Carel's bank only offers that (decision 7).
- Microsoft Money's own `.mny` files.
- Uploads over 1 MB.

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

- **Steps 1, 1b and 2 done (2026-11-07):** `src/zerobase/importer.py`, a pure module (no database or web), tested by 38 unit tests in `tests/test_importer.py`.
  - **CSV:** `read_csv`, `guess_mapping`, `guess_date_format` and `parse_csv(text, Mapping)`. The delimiter is whichever of `,`, `;` or tab the first line uses most. `Mapping.problem()` says why a mapping can't be used.
  - **OFX:** `parse_ofx` reads 1.x SGML and 2.x XML.
  - **Shared:** `decode` reads UTF-8 (BOM or none), falling back to Windows-1252. `is_ofx` tells the formats apart.
  - **`classify(rows, existing)`** gives each row a verdict: NEW, IMPORTED, MATCH (with the existing transaction's ID) or ERROR.
  - **Fixtures** are still made up. They should be checked against Carel's real download when it arrives.

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

*Last Updated: 2026-11-07 by Claude*
