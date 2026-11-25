#!/usr/bin/env python3
"""Daily Alpha Mining Factory CLI — 2 rounds/day x 10 models (5 XAUUSD + 5 ETHUSDT = 20/day).

Multi-timeframe causal directional/tactical Alpha backtesting across XAUUSD & ETHUSDT,
isolated per-model storage, cumulative Top-9 OOS Sharpe->DD board with DSR multiple-testing
haircut, and self-contained offline 9-panel HTML dashboard + archive hub.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = REPO_ROOT / "python"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from alpha_mining.research.alpha_backtest import AlphaBacktestOptions, run_alpha_backtest  # noqa: E402
from alpha_mining.research.alpha_dashboard import (  # noqa: E402
    render_daily_summary_markdown,
    render_dashboard_html,
    render_portal_index_html,
)
from alpha_mining.research.alpha_data import ASSETS, load_asset_series  # noqa: E402
from alpha_mining.research.alpha_signals import build_positions  # noqa: E402
from alpha_mining.research.alpha_spec import AlphaSpec, KNOWN_SYMBOLS, make_model_id, parse_spec  # noqa: E402
from alpha_mining.research.alpha_store import (  # noqa: E402
    AlphaModelStore,
    DEFAULT_MAX_DD_GATE_PCT,
    DEFAULT_MIN_TRADES,
    DEFAULT_TOP_N,
    merge_batch_models,
)

DEFAULT_STORE_DIR = REPO_ROOT / "alpha_mining"
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "cache" / "binance_vision"
DEFAULT_QUEUE_FILE = REPO_ROOT / "config" / "alpha_mining" / "daily_queue.json"


def select_next_queue_batch(
    queue_path: Path,
    store: AlphaModelStore,
    *,
    per_symbol: int | None = None,
    symbols: tuple[str, ...] = KNOWN_SYMBOLS,
) -> tuple[list[dict[str, Any]], str]:
    """Select the next ``per_symbol`` unmined candidates for EACH symbol (default 5 XAUUSD + 5 ETHUSDT = 10/round).

    When a symbol's unmined candidates run out, gracefully refreshes that symbol's current top leaders
    so scheduled rounds stay resilient without manual intervention.
    """
    raw = json.loads(queue_path.read_text(encoding="utf-8"))
    raw_candidates = raw.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise SystemExit(f"queue-file {queue_path} must contain a non-empty 'candidates' list")

    quota = int(per_symbol or raw.get("models_per_symbol_per_round", 5))
    if quota < 1:
        raise SystemExit("per-symbol quota must be >= 1")

    catalog = store.load_catalog()
    existing_models = catalog.get("models", {})
    mined_keys = {str(info.get("spec_key", "")) for info in existing_models.values()}
    next_idx = int(catalog.get("total_trials", 0))

    parsed_by_sym: dict[str, list[AlphaSpec]] = {sym: [] for sym in symbols}
    for entry in raw_candidates:
        spec = parse_spec(entry)
        if spec.symbol in parsed_by_sym and spec.key() not in mined_keys:
            parsed_by_sym[spec.symbol].append(spec)

    selected: list[dict[str, Any]] = []
    modes: set[str] = set()

    for sym in symbols:
        unmined = parsed_by_sym[sym][:quota]
        for spec in unmined:
            next_idx += 1
            selected.append({"model_id": make_model_id(next_idx, spec), "spec": spec})
            modes.add("queue_unmined")

        shortfall = quota - len(unmined)
        if shortfall > 0:
            board = store.compute_ranking(
                top_n=max(shortfall, DEFAULT_TOP_N),
                max_dd_pct=DEFAULT_MAX_DD_GATE_PCT,
                min_trades=DEFAULT_MIN_TRADES,
                write_file=False,
            )
            sym_leaders = (board.get("top_ranked_by_symbol") or {}).get(sym) or []
            refresh_ids = [str(r["model_id"]) for r in sym_leaders[:shortfall]]
            if len(refresh_ids) < shortfall:
                fallback = [
                    mid
                    for mid, info in existing_models.items()
                    if info.get("symbol") == sym and mid not in refresh_ids
                ]
                refresh_ids.extend(fallback[: shortfall - len(refresh_ids)])
            for mid in refresh_ids:
                spec_doc = store.load_spec(mid)
                selected.append({"model_id": mid, "spec": parse_spec(spec_doc)})
                modes.add("top_leaders_refresh")

    if not selected:
        raise SystemExit("unable to resolve alpha mining batch from queue or store")
    mode = "+".join(sorted(modes)) if len(modes) > 1 else next(iter(modes))
    return selected, mode


def _load_batch_specs(args: argparse.Namespace, store: AlphaModelStore) -> list[dict[str, Any]]:
    if args.batch_file is not None:
        raw = json.loads(args.batch_file.read_text(encoding="utf-8"))
        entries = raw.get("models", raw) if isinstance(raw, dict) else raw
        if not isinstance(entries, list) or not entries:
            raise SystemExit("batch-file must contain a non-empty list")
        catalog = store.load_catalog()
        existing = catalog.get("models", {})
        by_key = {str(info.get("spec_key", "")): mid for mid, info in existing.items()}
        next_idx = int(catalog.get("total_trials", 0))
        out: list[dict[str, Any]] = []
        for entry in entries:
            spec = parse_spec(entry)
            explicit_id = entry.get("model_id")
            if explicit_id:
                mid = str(explicit_id)
            elif spec.key() in by_key:
                mid = by_key[spec.key()]
            else:
                next_idx += 1
                mid = make_model_id(next_idx, spec)
            out.append({"model_id": mid, "spec": spec})
        return out

    symbols = tuple(s.strip().upper() for s in args.symbols.split(",") if s.strip())
    specs, mode = select_next_queue_batch(
        args.queue_file,
        store,
        per_symbol=args.per_symbol,
        symbols=symbols,
    )
    print(
        f"Selected {len(specs)} alpha models from {args.queue_file} (mode={mode}): "
        + ", ".join(f"{x['spec'].symbol}:{x['spec'].timeframe}:{x['spec'].family}" for x in specs)
    )
    return specs


def _cmd_run_daily(args: argparse.Namespace) -> int:
    store = AlphaModelStore(args.store_dir)
    store.ensure_initialized()

    batch_date = args.date or datetime.now(timezone.utc).date().isoformat()
    existing_day_models = store.load_daily_batch_models(batch_date)
    existing_rounds = sorted({int(m.get("round_no") or 1) for m in existing_day_models})

    if args.round:
        round_no = int(args.round)
    else:
        if existing_day_models and len(existing_rounds) >= args.max_rounds:
            print(
                f"Alpha batch {batch_date} already has {len(existing_rounds)} round(s) "
                f"({len(existing_day_models)} models) >= --max-rounds {args.max_rounds}; nothing to mine."
            )
            return 0
        round_no = (max(existing_rounds) + 1) if existing_rounds else 1

    batch_specs = _load_batch_specs(args, store)
    end_d = date.fromisoformat(args.end_date) if args.end_date else None

    # Cache loaded (symbol, timeframe, days_override) series so each dataset is fetched at most once per round.
    series_cache: dict[tuple[str, str, int | None], tuple[Any, dict[str, Any]]] = {}
    loader_summary: dict[str, Any] = {"round_no": round_no, "datasets": {}}

    round_metrics: list[dict[str, Any]] = []
    for item in batch_specs:
        mid = str(item["model_id"])
        spec: AlphaSpec = item["spec"]
        days_override = args.days if args.days > 0 else (spec.days if spec.days > 0 else None)
        cache_key = (spec.symbol, spec.timeframe, days_override)
        if cache_key not in series_cache:
            ser, meta = load_asset_series(
                spec.symbol,
                spec.timeframe,
                days=days_override,
                end_date=end_d,
                cache_dir=args.cache_dir,
                local_dir=args.local_dir,
            )
            series_cache[cache_key] = (ser, meta)
            loader_summary["datasets"][f"{spec.symbol}_{spec.timeframe}"] = meta
        ser, meta = series_cache[cache_key]

        desired = build_positions(ser, spec.family, spec.params, spec.direction)
        asset_cfg = ASSETS[spec.symbol]
        opt = AlphaBacktestOptions(
            cost_bps_per_side=asset_cfg.cost_bps_per_side,
            sl_pct=spec.sl_pct,
            tp_pct=spec.tp_pct,
            time_stop_bars=spec.time_stop_bars,
            oos_fraction=args.oos_fraction,
            initial_capital=args.initial_capital,
        )
        res = run_alpha_backtest(
            ser,
            desired,
            opt,
            symbol=spec.symbol,
            timeframe=spec.timeframe,
            direction=spec.direction,
        )
        rec = store.record_model_run(
            model_id=mid,
            batch_date=batch_date,
            spec=spec,
            result=res,
            round_no=round_no,
            loader_meta=meta,
        )
        round_metrics.append(rec)

    batch_metrics = merge_batch_models(existing_day_models, round_metrics)
    print(
        f"Alpha Round {round_no} mined {len(round_metrics)} model(s); "
        f"{batch_date} batch now holds {len(batch_metrics)} model(s)."
    )

    board = store.compute_ranking(
        top_n=args.top_n,
        max_dd_pct=args.max_dd_gate,
        min_trades=args.min_trades,
        write_file=True,
    )
    all_metrics = store.load_all_metrics()
    batch_ids = [m["model_id"] for m in batch_metrics]
    top_ids = [r["model_id"] for r in board.get("top_ranked", []) if r.get("model_id")]
    for rows in (board.get("top_ranked_by_symbol") or {}).values():
        top_ids.extend(r["model_id"] for r in rows if r.get("model_id"))
    extra_ids = [
        str(m["model_id"])
        for m in sorted(
            all_metrics,
            key=lambda x: (-float(x.get("oos_sharpe_ann", -999.0)), float(x.get("max_drawdown_pct", 999.0))),
        )[:60]
        if m.get("model_id")
    ]
    batch_series = store.load_batch_series(list(dict.fromkeys([*batch_ids, *top_ids, *extra_ids])))
    existing_days = store.load_daily_batches_summary()

    summary_md = render_daily_summary_markdown(
        batch_date=batch_date,
        batch_metrics=batch_metrics,
        ranking_board=board,
    )
    dash_html = render_dashboard_html(
        batch_date=batch_date,
        batch_metrics=batch_metrics,
        all_models_metrics=all_metrics,
        ranking_board=board,
        batch_series=batch_series,
        available_dates=existing_days,
    )
    ddir = store.save_daily_batch(
        batch_date=batch_date,
        batch_metrics=batch_metrics,
        ranking_board=board,
        summary_markdown=summary_md,
        dashboard_html=dash_html,
        loader_meta=loader_summary,
    )
    daily_days = store.load_daily_batches_summary()
    portal_html = render_portal_index_html(
        daily_days=daily_days,
        ranking_board=board,
        latest_date=daily_days[0]["batch_date"] if daily_days else batch_date,
    )
    portal_path = store.write_portal_index(portal_html)
    print(summary_md)
    print(f"Saved isolated alpha models under: {store.models_dir}")
    print(f"Saved Top-{args.top_n} Alpha Ranking Board: {store.ranking_path}")
    print(f"Saved Alpha Daily Dashboard HTML: {ddir / 'dashboard.html'}")
    print(f"Saved Alpha Daily Index JSON: {store.daily_index_path}")
    print(f"Saved Alpha Archive Hub HTML: {portal_path}")
    return 0


def _cmd_next_batch(args: argparse.Namespace) -> int:
    store = AlphaModelStore(args.store_dir)
    symbols = tuple(s.strip().upper() for s in args.symbols.split(",") if s.strip())
    specs, mode = select_next_queue_batch(
        args.queue_file,
        store,
        per_symbol=args.per_symbol,
        symbols=symbols,
    )
    payload = {
        "queue_file": str(args.queue_file),
        "selection_mode": mode,
        "count": len(specs),
        "by_symbol": {
            sym: sum(1 for x in specs if x["spec"].symbol == sym) for sym in symbols
        },
        "models": [{"model_id": x["model_id"], **x["spec"].to_dict()} for x in specs],
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print(f"Next alpha batch ({mode}, {len(specs)} models):")
    for idx, item in enumerate(payload["models"], start=1):
        print(
            f"  {idx:02d}. {item['model_id']} [{item['symbol']} {item['timeframe']} {item['direction']}] "
            f"— {item.get('hypothesis', '')}"
        )
    return 0


def _cmd_rank(args: argparse.Namespace) -> int:
    store = AlphaModelStore(args.store_dir)
    board = store.compute_ranking(
        top_n=args.top,
        max_dd_pct=args.max_dd,
        min_trades=args.min_trades,
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
    store = AlphaModelStore(args.store_dir)
    print(
        json.dumps(
            {
                "model_id": args.model_id,
                "spec": store.load_spec(args.model_id),
                "latest_metrics": store.load_metrics(args.model_id),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def _cmd_list_dates(args: argparse.Namespace) -> int:
    store = AlphaModelStore(args.store_dir)
    days = store.load_daily_batches_summary()
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
        print("No archived daily alpha batches found.")
        return 0
    for d in days:
        print(
            f"  - {d['batch_date']}: {d['model_count']} models (rounds {d['rounds']}, {d['by_symbol']}) | "
            f"OOS+ {d['profitable_oos_count']}/{d['model_count']} | "
            f"best OOS Sh {d['best_oos_sharpe']:.2f} ({d['best_oos_sharpe_model_id']})"
        )
    return 0


def _cmd_rebuild_dashboard(args: argparse.Namespace) -> int:
    store = AlphaModelStore(args.store_dir)
    board = store.compute_ranking(
        top_n=args.top_n,
        max_dd_pct=args.max_dd_gate,
        min_trades=args.min_trades,
        write_file=True,
    )
    all_metrics = store.load_all_metrics()
    available_dates = store.load_daily_batches_summary()
    if args.all_dates:
        targets = store.list_daily_dates()
    else:
        targets = [args.date or (available_dates[0]["batch_date"] if available_dates else datetime.now(timezone.utc).date().isoformat())]

    for bdate in targets:
        existing = store.load_daily_batch(bdate)
        batch_metrics = (
            [dict(m) for m in existing["models"]]
            if existing and isinstance(existing.get("models"), list) and existing["models"]
            else [m for m in all_metrics if m.get("batch_date") == bdate]
        )
        batch_ids = [m["model_id"] for m in batch_metrics]
        top_ids = [r["model_id"] for r in board.get("top_ranked", []) if r.get("model_id")]
        for rows in (board.get("top_ranked_by_symbol") or {}).values():
            top_ids.extend(r["model_id"] for r in rows if r.get("model_id"))
        extra_ids = [
            str(m["model_id"])
            for m in sorted(
                all_metrics,
                key=lambda x: (-float(x.get("oos_sharpe_ann", -999.0)), float(x.get("max_drawdown_pct", 999.0))),
            )[:60]
            if m.get("model_id")
        ]
        batch_series = store.load_batch_series(list(dict.fromkeys([*batch_ids, *top_ids, *extra_ids])))
        summary_md = render_daily_summary_markdown(batch_date=bdate, batch_metrics=batch_metrics, ranking_board=board)
        dash_html = render_dashboard_html(
            batch_date=bdate,
            batch_metrics=batch_metrics,
            all_models_metrics=all_metrics,
            ranking_board=board,
            batch_series=batch_series,
            available_dates=available_dates,
        )
        store.save_daily_batch(
            batch_date=bdate,
            batch_metrics=batch_metrics,
            ranking_board=board,
            summary_markdown=summary_md,
            dashboard_html=dash_html,
            loader_meta=(existing or {}).get("loader"),
        )
    daily_days = store.load_daily_batches_summary()
    portal_html = render_portal_index_html(
        daily_days=daily_days,
        ranking_board=board,
        latest_date=daily_days[0]["batch_date"] if daily_days else (targets[-1] if targets else ""),
    )
    store.write_portal_index(portal_html)
    print(f"Rebuilt {len(targets)} alpha dashboard(s) and hub {store.portal_index_path}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Daily Alpha Mining Factory — 4 rounds/day x 10 models (5 XAUUSD + 5 ETHUSDT = 40/day)."
    )
    parser.add_argument("--store-dir", type=Path, default=DEFAULT_STORE_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    rd = sub.add_parser("run-daily", help="Run one round of Alpha mining and accumulate into today's batch.")
    rd.add_argument("--date", default=None, help="Batch date YYYY-MM-DD (default: today UTC).")
    rd.add_argument("--queue-file", type=Path, default=DEFAULT_QUEUE_FILE)
    rd.add_argument("--batch-file", type=Path, default=None, help="Optional JSON batch override file.")
    rd.add_argument("--per-symbol", type=int, default=5, help="Models per symbol per round (default: 5 -> 10/round, 40/day).")
    rd.add_argument("--symbols", default=",".join(KNOWN_SYMBOLS), help="Comma-separated symbols (default: XAUUSD,ETHUSDT).")
    rd.add_argument("--round", type=int, default=0, help="Explicit round number (0 = auto next round).")
    rd.add_argument("--max-rounds", type=int, default=4, help="Auto mode: skip when date already has this many rounds (default: 4).")
    rd.add_argument("--days", type=int, default=0, help="Override lookback days for all timeframes (0 = per-TF default).")
    rd.add_argument("--end-date", default=None, help="Optional end date YYYY-MM-DD (default: yesterday UTC).")
    rd.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    rd.add_argument("--local-dir", type=Path, default=None, help="Optional local CSV dir with <SYMBOL>_<TF>.csv or <SYMBOL>_1m.csv.")
    rd.add_argument("--oos-fraction", type=float, default=0.30)
    rd.add_argument("--initial-capital", type=float, default=10_000.0)
    rd.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    rd.add_argument("--max-dd-gate", type=float, default=DEFAULT_MAX_DD_GATE_PCT)
    rd.add_argument("--min-trades", type=int, default=DEFAULT_MIN_TRADES)

    nb = sub.add_parser("next-batch", help="Preview the next round's models from daily_queue.json.")
    nb.add_argument("--queue-file", type=Path, default=DEFAULT_QUEUE_FILE)
    nb.add_argument("--per-symbol", type=int, default=5)
    nb.add_argument("--symbols", default=",".join(KNOWN_SYMBOLS))
    nb.add_argument("--json", action="store_true")

    rk = sub.add_parser("rank", help="Display cumulative Top-N Alpha Ranking Board.")
    rk.add_argument("--top", type=int, default=DEFAULT_TOP_N)
    rk.add_argument("--max-dd", type=float, default=DEFAULT_MAX_DD_GATE_PCT)
    rk.add_argument("--min-trades", type=int, default=DEFAULT_MIN_TRADES)
    rk.add_argument("--save", action="store_true")
    rk.add_argument("--json", action="store_true")

    sh = sub.add_parser("show", help="Inspect one isolated alpha model folder.")
    sh.add_argument("model_id")

    ld = sub.add_parser("list-dates", help="List archived daily alpha batches.")
    ld.add_argument("--json", action="store_true")

    rb = sub.add_parser("rebuild-dashboard", help="Rebuild alpha dashboard.html, daily/index.json, and index.html.")
    rb.add_argument("--date", default=None)
    rb.add_argument("--all-dates", action="store_true")
    rb.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    rb.add_argument("--max-dd-gate", type=float, default=DEFAULT_MAX_DD_GATE_PCT)
    rb.add_argument("--min-trades", type=int, default=DEFAULT_MIN_TRADES)
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
    if args.command == "list-dates":
        return _cmd_list_dates(args)
    if args.command == "rebuild-dashboard":
        return _cmd_rebuild_dashboard(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
