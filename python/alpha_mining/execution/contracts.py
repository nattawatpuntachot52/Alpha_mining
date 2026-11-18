"""Execution contracts enforcing that only Risk-approved decisions produce order requests."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from ..risk import RiskDecision, verify_risk_decision_seal
from . import ExecutionReport, OrderSide

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


def _make_order_seal_ops():
    secret = secrets.token_bytes(32)

    def sign_fields(
        client_order_id: str,
        intent_id: str,
        instrument: str,
        side: OrderSide,
        abs_exposure: float,
        risk_evaluated_at_utc: str,
    ) -> str:
        payload = json.dumps(
            {
                "client_order_id": client_order_id,
                "intent_id": intent_id,
                "instrument": instrument,
                "side": side,
                "abs_exposure": float(abs_exposure),
                "risk_evaluated_at_utc": risk_evaluated_at_utc,
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hmac.new(secret, payload, hashlib.sha256).hexdigest()

    def verify_order(order: ExecutionOrderRequest) -> bool:
        if not isinstance(order._seal, str) or not order._seal:
            return False
        expected = sign_fields(
            order.client_order_id,
            order.intent_id,
            order.instrument,
            order.side,
            float(order.abs_exposure),
            order.risk_evaluated_at_utc,
        )
        return hmac.compare_digest(order._seal, expected)

    return sign_fields, verify_order


_sign_order_fields, _verify_order_seal = _make_order_seal_ops()
del _make_order_seal_ops


@dataclass(frozen=True)
class ExecutionOrderRequest:
    """Idempotent order request constructed exclusively from an approved RiskDecision."""

    client_order_id: str
    intent_id: str
    instrument: str
    side: OrderSide
    abs_exposure: float
    risk_evaluated_at_utc: str
    _seal: str = field(default="", repr=False, compare=False, hash=False, kw_only=True)

    def __post_init__(self) -> None:
        if not isinstance(self.client_order_id, str) or not self.client_order_id.strip():
            raise ValueError("client_order_id must be non-empty")
        if not isinstance(self.intent_id, str) or not self.intent_id.strip():
            raise ValueError("intent_id must be non-empty")
        if not isinstance(self.instrument, str) or not self.instrument.strip():
            raise ValueError("instrument must be non-empty")
        if self.side not in ("buy", "sell"):
            raise ValueError(f"invalid order side {self.side!r}")
        if isinstance(self.abs_exposure, bool) or not isinstance(self.abs_exposure, (int, float)):
            raise ValueError("abs_exposure must be numeric")
        exp = float(self.abs_exposure)
        if not math.isfinite(exp) or exp <= 0.0:
            raise ValueError("abs_exposure must be strictly positive and finite")
        object.__setattr__(self, "abs_exposure", exp)
        _parse_utc_z_ns(self.risk_evaluated_at_utc, "risk_evaluated_at_utc")
        if not _verify_order_seal(self):
            raise PermissionError(
                "ExecutionOrderRequest must be constructed exclusively via build_order_from_risk_decision() from a sealed RiskDecision"
            )


def build_order_from_risk_decision(
    client_order_id: str,
    decision: RiskDecision,
    instrument: str,
) -> ExecutionOrderRequest:
    """Enforce that Execution can never construct an order without an approved sealed RiskDecision."""
    verify_risk_decision_seal(decision)
    if not decision.approved:
        raise ValueError(
            f"cannot construct order for unapproved RiskDecision {decision.intent_id!r}: {decision.rejection_reason}"
        )
    if isinstance(decision.approved_exposure, bool) or not isinstance(decision.approved_exposure, (int, float)):
        raise ValueError("approved_exposure must be numeric")
    exposure = float(decision.approved_exposure)
    if not math.isfinite(exposure) or exposure == 0.0:
        raise ValueError("cannot construct order with zero or non-finite approved_exposure")

    if not isinstance(client_order_id, str) or not client_order_id.strip():
        raise ValueError("client_order_id must be non-empty")
    if not isinstance(instrument, str) or not instrument.strip():
        raise ValueError("instrument must be non-empty")

    side: OrderSide = "buy" if exposure > 0.0 else "sell"
    abs_exp = abs(exposure)
    seal = _sign_order_fields(
        client_order_id,
        decision.intent_id,
        instrument,
        side,
        abs_exp,
        decision.evaluated_at_utc,
    )
    return ExecutionOrderRequest(
        client_order_id=client_order_id,
        intent_id=decision.intent_id,
        instrument=instrument,
        side=side,
        abs_exposure=abs_exp,
        risk_evaluated_at_utc=decision.evaluated_at_utc,
        _seal=seal,
    )


class ExecutionAdapter(Protocol):
    """Protocol for future broker/exchange adapters (MQL5, APIs, Rust routers)."""

    def submit_order(self, order: ExecutionOrderRequest) -> ExecutionReport: ...
