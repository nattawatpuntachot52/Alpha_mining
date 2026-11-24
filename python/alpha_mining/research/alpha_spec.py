"""Alpha strategy spec parsing, canonical identity (dedupe key) and model-id generation."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .alpha_signals import DIRECTIONS, FAMILIES, TIMEFRAME_MS, AlphaSpecError

KNOWN_SYMBOLS = ("XAUUSD", "ETHUSDT")
_DIR_CODE = {"long_only": "lo", "short_only": "so", "long_short": "ls"}


@dataclass(frozen=True)
class AlphaSpec:
    symbol: str
    timeframe: str
    family: str
    params: dict[str, Any]
    direction: str
    sl_pct: float = 0.0
    tp_pct: float = 0.0
    time_stop_bars: int = 0
    days: int = 0
    theme: str = ""
    hypothesis: str = ""

    def key(self) -> str:
        """Canonical identity: two specs with the same key are the SAME trial (never re-counted)."""
        payload = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "family": self.family,
            "params": self.params,
            "direction": self.direction,
            "sl_pct": self.sl_pct,
            "tp_pct": self.tp_pct,
            "time_stop_bars": self.time_stop_bars,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def slug(self) -> str:
        bits = [self.family]
        for v in self.params.values():
            if isinstance(v, (list, tuple, dict)):
                bits.append("x")
            else:
                bits.append(str(v))
        bits.append(_DIR_CODE[self.direction])
        if self.sl_pct > 0 or self.tp_pct > 0:
            bits.append(f"sl{self.sl_pct:g}tp{self.tp_pct:g}")
        if self.time_stop_bars > 0:
            bits.append(f"ts{self.time_stop_bars}")
        return re.sub(r"[^a-z0-9]+", "_", "_".join(bits).lower()).strip("_")

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "family": self.family,
            "params": self.params,
            "direction": self.direction,
            "sl_pct": self.sl_pct,
            "tp_pct": self.tp_pct,
            "time_stop_bars": self.time_stop_bars,
            "days": self.days,
            "theme": self.theme,
            "hypothesis": self.hypothesis,
        }


def _num(entry: Mapping[str, Any], key: str, default: float, *, lo: float = 0.0) -> float:
    v = entry.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) or float(v) < lo:
        raise AlphaSpecError(f"{key} must be a finite number >= {lo}, got {v!r}")
    return float(v)


def parse_spec(entry: Mapping[str, Any]) -> AlphaSpec:
    symbol = str(entry.get("symbol", "")).upper()
    if symbol not in KNOWN_SYMBOLS:
        raise AlphaSpecError(f"unknown symbol {symbol!r}; known: {KNOWN_SYMBOLS}")
    tf = str(entry.get("timeframe", "")).lower()
    if tf not in TIMEFRAME_MS:
        raise AlphaSpecError(f"unknown timeframe {tf!r}; known: {sorted(TIMEFRAME_MS)}")
    family = str(entry.get("family", ""))
    if family not in FAMILIES:
        raise AlphaSpecError(f"unknown family {family!r}; known: {sorted(FAMILIES)}")
    direction = str(entry.get("direction", "long_only"))
    if direction not in DIRECTIONS:
        raise AlphaSpecError(f"invalid direction {direction!r}")
    params = entry.get("params", {})
    if not isinstance(params, dict):
        raise AlphaSpecError("params must be an object")
    sl = _num(entry, "sl_pct", 0.0)
    if sl >= 100.0:
        raise AlphaSpecError("sl_pct must be < 100")
    return AlphaSpec(
        symbol=symbol,
        timeframe=tf,
        family=family,
        params=dict(params),
        direction=direction,
        sl_pct=sl,
        tp_pct=_num(entry, "tp_pct", 0.0),
        time_stop_bars=int(_num(entry, "time_stop_bars", 0)),
        days=int(_num(entry, "days", 0)),
        theme=str(entry.get("theme", "")),
        hypothesis=str(entry.get("hypothesis", "")),
    )


def make_model_id(index: int, spec: AlphaSpec) -> str:
    return f"alpha_{index:03d}_{spec.symbol.lower()}_{spec.timeframe}_{spec.slug()}"[:64].rstrip("_")
