"""Isolated per-model storage, catalog, Top-9 ranking and daily 2-round batches for Alpha Mining.

Layout (`alpha_mining/` under repository root):
- ``catalog.json``                       Master index (``model_id -> folder, spec_key, trial_number``)
- ``ranking_top9.json``                  Cumulative leaderboard (OOS Sharpe DESC, max DD ASC) + per-symbol boards
- ``models/<model_id>/spec.json``        Immutable strategy spec + hypothesis
- ``models/<model_id>/latest_metrics.json``
- ``models/<model_id>/latest_series.json``  Daily return series in basis points (dashboard + correlation)
- ``models/<model_id>/runs/<run_id>.json``  Immutable run audit record
- ``daily/<YYYY-MM-DD>/batch.json``      Same-day batch; Round 2 ACCUMULATES into Round 1 (10 -> 20 models)
- ``daily/<YYYY-MM-DD>/daily_summary.md`` / ``dashboard.html``
- ``daily/index.json`` and ``index.html`` (archive hub)
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .alpha_backtest import AlphaResult
from .alpha_spec import AlphaSpec
from .beta_store import merge_batch_models, validate_date_str, validate_model_id

SCHEMA_VERSION = "1.0"
DEFAULT_TOP_N = 9
DEFAULT_MAX_DD_GATE_PCT = 50.0
DEFAULT_MIN_TRADES = 30
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ND = statistics.NormalDist()
_EULER_GAMMA = 0.5772156649015329


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_json(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def expected_max_sharpe(trial_sharpes: Sequence[float], n_trials: int) -> float:
    """Expected maximum of ``n_trials`` independent Sharpe estimates under H0 (Bailey & Lopez de Prado)."""
    if n_trials < 2 or len(trial_sharpes) < 2:
        return 0.0
    sd = statistics.pstdev(trial_sharpes)
    if sd <= 1e-12:
        return 0.0
    a = _ND.inv_cdf(1.0 - 1.0 / n_trials)
    b = _ND.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    return sd * ((1.0 - _EULER_GAMMA) * a + _EULER_GAMMA * b)


def deflated_sharpe_approx(sr_daily: float, sr0_daily: float, n_days: float) -> float:
    """Approximate Deflated Sharpe Ratio (normal-returns denominator) -> probability SR beats the trial max."""
    if n_days < 10:
        return 0.0
    denom = math.sqrt(max(1.0 + 0.5 * sr_daily * sr_daily, 1e-9))
    return _ND.cdf((sr_daily - sr0_daily) * math.sqrt(max(n_days - 1.0, 1.0)) / denom)


class AlphaModelStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()
        self.models_dir = self.root_dir / "models"
        self.daily_dir = self.root_dir / "daily"
        self.catalog_path = self.root_dir / "catalog.json"
        self.ranking_path = self.root_dir / "ranking_top9.json"
        self.daily_index_path = self.daily_dir / "index.json"
        self.portal_index_path = self.root_dir / "index.html"

    # ------------------------------------------------------------------ basics
    def _model_dir(self, model_id: str) -> Path:
        mid = validate_model_id(model_id)
        candidate = (self.models_dir / mid).resolve()
        try:
            candidate.relative_to(self.models_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"model_id escapes models directory: {model_id!r}") from exc
        return candidate

    def ensure_initialized(self) -> None:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        if not self.catalog_path.is_file():
            _atomic_write_json(
                self.catalog_path,
                {"schema_version": SCHEMA_VERSION, "updated_at_utc": _now_utc_iso(), "total_trials": 0, "models": {}},
            )

    def load_catalog(self) -> dict[str, Any]:
        if not self.catalog_path.is_file():
            return {"schema_version": SCHEMA_VERSION, "updated_at_utc": _now_utc_iso(), "total_trials": 0, "models": {}}
        return json.loads(self.catalog_path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ models
    def record_model_run(
        self,
        *,
        model_id: str,
        batch_date: str,
        spec: AlphaSpec,
        result: AlphaResult,
        round_no: int | None = None,
        loader_meta: dict[str, Any] | None = None,
        evidence_status: str = "exploratory",
        run_id: str | None = None,
        recorded_at_utc: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_initialized()
        mid = validate_model_id(model_id)
        bdate = validate_date_str(batch_date)
        ts = recorded_at_utc or _now_utc_iso()
        mdir = self._model_dir(mid)
        runs_dir = mdir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)

        catalog = self.load_catalog()
        existing = (catalog.get("models") or {}).get(mid)
        if existing and isinstance(existing.get("trial_number"), int):
            trial_num = int(existing["trial_number"])
        else:
            trial_num = int(catalog.get("total_trials", 0)) + 1
            catalog["total_trials"] = trial_num

        spec_payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "model_id": mid,
            "trial_number": trial_num,
            "category": "alpha",
            "spec_key": spec.key(),
            **spec.to_dict(),
            "evidence_status": evidence_status,
            "created_batch_date": (existing or {}).get("created_batch_date", bdate),
            "updated_at_utc": ts,
        }
        spec_sha = _sha256_json(spec_payload)
        spec_payload["spec_sha256"] = spec_sha

        existing_runs = sorted(p.stem for p in runs_dir.glob("*.json"))
        resolved_run_id = run_id or f"{bdate}_run{len(existing_runs) + 1:02d}"

        metrics_payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "model_id": mid,
            "trial_number": trial_num,
            "run_id": resolved_run_id,
            "batch_date": bdate,
            "round_no": int(round_no) if round_no is not None else None,
            "recorded_at_utc": ts,
            "evidence_status": evidence_status,
            "spec_sha256": spec_sha,
            "spec_key": spec.key(),
            "family": spec.family,
            "theme": spec.theme,
            "hypothesis": spec.hypothesis,
            "params": spec.params,
            **result.summary_dict(),
            "data_source": (loader_meta or {}).get("source", ""),
            "data_is_proxy": bool((loader_meta or {}).get("is_proxy", False)),
        }

        run_record = {
            "schema_version": SCHEMA_VERSION,
            "run_id": resolved_run_id,
            "model_id": mid,
            "batch_date": bdate,
            "recorded_at_utc": ts,
            "spec": spec_payload,
            "metrics": metrics_payload,
            "loader": loader_meta or {},
        }

        _atomic_write_json(mdir / "spec.json", spec_payload)
        _atomic_write_json(mdir / "latest_metrics.json", metrics_payload)
        _atomic_write_text(
            mdir / "latest_series.json",
            json.dumps(result.daily_series, separators=(",", ":"), ensure_ascii=False) + "\n",
        )
        _atomic_write_json(runs_dir / f"{resolved_run_id}.json", run_record)

        catalog.setdefault("models", {})[mid] = {
            "model_id": mid,
            "trial_number": trial_num,
            "folder": f"models/{mid}",
            "spec_key": spec.key(),
            "symbol": spec.symbol,
            "timeframe": spec.timeframe,
            "family": spec.family,
            "direction": spec.direction,
            "created_batch_date": spec_payload["created_batch_date"],
            "latest_batch_date": bdate,
            "latest_run_id": resolved_run_id,
            "evidence_status": evidence_status,
            "spec_sha256": spec_sha,
            "updated_at_utc": ts,
        }
        catalog["updated_at_utc"] = ts
        _atomic_write_json(self.catalog_path, catalog)
        return metrics_payload

    def list_model_ids(self) -> list[str]:
        if not self.models_dir.is_dir():
            return []
        return sorted(
            p.name
            for p in self.models_dir.iterdir()
            if p.is_dir() and (p / "spec.json").is_file() and (p / "latest_metrics.json").is_file()
        )

    def load_metrics(self, model_id: str) -> dict[str, Any]:
        p = self._model_dir(model_id) / "latest_metrics.json"
        if not p.is_file():
            raise FileNotFoundError(f"alpha model {model_id!r} not found")
        return json.loads(p.read_text(encoding="utf-8"))

    def load_spec(self, model_id: str) -> dict[str, Any]:
        p = self._model_dir(model_id) / "spec.json"
        if not p.is_file():
            raise FileNotFoundError(f"alpha model {model_id!r} not found")
        return json.loads(p.read_text(encoding="utf-8"))

    def load_all_metrics(self) -> list[dict[str, Any]]:
        return [self.load_metrics(mid) for mid in self.list_model_ids()]

    def load_series(self, model_id: str) -> dict[str, Any]:
        sp = self._model_dir(model_id) / "latest_series.json"
        if not sp.is_file():
            return {}
        return json.loads(sp.read_text(encoding="utf-8"))

    def load_batch_series(self, model_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for mid in model_ids:
            s = self.load_series(mid)
            if s:
                out[mid] = s
        return out

    def load_all_stability_map(self) -> dict[str, dict[str, float]]:
        """Compute portfolio stability metrics (Vol/yr, Ulcer, R^2) for every isolated model on disk."""
        from .stability import stability_from_alpha_series

        out: dict[str, dict[str, float]] = {}
        for mid in self.list_model_ids():
            s = self.load_series(mid)
            if s:
                out[mid] = stability_from_alpha_series(s)
        return out

    def mined_spec_keys(self) -> set[str]:
        return {str(info.get("spec_key", "")) for info in (self.load_catalog().get("models") or {}).values()}

    # ------------------------------------------------------------------ ranking
    def compute_ranking(
        self,
        *,
        top_n: int = DEFAULT_TOP_N,
        max_dd_pct: float = DEFAULT_MAX_DD_GATE_PCT,
        min_trades: int = DEFAULT_MIN_TRADES,
        write_file: bool = True,
    ) -> dict[str, Any]:
        """Top-N board: OOS Sharpe DESC, Max DD ASC. Hard gates: no liquidation, enough trades, OOS profit.

        Also attaches an approximate Deflated Sharpe Ratio computed against ALL trials ever mined
        (``N_trials`` = catalog total), so the board never ignores multiple-testing inflation.
        """
        if top_n < 1:
            raise ValueError("top_n must be >= 1")
        all_metrics = self.load_all_metrics()
        catalog = self.load_catalog()
        n_trials = max(int(catalog.get("total_trials", len(all_metrics))), len(all_metrics))
        trial_sr = [float(m.get("daily_sharpe_raw", 0.0)) for m in all_metrics]
        sr0 = expected_max_sharpe(trial_sr, n_trials)

        qualified: list[dict[str, Any]] = []
        disqualified: list[dict[str, Any]] = []
        for m in all_metrics:
            entry = dict(m)
            entry["dsr_approx"] = round(
                deflated_sharpe_approx(float(m.get("daily_sharpe_raw", 0.0)), sr0, float(m.get("days_covered", 0.0))), 4
            )
            reasons: list[str] = []
            if bool(m.get("liquidated")):
                reasons.append("LIQUIDATED")
            if int(m.get("trades", 0)) < min_trades:
                reasons.append(f"TRADES_LT_{min_trades}")
            if float(m.get("max_drawdown_pct", 0.0)) > max_dd_pct:
                reasons.append(f"MAX_DD_EXCEEDS_{max_dd_pct:g}PCT")
            if float(m.get("oos_return_pct", 0.0)) <= 0.0:
                reasons.append("OOS_NOT_PROFITABLE")
            if float(m.get("oos_sharpe_ann", 0.0)) <= 0.0:
                reasons.append("OOS_SHARPE_LE_0")
            entry["gate_passed"] = not reasons
            entry["disqualify_reasons"] = reasons
            (qualified if not reasons else disqualified).append(entry)

        def _key(item: dict[str, Any]) -> tuple[Any, ...]:
            return (
                -round(float(item.get("oos_sharpe_ann", 0.0)), 6),
                round(float(item.get("max_drawdown_pct", 0.0)), 6),
                str(item.get("model_id", "")),
            )

        qualified.sort(key=_key)
        disqualified.sort(key=_key)

        def _rank(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
            out = []
            for idx, item in enumerate(rows[:top_n], start=1):
                row = dict(item)
                row["rank"] = idx
                out.append(row)
            return out

        by_symbol = {
            sym: _rank([q for q in qualified if q.get("symbol") == sym])
            for sym in sorted({str(q.get("symbol")) for q in all_metrics})
        }
        board: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "generated_at_utc": _now_utc_iso(),
            "ranking_rule": {
                "primary": "oos_sharpe_ann DESC",
                "secondary": "max_drawdown_pct ASC",
                "top_n": top_n,
                "hard_gates": {
                    "forbid_liquidation": True,
                    "min_trades": min_trades,
                    "max_drawdown_pct_limit": max_dd_pct,
                    "require_oos_profit": True,
                },
                "multiple_testing": {
                    "n_trials": n_trials,
                    "expected_max_daily_sharpe_h0": round(sr0, 6),
                    "dsr_note": "dsr_approx = P(SR > expected max SR of N_trials) under normal-returns approximation",
                },
            },
            "total_trials": n_trials,
            "total_models": len(all_metrics),
            "qualified_count": len(qualified),
            "disqualified_count": len(disqualified),
            "top_ranked": _rank(qualified),
            "top_ranked_by_symbol": by_symbol,
            "disqualified": disqualified,
        }
        if write_file:
            self.ensure_initialized()
            _atomic_write_json(self.ranking_path, board)
        return board

    # ------------------------------------------------------------------ daily batches
    def _daily_date_dir(self, batch_date: str) -> Path:
        bdate = validate_date_str(batch_date)
        candidate = (self.daily_dir / bdate).resolve()
        try:
            candidate.relative_to(self.daily_dir.resolve())
        except ValueError as exc:
            raise ValueError(f"batch_date escapes daily directory: {batch_date!r}") from exc
        return candidate

    def list_daily_dates(self) -> list[str]:
        if not self.daily_dir.is_dir():
            return []
        valid = []
        for p in self.daily_dir.iterdir():
            if p.is_dir() and _DATE_RE.fullmatch(p.name):
                try:
                    validate_date_str(p.name)
                except ValueError:
                    continue
                if (p / "batch.json").is_file():
                    valid.append(p.name)
        return sorted(valid)

    def load_daily_batch(self, batch_date: str) -> dict[str, Any] | None:
        bp = self._daily_date_dir(batch_date) / "batch.json"
        if not bp.is_file():
            return None
        return json.loads(bp.read_text(encoding="utf-8"))

    def load_daily_batch_models(self, batch_date: str) -> list[dict[str, Any]]:
        batch = self.load_daily_batch(batch_date)
        if not isinstance(batch, dict):
            return []
        return [dict(m) for m in (batch.get("models") or []) if isinstance(m, dict) and m.get("model_id")]

    def load_daily_batches_summary(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for bdate in reversed(self.list_daily_dates()):
            ddir = self._daily_date_dir(bdate)
            batch = self.load_daily_batch(bdate) or {}
            models = [m for m in (batch.get("models") or []) if isinstance(m, dict)]
            by_sym: dict[str, int] = {}
            for m in models:
                by_sym[str(m.get("symbol", "?"))] = by_sym.get(str(m.get("symbol", "?")), 0) + 1
            best = max(models, key=lambda m: float(m.get("oos_sharpe_ann", float("-inf")))) if models else None
            out.append(
                {
                    "batch_date": bdate,
                    "generated_at_utc": str(batch.get("generated_at_utc", "")),
                    "model_count": len(models),
                    "rounds": list(batch.get("rounds") or []),
                    "by_symbol": by_sym,
                    "model_ids": [str(m["model_id"]) for m in models if m.get("model_id")],
                    "best_oos_sharpe_model_id": str(best.get("model_id", "")) if best else "",
                    "best_oos_sharpe": round(float(best.get("oos_sharpe_ann", 0.0)), 3) if best else 0.0,
                    "profitable_oos_count": sum(1 for m in models if float(m.get("oos_return_pct", 0.0)) > 0),
                    "has_dashboard": (ddir / "dashboard.html").is_file(),
                    "has_summary": (ddir / "daily_summary.md").is_file(),
                    "dashboard_rel_path": f"daily/{bdate}/dashboard.html",
                    "summary_rel_path": f"daily/{bdate}/daily_summary.md",
                }
            )
        return out

    def write_daily_index(self) -> dict[str, Any]:
        self.ensure_initialized()
        days = self.load_daily_batches_summary()
        payload = {
            "schema_version": SCHEMA_VERSION,
            "generated_at_utc": _now_utc_iso(),
            "latest_date": days[0]["batch_date"] if days else "",
            "total_days": len(days),
            "dates": [d["batch_date"] for d in days],
            "days": days,
        }
        _atomic_write_json(self.daily_index_path, payload)
        return payload

    def write_portal_index(self, portal_html: str) -> Path:
        self.ensure_initialized()
        _atomic_write_text(self.portal_index_path, portal_html)
        return self.portal_index_path

    def save_daily_batch(
        self,
        *,
        batch_date: str,
        batch_metrics: Sequence[dict[str, Any]],
        ranking_board: dict[str, Any],
        summary_markdown: str,
        dashboard_html: str,
        loader_meta: dict[str, Any] | None = None,
    ) -> Path:
        bdate = validate_date_str(batch_date)
        ddir = self._daily_date_dir(bdate)
        ddir.mkdir(parents=True, exist_ok=True)
        top_rank_map = {r["model_id"]: r["rank"] for r in ranking_board.get("top_ranked", [])}
        rows = []
        for m in batch_metrics:
            row = dict(m)
            row["current_top9_rank"] = top_rank_map.get(m["model_id"])
            rows.append(row)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "batch_date": bdate,
            "generated_at_utc": _now_utc_iso(),
            "model_count": len(rows),
            "rounds": sorted({int(r["round_no"]) for r in rows if r.get("round_no") is not None}),
            "loader": loader_meta or {},
            "models": rows,
        }
        _atomic_write_json(ddir / "batch.json", payload)
        _atomic_write_text(ddir / "daily_summary.md", summary_markdown)
        _atomic_write_text(ddir / "dashboard.html", dashboard_html)
        self.write_daily_index()
        return ddir


__all__ = [
    "AlphaModelStore",
    "DEFAULT_MAX_DD_GATE_PCT",
    "DEFAULT_MIN_TRADES",
    "DEFAULT_TOP_N",
    "deflated_sharpe_approx",
    "expected_max_sharpe",
    "merge_batch_models",
]
