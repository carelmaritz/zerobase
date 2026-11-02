# TASK-H005: Credit card accounts

**Status**: TODO
**Priority**: H - High
**Effort**: L - 1-2 weeks
**Assigned**: Unassigned
**Created**: 2026-10-21
**Started**:
**Completed**:
**Branch**: TASK-H005
**Dependencies**: TASK-C001, TASK-H002

---

## Objective

Support credit cards the YNAB way: spending on a card from a funded category automatically sets aside money to pay the card, so the card payment is always covered by budgeted money.

---

## Background

A credit card today can only be modelled as a budget account with a negative balance. Spending on it reduces the category as expected, but nothing tracks how much cash is set aside to pay the bill, and paying the card (a transfer) doesn't fit the envelope model.

YNAB's model:
- Each credit card account gets a **Credit Card Payment category** (in a system "Credit Card Payments" group).
- When you spend £30 on the card from Groceries, and Groceries had at least £30 available, £30 moves from Groceries to the card's payment category automatically.
- If Groceries didn't have enough, the unfunded part is **credit overspending**: it becomes new debt (shown differently from cash overspending) and is not deducted from Ready to Assign next month.
- Paying the card is a **transfer** from a budget account to the card; it reduces the payment category's Available.
- Returns/refunds on the card move money back the other way.
- Existing debt when the card is added: the payment category starts underfunded; the user assigns to it to pay down debt.

---

## Technical Requirements

- Account kind `credit_card` (on-budget). Creating one creates its payment category; that category cannot be deleted or renamed independently while the account is open.
- `build_budget` extended: per month, for each card, compute the funded portion of card spending per category and move it into the card's payment category Available. Credit overspending tracked separately from cash overspending (does not reduce Ready to Assign).
- Card payments use the transfer mechanism from TASK-H002, with the payment category as the activity target.
- UI: payment categories shown in their own group; credit overspending visually distinct from cash overspending.

### Success Criteria
- [ ] Spending £30 from a category with ≥£30 available moves £30 to the card's payment category
- [ ] Spending more than available: funded part moves, unfunded part shown as credit overspending, Ready to Assign next month unaffected by it
- [ ] Paying the card from a checking account reduces payment category Available and card debt
- [ ] Refund on the card reverses the movement
- [ ] Starting a card with existing debt shows the payment category needing that amount
- [ ] Unit tests in `test_budget.py` covering each rule across month boundaries

### Out of Scope

- Interest and fees automation.
- Loans/mortgages as debt accounts (YNAB has these separately).
- Statement balances and due dates.
- Importing card statements (TASK-H006 handles CSV in general).

---

## Freedom

**Free to decide**: Internal structure of the computation, UI styling.

**Ask first**: The overall model. A simpler alternative (card as a plain budget account, no automatic payment category) is much less work; confirm the full YNAB model is wanted before starting. Also ask before storing any derived amounts instead of computing on read.

---

## Agreed plan (2026-11-02)

Approved by Carel on 2026-11-02, along with these decisions:
- The full YNAB model.
- Calculated on read; nothing derived is stored.
- Cash spending is funded first when a category is overspent with both kinds.
- When two cards partly drain the same category, the money goes to the cards in account order.
- Starting debt doesn't touch Ready to Assign.
- A negative payment category counts as cash overspending.
- The credit card type is fixed once the account is created.

### The maths

All computed on read in `build_budget`; nothing derived is stored. For each category and month:

- `C` = net non-card activity (cash), `R` = card refunds (cards whose net activity in the category is positive), and `S_c` = net spending on card `c` (cards whose net is negative, as a positive amount).
- `base = carry + assigned + C + R`. This is the money left after cash spending: **cash is funded first**, which is YNAB's documented rule.
- **Funding:** for each spending card, in account order, `funded_c = min(S_c, max(0, remaining))`, where `remaining` starts at `base` and drops by `S_c` each time. `funded_c` moves into card `c`'s payment category. A refund moves `R_c` out of it.
- **Available** = `carry + assigned + C + R − ΣS`. That's the same figure as today, so the category's own line doesn't change.
- If Available < 0 at month end:
  - **cash overspending** = `max(0, −base)`. This reduces Ready to Assign from the next month on, as today.
  - **credit overspending** = the rest. It does **not** touch Ready to Assign; it stays as card debt that isn't set aside.
  - Either way, the category starts the next month at 0.
- Funding works on **month totals**, so date order inside a month doesn't matter. Assigning more later in the same month funds earlier card spending (YNAB's "cover credit overspending"). Topping up in a *later* month doesn't fund it retroactively.
- **Payment category:** Available = carry + assigned + funded moves − refund moves + transfer activity. Each transfer between a budget account and the card adds −`x` to the payment category's activity, where `x` is the card side's amount: a £100 payment is `x = +100` → −100. A card-to-card balance transfer moves the set-aside money with the debt. If it goes negative (paying more than was set aside, or a refund after payment), that is **cash overspending**, as a red payment category is in YNAB.
- **"Needed"** on a payment line = `max(0, debt at month end − Available)`, shown as underfunded.
- **Starting debt:** a card's negative opening balance goes on the card in its own payment category. That transaction is debt, not activity. Ready to Assign is unchanged; the payment category shows the full amount as needed.

### Worked examples (each becomes a unit test)

| # | Setup | Result |
|---|---|---|
| 1 | Oct: Groceries assigned £100; £30 on the card | Groceries £70; Payment £30; card −£30; Ready to Assign unchanged |
| 2 | Oct: Groceries £100; £120 on the card | Groceries −£20 (credit overspending); Payment £100, £20 needed. Nov: Groceries £0, **Ready to Assign not reduced** |
| 3 | Oct: Groceries £50; £40 cash from Current, £30 on the card | base £10 → £10 funded; credit overspending £20; cash overspending £0 |
| 3b | As 3, but £60 cash | base −£10 → cash overspending £10 (Nov Ready to Assign −£10); credit overspending £30 |
| 4 | Example 2, then assign £20 more to Groceries in Oct | Fully funded: Payment £120, Groceries £0 |
| 5 | Example 2, then assign £20 to Groceries in Nov | Groceries £20; Payment still £100, still £20 needed |
| 6 | Example 2; Nov: pay £100 from Current | Payment £0; card −£20; £20 needed |
| 6b | Example 2; Nov: pay £120 | Payment −£20 → cash overspending → Dec Ready to Assign −£20 |
| 7 | Example 1; Nov: £10 refund on the card to Groceries | Groceries +£10; Payment −£10 for the month |
| 8 | New card with −£500 opening | Ready to Assign unchanged; Payment £0, £500 needed; assign £500 then pay £500 → both £0 |
| 9 | Two cards, Groceries £50; £40 on card A, £40 on card B (A has the lower ID) | A funded £40, B £10; credit overspending £30 |

### Schema (migration `0006`)

- `categories.account_id` (nullable, unique, FK → accounts, RESTRICT): set only on payment categories.
- New `categories.kind` value: `card_payment`.
- `category_groups.kind` (`standard` | `card_payments`): one system group per user, created with the first card.
- `credit_card` becomes an account kind. It is always a budget account.

### Steps, each with its completion test

1. **Maths first (riskiest):** split the per-category month loop in `build_budget` into a pure function, then add card funding. Done when examples 1–9 pass as unit tests, and the existing budget tests are unchanged.
2. **Migration `0006`:** done when up/down works and the drift test passes on SQLite and PostgreSQL.
3. **Create a card:** the "Credit card" type on the add form creates the account, its payment category, and the system group if missing. The opening balance becomes starting debt. Done when web tests pass.
4. **`build_budget` wiring:**
   - Card activity is split per card (SQL grouped by category, month and account).
   - Transfer activity goes to payment categories.
   - The view gains `credit_overspent`, `cash_overspent` and `needed`.
   - Done when the success criteria pass as web/budget tests, and 5,000 transactions over 3 years render `/budget` in < 0.5 s locally.
5. **Protection and pickers:**
   - Payment categories and the system group are excluded from the H003 routes and from adding categories.
   - Payment categories can't be chosen as a transaction's category; the server refuses them.
   - Renaming a card renames its payment category.
   - Closing a card hides its payment category, which still counts.
   - Deleting an empty card deletes its payment category, if that has no assignments.
   - The type can't change to or from credit card.
   - Done when each is tested.
6. **UI (plain):**
   - A "Credit Card Payments" group on the budget page.
   - Credit overspending in a different colour from cash overspending.
   - "£X needed" on payment lines.
   - Done when the web tests check the markup.
7. **Bookkeeping and deploy:**
   - Tests pass on PostgreSQL. Update the task file, `TASKS.md` and README.
   - Back up CT 161, deploy, and have Carel test, with the database checked after each step.

### Out of scope (beyond the list above)

- Cash advances (card → budget account money with no envelope).
- Converting existing negative budget accounts into cards. CT 161 has none.

## Implementation Plan

### Phase 1: Design spike
- [ ] Write out the maths for funded/unfunded card spending per month, including rollover of the payment category and of credit overspending, with worked examples in this file
- [ ] Confirm model with the user

### Phase 2: Model
- [ ] Migration: account kind, link from account to its payment category, system category flag
- [ ] Extend `build_budget`; unit tests first

### Phase 3: UI and flows
- [ ] Create card account flow, payment via transfer, display of credit overspending
- [ ] End-to-end tests

---

## Work Completed

*Fill when IN_PROGRESS or DONE.*

---

## Failed Approaches

None yet.

---

## Testing

### Test Strategy
Mostly pure unit tests on the maths with hand-checked expected values, plus web tests for the flows.

### Test Cases
- [ ] Fully funded spending, partially funded, unfunded
- [ ] Refund in a later month
- [ ] Payment greater than the payment category Available
- [ ] Two cards, same category
- [ ] Card spending in a month, category topped up next month (does not retroactively fund)

---

## Performance Considerations

- `build_budget` already walks every month since the first record per category on each page load. Card logic adds per-transaction work; check it stays fast with a few years of data (e.g. 5,000 transactions).

---

## Known Issues & Gotchas

- [ ] Funding is decided per transaction in date order within a month, against the category's available at that point; YNAB's exact ordering rules matter for edge cases. Document the rule chosen.
- [ ] Interacts with category deletion (TASK-H003): payment categories must be protected.

---

## Related Tasks

- **Depends On**: TASK-C001, TASK-H002
- **Blocks**: None
- **Related**: TASK-H003, TASK-H004

---

## References

- YNAB help centre, "Credit Cards in YNAB" guide (support.ynab.com)

---

*Last Updated: 2026-10-21 by Claude*
