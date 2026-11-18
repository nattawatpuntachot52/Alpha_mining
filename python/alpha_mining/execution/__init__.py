"""Execution layer boundary: order routing adapters (MQL5, broker APIs, Rust engines).

Execution translates risk-approved intents into idempotent order requests and records
fills. It MUST NOT alter risk limits or modify historical accounting records.
"""

from dataclasses import dataclass
from typing import Literal

OrderSide = Literal["buy", "sell"]


@dataclass(frozen=True)
class ExecutionReport:
    client_order_id: str
    intent_id: str
    instrument: str
    side: OrderSide
    filled_qty: float
    avg_fill_price: float
    fee_paid: float
    executed_at_utc: str


from .contracts import (  # noqa: E402
    ExecutionAdapter,
    ExecutionOrderRequest,
    build_order_from_risk_decision,
)

__all__ = [
    "ExecutionAdapter",
    "ExecutionOrderRequest",
    "ExecutionReport",
    "OrderSide",
    "build_order_from_risk_decision",
]
