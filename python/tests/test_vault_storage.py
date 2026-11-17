"""Tests for Quant Vault packaging, SHA-256 verification, path safety, and Drive sync."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))

from alpha_mining.storage.vault import (  # noqa: E402
    VaultError,
    VaultIntegrityError,
    default_vault_config_path,
    extract_verified_archive,
    pack_artifact,
    pull_from_drive,
    push_to_drive,
    sha256_file,
)


class TestVaultStorage(unittest.TestCase):
    def setUp(self) -> None:
        self.vault_cfg = default_vault_config_path(REPO_ROOT)

    def test_pack_verify_and_extract_round_trip_and_tamper_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            src = tmp_dir / "dataset_src"
            (src / "sub").mkdir(parents=True)
            (src / "features.parquet").write_bytes(b"PAR1synthetic-data-payload")
            (src / "sub" / "meta.json").write_text('{"rows": 42}\n', encoding="utf-8")

            manifest_path = tmp_dir / "manifests" / "synth_ds.manifest.json"
            archive_dir = tmp_dir / "cache"

            manifest = pack_artifact(
                src,
                artifact_id="synth_ds_v1",
                category="dataset",
                manifest_out=manifest_path,
                archive_dir=archive_dir,
                vault_config_path=self.vault_cfg,
                source_commit="abc1234",
                codec="gz",
            )
            self.assertEqual(manifest["compression"], "tar.gz")
            self.assertTrue(manifest["cache_key"].startswith("alpha-vault-dataset-synth_ds_v1-"))
            self.assertEqual(len(manifest["files"]), 2)

            archive_path = archive_dir / manifest["archive_name"]
            dest = tmp_dir / "extracted"
            res = extract_verified_archive(archive_path, manifest_path, dest)
            self.assertTrue(res["verified"])
            self.assertEqual(res["files_verified"], 2)
            self.assertEqual(
                (dest / "features.parquet").read_bytes(),
                b"PAR1synthetic-data-payload",
            )

            # Tamper 1 byte -> must fail checksum check before extraction
            tampered = archive_path.read_bytes()
            archive_path.write_bytes(tampered[:-1] + bytes([tampered[-1] ^ 0xFF]))
            with self.assertRaises(VaultIntegrityError):
                extract_verified_archive(archive_path, manifest_path, tmp_dir / "bad_dest")

    def test_rejects_symlinks_and_tar_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            src = tmp_dir / "src"
            src.mkdir()
            outside = tmp_dir / "secret.txt"
            outside.write_text("top-secret", encoding="utf-8")
            (src / "link.txt").symlink_to(outside)

            with self.assertRaises(VaultError):
                pack_artifact(
                    src,
                    artifact_id="bad_sym",
                    category="dataset",
                    manifest_out=tmp_dir / "m.json",
                    archive_dir=tmp_dir / "c",
                    vault_config_path=self.vault_cfg,
                    codec="gz",
                )

            # Craft malicious tar.gz with path traversal member whose archive_sha256 matches manifest
            evil_tar = tmp_dir / "evil.tar.gz"
            with tarfile.open(evil_tar, "w:gz") as tf:
                payload = b"pwn"
                info = tarfile.TarInfo(name="../../escape.txt")
                info.size = len(payload)
                tf.addfile(info, io.BytesIO(payload))
            digest, size = sha256_file(evil_tar)
            evil_manifest = tmp_dir / "evil.manifest.json"
            evil_manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "artifact_id": "evil_pack",
                        "category": "dataset",
                        "compression": "tar.gz",
                        "archive_name": "evil.tar.gz",
                        "archive_sha256": digest,
                        "archive_bytes": size,
                        "files": [{"relpath": "../../escape.txt", "sha256": digest, "bytes": 3}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(VaultIntegrityError):
                extract_verified_archive(evil_tar, evil_manifest, tmp_dir / "extract_root")

    def test_push_and_pull_drive_cache_hit_and_miss(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            src = tmp_dir / "bt_src"
            src.mkdir()
            (src / "pnl.parquet").write_bytes(b"backtest-bytes")

            manifest_path = tmp_dir / "bt.manifest.json"
            cache_dir = tmp_dir / "hot_cache"
            manifest = pack_artifact(
                src,
                artifact_id="bt_run_01",
                category="backtest_cache",
                manifest_out=manifest_path,
                archive_dir=cache_dir,
                vault_config_path=self.vault_cfg,
                codec="gz",
            )
            archive_path = cache_dir / manifest["archive_name"]

            with mock.patch("alpha_mining.storage.vault.shutil.which", return_value=None):
                with self.assertRaises(VaultError):
                    push_to_drive(manifest_path, archive_path, backend="gdrive")

            commands_seen: list[list[str]] = []

            def fake_gdrive_push(cmd: list[str]) -> subprocess.CompletedProcess[str]:
                commands_seen.append(cmd)
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    f"Uploaded {archive_path.name} (ID: drive-file-999)\n",
                    "",
                )

            with mock.patch("alpha_mining.storage.vault.shutil.which", return_value="/usr/bin/gdrive"):
                pushed = push_to_drive(
                    manifest_path,
                    archive_path,
                    backend="gdrive",
                    runner=fake_gdrive_push,
                )
            self.assertEqual(pushed["gdrive_file_id"], "drive-file-999")
            self.assertIn("1mSUfgnR4yNhSi3ggM_DYHMjP9ynB5Yxr", commands_seen[0])

            # Cache hit skips Drive download completely (works even when Drive CLIs are absent)
            def fail_if_called(cmd: list[str]) -> subprocess.CompletedProcess[str]:
                raise AssertionError(f"Drive download should not run on cache hit: {cmd}")

            with mock.patch("alpha_mining.storage.vault.shutil.which", return_value=None):
                hit_res = pull_from_drive(
                    manifest_path,
                    tmp_dir / "out_hit",
                    cache_dir=cache_dir,
                    backend="gdrive",
                    runner=fail_if_called,
                )
            self.assertTrue(hit_res["cache_hit"])

            # Move archive aside and test cache miss download from Drive
            saved_bytes = archive_path.read_bytes()
            archive_path.unlink()

            def fake_gdrive_pull(cmd: list[str]) -> subprocess.CompletedProcess[str]:
                out_idx = cmd.index("--out") + 1
                Path(cmd[out_idx]).write_bytes(saved_bytes)
                return subprocess.CompletedProcess(cmd, 0, "Downloaded ok\n", "")

            with mock.patch("alpha_mining.storage.vault.shutil.which", return_value="/usr/bin/gdrive"):
                miss_res = pull_from_drive(
                    manifest_path,
                    tmp_dir / "out_miss",
                    cache_dir=cache_dir,
                    backend="gdrive",
                    runner=fake_gdrive_pull,
                )
            self.assertFalse(miss_res["cache_hit"])
            self.assertEqual((tmp_dir / "out_miss" / "pnl.parquet").read_bytes(), b"backtest-bytes")

    def test_deterministic_tar_gz_reproducibility_across_mtimes(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            src_a = tmp_dir / "a"
            src_b = tmp_dir / "b"
            src_a.mkdir()
            src_b.mkdir()
            fa = src_a / "data.parquet"
            fb = src_b / "data.parquet"
            fa.write_bytes(b"identical-quant-payload")
            fb.write_bytes(b"identical-quant-payload")
            os.utime(fa, (1000000, 1000000))
            os.utime(fb, (2000000, 2000000))

            m_a = pack_artifact(
                src_a,
                artifact_id="repro_ds",
                category="dataset",
                manifest_out=tmp_dir / "ma.json",
                archive_dir=tmp_dir / "ca",
                vault_config_path=self.vault_cfg,
                codec="gz",
            )
            m_b = pack_artifact(
                src_b,
                artifact_id="repro_ds",
                category="dataset",
                manifest_out=tmp_dir / "mb.json",
                archive_dir=tmp_dir / "cb",
                vault_config_path=self.vault_cfg,
                codec="gz",
            )
            self.assertEqual(m_a["archive_sha256"], m_b["archive_sha256"])
            self.assertEqual(m_a["cache_key"], m_b["cache_key"])

    def test_hardlinks_xz_roundtrip_symlink_dir_and_unmanifested_member_rejection(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            src = tmp_dir / "hard_src"
            src.mkdir()
            f1 = src / "a.parquet"
            f2 = src / "b.parquet"
            f1.write_bytes(b"shared-inode-content")
            os.link(f1, f2)

            manifest_path = tmp_dir / "hard.manifest.json"
            cache_dir = tmp_dir / "cache"
            manifest = pack_artifact(
                src,
                artifact_id="hardlink_ds",
                category="dataset",
                manifest_out=manifest_path,
                archive_dir=cache_dir,
                vault_config_path=self.vault_cfg,
                codec="xz",
            )
            self.assertEqual(manifest["compression"], "tar.xz")
            dest = tmp_dir / "out_hard"
            res = extract_verified_archive(cache_dir / manifest["archive_name"], manifest_path, dest)
            self.assertTrue(res["verified"])
            self.assertEqual((dest / "b.parquet").read_bytes(), b"shared-inode-content")

            # Reject symlink directory in source payload
            sym_src = tmp_dir / "sym_src"
            sym_src.mkdir()
            ext_dir = tmp_dir / "ext_dir"
            ext_dir.mkdir()
            (ext_dir / "leak.txt").write_text("leak", encoding="utf-8")
            (sym_src / "linked_sub").symlink_to(ext_dir)
            with self.assertRaises(VaultError):
                pack_artifact(
                    sym_src,
                    artifact_id="sym_dir_bad",
                    category="dataset",
                    manifest_out=tmp_dir / "s.json",
                    archive_dir=tmp_dir / "sc",
                    vault_config_path=self.vault_cfg,
                    codec="gz",
                )

            # Reject archive containing an unmanifested extra file even with matching archive_sha256
            extra_tar = tmp_dir / "extra.tar.gz"
            with tarfile.open(extra_tar, "w:gz") as tf:
                p1 = b"legit"
                i1 = tarfile.TarInfo(name="legit.txt")
                i1.size = len(p1)
                tf.addfile(i1, io.BytesIO(p1))
                p2 = b"sneaky"
                i2 = tarfile.TarInfo(name="extra.txt")
                i2.size = len(p2)
                tf.addfile(i2, io.BytesIO(p2))
            extra_sha, extra_size = sha256_file(extra_tar)
            legit_sha = __import__("hashlib").sha256(b"legit").hexdigest()
            extra_manifest = tmp_dir / "extra.manifest.json"
            extra_manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "artifact_id": "extra_pack",
                        "category": "dataset",
                        "compression": "tar.gz",
                        "archive_name": "extra.tar.gz",
                        "archive_sha256": extra_sha,
                        "archive_bytes": extra_size,
                        "files": [{"relpath": "legit.txt", "sha256": legit_sha, "bytes": 5}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(VaultIntegrityError) as ctx:
                extract_verified_archive(extra_tar, extra_manifest, tmp_dir / "extra_out")
            self.assertIn("unmanifested", str(ctx.exception))

            # Reject archive_name traversal in manifest
            bad_name_manifest = tmp_dir / "bad_name.manifest.json"
            bad_name_manifest.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "artifact_id": "bad_name",
                        "category": "dataset",
                        "compression": "tar.gz",
                        "archive_name": "../escape.tar.gz",
                        "archive_sha256": extra_sha,
                        "files": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(VaultIntegrityError):
                extract_verified_archive(extra_tar, bad_name_manifest, tmp_dir / "bad_name_out")

    def test_gdrive_update_rclone_auto_fallback_and_cli(self) -> None:
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            src = tmp_dir / "snap"
            src.mkdir()
            (src / "state.json").write_text('{"ok": true}\n', encoding="utf-8")

            manifest_path = tmp_dir / "snap.manifest.json"
            cache_dir = tmp_dir / "cache"
            manifest = pack_artifact(
                src,
                artifact_id="snap_01",
                category="state_snapshot",
                manifest_out=manifest_path,
                archive_dir=cache_dir,
                vault_config_path=self.vault_cfg,
                codec="gz",
            )
            archive_path = cache_dir / manifest["archive_name"]

            # Pre-populate gdrive_file_id -> push_to_drive must issue `gdrive mutate update`
            m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            m_data["gdrive_file_id"] = "existing-file-123"
            manifest_path.write_text(json.dumps(m_data, indent=2) + "\n", encoding="utf-8")

            seen_cmds: list[list[str]] = []

            def fake_update(cmd: list[str]) -> subprocess.CompletedProcess[str]:
                seen_cmds.append(cmd)
                return subprocess.CompletedProcess(cmd, 0, "Updated\n", "")

            with mock.patch("alpha_mining.storage.vault.shutil.which", return_value="/usr/bin/gdrive"):
                updated = push_to_drive(manifest_path, archive_path, backend="gdrive", runner=fake_update)
            self.assertEqual(seen_cmds[0][:4], ["gdrive", "mutate", "update", "existing-file-123"])
            self.assertEqual(updated["gdrive_file_id"], "existing-file-123")

            # Test rclone push + backend="auto" fallback on pull when gdrive_file_id is None
            m_data["gdrive_file_id"] = None
            manifest_path.write_text(json.dumps(m_data, indent=2) + "\n", encoding="utf-8")
            rclone_cmds: list[list[str]] = []

            def fake_rclone_push(cmd: list[str]) -> subprocess.CompletedProcess[str]:
                rclone_cmds.append(cmd)
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with mock.patch("alpha_mining.storage.vault.shutil.which", return_value="/usr/bin/tool"):
                push_to_drive(manifest_path, archive_path, backend="rclone", runner=fake_rclone_push)
            self.assertEqual(rclone_cmds[0][0], "rclone")
            self.assertIn("gdrive:Alpha_mining_Vault/state_snapshots/snap_01.tar.gz", rclone_cmds[0])

            saved_bytes = archive_path.read_bytes()
            archive_path.unlink()
            pull_cmds: list[list[str]] = []

            def fake_auto_pull(cmd: list[str]) -> subprocess.CompletedProcess[str]:
                pull_cmds.append(cmd)
                Path(cmd[-1]).write_bytes(saved_bytes)
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with mock.patch("alpha_mining.storage.vault.shutil.which", return_value="/usr/bin/tool"):
                pulled = pull_from_drive(
                    manifest_path,
                    tmp_dir / "rclone_out",
                    cache_dir=cache_dir,
                    backend="auto",
                    runner=fake_auto_pull,
                )
            self.assertEqual(pull_cmds[0][0], "rclone")
            self.assertTrue(pulled["verified"])

            # Test vault_sync.py CLI end-to-end (pack, cache-key, verify-archive, extract)
            script = REPO_ROOT / "scripts" / "vault_sync.py"
            cli_manifest = tmp_dir / "cli.manifest.json"
            cli_cache = tmp_dir / "cli_cache"
            cli_dest = tmp_dir / "cli_dest"

            for args in (
                [
                    "pack",
                    "--source",
                    str(src),
                    "--artifact-id",
                    "cli_snap",
                    "--category",
                    "state_snapshot",
                    "--manifest-out",
                    str(cli_manifest),
                    "--archive-dir",
                    str(cli_cache),
                    "--codec",
                    "gz",
                ],
                ["cache-key", "--manifest", str(cli_manifest)],
                [
                    "verify-archive",
                    "--manifest",
                    str(cli_manifest),
                    "--archive",
                    str(cli_cache / "cli_snap.tar.gz"),
                ],
                [
                    "extract",
                    "--manifest",
                    str(cli_manifest),
                    "--archive",
                    str(cli_cache / "cli_snap.tar.gz"),
                    "--dest",
                    str(cli_dest),
                ],
            ):
                proc = subprocess.run(
                    [sys.executable, str(script), *args],
                    cwd=str(REPO_ROOT),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(proc.returncode, 0, f"{args} failed: {proc.stderr}")
            self.assertTrue((cli_dest / "state.json").is_file())


if __name__ == "__main__":
    unittest.main()
