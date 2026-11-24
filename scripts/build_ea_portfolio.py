#!/usr/bin/env python3
"""CLI for validating modular alpha/beta/omega models and assembling MT5 .mq5 EAs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python"))

from alpha_mining.strategy.model_registry import (  # noqa: E402
    ModelRegistryError,
    assemble_portfolio_mq5,
    assemble_single_model_mq5,
    load_and_validate_registry,
    load_portfolio_spec,
)


def _cmd_validate(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    registry = load_and_validate_registry(repo_root)
    portfolios_dir = repo_root / "portfolios"
    validated_portfolios: list[str] = []
    if portfolios_dir.is_dir():
        for manifest in sorted(portfolios_dir.glob("*.json")):
            spec = load_portfolio_spec(manifest, registry)
            assembled = assemble_portfolio_mq5(registry, spec)
            if args.check_assembled and spec.output_path:
                out_file = (repo_root / spec.output_path).resolve()
                if not out_file.is_file():
                    raise ModelRegistryError(f"missing assembled EA file: {spec.output_path}")
                existing = out_file.read_text(encoding="utf-8")
                if existing != assembled:
                    raise ModelRegistryError(
                        f"drift detected in {spec.output_path}; run scripts/build_ea_portfolio.py build"
                    )
            validated_portfolios.append(spec.portfolio_id)

    print(
        json.dumps(
            {
                "status": "ok",
                "models_validated": len(registry.models),
                "portfolios_validated": validated_portfolios,
            },
            indent=2,
        )
    )
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    registry = load_and_validate_registry(args.repo_root.resolve())
    rows = [
        {
            "model_id": m.model_id,
            "category": m.category,
            "mql5_prefix": m.mql5_prefix,
            "magic_number": m.magic_number,
            "timeframe": m.timeframe,
            "direction": m.direction,
            "default_lot": m.default_lot,
            "evidence_status": m.evidence_status,
            "sha256_short": m.combined_sha256[:12],
        }
        for m in registry.models
    ]
    if args.format == "json":
        print(json.dumps(rows, indent=2))
        return 0

    header = f"{'model_id':<24} {'cat':<6} {'prefix':<10} {'magic':<10} {'tf':<10} {'status':<14} {'sha12'}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['model_id']:<24} {r['category']:<6} {r['mql5_prefix']:<10} "
            f"{r['magic_number']:<10} {r['timeframe']:<10} {r['evidence_status']:<14} {r['sha256_short']}"
        )
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    registry = load_and_validate_registry(repo_root)
    portfolio_path = args.portfolio if args.portfolio.is_absolute() else (repo_root / args.portfolio)
    spec = load_portfolio_spec(portfolio_path, registry)
    assembled = assemble_portfolio_mq5(registry, spec)

    out_path: Path | None = args.out
    if out_path is None and spec.output_path:
        out_path = repo_root / spec.output_path

    if args.check:
        if out_path is None or not out_path.is_file():
            raise ModelRegistryError(f"target assembled file does not exist for --check: {out_path}")
        if out_path.read_text(encoding="utf-8") != assembled:
            raise ModelRegistryError(f"assembled file drift detected: {out_path}")
        print(f"OK (up-to-date): {out_path}")
        return 0

    if out_path is None:
        sys.stdout.write(assembled)
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(assembled, encoding="utf-8", newline="\n")
    print(f"Built {out_path} ({len(spec.slots)} models)")
    return 0


def _cmd_build_single(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    registry = load_and_validate_registry(repo_root)
    assembled = assemble_single_model_mq5(
        registry,
        args.model,
        default_lot=args.lot,
        account_lock=args.account_lock,
    )
    if args.out is None:
        sys.stdout.write(assembled)
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(assembled, encoding="utf-8")
    print(f"Built standalone EA for {args.model} -> {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate modular models/ registry and assemble self-contained MT5 .mq5 EAs"
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="Validate registry, model specs, modules, and portfolios")
    p_val.add_argument(
        "--check-assembled",
        action="store_true",
        help="Also verify committed assembled .mq5 files have zero drift",
    )
    p_val.set_defaults(func=_cmd_validate)

    p_list = sub.add_parser("list", help="List all registered models")
    p_list.add_argument("--format", choices=("table", "json"), default="table")
    p_list.set_defaults(func=_cmd_list)

    p_build = sub.add_parser("build", help="Assemble a multi-model portfolio .mq5 EA")
    p_build.add_argument("--portfolio", type=Path, required=True)
    p_build.add_argument("--out", type=Path, default=None)
    p_build.add_argument("--check", action="store_true", help="Fail if output file differs from build")
    p_build.set_defaults(func=_cmd_build)

    p_single = sub.add_parser("build-single", help="Assemble a standalone single-model .mq5 EA")
    p_single.add_argument("--model", required=True)
    p_single.add_argument("--lot", type=float, default=None)
    p_single.add_argument("--account-lock", type=int, default=0)
    p_single.add_argument("--out", type=Path, default=None)
    p_single.set_defaults(func=_cmd_build_single)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ModelRegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
