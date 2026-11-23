#!/usr/bin/env python3
"""CLI entrypoint for the Alpha_mining 1-minute Binance market collector (Options, Spot, Delivery Futures)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = REPO_ROOT / "python"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from alpha_mining.research.binance_collector import (  # noqa: E402
    Binance1mCollector,
    compact_day_to_parquet,
    load_collector_config,
    prune_uploaded_local_parquet,
    upload_day_to_drive,
    upload_pending_days,
)

DEFAULT_CONFIG = REPO_ROOT / "config" / "collector" / "binance_1m_collector.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lightweight 1m Binance collector (Options Chain, Spot, USD-M & COIN-M Delivery Futures -> Parquet Zstd -> Google Drive)."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Path to collector JSON config (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=REPO_ROOT,
        help=f"Base directory for relative storage paths (default: {REPO_ROOT})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate-config", help="Validate collector configuration schema and invariants.")

    sub.add_parser("once", help="Collect one synchronized snapshot across all enabled markets into local spool.")

    run_p = sub.add_parser("run", help="Run continuous UTC-aligned 1-minute collector loop with midnight Parquet compaction and Drive upload.")
    run_p.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="Optional tick limit for bounded smoke runs (default: run indefinitely).",
    )

    comp_p = sub.add_parser("compact", help="Compact a spooled UTC day (YYYY-MM-DD) into Parquet Zstd + SHA-256 manifest.")
    comp_p.add_argument("--date", required=True, help="Target UTC date (YYYY-MM-DD).")
    comp_p.add_argument("--upload", action="store_true", help="Upload compacted Parquet + manifest files via rclone copy.")
    comp_p.add_argument("--prune", action="store_true", help="Prune uploaded local Parquet files older than retention_local_days.")

    up_p = sub.add_parser("upload-pending", help="Retry rclone Drive upload for any compacted past UTC days missing upload receipts.")
    up_p.add_argument(
        "--before-date",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        help="Upload compacted days strictly earlier than this UTC date (default: today UTC).",
    )

    sub.add_parser("status", help="Inspect collector heartbeat health.json and local spool/parquet inventory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    cfg = load_collector_config(args.config)
    base_dir: Path = args.base_dir.resolve()

    if args.command == "validate-config":
        print(
            json.dumps(
                {
                    "valid": True,
                    "collector_id": cfg.collector_id,
                    "interval_seconds": cfg.interval_seconds,
                    "underlyings": list(cfg.underlyings),
                    "spot_symbols": list(cfg.spot_symbols),
                    "markets_enabled": {
                        "options": cfg.options.enabled,
                        "spot": cfg.spot.enabled,
                        "futures_usdm": cfg.futures_usdm.enabled,
                        "futures_coinm": cfg.futures_coinm.enabled,
                    },
                    "futures_usdm_contract_types": list(cfg.futures_usdm.contract_types),
                    "futures_coinm_contract_types": list(cfg.futures_coinm.contract_types),
                    "parquet_compression": cfg.storage.parquet_compression,
                    "parquet_compression_level": cfg.storage.parquet_compression_level,
                    "rclone_remote": cfg.storage.rclone_remote,
                },
                indent=2,
            )
        )
        return 0

    if args.command == "once":
        collector = Binance1mCollector(cfg, base_dir=base_dir)
        summary = collector.collect_once()
        print(json.dumps(summary, indent=2))
        return 0 if summary["error_count"] == 0 else 1

    if args.command == "run":
        collector = Binance1mCollector(cfg, base_dir=base_dir)
        history = collector.run_forever(max_ticks=args.max_ticks)
        print(json.dumps({"ticks_completed": len(history), "last_tick": history[-1] if history else None}, indent=2))
        return 0

    if args.command == "compact":
        compacted = compact_day_to_parquet(cfg, base_dir=base_dir, date_utc=args.date)
        output: dict[str, object] = {"date_utc": args.date, "compacted": compacted}
        if args.upload and compacted:
            output["uploaded"] = upload_day_to_drive(
                cfg,
                base_dir=base_dir,
                date_utc=args.date,
                datasets=list(compacted.keys()),
            )
        if args.prune:
            output["pruned"] = prune_uploaded_local_parquet(cfg, base_dir=base_dir)
        print(json.dumps(output, indent=2))
        return 0

    if args.command == "upload-pending":
        uploaded = upload_pending_days(cfg, base_dir=base_dir, before_date_utc=args.before_date)
        pruned = prune_uploaded_local_parquet(cfg, base_dir=base_dir)
        print(json.dumps({"uploaded": uploaded, "pruned": pruned}, indent=2))
        return 0

    if args.command == "status":
        spool_dir = cfg.resolve_spool_dir(base_dir)
        out_dir = cfg.resolve_output_dir(base_dir)
        health_file = spool_dir / "health.json"
        health = json.loads(health_file.read_text(encoding="utf-8")) if health_file.is_file() else None
        spooled_days = sorted(p.name for p in spool_dir.iterdir() if p.is_dir()) if spool_dir.exists() else []
        parquet_files = sorted(str(p.relative_to(out_dir)) for p in out_dir.rglob("*.parquet")) if out_dir.exists() else []
        print(
            json.dumps(
                {
                    "collector_id": cfg.collector_id,
                    "spool_dir": str(spool_dir),
                    "output_dir": str(out_dir),
                    "spooled_days": spooled_days,
                    "local_parquet_count": len(parquet_files),
                    "local_parquet_recent": parquet_files[-12:],
                    "last_health": health,
                },
                indent=2,
            )
        )
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
