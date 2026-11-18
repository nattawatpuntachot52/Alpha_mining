"""Hybrid Quant Data & State Vault (Git SHA-256 Manifest + Actions Hot Cache + Google Drive)."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Literal

from ..control_plane.ovca_bridge import utc_now_z

Category = Literal["dataset", "backtest_cache", "state_snapshot"]
Codec = Literal["auto", "zstd", "gz", "xz"]
Backend = Literal["auto", "gdrive", "rclone"]

ARTIFACT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,180}$")
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
DRIVE_ID_IN_TEXT_RE = re.compile(r"\(ID:\s*([A-Za-z0-9_-]+)\)")


class VaultError(RuntimeError):
    """Raised on vault packaging, transport, or configuration failures."""


class VaultIntegrityError(VaultError):
    """Raised when SHA-256 verification or archive safety checks fail."""


CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _default_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False)


def default_vault_config_path(repo_root: Path) -> Path:
    return repo_root / "config" / "storage" / "drive_vault.json"


def load_vault_config(config_path: Path) -> dict[str, Any]:
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise VaultError(f"failed to read vault config '{config_path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise VaultError(f"invalid JSON in vault config '{config_path}': {exc}") from exc
    if not isinstance(cfg, dict) or not isinstance(cfg.get("categories"), dict):
        raise VaultError(f"vault config '{config_path}' missing 'categories' object")
    return cfg


def validate_artifact_id(artifact_id: str) -> None:
    if not ARTIFACT_ID_RE.fullmatch(artifact_id):
        raise VaultError(
            f"invalid artifact_id '{artifact_id}': must match [A-Za-z0-9][A-Za-z0-9._-]{{0,127}}"
        )


def _validate_safe_archive_name(archive_name: str) -> None:
    if not isinstance(archive_name, str) or not SAFE_FILENAME_RE.fullmatch(archive_name):
        raise VaultIntegrityError(f"unsafe or malformed manifest archive_name: {archive_name!r}")


def _validate_safe_relpath(relpath: str) -> str:
    if not isinstance(relpath, str) or not relpath or "\\" in relpath:
        raise VaultIntegrityError(f"unsafe manifest relpath: {relpath!r}")
    p = PurePosixPath(relpath)
    if p.is_absolute() or ".." in p.parts or p.parts == (".",):
        raise VaultIntegrityError(f"path traversal in manifest relpath: {relpath!r}")
    return p.as_posix()


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _resolve_codec(codec: Codec) -> Literal["tar.zst", "tar.gz", "tar.xz"]:
    if codec == "zstd":
        if not shutil.which("zstd"):
            raise VaultError("codec 'zstd' requested but 'zstd' binary is not on PATH")
        return "tar.zst"
    if codec == "auto":
        return "tar.zst" if shutil.which("zstd") else "tar.gz"
    if codec == "gz":
        return "tar.gz"
    if codec == "xz":
        return "tar.xz"
    raise VaultError(f"unsupported compression codec: {codec}")


def _collect_safe_files(source_dir: Path) -> list[tuple[Path, str]]:
    if source_dir.is_symlink() or not source_dir.is_dir():
        raise VaultError(f"source directory does not exist or is symlink: {source_dir}")
    base_resolved = source_dir.resolve()
    items: list[tuple[Path, str]] = []

    for dirpath, dirnames, filenames in os.walk(source_dir, followlinks=False):
        cur_dir = Path(dirpath)
        for dname in dirnames:
            dpath = cur_dir / dname
            if dpath.is_symlink():
                raise VaultError(f"symlink directories are disallowed inside vault payloads: {dpath}")
        for fname in filenames:
            fpath = cur_dir / fname
            if fpath.is_symlink():
                raise VaultError(f"symlinks are disallowed inside vault payloads: {fpath}")
            if not fpath.is_file():
                raise VaultError(f"non-regular files are disallowed inside vault payloads: {fpath}")
            resolved = fpath.resolve()
            if not resolved.is_relative_to(base_resolved):
                raise VaultError(f"path escapes source directory: {fpath}")
            rel = fpath.relative_to(source_dir).as_posix()
            items.append((fpath, rel))

    items.sort(key=lambda pair: pair[1])
    if not items:
        raise VaultError(f"no files found in source directory: {source_dir}")
    return items


def build_cache_key(category: Category, artifact_id: str, archive_sha256: str) -> str:
    return f"alpha-vault-{category}-{artifact_id}-{archive_sha256[:16]}"


def _add_deterministic_regular_file(tf: tarfile.TarFile, abs_path: Path, relpath: str) -> None:
    """Write regular file entry cleanly without hardlink deduplication or host uid/mtime leaks."""
    info = tf.gettarinfo(str(abs_path), arcname=relpath)
    info.type = tarfile.REGTYPE
    info.linkname = ""
    info.size = abs_path.stat().st_size
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.mode = (info.mode & 0o777) or 0o644
    with abs_path.open("rb") as fh:
        tf.addfile(info, fh)


def pack_artifact(
    source_dir: Path,
    *,
    artifact_id: str,
    category: Category,
    manifest_out: Path,
    archive_dir: Path,
    vault_config_path: Path,
    source_commit: str = "UNKNOWN",
    codec: Codec = "auto",
    runner: CommandRunner = _default_runner,
) -> dict[str, Any]:
    """Create a deterministic compressed archive + SHA-256 manifest JSON."""
    validate_artifact_id(artifact_id)
    cfg = load_vault_config(vault_config_path)
    cat_info = cfg["categories"].get(category)
    if not isinstance(cat_info, dict) or not cat_info.get("folder_id"):
        raise VaultError(f"unknown or unconfigured vault category: {category}")

    safe_files = _collect_safe_files(source_dir)
    compression = _resolve_codec(codec)
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"{artifact_id}.{compression}"
    _validate_safe_archive_name(archive_name)
    archive_path = archive_dir / archive_name

    file_records: list[dict[str, Any]] = []
    uncompressed_bytes = 0
    for abs_path, relpath in safe_files:
        digest, size = sha256_file(abs_path)
        uncompressed_bytes += size
        file_records.append({"relpath": relpath, "sha256": digest, "bytes": size})

    if compression == "tar.zst":
        with tempfile.TemporaryDirectory() as tmp:
            raw_tar = Path(tmp) / f"{artifact_id}.tar"
            with tarfile.open(raw_tar, mode="w") as tf:
                for abs_path, relpath in safe_files:
                    _add_deterministic_regular_file(tf, abs_path, relpath)
            proc = runner(["zstd", "-q", "-f", "-o", str(archive_path), str(raw_tar)])
            if proc.returncode != 0:
                raise VaultError(f"zstd compression failed: {proc.stderr.strip()}")
    elif compression == "tar.gz":
        with archive_path.open("wb") as raw_fh:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_fh, mtime=0) as gz_fh:
                with tarfile.open(fileobj=gz_fh, mode="w") as tf:
                    for abs_path, relpath in safe_files:
                        _add_deterministic_regular_file(tf, abs_path, relpath)
    else:
        with tarfile.open(archive_path, mode="w:xz") as tf:
            for abs_path, relpath in safe_files:
                _add_deterministic_regular_file(tf, abs_path, relpath)

    archive_sha256, archive_bytes = sha256_file(archive_path)
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "artifact_id": artifact_id,
        "category": category,
        "created_at_utc": utc_now_z(),
        "source_commit": source_commit,
        "compression": compression,
        "archive_name": archive_name,
        "archive_sha256": archive_sha256,
        "archive_bytes": archive_bytes,
        "uncompressed_bytes": uncompressed_bytes,
        "cache_key": build_cache_key(category, artifact_id, archive_sha256),
        "gdrive_folder_id": cat_info["folder_id"],
        "gdrive_folder_name": cat_info.get("folder_name", category),
        "gdrive_file_id": None,
        "gdrive_url": None,
        "files": file_records,
    }
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise VaultError(f"failed to read manifest '{manifest_path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise VaultError(f"invalid JSON in manifest '{manifest_path}': {exc}") from exc
    if not isinstance(data, dict):
        raise VaultError(f"manifest '{manifest_path}' must contain a JSON object")

    required = ("schema_version", "artifact_id", "category", "compression", "archive_name", "archive_sha256", "files")
    for key in required:
        if key not in data:
            raise VaultError(f"manifest '{manifest_path}' missing required field '{key}'")

    for str_key in ("schema_version", "artifact_id", "category", "compression", "archive_name", "archive_sha256"):
        if not isinstance(data[str_key], str):
            raise VaultIntegrityError(
                f"manifest '{manifest_path}' field '{str_key}' must be a string, got {type(data[str_key]).__name__}"
            )

    validate_artifact_id(data["artifact_id"])
    _validate_safe_archive_name(data["archive_name"])
    if not SHA256_HEX_RE.fullmatch(data["archive_sha256"]):
        raise VaultIntegrityError(
            f"manifest '{manifest_path}' field 'archive_sha256' must be 64 lowercase hex chars"
        )
    if "archive_bytes" in data and (type(data["archive_bytes"]) is not int or data["archive_bytes"] < 0):
        raise VaultIntegrityError(
            f"manifest '{manifest_path}' field 'archive_bytes' must be a non-negative integer"
        )
    if not isinstance(data["files"], list):
        raise VaultError(f"manifest '{manifest_path}' field 'files' must be a list")
    for entry in data["files"]:
        if not isinstance(entry, dict) or "relpath" not in entry or "sha256" not in entry or "bytes" not in entry:
            raise VaultIntegrityError(f"manifest '{manifest_path}' contains malformed file entry")
        if not isinstance(entry["relpath"], str):
            raise VaultIntegrityError(f"manifest '{manifest_path}' file entry 'relpath' must be a string")
        _validate_safe_relpath(entry["relpath"])
        if not isinstance(entry["sha256"], str) or not SHA256_HEX_RE.fullmatch(entry["sha256"]):
            raise VaultIntegrityError(
                f"manifest '{manifest_path}' file entry '{entry['relpath']}' has invalid sha256"
            )
        if type(entry["bytes"]) is not int or entry["bytes"] < 0:
            raise VaultIntegrityError(
                f"manifest '{manifest_path}' file entry '{entry['relpath']}' 'bytes' must be a non-negative int"
            )
    return data


def verify_archive_checksum(archive_path: Path, manifest: dict[str, Any]) -> None:
    if not archive_path.is_file():
        raise VaultIntegrityError(f"archive not found: {archive_path}")
    actual_sha, actual_bytes = sha256_file(archive_path)
    if actual_sha != manifest["archive_sha256"]:
        raise VaultIntegrityError(
            f"archive SHA-256 mismatch for '{archive_path.name}': expected {manifest['archive_sha256']}, got {actual_sha}"
        )
    if "archive_bytes" in manifest and (
        type(manifest["archive_bytes"]) is not int or actual_bytes != manifest["archive_bytes"]
    ):
        raise VaultIntegrityError(
            f"archive size mismatch for '{archive_path.name}': expected {manifest['archive_bytes']}, got {actual_bytes}"
        )


def _safe_extract_tar(tf: tarfile.TarFile, dest_dir: Path, expected_relpaths: set[str]) -> None:
    dest_resolved = dest_dir.resolve()
    members = tf.getmembers()
    extracted_regular_paths: set[str] = set()

    for member in members:
        if not (member.isreg() or member.isdir()):
            raise VaultIntegrityError(f"disallowed special tar member: {member.name}")
        if "\\" in member.name:
            raise VaultIntegrityError(f"unsafe backslash in tar member: {member.name}")
        member_path = Path(member.name)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise VaultIntegrityError(f"unsafe path traversal in tar member: {member.name}")
        target = (dest_dir / member_path).resolve()
        if target != dest_resolved and not target.is_relative_to(dest_resolved):
            raise VaultIntegrityError(f"tar member escapes destination dir: {member.name}")

        member.mode = member.mode & 0o777
        if member.isreg():
            norm_rel = PurePosixPath(member.name).as_posix()
            if norm_rel not in expected_relpaths:
                raise VaultIntegrityError(f"unexpected unmanifested file inside archive: {norm_rel}")
            extracted_regular_paths.add(norm_rel)

    missing = expected_relpaths - extracted_regular_paths
    if missing:
        raise VaultIntegrityError(f"manifested file(s) missing from archive: {sorted(missing)}")

    tf.extractall(dest_dir, members=members, numeric_owner=True)


def extract_verified_archive(
    archive_path: Path,
    manifest_path: Path,
    dest_dir: Path,
    *,
    runner: CommandRunner = _default_runner,
) -> dict[str, Any]:
    """Verify archive checksum, extract safely without traversal/extra files, and verify every file SHA-256."""
    manifest = load_manifest(manifest_path)
    verify_archive_checksum(archive_path, manifest)

    expected_relpaths = {_validate_safe_relpath(str(entry["relpath"])) for entry in manifest["files"]}
    dest_dir.mkdir(parents=True, exist_ok=True)
    compression = manifest["compression"]

    if compression == "tar.zst":
        if not shutil.which("zstd"):
            raise VaultError("cannot extract '.tar.zst' because 'zstd' binary is not on PATH")
        with tempfile.TemporaryDirectory() as tmp:
            raw_tar = Path(tmp) / "payload.tar"
            proc = runner(["zstd", "-d", "-q", "-f", "-o", str(raw_tar), str(archive_path)])
            if proc.returncode != 0:
                raise VaultError(f"zstd decompression failed: {proc.stderr.strip()}")
            with tarfile.open(raw_tar, mode="r") as tf:
                _safe_extract_tar(tf, dest_dir, expected_relpaths)
    elif compression == "tar.gz":
        with tarfile.open(archive_path, mode="r:gz") as tf:
            _safe_extract_tar(tf, dest_dir, expected_relpaths)
    elif compression == "tar.xz":
        with tarfile.open(archive_path, mode="r:xz") as tf:
            _safe_extract_tar(tf, dest_dir, expected_relpaths)
    else:
        raise VaultError(f"unsupported manifest compression '{compression}'")

    dest_resolved = dest_dir.resolve()
    for entry in manifest["files"]:
        relpath = _validate_safe_relpath(str(entry["relpath"]))
        target = (dest_dir / relpath).resolve()
        if not target.is_relative_to(dest_resolved) or target.is_symlink() or not target.is_file():
            raise VaultIntegrityError(f"expected extracted file missing or unsafe: {relpath}")
        actual_sha, actual_bytes = sha256_file(target)
        if actual_sha != entry["sha256"] or actual_bytes != int(entry["bytes"]):
            raise VaultIntegrityError(
                f"extracted file checksum mismatch for '{relpath}': expected {entry['sha256']}, got {actual_sha}"
            )

    return {
        "verified": True,
        "artifact_id": manifest["artifact_id"],
        "files_verified": len(manifest["files"]),
        "dest_dir": str(dest_dir),
    }


def _parse_gdrive_file_id(output: str) -> str | None:
    stripped = output.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict) and parsed.get("id"):
            return str(parsed["id"])
    except json.JSONDecodeError:
        pass
    match = DRIVE_ID_IN_TEXT_RE.search(stripped)
    if match:
        return match.group(1)
    return None


def _select_backend(backend: Backend, *, prefer_rclone_when_no_id: bool = False, has_file_id: bool = True) -> Literal["gdrive", "rclone"]:
    if backend == "gdrive":
        if not shutil.which("gdrive"):
            raise VaultError("'gdrive' backend requested but 'gdrive' CLI is not installed")
        return "gdrive"
    if backend == "rclone":
        if not shutil.which("rclone"):
            raise VaultError("'rclone' backend requested but 'rclone' CLI is not installed")
        return "rclone"

    if prefer_rclone_when_no_id and not has_file_id and shutil.which("rclone"):
        return "rclone"
    if shutil.which("gdrive"):
        return "gdrive"
    if shutil.which("rclone"):
        return "rclone"
    raise VaultError("neither 'gdrive' nor 'rclone' CLI found on PATH")


def push_to_drive(
    manifest_path: Path,
    archive_path: Path,
    *,
    backend: Backend = "auto",
    rclone_remote: str = "gdrive:Alpha_mining_Vault",
    dry_run: bool = False,
    runner: CommandRunner = _default_runner,
) -> dict[str, Any]:
    """Upload or update verified archive to Google Drive Vault and record gdrive_file_id in manifest."""
    manifest = load_manifest(manifest_path)
    verify_archive_checksum(archive_path, manifest)
    selected = _select_backend(backend)
    existing_id = manifest.get("gdrive_file_id")
    folder_id = manifest.get("gdrive_folder_id")

    if selected == "gdrive":
        if existing_id:
            cmd = ["gdrive", "mutate", "update", str(existing_id), str(archive_path)]
        else:
            if not folder_id:
                raise VaultError("manifest missing gdrive_folder_id for initial upload")
            cmd = [
                "gdrive",
                "mutate",
                "upload",
                str(archive_path),
                "--parent",
                str(folder_id),
                "--json",
            ]
    else:
        folder_name = manifest.get("gdrive_folder_name", manifest["category"])
        cmd = [
            "rclone",
            "copyto",
            str(archive_path),
            f"{rclone_remote}/{folder_name}/{manifest['archive_name']}",
        ]

    if dry_run:
        return {"dry_run": True, "backend": selected, "command": cmd}

    proc = runner(cmd)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise VaultError(f"Drive push failed via {selected}: {detail}")

    if selected == "gdrive":
        parsed_id = _parse_gdrive_file_id(proc.stdout) or existing_id
        if parsed_id:
            manifest["gdrive_file_id"] = parsed_id
            manifest["gdrive_url"] = f"https://drive.google.com/file/d/{parsed_id}/view"
    manifest["last_pushed_utc"] = utc_now_z()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def pull_from_drive(
    manifest_path: Path,
    dest_dir: Path,
    *,
    cache_dir: Path,
    backend: Backend = "auto",
    rclone_remote: str = "gdrive:Alpha_mining_Vault",
    runner: CommandRunner = _default_runner,
) -> dict[str, Any]:
    """Hydrate from hot cache first; fallback to Google Drive Vault on miss, then verify and extract."""
    manifest = load_manifest(manifest_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_archive = (cache_dir / manifest["archive_name"]).resolve()
    if not cached_archive.is_relative_to(cache_dir.resolve()):
        raise VaultIntegrityError("archive path escapes cache directory")

    cache_hit = False
    if cached_archive.is_file():
        try:
            verify_archive_checksum(cached_archive, manifest)
            cache_hit = True
        except VaultIntegrityError:
            cache_hit = False

    if not cache_hit:
        file_id = manifest.get("gdrive_file_id")
        selected = _select_backend(
            backend,
            prefer_rclone_when_no_id=True,
            has_file_id=bool(file_id),
        )
        if selected == "gdrive":
            if not file_id:
                raise VaultError(
                    "cache miss and manifest has no 'gdrive_file_id'; push artifact first or use rclone"
                )
            cmd = ["gdrive", "readonly", "download", str(file_id), "--out", str(cached_archive)]
        else:
            folder_name = manifest.get("gdrive_folder_name", manifest["category"])
            cmd = [
                "rclone",
                "copyto",
                f"{rclone_remote}/{folder_name}/{manifest['archive_name']}",
                str(cached_archive),
            ]
        proc = runner(cmd)
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip()
            raise VaultError(f"Drive pull failed via {selected}: {detail}")

    result = extract_verified_archive(cached_archive, manifest_path, dest_dir, runner=runner)
    result["cache_hit"] = cache_hit
    result["cached_archive"] = str(cached_archive)
    return result
