"""Site-wide daily budget for Meta credits. Only calls that really reach a model count (cached answers
are free), so the sample plans keep working after the budget is used up."""
from __future__ import annotations

import contextvars


class BudgetClosed(Exception):
    pass


closed: contextvars.ContextVar[bool] = contextvars.ContextVar("budget_closed", default=False)
spent: contextvars.ContextVar[list | None] = contextvars.ContextVar("budget_spent", default=None)


def spend() -> None:
    """Call right before a real (uncached) model call."""
    if closed.get():
        raise BudgetClosed()
    box = spent.get()
    if box is not None:
        box[0] += 1
