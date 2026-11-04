import pytest

from app.budget import BudgetClosed, closed, spend, spent


def test_spend_counts_and_closes():
    box = [0]
    t = spent.set(box)
    spend(); spend()
    assert box[0] == 2
    c = closed.set(True)
    with pytest.raises(BudgetClosed):
        spend()
    closed.reset(c); spent.reset(t)
