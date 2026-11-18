"""Accounting cost-attribution contracts converting reconciled executions into net R outcomes."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime

from . import ReconciliationEntry

_UTC_Z_RE = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]{1,9}))?Z$")


def _parse_utc_z_ns(ts: str, field_name: str) -> tuple[datetime, int]:
    if not isinstance(ts, str):
        raise ValueError(f"invalid {field_name} {ts!r}: expected UTC ISO-8601 ending in 'Z'")
    match = _UTC_Z_RE.fullmatch(ts)
    if not match:
        raise ValueError(f"invalid {field_name} {ts!r}: expected UTC ISO-8601 ending in 'Z'")
    sec_dt = datetime.fromisoformat(match.group(1) + "+00:00")
    ns = int((match.group(2) or "").ljust(9, "0"))
    return sec_dt, ns


def _check_finite(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    f = float(value)
    if not math.isfinite(f):
        raise ValueError(f"{field_name} must be finite, got {value!r}")
    return f


def _check_nonneg_finite(value: float, field_name: str) -> float:
    f = _check_finite(value, field_name)
    if f < 0.0:
        raise ValueError(f"{field_name} must be non-negative finite, got {value!r}")
    return f


@dataclass(frozen=True)
class CostAssumptions:
    """Explicit cost components deducted in R units before evaluating edge."""

    commission_r: float = 0.0
    slippage_r: float = 0.0
    spread_cost_r: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "commission_r", _check_nonneg_finite(self.commission_r, "commission_r"))
        object.__setattr__(self, "slippage_r", _check_nonneg_finite(self.slippage_r, "slippage_r"))
        object.__setattr__(self, "spread_cost_r", _check_nonneg_finite(self.spread_cost_r, "spread_cost_r"))

    @property
    def total_cost_r(self) -> float:
        return self.commission_r + self.slippage_r + self.spread_cost_r


@dataclass(frozen=True)
class AccountedOutcome:
    """Cost-adjusted performance summary ready to feed Brain Memory Outcome resolution."""

    entry_id: str
    gross_r: float
    total_cost_r: float
    net_r: float
    realized_at_utc: str

    def __post_init__(self) -> None:
        if not isinstance(self.entry_id, str) or not self.entry_id.strip():
            raise ValueError("AccountedOutcome.entry_id must be a non-empty string")
        object.__setattr__(self, "gross_r", _check_finite(self.gross_r, "gross_r"))
        object.__setattr__(self, "total_cost_r", _check_nonneg_finite(self.total_cost_r, "total_cost_r"))
        object.__setattr__(self, "net_r", _check_finite(self.net_r, "net_r"))
        _parse_utc_z_ns(self.realized_at_utc, "realized_at_utc")


def compute_net_r(gross_r: float, costs: CostAssumptions) -> tuple[float, float]:
    """Return (net_r, total_cost_r) from gross R and explicit transaction cost components."""
    g = _check_finite(gross_r, "gross_r")
    if not isinstance(costs, CostAssumptions):
        raise TypeError("costs must be a CostAssumptions instance")
    total_cost = _check_nonneg_finite(costs.total_cost_r, "total_cost_r")
    net = g - total_cost
    if not math.isfinite(net):
        raise ValueError("computed net_r overflowed to non-finite float")
    return net, total_cost


def account_for_reconciliation(
    entry: ReconciliationEntry,
    *,
    risk_unit_value: float,
    spread_cost_r: float = 0.0,
) -> AccountedOutcome:
    """Convert a reconciled ledger entry into cost-adjusted R metrics."""
    if not isinstance(entry, ReconciliationEntry):
        raise TypeError("entry must be a ReconciliationEntry")
    if not isinstance(entry.entry_id, str) or not entry.entry_id.strip():
        raise ValueError("ReconciliationEntry.entry_id must be a non-empty string")
    if not isinstance(entry.client_order_id, str) or not entry.client_order_id.strip():
        raise ValueError("ReconciliationEntry.client_order_id must be a non-empty string")
    if not entry.reconciled:
        raise ValueError(f"ReconciliationEntry {entry.entry_id!r} is not reconciled yet")
    _parse_utc_z_ns(entry.reconciled_at_utc, "entry.reconciled_at_utc")

    r_unit = _check_finite(risk_unit_value, "risk_unit_value")
    if r_unit <= 0.0:
        raise ValueError("risk_unit_value must be strictly positive and finite")
    realized_pnl = _check_finite(entry.realized_pnl, "realized_pnl")

    fee_paid = _check_nonneg_finite(entry.fee_paid, "entry.fee_paid")
    slippage = _check_nonneg_finite(entry.slippage_cost, "entry.slippage_cost")
    spread_r = _check_nonneg_finite(spread_cost_r, "spread_cost_r")

    gross_r = realized_pnl / r_unit
    commission_r = fee_paid / r_unit
    slippage_r = slippage / r_unit
    for metric_name, metric_val in (
        ("gross_r", gross_r),
        ("commission_r", commission_r),
        ("slippage_r", slippage_r),
    ):
        if not math.isfinite(metric_val):
            raise ValueError(f"computed {metric_name} overflowed to non-finite float")

    costs = CostAssumptions(
        commission_r=commission_r,
        slippage_r=slippage_r,
        spread_cost_r=spread_r,
    )
    net_r, total_cost_r = compute_net_r(gross_r, costs)
    return AccountedOutcome(
        entry_id=entry.entry_id,
        gross_r=gross_r,
        total_cost_r=total_cost_r,
        net_r=net_r,
        realized_at_utc=entry.reconciled_at_utc,
    )
