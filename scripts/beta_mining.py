#!/usr/bin/env python3
"""Daily Beta Mining Factory CLI — 2 rounds/day x 5 isolated models (10/day), compare, rank Top-9 (Cashflow->DD), and build dashboard.html."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = REPO_ROOT / "python"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from alpha_mining.research.backtest_lgb154 import (  # noqa: E402
    BacktestOptions,
    find_worst_crash_window,
    run_lgb154_backtest,
)
from alpha_mining.research.beta_dashboard import (  # noqa: E402
    render_daily_summary_markdown,
    render_dashboard_html,
    render_portal_index_html,
)
from alpha_mining.research.beta_store import (  # noqa: E402
    BetaModelStore,
    DEFAULT_MAX_DD_GATE_PCT,
    DEFAULT_TOP_N,
    compute_return_correlation_matrix,
    merge_batch_models,
)
from alpha_mining.research.kline_loader import (  # noqa: E402
    fetch_binance_vision_funding_rates,
    fetch_binance_vision_klines,
    fetch_data_api_spot_klines,
    load_local_klines,
)
from alpha_mining.strategy.lgb154 import (  # noqa: E402
    Lgb154Config,
    RpRange,
    build_grid_levels,
    create_signal_provider,
)

DEFAULT_STORE_DIR = REPO_ROOT / "beta_mining"
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "cache" / "binance_vision"


def _slugify_signal(sig_spec: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", sig_spec.strip().lower()).strip("_")


def _build_grid_cfg(
    *,
    profile: str,
    symbol: str | None,
    high: float,
    low: float,
    spacing_pct: float,
    max_position_qty: float,
    max_notional: float,
    order_qty: float | None = None,
) -> Lgb154Config:
    base = Lgb154Config.ethusd_coinm_default() if profile == "coinm" else Lgb154Config.ethusdt_usdm_default()
    d_high = Decimal(str(high))
    d_low = Decimal(str(low))
    d_spacing = Decimal(str(spacing_pct))
    d_max_pos = Decimal(str(max_position_qty))
    d_order_qty = Decimal(str(order_qty)) if order_qty is not None else base.order_quantity
    levels = build_grid_levels(d_high, d_low, d_spacing, base.tick_size)
    req_entry = base.quote_notional(d_order_qty, d_high)
    d_entry_cap = max(base.max_entry_order_notional_usdt, req_entry)
    d_max_not = max(Decimal(str(max_notional)), base.quote_notional(d_max_pos, d_high))
    return replace(
        base,
        symbol=symbol.upper() if symbol else base.symbol,
        high=d_high,
        low=d_low,
        spacing_pct=d_spacing,
        order_quantity=d_order_qty,
        max_entry_order_quantity=max(base.max_entry_order_quantity, d_order_qty),
        max_entry_order_notional_usdt=d_entry_cap,
        max_position_quantity=d_max_pos,
        max_notional_usdt=d_max_not,
        rp_ranges=(
            RpRange(
                from_grid=0,
                to_grid=levels[-1][0],
                rp_id=base.rp_ranges[0].rp_id,
                max_quantity=d_max_pos,
                max_notional_usdt=d_max_not,
            ),
        ),
    )


DEFAULT_SIGNALS = "ha_1m,ema_9_21,ema_12_26,supertrend_10_3,rsi_reversion_14_40_60"


def select_next_queue_batch(
    queue_path: Path,
    store: BetaModelStore,
    *,
    batch_size: int | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Select the next `batch_size` unmined candidate specs from a daily queue JSON file.

    Falls back to refreshing the current top `batch_size` models once all queued candidates
    have been mined, so scheduled daily runs remain resilient without manual intervention.
    """
    raw = json.loads(queue_path.read_text(encoding="utf-8"))
    candidates = raw.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise SystemExit(f"queue-file {queue_path} must contain a non-empty 'candidates' list")
    limit = int(batch_size or raw.get("models_per_round", raw.get("models_per_day", 5)))
    if limit < 1:
        raise SystemExit("batch-size must be >= 1")

    catalog = store.load_catalog()
    existing = catalog.get("models", {})
    existing_specs = {str(info.get("signal_spec", "")).strip() for info in existing.values()}
    next_idx = int(catalog.get("total_trials", 0))

    unmined = [c for c in candidates if str(c.get("signal_spec", "")).strip() not in existing_specs]
    if unmined:
        picked = unmined[:limit]
        out: list[dict[str, Any]] = []
        for entry in picked:
            sig = str(entry["signal_spec"]).strip()
            slug = _slugify_signal(sig)
            next_idx += 1
            mid = f"beta_{next_idx:03d}_{slug}"[:64]
            tags = ["beta_mining"]
            if entry.get("theme"):
                tags.append(str(entry["theme"]))
            out.append(
                {
                    "model_id": mid,
                    "signal_spec": sig,
                    "hypothesis": str(entry.get("hypothesis", "")),
                    "tags": tags,
                }
            )
        return out, "queue_unmined"

    # All queued candidates are already mined -> refresh current top leaders on the rolling window.
    board = store.compute_ranking(top_n=max(limit, DEFAULT_TOP_N), max_dd_pct=DEFAULT_MAX_DD_GATE_PCT, write_file=False)
    top_rows = board.get("top_ranked") or []
    refresh_ids = [str(r["model_id"]) for r in top_rows[:limit]]
    if not refresh_ids:
        refresh_ids = list(existing.keys())[:limit]
    out_refresh: list[dict[str, Any]] = []
    for mid in refresh_ids:
        info = existing.get(mid, {})
        sig = str(info.get("signal_spec", "")).strip()
        if sig:
            out_refresh.append(
                {
                    "model_id": mid,
                    "signal_spec": sig,
                    "hypothesis": f"Rolling-window refresh of top-ranked model {mid}.",
                    "tags": ["beta_mining", "rolling_refresh"],
                }
            )
    if not out_refresh:
        raise SystemExit("unable to resolve fallback refresh models from store")
    return out_refresh, "top_leaders_refresh"


def _load_batch_specs(args: argparse.Namespace, store: BetaModelStore) -> list[dict[str, Any]]:
    if args.batch_file is not None:
        raw = json.loads(args.batch_file.read_text(encoding="utf-8"))
        entries = raw.get("models", raw) if isinstance(raw, dict) else raw
        if not isinstance(entries, list) or not entries:
            raise SystemExit("batch-file must contain a non-empty list of model definitions")
        return [dict(e) for e in entries]

    raw_signals = (args.signals or "").strip()
    if not raw_signals and args.queue_file is not None:
        specs, mode = select_next_queue_batch(args.queue_file, store, batch_size=args.batch_size)
        print(f"Selected {len(specs)} models from {args.queue_file} (mode={mode}): {[s['signal_spec'] for s in specs]}")
        return specs

    sig_specs = [s.strip() for s in (raw_signals or DEFAULT_SIGNALS).split(",") if s.strip()]
    if not sig_specs:
        raise SystemExit("provide --signals, --queue-file, or --batch-file")
    catalog = store.load_catalog()
    existing = catalog.get("models", {})
    next_idx = int(catalog.get("total_trials", 0))
    out: list[dict[str, Any]] = []
    for sig in sig_specs:
        slug = _slugify_signal(sig)
        matched = next((mid for mid, info in existing.items() if info.get("signal_spec") == sig), None)
        if matched:
            mid = matched
        else:
            next_idx += 1
            mid = f"beta_{next_idx:03d}_{slug}"[:64]
        out.append({"model_id": mid, "signal_spec": sig})
    return out


def _cmd_run_daily(args: argparse.Namespace) -> int:
    store = BetaModelStore(args.store_dir)
    store.ensure_initialized()

    batch_date = args.date or datetime.now(timezone.utc).date().isoformat()

    # Same-day multi-round accumulation: Round 2 merges into (never overwrites) Round 1.
    existing_day_models = store.load_daily_batch_models(batch_date)
    existing_rounds = sorted({int(m.get("round_no") or 1) for m in existing_day_models})
    if args.round:
        round_no = int(args.round)
    else:
        if existing_day_models and len(existing_rounds) >= args.max_rounds:
            print(
                f"Batch {batch_date} already has {len(existing_rounds)} round(s) "
                f"({len(existing_day_models)} models) >= --max-rounds {args.max_rounds}; nothing to mine."
            )
            return 0
        round_no = (max(existing_rounds) + 1) if existing_rounds else 1

    cfg = _build_grid_cfg(
        profile=args.profile,
        symbol=args.symbol,
        high=args.high,
        low=args.low,
        spacing_pct=args.spacing_pct,
        max_position_qty=args.max_position_qty,
        max_notional=args.max_notional,
        order_qty=args.order_qty,
    )
    market = args.market or ("cm" if cfg.is_coinm else "um")
    end_d = date.fromisoformat(args.end_date) if args.end_date else (datetime.now(timezone.utc).date() - timedelta(days=1))
    start_d = date.fromisoformat(args.start_date) if args.start_date else (end_d - timedelta(days=max(1, args.days) - 1))

    funding_rates: dict[int, float] = {}
    loader_meta: dict[str, Any] = {"source": args.source, "market": market, "round_no": round_no}
    if args.source == "local":
        if args.local_path is None:
            raise SystemExit("--local-path is required when --source=local")
        bars = load_local_klines(args.local_path)
        loader_meta["path"] = str(args.local_path)
    elif args.source == "data-api":
        start_ms = int(datetime(start_d.year, start_d.month, start_d.day, tzinfo=timezone.utc).timestamp() * 1000)
        end_ms = int(datetime(end_d.year, end_d.month, end_d.day, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
        bars = fetch_data_api_spot_klines(symbol=cfg.symbol, start_ms=start_ms, end_ms=end_ms)
    else:
        bars, stats = fetch_binance_vision_klines(
            symbol=cfg.symbol,
            interval="1m",
            market=market,
            start_date=start_d,
            end_date=end_d,
            cache_dir=args.cache_dir,
        )
        loader_meta.update(stats)
        if not args.no_funding and market in {"um", "cm"}:
            funding_rates = fetch_binance_vision_funding_rates(
                symbol=cfg.symbol,
                market=market,
                start_date=start_d,
                end_date=end_d,
                cache_dir=args.cache_dir,
            )
            loader_meta["historical_funding_points"] = len(funding_rates)

    if len(bars) < 2:
        raise SystemExit(f"insufficient bars loaded ({len(bars)})")

    opt = BacktestOptions(
        initial_capital=Decimal(str(args.initial_capital)),
        fill_mode=args.fill_mode,
        use_funding=not args.no_funding,
        record_trades=False,
        recovery_mode=args.recovery_mode,
    )

    crash_bars = None
    stress_cfg = None
    if args.stress_crash_days > 0 and len(bars) >= 120:
        s_idx, e_idx, _drop = find_worst_crash_window(bars, window_days=args.stress_crash_days)
        crash_bars = bars[s_idx : e_idx + 1]
        peak = max(b.high for b in crash_bars[: min(300, len(crash_bars))])
        s_high = Decimal(f"{peak:.2f}")
        s_low = Decimal(f"{peak * 0.80:.2f}")
        s_levels = build_grid_levels(s_high, s_low, cfg.spacing_pct, cfg.tick_size)
        s_entry_cap = max(cfg.max_entry_order_notional_usdt, cfg.quote_notional(cfg.order_quantity, s_high))
        s_not_cap = max(cfg.max_notional_usdt, cfg.quote_notional(cfg.max_position_quantity, s_high))
        stress_cfg = replace(
            cfg,
            high=s_high,
            low=s_low,
            max_entry_order_notional_usdt=s_entry_cap,
            max_notional_usdt=s_not_cap,
            rp_ranges=(
                RpRange(
                    from_grid=0,
                    to_grid=s_levels[-1][0],
                    rp_id=cfg.rp_ranges[0].rp_id,
                    max_quantity=cfg.max_position_quantity,
                    max_notional_usdt=s_not_cap,
                ),
            ),
        )

    batch_specs = _load_batch_specs(args, store)
    batch_metrics: list[dict[str, Any]] = []
    for item in batch_specs:
        mid = str(item["model_id"])
        sig_spec = str(item["signal_spec"])
        sp = create_signal_provider(sig_spec)
        res = run_lgb154_backtest(bars, cfg, signal_provider=sp, options=opt, funding_rates_8h=funding_rates)

        crash_res = None
        if crash_bars is not None and stress_cfg is not None:
            sp_crash = create_signal_provider(sig_spec)
            crash_res = run_lgb154_backtest(
                crash_bars, stress_cfg, signal_provider=sp_crash, options=opt, funding_rates_8h=funding_rates
            )

        rec = store.record_model_run(
            model_id=mid,
            batch_date=batch_date,
            signal_spec=sig_spec,
            result=res,
            crash_result=crash_res,
            hypothesis=str(item.get("hypothesis", "")),
            round_no=round_no,
            tags=item.get("tags", ("beta_mining",)),
            config_snapshot={
                "profile": args.profile,
                "high": str(cfg.high),
                "low": str(cfg.low),
                "spacing_pct": str(cfg.spacing_pct),
                "order_quantity": str(cfg.order_quantity),
                "max_position_quantity": str(cfg.max_position_quantity),
                "max_notional_usdt": str(cfg.max_notional_usdt),
                "initial_capital": str(opt.initial_capital),
                "recovery_mode": opt.recovery_mode,
                "fill_mode": opt.fill_mode,
            },
        )
        batch_metrics.append(rec)

    round_metrics = list(batch_metrics)
    batch_metrics = merge_batch_models(existing_day_models, round_metrics)
    print(
        f"Round {round_no} mined {len(round_metrics)} model(s); "
        f"{batch_date} batch now holds {len(batch_metrics)} model(s)."
    )

    board = store.compute_ranking(
        top_n=args.top_n,
        max_dd_pct=args.max_dd_gate,
        rank_by="cashflow_dd",
        write_file=True,
    )
    all_metrics = [m.latest_metrics for m in store.load_all_models()]
    batch_ids = [m["model_id"] for m in batch_metrics]
    batch_series = store.load_batch_series(batch_ids)
    corr_matrix = compute_return_correlation_matrix(batch_ids, batch_series)
    existing_days = store.load_daily_batches_summary(max_dd_pct=args.max_dd_gate)
    summary_md = render_daily_summary_markdown(
        batch_date=batch_date, batch_metrics=batch_metrics, ranking_board=board
    )
    dash_html = render_dashboard_html(
        batch_date=batch_date,
        batch_metrics=batch_metrics,
        all_models_metrics=all_metrics,
        ranking_board=board,
        batch_series=batch_series,
        corr_matrix=corr_matrix,
        available_dates=existing_days,
    )
    ddir = store.save_daily_batch(
        batch_date=batch_date,
        batch_metrics=batch_metrics,
        ranking_board=board,
        summary_markdown=summary_md,
        dashboard_html=dash_html,
        loader_meta=loader_meta,
    )
    daily_days = store.load_daily_batches_summary(max_dd_pct=args.max_dd_gate)
    portal_html = render_portal_index_html(
        daily_days=daily_days,
        ranking_board=board,
        latest_date=daily_days[0]["batch_date"] if daily_days else batch_date,
    )
    portal_path = store.write_portal_index(portal_html)
    print(summary_md)
    print(f"Saved isolated models under: {store.models_dir}")
    print(f"Saved Top-{args.top_n} Ranking Board: {store.ranking_path}")
    print(f"Saved Daily Dashboard HTML: {ddir / 'dashboard.html'}")
    print(f"Saved Daily Index JSON: {store.daily_index_path}")
    print(f"Saved Archive Hub HTML: {portal_path}")
    return 0


def _cmd_rank(args: argparse.Namespace) -> int:
    store = BetaModelStore(args.store_dir)
    board = store.compute_ranking(
        top_n=args.top,
        max_dd_pct=args.max_dd,
        rank_by=args.rank_by,
        write_file=args.save,
    )
    if args.json:
        print(json.dumps(board, indent=2, ensure_ascii=False))
        return 0
    print(
        render_daily_summary_markdown(
            batch_date=datetime.now(timezone.utc).date().isoformat(),
            batch_metrics=[],
            ranking_board=board,
        )
    )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    store = BetaModelStore(args.store_dir)
    loaded = store.load_model(args.model_id)
    print(
        json.dumps(
            {
                "model_id": loaded.model_id,
                "folder": str(loaded.model_dir),
                "has_custom_signal_py": loaded.has_custom_signal_py,
                "run_count": len(loaded.run_files),
                "spec": loaded.spec,
                "latest_metrics": loaded.latest_metrics,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    store = BetaModelStore(args.store_dir)
    ids = [x.strip() for x in args.models.split(",") if x.strip()] if args.models else None
    metrics = store.compare_models(ids)
    board = store.compute_ranking(top_n=DEFAULT_TOP_N, max_dd_pct=DEFAULT_MAX_DD_GATE_PCT, write_file=False)
    print(
        render_daily_summary_markdown(
            batch_date=datetime.now(timezone.utc).date().isoformat(),
            batch_metrics=metrics,
            ranking_board=board,
        )
    )
    return 0


def _rebuild_one_daily_date(
    store: BetaModelStore,
    *,
    bdate: str,
    all_metrics: list[dict[str, Any]],
    board: dict[str, Any],
    available_dates: list[dict[str, Any]],
) -> Path:
    existing_batch = store.load_daily_batch(bdate)
    if existing_batch and isinstance(existing_batch.get("models"), list) and existing_batch["models"]:
        batch_metrics = [dict(m) for m in existing_batch["models"]]
        loader_meta = existing_batch.get("loader") if isinstance(existing_batch.get("loader"), dict) else None
    else:
        batch_metrics = [m for m in all_metrics if m.get("batch_date") == bdate] or all_metrics
        loader_meta = None
    batch_ids = [m["model_id"] for m in batch_metrics]
    batch_series = store.load_batch_series(batch_ids)
    corr_matrix = compute_return_correlation_matrix(batch_ids, batch_series)
    summary_md = render_daily_summary_markdown(
        batch_date=bdate, batch_metrics=batch_metrics, ranking_board=board
    )
    dash_html = render_dashboard_html(
        batch_date=bdate,
        batch_metrics=batch_metrics,
        all_models_metrics=all_metrics,
        ranking_board=board,
        batch_series=batch_series,
        corr_matrix=corr_matrix,
        available_dates=available_dates,
    )
    return store.save_daily_batch(
        batch_date=bdate,
        batch_metrics=batch_metrics,
        ranking_board=board,
        summary_markdown=summary_md,
        dashboard_html=dash_html,
        loader_meta=loader_meta,
    )


def _cmd_rebuild_dashboard(args: argparse.Namespace) -> int:
    store = BetaModelStore(args.store_dir)
    board = store.compute_ranking(top_n=args.top_n, max_dd_pct=args.max_dd_gate, write_file=True)
    all_metrics = [m.latest_metrics for m in store.load_all_models()]
    available_dates = store.load_daily_batches_summary(max_dd_pct=args.max_dd_gate)

    if args.all_dates:
        target_dates = store.list_daily_dates()
        if not target_dates:
            target_dates = [args.date or datetime.now(timezone.utc).date().isoformat()]
    else:
        target_dates = [args.date or (available_dates[0]["batch_date"] if available_dates else datetime.now(timezone.utc).date().isoformat())]

    rebuilt_paths: list[Path] = []
    for bdate in target_dates:
        ddir = _rebuild_one_daily_date(
            store,
            bdate=bdate,
            all_metrics=all_metrics,
            board=board,
            available_dates=available_dates,
        )
        rebuilt_paths.append(ddir / "dashboard.html")

    daily_days = store.load_daily_batches_summary(max_dd_pct=args.max_dd_gate)
    portal_html = render_portal_index_html(
        daily_days=daily_days,
        ranking_board=board,
        latest_date=daily_days[0]["batch_date"] if daily_days else target_dates[-1],
    )
    portal_path = store.write_portal_index(portal_html)
    for p in rebuilt_paths:
        print(f"Rebuilt dashboard: {p}")
    print(f"Rebuilt daily index: {store.daily_index_path}")
    print(f"Rebuilt archive hub: {portal_path}")
    return 0


def _cmd_list_dates(args: argparse.Namespace) -> int:
    store = BetaModelStore(args.store_dir)
    days = store.load_daily_batches_summary(max_dd_pct=args.max_dd_gate)
    payload = {
        "total_days": len(days),
        "latest_date": days[0]["batch_date"] if days else "",
        "dates": [d["batch_date"] for d in days],
        "days": days,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if not days:
        print("No archived daily batches found.")
        return 0
    print(f"Archived daily batches ({len(days)} days, newest-first):")
    for d in days:
        print(
            f"  - {d['batch_date']}: {d['model_count']} models "
            f"(pass {d['qualified_count']}/{d['model_count']}) | "
            f"best CF {d['best_cashflow_usd']:+.2f} ({d['best_cashflow_model_id']}) | "
            f"low DD {d['lowest_dd_pct']:.2f}% -> {d['dashboard_rel_path']}"
        )
    return 0


def _cmd_next_batch(args: argparse.Namespace) -> int:
    store = BetaModelStore(args.store_dir)
    specs, mode = select_next_queue_batch(args.queue_file, store, batch_size=args.batch_size)
    payload = {
        "queue_file": str(args.queue_file),
        "selection_mode": mode,
        "count": len(specs),
        "models": specs,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print(f"Next batch ({mode}, {len(specs)} models):")
    for idx, item in enumerate(specs, start=1):
        print(f"  {idx}. {item['model_id']} ({item['signal_spec']}) — {item.get('hypothesis', '')}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Daily Beta Mining Factory — isolated per-model store, Top-9 Cashflow->DD board, and HTML Dashboard."
    )
    parser.add_argument("--store-dir", type=Path, default=DEFAULT_STORE_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    rd = sub.add_parser("run-daily", help="Run a daily batch of models, save isolated folders, update Top-9, build dashboard.html.")
    rd.add_argument("--date", default=None, help="Batch date YYYY-MM-DD (default: today UTC).")
    rd.add_argument("--batch-file", type=Path, default=None, help="Optional JSON batch spec file.")
    rd.add_argument("--queue-file", type=Path, default=None, help="Optional daily mining queue JSON file (auto-selects next unmined models).")
    rd.add_argument("--batch-size", type=int, default=5, help="Number of models to draw per round when using --queue-file (default: 5).")
    rd.add_argument("--round", type=int, default=0, help="Round number within the day (default: auto = next round after those already saved for --date).")
    rd.add_argument("--max-rounds", type=int, default=2, help="Auto mode only: skip when the date already has this many rounds (default: 2).")
    rd.add_argument(
        "--signals",
        default=None,
        help="Comma-separated signal specs (overrides --queue-file; defaults to 5 Day-1 baseline signals if neither is given).",
    )
    rd.add_argument("--profile", choices=["usdm", "coinm"], default="usdm")
    rd.add_argument("--symbol", default=None)
    rd.add_argument("--source", choices=["vision", "data-api", "local"], default="vision")
    rd.add_argument("--market", choices=["um", "cm", "spot"], default=None)
    rd.add_argument("--local-path", type=Path, default=None)
    rd.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    rd.add_argument("--days", type=int, default=1000)
    rd.add_argument("--start-date", default=None)
    rd.add_argument("--end-date", default=None)
    rd.add_argument("--high", type=float, default=5000.0)
    rd.add_argument("--low", type=float, default=500.0)
    rd.add_argument("--spacing-pct", type=float, default=0.20)
    rd.add_argument("--order-qty", type=float, default=None)
    rd.add_argument("--max-position-qty", type=float, default=2.0)
    rd.add_argument("--max-notional", type=float, default=10000.0)
    rd.add_argument("--initial-capital", type=float, default=10000.0)
    rd.add_argument("--fill-mode", choices=["strict_cross", "touch"], default="strict_cross")
    rd.add_argument("--recovery-mode", choices=["partial_only", "legacy_v3"], default="partial_only")
    rd.add_argument("--no-funding", action="store_true")
    rd.add_argument("--stress-crash-days", type=int, default=30)
    rd.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    rd.add_argument("--max-dd-gate", type=float, default=DEFAULT_MAX_DD_GATE_PCT)

    nb = sub.add_parser("next-batch", help="Preview the next N unmined models from a daily mining queue JSON.")
    nb.add_argument("--queue-file", type=Path, default=REPO_ROOT / "config" / "beta_mining" / "daily_queue.json")
    nb.add_argument("--batch-size", type=int, default=5)
    nb.add_argument("--json", action="store_true")

    rk = sub.add_parser("rank", help="Display cumulative Top-N Ranking Board.")
    rk.add_argument("--top", type=int, default=DEFAULT_TOP_N)
    rk.add_argument("--max-dd", type=float, default=DEFAULT_MAX_DD_GATE_PCT)
    rk.add_argument("--rank-by", choices=["cashflow_dd", "efficiency", "mtm"], default="cashflow_dd")
    rk.add_argument("--save", action="store_true", help="Persist updated ranking_top9.json.")
    rk.add_argument("--json", action="store_true")

    sh = sub.add_parser("show", help="Inspect one isolated model folder.")
    sh.add_argument("model_id")

    cp = sub.add_parser("compare", help="Compare specified or all isolated models.")
    cp.add_argument("--models", default=None, help="Comma-separated model_ids (default: all).")

    rb = sub.add_parser("rebuild-dashboard", help="Rebuild dashboard.html, daily/index.json, and beta_mining/index.html.")
    rb.add_argument("--date", default=None)
    rb.add_argument("--all-dates", action="store_true", help="Rebuild every historical daily dashboard with updated date switcher index.")
    rb.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    rb.add_argument("--max-dd-gate", type=float, default=DEFAULT_MAX_DD_GATE_PCT)

    ld = sub.add_parser("list-dates", help="List archived historical daily mining batches (newest-first).")
    ld.add_argument("--max-dd-gate", type=float, default=DEFAULT_MAX_DD_GATE_PCT)
    ld.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "run-daily":
        return _cmd_run_daily(args)
    if args.command == "next-batch":
        return _cmd_next_batch(args)
    if args.command == "rank":
        return _cmd_rank(args)
    if args.command == "show":
        return _cmd_show(args)
    if args.command == "compare":
        return _cmd_compare(args)
    if args.command == "rebuild-dashboard":
        return _cmd_rebuild_dashboard(args)
    if args.command == "list-dates":
        return _cmd_list_dates(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
