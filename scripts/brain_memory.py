#!/usr/bin/env python3
"""CLI for Daily Brain Memory JSONL recording, outcome resolution, validation, and Drive Vault snapshots."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python"))

from alpha_mining.storage import (  # noqa: E402
    BrainEpisode,
    BrainMemoryError,
    EpisodeOutcome,
    VaultError,
    append_episode,
    load_episodes,
    load_manifest,
    pack_daily_snapshot,
    plan_snapshot_sync,
    push_to_drive,
    render_day_markdown,
    resolve_episode_outcome,
    summarize_day,
)


def _current_git_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else "UNKNOWN"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alpha_mining Daily Brain Memory & Snapshot CLI")
    parser.add_argument(
        "--memory-dir",
        type=Path,
        default=REPO_ROOT / "workflows" / "memory",
        help="Directory holding YYYY-MM-DD.jsonl daily memory logs",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    rec_p = sub.add_parser("record", help="Validate and append a BrainEpisode JSON record")
    rec_p.add_argument("--input-json", type=Path, required=True, help="Path to JSON file defining one BrainEpisode")

    res_p = sub.add_parser("resolve", help="Resolve a pending BrainEpisode outcome without mutating inputs")
    res_p.add_argument("--session-date", required=True)
    res_p.add_argument("--episode-id", required=True)
    res_p.add_argument("--outcome-json", type=Path, required=True)

    val_p = sub.add_parser("validate", help="Validate all daily JSONL files (or a single date)")
    val_p.add_argument("--session-date", default=None)

    sum_p = sub.add_parser("summarize", help="Generate deterministic summary of one session date")
    sum_p.add_argument("--session-date", required=True)
    sum_p.add_argument("--format", choices=("json", "markdown"), default="json")

    plan_p = sub.add_parser("plan-sync", help="Detect daily logs missing snapshots, changed since push, or unpushed")
    plan_p.add_argument("--manifest-dir", type=Path, action="append", default=[])
    plan_p.add_argument("--authoritative-manifest-dir", type=Path, default=None)
    plan_p.add_argument("--session-date", default="auto")
    plan_p.add_argument("--force", action="store_true")

    pack_p = sub.add_parser("pack-snapshot", help="Pack daily log + summary into state_snapshot Vault manifest")
    pack_p.add_argument("--session-date", required=True)
    pack_p.add_argument("--manifest-out", type=Path)
    pack_p.add_argument("--archive-dir", type=Path, default=REPO_ROOT / ".vault_cache")
    pack_p.add_argument("--codec", choices=("auto", "zstd", "gz", "xz"), default="auto")

    push_p = sub.add_parser("push-snapshot", help="Push packed brain-daily manifest archive to Google Drive Vault")
    push_p.add_argument("--manifest", type=Path, required=True)
    push_p.add_argument("--archive", type=Path)
    push_p.add_argument("--backend", choices=("auto", "gdrive", "rclone"), default="auto")
    push_p.add_argument("--rclone-remote", default="gdrive:Alpha_mining_Vault")
    push_p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "record":
            raw = json.loads(args.input_json.read_text(encoding="utf-8"))
            episode = BrainEpisode.from_dict(raw)
            out_path = append_episode(args.memory_dir, episode)
            out: dict[str, object] = {
                "recorded": True,
                "episode_id": episode.episode_id,
                "session_date": episode.session_date,
                "file": str(out_path),
            }
            print(json.dumps(out, indent=2, ensure_ascii=False))
            return 0

        if args.cmd == "resolve":
            raw = json.loads(args.outcome_json.read_text(encoding="utf-8"))
            outcome = EpisodeOutcome.from_dict(raw)
            updated = resolve_episode_outcome(
                args.memory_dir,
                args.session_date,
                args.episode_id,
                outcome,
            )
            print(json.dumps({"resolved": True, "episode_id": updated.episode_id, "status": updated.outcome.status}, indent=2))
            return 0

        if args.cmd == "validate":
            episodes = load_episodes(args.memory_dir, args.session_date)
            print(json.dumps({"valid": True, "episode_count": len(episodes), "memory_dir": str(args.memory_dir)}, indent=2))
            return 0

        if args.cmd == "summarize":
            summary = summarize_day(args.memory_dir, args.session_date)
            if args.format == "markdown":
                print(render_day_markdown(summary), end="")
            else:
                print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 0

        if args.cmd == "plan-sync":
            manifest_dirs = args.manifest_dir or [REPO_ROOT / "workflows" / "vault_manifests"]
            plan = plan_snapshot_sync(
                args.memory_dir,
                manifest_dirs=manifest_dirs,
                authoritative_manifest_dir=args.authoritative_manifest_dir,
                session_date=args.session_date,
                force=args.force,
            )
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return 0

        if args.cmd == "pack-snapshot":
            manifest = pack_daily_snapshot(
                args.memory_dir,
                args.session_date,
                repo_root=REPO_ROOT,
                manifest_out=args.manifest_out,
                archive_dir=args.archive_dir,
                source_commit=_current_git_sha(),
                codec=args.codec,
            )
            print(json.dumps(manifest, indent=2, ensure_ascii=False))
            return 0

        if args.cmd == "push-snapshot":
            manifest_data = load_manifest(args.manifest)
            archive = args.archive or (REPO_ROOT / ".vault_cache" / manifest_data["archive_name"])
            res = push_to_drive(
                args.manifest,
                archive,
                backend=args.backend,
                rclone_remote=args.rclone_remote,
                dry_run=args.dry_run,
            )
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0

        parser.error(f"unknown subcommand: {args.cmd}")
        return 2
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, BrainMemoryError, VaultError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
