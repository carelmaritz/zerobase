# TASK-M007: Investment accounts (crypto, pension, Stocks & Shares ISA)

**Status**: IN_PROGRESS
**Priority**: M - Medium
**Effort**: M - 3-5 days
**Assigned**: Claude
**Created**: 2026-11-13
**Started**: 2026-11-13
**Completed**:
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
- **Accounts page:** Crypto shows as "Coinbase · 0.25 BTC". The add form hides the "Budget account" tick for the investment types, and shows Coin and Amount only for Crypto (CSS `:has()`, as the target form does).

---

## Technical Requirements

### Success Criteria
- [ ] The three types can be added; they are always tracking accounts, whatever the form sends.
- [ ] A Crypto account stores its symbol (capitals) and exact amount held; bad symbols or amounts are refused with a message.
- [ ] "Update value" on a tracking account adds one "Market value change" row for the difference; none when unchanged; never on a budget account.
- [ ] A budget account can't be switched to an investment type.
- [ ] Ready to Assign and every category are unchanged by value updates (test).
- [ ] Migration `0011` adds `accounts.symbol` and `accounts.quantity`; the migration test covers it.
- [ ] Tested on SQLite and PostgreSQL; ruff clean.

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
- [ ] Constants for the new kinds in `models.py`; `Account.symbol`, `Account.quantity`; migration `0011`.
- [ ] Parsing and checks for symbol and amount, with unit tests.

### Phase 2: routes and pages
- [ ] Add and edit forms: forced off-budget, refusals, symbol and amount for Crypto.
- [ ] `GET`/`POST /accounts/{id}/value` and its page; the link on tracking accounts.
- [ ] Accounts page shows the coin and amount.
- [ ] Tests, both databases; deploy to CT 161 for Carel to test.

---

## Work Completed

2026-11-13 (branch `TASK-M007`):
- **Model and migration `0011`:** `CRYPTO`, `PENSION`, `ISA_STOCKS`, `INVESTMENT_KINDS` and the `ExactDecimal` type in `models.py`; `Account.symbol`, `Account.quantity`, and the `quantity_text` and `holding` properties.
- **Parsing:** `investments.py` (`parse_symbol`, `parse_quantity`).
- **Accounts (`routers/accounts.py`):** the new kinds; investments forced off budget on add; a budget account can't be switched to an investment kind (refused, and not offered); the coin fields are saved only for Crypto and cleared when it stops being Crypto.
- **Update value:** `routers/valuation.py`, `account_value.html`. The difference from the balance **on the chosen date** becomes one cleared "Market value change" row with no category. The account row is locked (`FOR UPDATE`) while it's worked out. 404 on budget and closed accounts.
- **Pages:** the Accounts list shows "· 0.25 BTC" and an "Update value" link on tracking accounts; the add and edit forms show the coin fields only for Crypto, and the add form hides the budget tick for investments (CSS `:has()`).
- **Tests:** `tests/test_investments.py` (parsing, forced tracking, refusals, value updates, Ready to Assign unchanged, another user gets 404, contributions as transfers), and the `0011` migration test. 353 pass on SQLite (1 skipped), 354 on PostgreSQL.

---

## Failed Approaches

None yet.

---

## Related Tasks

- **Depends On**: TASK-H004
- **Related**: TASK-M003 (net worth), TASK-M006 (reconciliation adjustments work the same way)

---

*Last Updated: 2026-11-13 by Claude*
