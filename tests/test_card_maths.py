"""Credit card budget maths, on plain data (TASK-H005).

Each test is a worked example from the agreed plan in TASKS/TASK-H005.md. Amounts are
pence; card spending is negative activity on the card.
"""

from datetime import date

from zerobase.budget import Ledger, compute_budget

OCT, NOV, DEC = date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1)
GROCERIES = 1
CARD_A, CARD_B = 101, 102
PAY_A, PAY_B = 201, 202
INCOME = 1_000_00  # in October, so Ready to Assign has something to start from


def ledger(**kwargs) -> Ledger:
    return Ledger(income={OCT: INCOME}, payment_categories={CARD_A: PAY_A}, **kwargs)


def figures(book: Ledger, month: date):
    lines, ready = compute_budget(book, [GROCERIES], month)
    return lines[GROCERIES], lines, ready


def test_1_funded_card_spending_moves_to_the_payment_category():
    book = ledger(
        assigned={(GROCERIES, OCT): 100_00},
        card={(GROCERIES, OCT, CARD_A): -30_00},
        card_balances={CARD_A: -30_00},
    )
    groceries, lines, ready = figures(book, OCT)
    assert (groceries.available, groceries.activity) == (70_00, -30_00)
    payment = lines[PAY_A]
    assert (payment.activity, payment.available, payment.needed) == (30_00, 30_00, 0)
    assert ready == INCOME - 100_00


def example_2(**extra) -> Ledger:
    """Groceries £100 in October; £120 on the card."""
    assigned = {(GROCERIES, OCT): 100_00, **extra.pop("assigned", {})}
    balances = extra.pop("card_balances", {CARD_A: -120_00})
    return ledger(
        assigned=assigned,
        card={(GROCERIES, OCT, CARD_A): -120_00},
        card_balances=balances,
        **extra,
    )


def test_2_unfunded_card_spending_is_credit_overspending():
    groceries, lines, ready = figures(example_2(), OCT)
    assert groceries.available == -20_00
    assert (groceries.credit_overspent, groceries.cash_overspent) == (20_00, 0)
    assert (lines[PAY_A].available, lines[PAY_A].needed) == (100_00, 20_00)

    groceries, lines, ready_nov = figures(example_2(), NOV)
    assert groceries.available == 0
    assert ready_nov == ready  # credit overspending doesn't reduce Ready to Assign
    assert (lines[PAY_A].available, lines[PAY_A].needed) == (100_00, 20_00)


def test_3_cash_is_funded_before_card_spending():
    book = ledger(
        assigned={(GROCERIES, OCT): 50_00},
        cash={(GROCERIES, OCT): -40_00},
        card={(GROCERIES, OCT, CARD_A): -30_00},
    )
    groceries, lines, _ = figures(book, OCT)
    assert groceries.available == -20_00
    assert (groceries.cash_overspent, groceries.credit_overspent) == (0, 20_00)
    assert lines[PAY_A].available == 10_00


def test_3b_cash_overspending_alongside_credit_overspending():
    book = ledger(
        assigned={(GROCERIES, OCT): 50_00},
        cash={(GROCERIES, OCT): -60_00},
        card={(GROCERIES, OCT, CARD_A): -30_00},
    )
    groceries, lines, ready = figures(book, OCT)
    assert groceries.available == -40_00
    assert (groceries.cash_overspent, groceries.credit_overspent) == (10_00, 30_00)
    assert lines[PAY_A].available == 0
    _, _, ready_nov = figures(book, NOV)
    assert ready_nov == ready - 10_00  # only the cash part


def test_4_assigning_more_in_the_same_month_funds_the_card_spending():
    book = example_2(assigned={(GROCERIES, OCT): 120_00})
    groceries, lines, _ = figures(book, OCT)
    assert (groceries.available, groceries.credit_overspent) == (0, 0)
    assert (lines[PAY_A].available, lines[PAY_A].needed) == (120_00, 0)


def test_5_assigning_next_month_does_not_fund_it_retroactively():
    book = example_2(assigned={(GROCERIES, NOV): 20_00})
    groceries, lines, _ = figures(book, NOV)
    assert groceries.available == 20_00
    assert (lines[PAY_A].available, lines[PAY_A].needed) == (100_00, 20_00)


def test_6_paying_the_card_uses_the_payment_category():
    book = example_2(payments={(CARD_A, NOV): -100_00}, card_balances={CARD_A: -20_00})
    _, lines, _ = figures(book, NOV)
    payment = lines[PAY_A]
    assert (payment.activity, payment.available, payment.needed) == (-100_00, 0, 20_00)


def test_6b_paying_more_than_was_set_aside_is_cash_overspending():
    book = example_2(payments={(CARD_A, NOV): -120_00}, card_balances={CARD_A: 0})
    _, lines, ready_nov = figures(book, NOV)
    assert lines[PAY_A].available == -20_00 and lines[PAY_A].cash_overspent == 20_00
    _, _, ready_dec = figures(book, DEC)
    assert ready_dec == ready_nov - 20_00


def test_7_a_refund_on_the_card_moves_money_back_to_the_category():
    book = ledger(
        assigned={(GROCERIES, OCT): 100_00},
        card={(GROCERIES, OCT, CARD_A): -30_00, (GROCERIES, NOV, CARD_A): 10_00},
        card_balances={CARD_A: -20_00},
    )
    groceries, lines, _ = figures(book, NOV)
    assert (groceries.activity, groceries.available) == (10_00, 80_00)
    payment = lines[PAY_A]
    assert (payment.activity, payment.available, payment.needed) == (-10_00, 20_00, 0)


def test_8_starting_debt_leaves_ready_to_assign_alone():
    book = ledger(card_balances={CARD_A: -500_00})
    _, lines, ready = figures(book, OCT)
    assert ready == INCOME
    assert (lines[PAY_A].available, lines[PAY_A].needed) == (0, 500_00)

    book.assigned[(PAY_A, OCT)] = 500_00
    _, lines, ready = figures(book, OCT)
    assert (lines[PAY_A].available, lines[PAY_A].needed, ready) == (500_00, 0, INCOME - 500_00)

    book.payments[(CARD_A, OCT)] = -500_00
    book.card_balances[CARD_A] = 0
    _, lines, _ = figures(book, OCT)
    assert (lines[PAY_A].available, lines[PAY_A].needed) == (0, 0)


def test_9_two_cards_are_funded_in_account_order():
    book = ledger(
        assigned={(GROCERIES, OCT): 50_00},
        card={(GROCERIES, OCT, CARD_B): -40_00, (GROCERIES, OCT, CARD_A): -40_00},
    )
    book.payment_categories[CARD_B] = PAY_B
    groceries, lines, _ = figures(book, OCT)
    assert (lines[PAY_A].available, lines[PAY_B].available) == (40_00, 10_00)
    assert (groceries.available, groceries.credit_overspent) == (-30_00, 30_00)


def test_without_cards_the_maths_is_unchanged():
    book = Ledger(
        income={OCT: 100_00},
        assigned={(GROCERIES, OCT): 50_00},
        cash={(GROCERIES, OCT): -70_00},
    )
    groceries, _, ready = figures(book, OCT)
    assert (groceries.available, groceries.cash_overspent) == (-20_00, 20_00)
    assert ready == 50_00
    _, _, ready_nov = figures(book, NOV)
    assert ready_nov == 30_00
