"""Hybrid storage layer separating Git SHA-256 manifests from Actions hot cache and Google Drive."""

from .vault import (
    VaultError,
    VaultIntegrityError,
    build_cache_key,
    default_vault_config_path,
    extract_verified_archive,
    load_manifest,
    load_vault_config,
    pack_artifact,
    pull_from_drive,
    push_to_drive,
    sha256_file,
    verify_archive_checksum,
)

__all__ = [
    "VaultError",
    "VaultIntegrityError",
    "build_cache_key",
    "default_vault_config_path",
    "extract_verified_archive",
    "load_manifest",
    "load_vault_config",
    "pack_artifact",
    "pull_from_drive",
    "push_to_drive",
    "sha256_file",
    "verify_archive_checksum",
]
