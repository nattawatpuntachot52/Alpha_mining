#!/usr/bin/env python3
"""CLI for packaging, SHA-256 verification, hot-cache keying, and Google Drive Vault sync."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python"))

from alpha_mining.storage.vault import (  # noqa: E402
    VaultError,
    default_vault_config_path,
    extract_verified_archive,
    load_manifest,
    pack_artifact,
    pull_from_drive,
    push_to_drive,
    verify_archive_checksum,
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
    parser = argparse.ArgumentParser(description="Alpha_mining Drive Vault + Hot Cache CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pack_p = sub.add_parser("pack", help="Pack directory into compressed archive and write SHA-256 manifest")
    pack_p.add_argument("--source", type=Path, required=True)
    pack_p.add_argument("--artifact-id", required=True)
    pack_p.add_argument("--category", choices=("dataset", "backtest_cache", "state_snapshot"), required=True)
    pack_p.add_argument("--manifest-out", type=Path)
    pack_p.add_argument("--archive-dir", type=Path, default=REPO_ROOT / ".vault_cache")
    pack_p.add_argument("--codec", choices=("auto", "zstd", "gz", "xz"), default="auto")

    key_p = sub.add_parser("cache-key", help="Print Actions cache key for a manifest")
    key_p.add_argument("--manifest", type=Path, required=True)

    ver_p = sub.add_parser("verify-archive", help="Verify archive SHA-256 against manifest")
    ver_p.add_argument("--manifest", type=Path, required=True)
    ver_p.add_argument("--archive", type=Path, required=True)

    ext_p = sub.add_parser("extract", help="Verify archive SHA-256 and safely extract + verify all files")
    ext_p.add_argument("--manifest", type=Path, required=True)
    ext_p.add_argument("--archive", type=Path, required=True)
    ext_p.add_argument("--dest", type=Path, required=True)

    push_p = sub.add_parser("push-drive", help="Upload or update verified archive to Google Drive Vault")
    push_p.add_argument("--manifest", type=Path, required=True)
    push_p.add_argument("--archive", type=Path)
    push_p.add_argument("--backend", choices=("auto", "gdrive", "rclone"), default="auto")
    push_p.add_argument("--rclone-remote", default="gdrive:00_Katherine_Workspace/01_Alpha_Mining")
    push_p.add_argument("--dry-run", action="store_true")

    pull_p = sub.add_parser("pull-drive", help="Hydrate from hot cache or Drive Vault, verify, and extract")
    pull_p.add_argument("--manifest", type=Path, required=True)
    pull_p.add_argument("--dest", type=Path, required=True)
    pull_p.add_argument("--cache-dir", type=Path, default=REPO_ROOT / ".vault_cache")
    pull_p.add_argument("--backend", choices=("auto", "gdrive", "rclone"), default="auto")
    pull_p.add_argument("--rclone-remote", default="gdrive:00_Katherine_Workspace/01_Alpha_Mining")

    args = parser.parse_args(argv)
    vault_cfg = default_vault_config_path(REPO_ROOT)

    try:
        if args.cmd == "pack":
            manifest_out = args.manifest_out or (
                REPO_ROOT / "workflows" / "vault_manifests" / f"{args.artifact_id}.manifest.json"
            )
            out = pack_artifact(
                args.source,
                artifact_id=args.artifact_id,
                category=args.category,
                manifest_out=manifest_out,
                archive_dir=args.archive_dir,
                vault_config_path=vault_cfg,
                source_commit=_current_git_sha(),
                codec=args.codec,
            )
        elif args.cmd == "cache-key":
            m = load_manifest(args.manifest)
            print(m["cache_key"])
            return 0
        elif args.cmd == "verify-archive":
            m = load_manifest(args.manifest)
            verify_archive_checksum(args.archive, m)
            out = {"verified": True, "artifact_id": m["artifact_id"], "archive_sha256": m["archive_sha256"]}
        elif args.cmd == "extract":
            out = extract_verified_archive(args.archive, args.manifest, args.dest)
        elif args.cmd == "push-drive":
            m = load_manifest(args.manifest)
            archive = args.archive or (REPO_ROOT / ".vault_cache" / m["archive_name"])
            out = push_to_drive(
                args.manifest,
                archive,
                backend=args.backend,
                rclone_remote=args.rclone_remote,
                dry_run=args.dry_run,
            )
        elif args.cmd == "pull-drive":
            out = pull_from_drive(
                args.manifest,
                args.dest,
                cache_dir=args.cache_dir,
                backend=args.backend,
                rclone_remote=args.rclone_remote,
            )
        else:
            parser.error(f"unknown subcommand: {args.cmd}")
            return 2
    except VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
