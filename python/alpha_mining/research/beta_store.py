"""Isolated per-model storage, catalog, and Top-9 Cashflow->DD Ranking Board for daily Beta Mining.

Layout (`beta_mining/` under repository root):
- `catalog.json`                       Master index (`model_id -> folder, latest_run, trial_number`)
- `ranking_top9.json`                  Cumulative Top-N leaderboard (`realized_net_pnl` DESC, `max_drawdown_pct` ASC)
- `models/<model_id>/spec.json`        Immutable strategy/grid/signal specification & hypothesis
- `models/<model_id>/signal.py`        Optional standalone custom `build_signal(params)` plugin
- `models/<model_id>/latest_metrics.json` Latest backtest summary + crash stress metrics
- `models/<model_id>/runs/<run_id>.json`  Immutable full run audit record (pinned config SHA-256)
- `daily/<YYYY-MM-DD>/batch.json`      Daily batch (e.g., 5 models) side-by-side comparison
- `daily/<YYYY-MM-DD>/daily_summary.md` Concise Thai/English executive summary
- `daily/<YYYY-MM-DD>/dashboard.html`  Self-contained interactive HTML dashboard
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from ..strategy.lgb154 import SignalProvider, create_signal_provider
from .backtest_lgb154 import BacktestResult, compute_beta_and_corr

SCHEMA_VERSION = "1.0"
DEFAULT_MAX_DD_GATE_PCT = 40.0
DEFAULT_TOP_N = 9
_MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_json(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def validate_model_id(model_id: str) -> str:
    if not isinstance(model_id, str) or not _MODEL_ID_RE.fullmatch(model_id):
        raise ValueError(
            f"invalid model_id {model_id!r}: must match ^[a-z0-9][a-z0-9_-]{{0,63}}$"
        )
    return model_id


def validate_date_str(date_str: str) -> str:
    if not isinstance(date_str, str) or not _DATE_RE.fullmatch(date_str):
        raise ValueError(f"invalid date {date_str!r}: expected YYYY-MM-DD")
    return date_str


@dataclass(frozen=True)
class LoadedBetaModel:
    """Self-contained view of one isolated beta model folder."""

    model_id: str
    model_dir: Path
    spec: dict[str, Any]
    latest_metrics: dict[str, Any]
    run_files: tuple[Path, ...]
    has_custom_signal_py: bool


class BetaModelStore:
    """Easy-access SDK for isolated per-model Beta Mining storage & Top-9 Cashflow->DD ranking."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()
        self.models_dir = self.root_dir / "models"
        self.daily_dir = self.root_dir / "daily"
        self.catalog_path = self.root_dir / "catalog.json"
        self.ranking_path = self.root_dir / "ranking_top9.json"

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
                {
                    "schema_version": SCHEMA_VERSION,
                    "updated_at_utc": _now_utc_iso(),
                    "total_trials": 0,
                    "models": {},
                },
            )

    def load_catalog(self) -> dict[str, Any]:
        if not self.catalog_path.is_file():
            return {
                "schema_version": SCHEMA_VERSION,
                "updated_at_utc": _now_utc_iso(),
                "total_trials": 0,
                "models": {},
            }
        return json.loads(self.catalog_path.read_text(encoding="utf-8"))

    def record_model_run(
        self,
        *,
        model_id: str,
        batch_date: str,
        signal_spec: str,
        result: BacktestResult,
        crash_result: BacktestResult | None = None,
        hypothesis: str = "",
        tags: Sequence[str] = (),
        evidence_status: str = "reproducible",
        config_snapshot: dict[str, Any] | None = None,
        run_id: str | None = None,
        recorded_at_utc: str | None = None,
    ) -> dict[str, Any]:
        """Persist one model's spec, latest metrics, and immutable run record into its isolated folder."""
        self.ensure_initialized()
        mid = validate_model_id(model_id)
        bdate = validate_date_str(batch_date)
        ts = recorded_at_utc or _now_utc_iso()
        mdir = self._model_dir(mid)
        runs_dir = mdir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)

        catalog = self.load_catalog()
        existing_entry = (catalog.get("models") or {}).get(mid)
        if existing_entry and isinstance(existing_entry.get("trial_number"), int):
            trial_num = int(existing_entry["trial_number"])
        else:
            trial_num = int(catalog.get("total_trials", 0)) + 1
            catalog["total_trials"] = trial_num

        summary = result.summary_dict()
        realized_cf = float(result.realized_net_pnl)
        init_cap = float(result.initial_capital)
        cashflow_pct = (realized_cf / init_cap * 100.0) if init_cap > 0.0 else 0.0
        cashflow_per_30d = (realized_cf / max(result.days_covered, 1.0)) * 30.0
        max_dd_pct = float(result.max_drawdown_pct)
        cf_dd_ratio = (cashflow_pct / max_dd_pct) if max_dd_pct > 1e-9 else 0.0

        spec_payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "model_id": mid,
            "trial_number": trial_num,
            "category": "beta",
            "signal_spec": signal_spec,
            "signal_name": result.signal_name,
            "symbol": result.symbol,
            "product_type": result.product_type,
            "settlement_unit": result.settlement_unit,
            "zone_high": result.zone_high,
            "zone_low": result.zone_low,
            "spacing_pct": result.spacing_pct,
            "grid_levels_count": result.grid_levels_count,
            "initial_capital": result.initial_capital,
            "fill_mode": result.fill_mode,
            "hypothesis": hypothesis.strip() or f"Evaluate pluggable signal {signal_spec!r} on LGB154 grid.",
            "tags": sorted({str(t).strip() for t in tags if str(t).strip()}),
            "evidence_status": evidence_status,
            "config_snapshot": config_snapshot or {},
            "created_batch_date": (existing_entry or {}).get("created_batch_date", bdate),
            "updated_at_utc": ts,
        }
        spec_sha = _sha256_json(spec_payload)
        spec_payload["spec_sha256"] = spec_sha

        existing_runs = sorted(p.stem for p in runs_dir.glob("*.json"))
        resolved_run_id = run_id or f"{bdate}_run{len(existing_runs) + 1:02d}"

        crash_summary = crash_result.summary_dict() if crash_result is not None else None
        metrics_payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "model_id": mid,
            "trial_number": trial_num,
            "run_id": resolved_run_id,
            "batch_date": bdate,
            "recorded_at_utc": ts,
            "signal_spec": signal_spec,
            "signal_name": result.signal_name,
            "evidence_status": evidence_status,
            "spec_sha256": spec_sha,
            # Core ranking & dashboard fields
            "cashflow_net_usd": round(realized_cf, 6),
            "cashflow_pct": round(cashflow_pct, 4),
            "cashflow_per_30d_usd": round(cashflow_per_30d, 4),
            "max_drawdown_pct": round(max_dd_pct, 4),
            "max_drawdown_abs": round(float(result.max_drawdown_abs), 6),
            "cashflow_to_dd_ratio": round(cf_dd_ratio, 4),
            "would_liquidate": bool(result.would_liquidate),
            "liquidation_bar_utc": result.liquidation_bar_utc,
            # Full MTM & operational metrics
            "mtm_return_pct": round(float(result.total_mtm_return_pct), 4),
            "mtm_pnl_usd": round(float(result.total_mtm_pnl), 6),
            "unrealized_end_usd": round(float(result.unrealized_pnl_end), 6),
            "worst_unrealized_usd": round(float(result.worst_unrealized_pnl), 6),
            "total_fees_paid": round(float(result.total_fees_paid), 6),
            "total_funding_pnl": round(float(result.total_funding_pnl), 6),
            "sharpe_daily_ann": round(float(result.sharpe_daily_ann), 4),
            "sortino_daily_ann": round(float(result.sortino_daily_ann), 4),
            "calmar_ratio": round(float(result.calmar_ratio), 4),
            "buy_fills": int(result.buy_fills),
            "sell_fills": int(result.sell_fills),
            "closed_trades_count": int(result.closed_trades_count),
            "win_rate_pct": round(float(result.win_rate_pct), 2),
            "avg_hold_minutes": round(float(result.avg_hold_minutes), 2),
            "max_open_qty": round(float(result.max_open_qty), 6),
            "ending_open_qty": round(float(result.ending_open_qty), 6),
            "max_open_notional": round(float(result.max_open_notional), 2),
            "buy_volume_eth": round(float(result.buy_volume_eth), 6),
            "sell_volume_eth": round(float(result.sell_volume_eth), 6),
            "turnover_usd": round(float(result.turnover_usd), 2),
            "max_utilization_pct": round(float(result.max_utilization_pct), 2),
            "avg_weekly_cf_usd": round(float(result.avg_weekly_cf_usd), 4),
            "weekly_count": int(result.weekly_count),
            "beta_to_eth": round(float(result.beta_to_eth), 4),
            "corr_to_eth": round(float(result.corr_to_eth), 4),
            "window_start_utc": result.start_utc,
            "window_end_utc": result.end_utc,
            "days_covered": float(result.days_covered),
            "bar_count": int(result.bar_count),
            "zone_high": float(result.zone_high),
            "zone_low": float(result.zone_low),
            "spacing_pct": float(result.spacing_pct),
            "initial_capital": float(result.initial_capital),
            "fill_mode": result.fill_mode,
            "symbol": result.symbol,
            "product_type": result.product_type,
            "settlement_unit": result.settlement_unit,
            "crash_stress": (
                {
                    "window_start_utc": crash_summary["start_utc"],
                    "window_end_utc": crash_summary["end_utc"],
                    "zone_high": crash_summary["zone_high"],
                    "zone_low": crash_summary["zone_low"],
                    "mtm_return_pct": crash_summary["total_mtm_return_pct"],
                    "max_drawdown_pct": crash_summary["max_drawdown_pct"],
                    "max_drawdown_abs": crash_summary["max_drawdown_abs"],
                    "cashflow_net_usd": crash_summary["realized_net_pnl"],
                    "ending_open_qty": crash_summary["ending_open_qty"],
                    "would_liquidate": crash_summary["would_liquidate"],
                    "closed_trades_count": crash_summary["closed_trades_count"],
                }
                if crash_summary is not None
                else None
            ),
        }

        run_record = {
            "schema_version": SCHEMA_VERSION,
            "run_id": resolved_run_id,
            "model_id": mid,
            "batch_date": bdate,
            "recorded_at_utc": ts,
            "spec": spec_payload,
            "metrics": metrics_payload,
            "raw_summary": summary,
        }

        _atomic_write_json(mdir / "spec.json", spec_payload)
        _atomic_write_json(mdir / "latest_metrics.json", metrics_payload)
        if result.daily_series:
            _atomic_write_text(
                mdir / "latest_series.json",
                json.dumps(result.daily_series, separators=(",", ":"), ensure_ascii=False) + "\n",
            )
        _atomic_write_json(runs_dir / f"{resolved_run_id}.json", run_record)

        catalog.setdefault("models", {})[mid] = {
            "model_id": mid,
            "trial_number": trial_num,
            "folder": f"models/{mid}",
            "signal_spec": signal_spec,
            "signal_name": result.signal_name,
            "symbol": result.symbol,
            "product_type": result.product_type,
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

    def load_model(self, model_id: str) -> LoadedBetaModel:
        mdir = self._model_dir(model_id)
        spec_p = mdir / "spec.json"
        met_p = mdir / "latest_metrics.json"
        if not spec_p.is_file() or not met_p.is_file():
            raise FileNotFoundError(f"beta model {model_id!r} not found under {mdir}")
        runs_dir = mdir / "runs"
        run_files = tuple(sorted(runs_dir.glob("*.json"))) if runs_dir.is_dir() else ()
        return LoadedBetaModel(
            model_id=model_id,
            model_dir=mdir,
            spec=json.loads(spec_p.read_text(encoding="utf-8")),
            latest_metrics=json.loads(met_p.read_text(encoding="utf-8")),
            run_files=run_files,
            has_custom_signal_py=(mdir / "signal.py").is_file(),
        )

    def load_all_models(self) -> list[LoadedBetaModel]:
        return [self.load_model(mid) for mid in self.list_model_ids()]

    def load_series(self, model_id: str) -> dict[str, Any]:
        """Load the isolated daily/weekly time series for a single model (empty dict if absent)."""
        mdir = self._model_dir(model_id)
        sp = mdir / "latest_series.json"
        if not sp.is_file():
            return {}
        return json.loads(sp.read_text(encoding="utf-8"))

    def load_batch_series(self, model_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        """Load isolated time series for a set of models."""
        out: dict[str, dict[str, Any]] = {}
        for mid in model_ids:
            s = self.load_series(mid)
            if s:
                out[mid] = s
        return out

    def load_signal_provider(self, model_id: str) -> SignalProvider:
        """Load an isolated model's signal plugin (`models/<id>/signal.py` or built-in spec)."""
        loaded = self.load_model(model_id)
        custom_py = loaded.model_dir / "signal.py"
        if custom_py.is_file():
            mod_spec = importlib.util.spec_from_file_location(f"beta_signal_{loaded.model_id}", custom_py)
            if mod_spec is None or mod_spec.loader is None:
                raise ImportError(f"unable to load custom signal plugin: {custom_py}")
            mod = importlib.util.module_from_spec(mod_spec)
            mod_spec.loader.exec_module(mod)
            builder = getattr(mod, "build_signal", None)
            if not callable(builder):
                raise ValueError(f"{custom_py} must define callable build_signal(spec: dict) -> SignalProvider")
            return builder(loaded.spec)
        return create_signal_provider(str(loaded.spec["signal_spec"]))

    def compare_models(self, model_ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
        ids = list(model_ids) if model_ids is not None else self.list_model_ids()
        return [self.load_model(mid).latest_metrics for mid in ids]

    def compute_ranking(
        self,
        *,
        top_n: int = DEFAULT_TOP_N,
        max_dd_pct: float = DEFAULT_MAX_DD_GATE_PCT,
        rank_by: str = "cashflow_dd",
        write_file: bool = True,
    ) -> dict[str, Any]:
        """Compute Top-N Ranking Board: Primary = Net Realized Cashflow DESC, Secondary = Max DD % ASC.

        Hard Safety Gate: `not would_liquidate` AND `max_drawdown_pct <= max_dd_pct`.
        Disqualified models are preserved transparently in `disqualified` (never silently dropped).
        """
        if rank_by not in {"cashflow_dd", "efficiency", "mtm"}:
            raise ValueError(f"unsupported rank_by {rank_by!r}; expected cashflow_dd, efficiency, or mtm")
        if top_n < 1:
            raise ValueError("top_n must be >= 1")

        all_metrics = [m.latest_metrics for m in self.load_all_models()]
        qualified: list[dict[str, Any]] = []
        disqualified: list[dict[str, Any]] = []

        for m in all_metrics:
            reasons: list[str] = []
            if bool(m.get("would_liquidate")):
                reasons.append("LIQUIDATED")
            dd_val = float(m.get("max_drawdown_pct", 0.0))
            if dd_val > max_dd_pct:
                reasons.append(f"MAX_DD_EXCEEDS_{max_dd_pct:g}PCT")

            entry = dict(m)
            entry["gate_passed"] = len(reasons) == 0
            entry["disqualify_reasons"] = reasons
            if entry["gate_passed"]:
                qualified.append(entry)
            else:
                disqualified.append(entry)

        def _sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
            cf = float(item.get("cashflow_net_usd", 0.0))
            dd = float(item.get("max_drawdown_pct", 0.0))
            eff = float(item.get("cashflow_to_dd_ratio", 0.0))
            mtm = float(item.get("mtm_return_pct", 0.0))
            mid = str(item.get("model_id", ""))
            if rank_by == "cashflow_dd":
                # Primary: Highest Cashflow DESC, Secondary: Lowest Max DD ASC
                return (-round(cf, 6), round(dd, 6), mid)
            if rank_by == "efficiency":
                return (-round(eff, 6), -round(cf, 6), round(dd, 6), mid)
            return (-round(mtm, 6), round(dd, 6), mid)

        qualified.sort(key=_sort_key)
        disqualified.sort(key=_sort_key)

        ranked_top: list[dict[str, Any]] = []
        for idx, item in enumerate(qualified[:top_n], start=1):
            row = dict(item)
            row["rank"] = idx
            ranked_top.append(row)

        catalog = self.load_catalog()
        board: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "generated_at_utc": _now_utc_iso(),
            "ranking_rule": {
                "primary": "cashflow_net_usd DESC" if rank_by == "cashflow_dd" else rank_by,
                "secondary": "max_drawdown_pct ASC",
                "rank_by": rank_by,
                "top_n": top_n,
                "hard_gates": {
                    "forbid_liquidation": True,
                    "max_drawdown_pct_limit": max_dd_pct,
                },
            },
            "total_trials": int(catalog.get("total_trials", len(all_metrics))),
            "total_models": len(all_metrics),
            "qualified_count": len(qualified),
            "disqualified_count": len(disqualified),
            "top_ranked": ranked_top,
            "disqualified": disqualified,
        }
        if write_file:
            self.ensure_initialized()
            _atomic_write_json(self.ranking_path, board)
        return board

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
        """Write immutable daily comparison JSON, Markdown summary, and interactive HTML dashboard."""
        bdate = validate_date_str(batch_date)
        ddir = self.daily_dir / bdate
        ddir.mkdir(parents=True, exist_ok=True)

        top_rank_map = {r["model_id"]: r["rank"] for r in ranking_board.get("top_ranked", [])}
        batch_rows = []
        for m in batch_metrics:
            row = dict(m)
            row["current_top9_rank"] = top_rank_map.get(m["model_id"])
            batch_rows.append(row)

        batch_payload = {
            "schema_version": SCHEMA_VERSION,
            "batch_date": bdate,
            "generated_at_utc": _now_utc_iso(),
            "model_count": len(batch_rows),
            "loader": loader_meta or {},
            "models": batch_rows,
            "ranking_snapshot_top_n": ranking_board.get("ranking_rule", {}).get("top_n", DEFAULT_TOP_N),
        }
        _atomic_write_json(ddir / "batch.json", batch_payload)
        _atomic_write_text(ddir / "daily_summary.md", summary_markdown)
        _atomic_write_text(ddir / "dashboard.html", dashboard_html)
        return ddir


def compute_return_correlation_matrix(
    model_ids: Sequence[str],
    series_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compute pairwise Pearson correlation matrix across all daily batch models + ETH benchmark."""
    ordered_ids = [mid for mid in model_ids if mid in series_by_id and series_by_id[mid].get("daily_returns")]
    if not ordered_ids:
        return {"labels": [], "matrix": []}

    vectors: list[tuple[str, list[float]]] = [
        (mid, [float(x) for x in series_by_id[mid]["daily_returns"]]) for mid in ordered_ids
    ]
    eth_vec = [float(x) for x in (series_by_id[ordered_ids[0]].get("eth_daily_returns") or [])]
    if eth_vec:
        vectors.append(("ETH", eth_vec))

    labels = [name for name, _ in vectors]
    matrix: list[list[float]] = []
    for i, (_, vi) in enumerate(vectors):
        row: list[float] = []
        for j, (_, vj) in enumerate(vectors):
            if i == j:
                row.append(1.0)
            else:
                _, corr = compute_beta_and_corr(vi, vj)
                row.append(round(corr, 3))
        matrix.append(row)
    return {"labels": labels, "matrix": matrix}
