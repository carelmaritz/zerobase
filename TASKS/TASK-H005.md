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
