#!/usr/bin/env python3
"""CLI runner for LGB154 V3 Pluggable 1m Backtest Engine (Baseline HA, Signal A/B, and Crash Stress Test)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = REPO_ROOT / "python"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from alpha_mining.research.backtest_lgb154 import (  # noqa: E402
    BacktestOptions,
    compare_signals,
    find_worst_crash_window,
    render_comparison_markdown,
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


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw.strip())


def _build_config(args: argparse.Namespace) -> Lgb154Config:
    base = Lgb154Config.ethusd_coinm_default() if args.profile == "coinm" else Lgb154Config.ethusdt_usdm_default()
    updates: dict[str, object] = {}
    if args.symbol:
        updates["symbol"] = args.symbol.upper()
    if args.high is not None:
        updates["high"] = Decimal(str(args.high))
    if args.low is not None:
        updates["low"] = Decimal(str(args.low))
    if args.spacing_pct is not None:
        updates["spacing_pct"] = Decimal(str(args.spacing_pct))
    if args.max_position_qty is not None:
        updates["max_position_quantity"] = Decimal(str(args.max_position_qty))
    if args.max_notional is not None:
        updates["max_notional_usdt"] = Decimal(str(args.max_notional))
    if args.tp_mode is not None:
        updates["tp_pricing_mode"] = args.tp_mode
    if args.max_loss is not None:
        updates["max_loss_usdt"] = Decimal(str(args.max_loss))

    if updates:
        temp_high = Decimal(str(updates.get("high", base.high)))
        temp_low = Decimal(str(updates.get("low", base.low)))
        temp_spacing = Decimal(str(updates.get("spacing_pct", base.spacing_pct)))
        levels = build_grid_levels(temp_high, temp_low, temp_spacing, base.tick_size)
        max_qty = Decimal(str(updates.get("max_position_quantity", base.max_position_quantity)))
        req_entry_notional = base.quote_notional(base.order_quantity, temp_high)
        if args.high is not None and req_entry_notional > base.max_entry_order_notional_usdt:
            updates["max_entry_order_notional_usdt"] = req_entry_notional
        req_total_notional = base.quote_notional(max_qty, temp_high)
        if args.max_notional is not None:
            max_not = Decimal(str(args.max_notional))
        else:
            max_not = max(base.max_notional_usdt, req_total_notional)
            updates["max_notional_usdt"] = max_not
        updates["rp_ranges"] = (
            RpRange(
                from_grid=0,
                to_grid=levels[-1][0],
                rp_id=base.rp_ranges[0].rp_id,
                max_quantity=max_qty,
                max_notional_usdt=max_not,
            ),
        )
        return replace(base, **updates)  # type: ignore[arg-type]
    return base


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run LGB154 V3 1m backtests (Binance Vision 1000-day archive, data-api REST, or local CSV/Parquet)."
    )
    p.add_argument("--profile", choices=["usdm", "coinm"], default="usdm")
    p.add_argument("--symbol", default=None, help="Override symbol (default: ETHUSDT for usdm, ETHUSD_PERP for coinm).")
    p.add_argument("--source", choices=["vision", "data-api", "local"], default="vision")
    p.add_argument("--market", choices=["um", "cm", "spot"], default=None, help="Binance Vision market (default matches profile).")
    p.add_argument("--local-path", type=Path, default=None, help="Local CSV/ZIP/Parquet file or directory when --source=local.")
    p.add_argument("--cache-dir", type=Path, default=REPO_ROOT / "data" / "cache" / "binance_vision")
    p.add_argument("--days", type=int, default=1000, help="Trailing lookback days when start-date is omitted.")
    p.add_argument("--start-date", default=None, help="UTC start date YYYY-MM-DD.")
    p.add_argument("--end-date", default=None, help="UTC end date YYYY-MM-DD (default: yesterday UTC).")
    p.add_argument("--signals", default="ha_1m", help="Comma-separated signal specs (e.g. ha_1m,ema_9_21,rsi_reversion,supertrend).")
    p.add_argument("--fill-mode", choices=["strict_cross", "touch"], default="strict_cross")
    p.add_argument(
        "--recovery-mode",
        choices=["partial_only", "legacy_v3"],
        default="partial_only",
        help="partial_only avoids bot.py L2417 zero-fill zombie-group starvation; legacy_v3 reproduces bot.py 1:1.",
    )
    p.add_argument("--initial-capital", type=float, default=None, help="Initial capital (USDT for usdm, ETH for coinm).")
    p.add_argument("--high", type=float, default=None, help="Override grid upper bound.")
    p.add_argument("--low", type=float, default=None, help="Override grid lower bound.")
    p.add_argument("--spacing-pct", type=float, default=None, help="Override geometric grid spacing %.")
    p.add_argument("--max-position-qty", type=float, default=None)
    p.add_argument("--max-notional", type=float, default=None)
    p.add_argument("--tp-mode", choices=["PROFIT_PLUS_COMMISSION", "NET"], default=None)
    p.add_argument("--max-loss", type=float, default=None, help="Optional emergency max loss stop (0 = disabled).")
    p.add_argument("--no-funding", action="store_true", help="Disable 8h funding settlement.")
    p.add_argument("--stress-crash-days", type=int, default=0, help="If >0, also run isolated crash stress test on steepest N-day drop.")
    p.add_argument("--json-out", type=Path, default=None)
    p.add_argument("--md-out", type=Path, default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    cfg = _build_config(args)
    market = args.market or ("cm" if cfg.is_coinm else "um")

    end_d = _parse_date(args.end_date) if args.end_date else (datetime.now(timezone.utc).date() - timedelta(days=1))
    start_d = _parse_date(args.start_date) if args.start_date else (end_d - timedelta(days=max(1, args.days) - 1))

    funding_rates: dict[int, float] = {}
    loader_meta: dict[str, object] = {"source": args.source, "market": market}

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
        raise SystemExit(f"loaded insufficient bars ({len(bars)}) for {cfg.symbol} ({start_d}..{end_d})")

    init_cap = Decimal(str(args.initial_capital)) if args.initial_capital is not None else (
        Decimal("1.0") if cfg.is_coinm else Decimal("1000")
    )
    opt = BacktestOptions(
        initial_capital=init_cap,
        fill_mode=args.fill_mode,
        use_funding=not args.no_funding,
        record_trades=False,
        recovery_mode=args.recovery_mode,
    )

    sig_specs = [s.strip() for s in args.signals.split(",") if s.strip()]
    providers = [create_signal_provider(s) for s in sig_specs]

    main_results = compare_signals(bars, cfg, providers, options=opt, funding_rates_8h=funding_rates)
    md_sections = [
        render_comparison_markdown(
            main_results,
            title=f"LGB154 V3 Backtest ({cfg.symbol} {cfg.product_type} — {len(bars):,} 1m bars)",
        )
    ]

    payload: dict[str, object] = {
        "loader": loader_meta,
        "main_results": [r.summary_dict() for r in main_results],
    }

    if args.stress_crash_days > 0:
        s_idx, e_idx, drop_pct = find_worst_crash_window(bars, window_days=args.stress_crash_days)
        crash_bars = bars[s_idx : e_idx + 1]
        # Anchor stress zone directly at the crash start price (high = peak, low = peak * 0.80)
        peak_price = max(b.high for b in crash_bars[: min(300, len(crash_bars))])
        stress_high = Decimal(f"{peak_price:.2f}")
        stress_low = Decimal(f"{peak_price * 0.80:.2f}")
        s_levels = build_grid_levels(stress_high, stress_low, cfg.spacing_pct, cfg.tick_size)
        stress_entry_cap = max(cfg.max_entry_order_notional_usdt, cfg.quote_notional(cfg.order_quantity, stress_high))
        stress_notional_cap = max(cfg.max_notional_usdt, cfg.quote_notional(cfg.max_position_quantity, stress_high))
        stress_cfg = replace(
            cfg,
            high=stress_high,
            low=stress_low,
            max_entry_order_notional_usdt=stress_entry_cap,
            max_notional_usdt=stress_notional_cap,
            rp_ranges=(
                RpRange(
                    from_grid=0,
                    to_grid=s_levels[-1][0],
                    rp_id=cfg.rp_ranges[0].rp_id,
                    max_quantity=cfg.max_position_quantity,
                    max_notional_usdt=stress_notional_cap,
                ),
            ),
        )
        stress_providers = [create_signal_provider(s) for s in sig_specs]
        stress_results = compare_signals(
            crash_bars, stress_cfg, stress_providers, options=opt, funding_rates_8h=funding_rates
        )
        payload["crash_stress_test"] = {
            "window_days": args.stress_crash_days,
            "detected_drop_pct": drop_pct,
            "anchored_high": float(stress_high),
            "anchored_low": float(stress_low),
            "results": [r.summary_dict() for r in stress_results],
        }
        md_sections.append(
            render_comparison_markdown(
                stress_results,
                title=f"Crash Stress Test (Worst {args.stress_crash_days}d Drop: {drop_pct:.1f}% — Zone Anchored at Crash Peak)",
            )
        )

    md_text = "\n".join(md_sections)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.md_out is not None:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(md_text, encoding="utf-8")
    else:
        print(md_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
