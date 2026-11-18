"""Accounting layer boundary: immutable ledger, cost attribution, and reconciliation.

Accounting reconciles execution fills against broker/exchange statements independently
of strategy or execution assumptions.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReconciliationEntry:
    entry_id: str
    client_order_id: str
    realized_pnl: float
    fee_paid: float
    slippage_cost: float
    reconciled: bool
    reconciled_at_utc: str


from .contracts import (  # noqa: E402
    AccountedOutcome,
    CostAssumptions,
    account_for_reconciliation,
    compute_net_r,
)

__all__ = [
    "AccountedOutcome",
    "CostAssumptions",
    "ReconciliationEntry",
    "account_for_reconciliation",
    "compute_net_r",
]
