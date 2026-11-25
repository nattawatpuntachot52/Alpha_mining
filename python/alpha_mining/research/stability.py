"""Portfolio stability & volatility metrics computed from daily equity/return series.

Provides transparent, deterministic stability measurements for both Alpha and Beta tracks:
- ``ann_vol_pct``: Annualized daily return volatility (%/year, sqrt(365) scaling for 24/7 crypto/PAXG).
- ``ulcer_index_pct``: Root-mean-square percentage drawdown (captures depth and duration of swings).
- ``equity_r2``: Linear regression R^2 of log-equity vs time in [0.0, 1.0] (0.0 when trend slope <= 0).
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


def compute_stability_metrics(daily_returns: Sequence[float]) -> dict[str, float]:
    """Compute annualized volatility %, Ulcer Index %, and log-equity R^2 from daily simple returns."""
    rets = [float(r) for r in daily_returns if r is not None and math.isfinite(float(r))]
    n = len(rets)
    if n < 5:
        return {"ann_vol_pct": 0.0, "ulcer_index_pct": 0.0, "equity_r2": 0.0}

    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / max(1, n - 1)
    ann_vol_pct = math.sqrt(max(0.0, var)) * math.sqrt(365.0) * 100.0

    eq = 1.0
    pk = 1.0
    dd_sq_sum = 0.0
    log_eq: list[float] = []
    for r in rets:
        eq *= max(1e-6, 1.0 + r)
        if eq > pk:
            pk = eq
        dd_pct = (1.0 - eq / pk) * 100.0
        dd_sq_sum += dd_pct * dd_pct
        log_eq.append(math.log(max(1e-6, eq)))

    ulcer_index_pct = math.sqrt(dd_sq_sum / n)

    mx = (n - 1) / 2.0
    my = sum(log_eq) / n
    sxx = sum((i - mx) ** 2 for i in range(n))
    sxy = sum((i - mx) * (y - my) for i, y in enumerate(log_eq))
    syy = sum((y - my) ** 2 for y in log_eq)
    if sxx > 1e-12 and syy > 1e-12 and sxy > 0.0:
        equity_r2 = max(0.0, min(1.0, (sxy * sxy) / (sxx * syy)))
    else:
        equity_r2 = 0.0

    return {
        "ann_vol_pct": round(ann_vol_pct, 2),
        "ulcer_index_pct": round(ulcer_index_pct, 2),
        "equity_r2": round(equity_r2, 3),
    }


def stability_from_alpha_series(series_doc: Mapping[str, Any] | None) -> dict[str, float]:
    """Compute stability metrics from an Alpha ``latest_series.json`` payload (``strategy_bp``)."""
    if not isinstance(series_doc, Mapping):
        return {"ann_vol_pct": 0.0, "ulcer_index_pct": 0.0, "equity_r2": 0.0}
    bps = series_doc.get("strategy_bp")
    if not isinstance(bps, list) or len(bps) < 5:
        return {"ann_vol_pct": 0.0, "ulcer_index_pct": 0.0, "equity_r2": 0.0}
    return compute_stability_metrics([float(bp) / 1e4 for bp in bps])


def stability_from_beta_series(series_doc: Mapping[str, Any] | None) -> dict[str, float]:
    """Compute stability metrics from a Beta ``latest_series.json`` payload (``daily_returns`` or ``equity``)."""
    if not isinstance(series_doc, Mapping):
        return {"ann_vol_pct": 0.0, "ulcer_index_pct": 0.0, "equity_r2": 0.0}
    d_rets = series_doc.get("daily_returns")
    if isinstance(d_rets, list) and len(d_rets) >= 5:
        return compute_stability_metrics(d_rets)
    eq = series_doc.get("equity")
    if isinstance(eq, list) and len(eq) >= 6:
        derived: list[float] = []
        for i in range(1, len(eq)):
            prev = 1.0 + float(eq[i - 1]) / 100.0
            curr = 1.0 + float(eq[i]) / 100.0
            derived.append((curr / prev - 1.0) if prev > 1e-9 else 0.0)
        return compute_stability_metrics(derived)
    return {"ann_vol_pct": 0.0, "ulcer_index_pct": 0.0, "equity_r2": 0.0}


def enrich_models_with_stability(
    models: Sequence[dict[str, Any]],
    series_map: Mapping[str, Mapping[str, Any]],
    *,
    kind: str,
) -> list[dict[str, Any]]:
    """Return shallow copies of metric dicts enriched with ``ann_vol_pct``, ``ulcer_index_pct``, and ``equity_r2``."""
    fn = stability_from_alpha_series if kind == "alpha" else stability_from_beta_series
    cache: dict[str, dict[str, float]] = {}
    out: list[dict[str, Any]] = []
    for m in models:
        rec = dict(m)
        mid = str(rec.get("model_id", ""))
        if mid and mid in series_map:
            if mid not in cache:
                cache[mid] = fn(series_map[mid])
            rec.update(cache[mid])
        else:
            rec.setdefault("ann_vol_pct", 0.0)
            rec.setdefault("ulcer_index_pct", 0.0)
            rec.setdefault("equity_r2", 0.0)
        out.append(rec)
    return out
