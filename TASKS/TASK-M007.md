# TASK-M007: Investment accounts (crypto, pension, Stocks & Shares ISA)

**Status**: DONE
**Priority**: M - Medium
**Effort**: M - 3-5 days
**Assigned**: Claude
**Created**: 2026-11-13
**Started**: 2026-11-13
**Completed**: 2026-11-18
**Branch**: TASK-M007
**Dependencies**: TASK-H004 (manage accounts)

---

## Objective

Let Carel track crypto, pensions (Vanguard funds) and Stocks & Shares ISAs, whose value changes without any spending, without disturbing the budget.

---

## Background

The account types today are Current account, Savings, Cash, Other and Credit card. Only Credit card behaves differently; the rest are labels, and "Budget account" is a separate tick fixed at creation. A tracking account's balance can only move by transactions, so a market move can't be recorded except as a made-up transaction.

---

## Agreed with Carel (2026-11-13)

1. **New types:** Crypto, Pension, Stocks & Shares ISA. (Cash ISA not wanted; Savings covers it.)
2. **Always off budget:** the app forces these three to be tracking accounts, so a market move never reaches Ready to Assign. Paying in is a transfer from a budget account, which shows as budget spending in the chosen category, as today.
3. **Value only:** an "Update value" action takes today's value and records the difference as a gain or loss. No holdings, no automatic prices (a later task could add them).
4. **Crypto: one account per coin**, with the coin's trading symbol (BTC, XRP, SOL) and the **amount held** (e.g. 0.25).

## Claude's calls (kept by Carel, 2026-11-13)

- **Keys stored:** `crypto`, `pension`, `isa_stocks`. Shown as "Crypto", "Pension", "Stocks & Shares ISA".
- **Coin symbol:** 1–10 letters or digits, saved in capitals. Optional, so an account can be added before the coin is known.
- **Amount held:** exact, up to 18 decimal places (ETH goes to 18), never rounded, not negative. Optional. Stored as decimal **text** (`ExactDecimal`, `String(48)`), not `NUMERIC`: SQLite has no decimal type and SQLAlchemy would round it through a float there.
- **Update value** is offered on **every tracking account** (also handy for a mortgage or a house), not on budget accounts, where it would invent income.
  - The form takes the new value in £ and a date (today by default); on a Crypto account it also takes the amount held.
  - It adds one cleared transaction, payee **"Market value change"**, no category, for the difference. No difference, no row (the amount held is still saved).
  - The difference is worked out afresh on every post, so pressing Save twice adds it once.
- **Changing type later:**
  - A budget account can't become an investment type (it would have to leave the budget, which would rewrite history). Refused with a message.
  - A tracking account can switch freely among the non-card types.
  - Moving away from Crypto clears the symbol and amount.
- **Accounts page:** Crypto shows as "Coinbase · 0.25 BTC". The Coin and Amount held boxes are always on the add and edit forms, labelled "(Crypto only)" and ignored for other types (changed after iPad testing; see Failed Approaches).

---

## Technical Requirements

### Success Criteria
- [x] The three types can be added; they are always tracking accounts, whatever the form sends.
- [x] A Crypto account stores its symbol (capitals) and exact amount held; bad symbols or amounts are refused with a message.
- [x] "Update value" on a tracking account adds one "Market value change" row for the difference; none when unchanged; never on a budget account.
- [x] A budget account can't be switched to an investment type.
- [x] Ready to Assign and every category are unchanged by value updates (test).
- [x] Migration `0011` adds `accounts.symbol` and `accounts.quantity`; the migration test covers it.
- [x] Tested on SQLite and PostgreSQL; ruff clean.

### Out of Scope
- Holdings (several funds or coins in one account), unit prices, automatic price lookups.
- Net worth and asset/liability grouping (TASK-M003).
- Fund codes for Vanguard funds (a later price task could add them).

---

## Freedom

**Free to decide**: names, layout, wording, test structure.

**Ask first**: new dependencies, any outside network call, changes to how budget accounts work.

---

## Implementation Plan

### Phase 1: data
- [x] Constants for the new kinds in `models.py`; `Account.symbol`, `Account.quantity`; migration `0011`.
- [x] Parsing and checks for symbol and amount, with unit tests.

### Phase 2: routes and pages
- [x] Add and edit forms: forced off-budget, refusals, symbol and amount for Crypto.
- [x] `GET`/`POST /accounts/{id}/value` and its page; the link on tracking accounts.
- [x] Accounts page shows the coin and amount.
- [x] Tests, both databases; deploy to CT 161 for Carel to test.

---

## Work Completed

2026-11-13 (branch `TASK-M007`):
- **Model and migration `0011`:** `CRYPTO`, `PENSION`, `ISA_STOCKS`, `INVESTMENT_KINDS` and the `ExactDecimal` type in `models.py`; `Account.symbol`, `Account.quantity`, and the `quantity_text` and `holding` properties.
- **Parsing:** `investments.py` (`parse_symbol`, `parse_quantity`).
- **Accounts (`routers/accounts.py`):** the new kinds; investments forced off budget on add; a budget account can't be switched to an investment kind (refused, and not offered); the coin fields are saved only for Crypto and cleared when it stops being Crypto.
- **Update value:** `routers/valuation.py`, `account_value.html`. The difference from the balance **on the chosen date** becomes one cleared "Market value change" row with no category. The account row is locked (`FOR UPDATE`) while it's worked out. 404 on budget and closed accounts.
- **Pages:** the Accounts list shows "· 0.25 BTC" and an "Update value" link on tracking accounts; the add and edit forms show the coin fields only for Crypto, and the add form hides the budget tick for investments (CSS `:has()`).
- **Tests:** `tests/test_investments.py` (parsing, forced tracking, refusals, value updates, Ready to Assign unchanged, another user gets 404, contributions as transfers), and the `0011` migration test. 353 pass on SQLite (1 skipped), 354 on PostgreSQL.

2026-11-17/18: Carel tested on CT 161; every step was checked in the database.
1. Crypto add: from the iPad, Coinbase BTC (account 7) saved with no coin or amount; from the laptop, Solana (8) saved `SOL` / `100`. Coinbase BTC's coin was then set via Manage.
2. Update value on Coinbase BTC to £16,000: one cleared +£1,000 "Market value change" row (226), no category; the same value again added no row but saved the amount held (0.3).
3. Pension HL (9): £50,000 opening (227), Update value to £49,000 gave −£1,000 (228); no amount field.
4. Current account's Type list offers no investment types.
5. No "Update value" on budget accounts.
Ready to Assign was unchanged by M007 (same figures from the pre-M007 backup: Oct £1,293.30, Nov £5.00, Dec −£15.00; the drift since M001 is the M002 Phone Bill test rows overspending Phone & Internet).

After testing: the coin boxes are always shown, labelled "(Crypto only)", and the option-driven `:has()` rules were removed (Carel's choice), with a test. 354 pass on SQLite (1 skipped), 355 on PostgreSQL.

---

## Failed Approaches

- **Showing or hiding form parts by the `<select>`'s chosen option (CSS `:has(option:checked)`):** on Carel's iPad (Safari, then Firefox) the add form saved Coinbase BTC with an empty coin and amount, while the laptop saved them fine. The exact cause wasn't found. Carel chose to always show the boxes, labelled "(Crypto only)", and the budget tick and investment note are no longer hidden either (the server forces investment types off budget anyway). Radio-driven `:has()`, as on the target form, does work on the iPad.

---

## Related Tasks

- **Depends On**: TASK-H004
- **Related**: TASK-M003 (net worth), TASK-M006 (reconciliation adjustments work the same way)

---

*Last Updated: 2026-11-18 by Claude*
