"""Unit and adversarial tests for atomic model registry and deterministic MQL5 assembly."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))

from alpha_mining.strategy.model_registry import (  # noqa: E402
    ModelRegistryError,
    assemble_portfolio_mq5,
    assemble_single_model_mq5,
    load_and_validate_registry,
    load_portfolio_spec,
)


def _copy_models_fixture(dst_root: Path) -> None:
    shutil.copytree(REPO_ROOT / "models", dst_root / "models")
    shutil.copytree(REPO_ROOT / "portfolios", dst_root / "portfolios")


class TestModelRegistryAndAssembler(unittest.TestCase):
    def test_repo_registry_and_assembled_bundle_have_zero_drift(self) -> None:
        registry = load_and_validate_registry(REPO_ROOT)
        self.assertEqual(len(registry.models), 12)

        ids = [m.model_id for m in registry.models]
        self.assertEqual(
            ids,
            [
                "alpha005",
                "alpha055",
                "alpha010",
                "heiken_ma_12_26",
                "impulse_efficiency_s1",
                "impulse_efficiency_s2",
                "monthly_day20",
                "macross_sma_28_101",
                "donchian_breakout_40_10",
                "ema_4h_5_20",
                "session_a_22_06",
                "session_b_21_04",
            ],
        )

        # Globally unique Magic Numbers and prefixes
        magics = [m.magic_number for m in registry.models]
        self.assertEqual(len(set(magics)), len(magics))
        prefixes = [m.mql5_prefix.lower() for m in registry.models]
        self.assertEqual(len(set(prefixes)), len(prefixes))

        # Validate live_bundle_v1 portfolio and zero drift against committed .mq5
        portfolio_path = REPO_ROOT / "portfolios" / "live_bundle_v1.json"
        spec = load_portfolio_spec(portfolio_path, registry)
        assembled_a = assemble_portfolio_mq5(registry, spec)
        assembled_b = assemble_portfolio_mq5(registry, spec)
        self.assertEqual(assembled_a, assembled_b)

        committed_path = REPO_ROOT / "portfolios" / "assembled" / "live_bundle_v1.mq5"
        self.assertTrue(committed_path.is_file())
        self.assertEqual(committed_path.read_text(encoding="utf-8"), assembled_a)

        # Verify every included model exposes ONLY Enable + Lot inputs and lifecycle calls
        self.assertIn("input long Account_Lock = 0;", assembled_a)
        for slot in spec.slots:
            rec = registry.get(slot.model_id)
            self.assertIn(f"input bool   Enable_{rec.mql5_prefix} =", assembled_a)
            self.assertIn(f"input double Lot_{rec.mql5_prefix}    =", assembled_a)
            self.assertIn(f"Init_{rec.mql5_prefix}();", assembled_a)
            self.assertIn(f"LogConfig_{rec.mql5_prefix}();", assembled_a)
            self.assertIn(
                f"EnforceDisabled_{rec.mql5_prefix}(Enable_{rec.mql5_prefix}, Lot_{rec.mql5_prefix});",
                assembled_a,
            )
            self.assertIn(
                f"Process_{rec.mql5_prefix}(Enable_{rec.mql5_prefix}, Lot_{rec.mql5_prefix});",
                assembled_a,
            )
            self.assertIn(str(rec.magic_number), assembled_a)

        # Market-closed (retcode 10018) cooldown guard must be present in every assembled EA
        self.assertIn("IsMarketTradeAllowed", assembled_a)
        self.assertIn("TRADE_RETCODE_MARKET_CLOSED", assembled_a)

        # Tested 9-model Portfolio C v2 (5 new MT5 models) assembles with zero drift
        p9_spec = load_portfolio_spec(REPO_ROOT / "portfolios" / "portfolio_c_9models_v2.json", registry)
        self.assertEqual(
            [s.model_id for s in p9_spec.slots],
            [
                "alpha005",
                "alpha055",
                "alpha010",
                "heiken_ma_12_26",
                "macross_sma_28_101",
                "donchian_breakout_40_10",
                "ema_4h_5_20",
                "session_a_22_06",
                "session_b_21_04",
            ],
        )
        p9_assembled = assemble_portfolio_mq5(registry, p9_spec)
        p9_committed = REPO_ROOT / "portfolios" / "assembled" / "portfolio_c_9models_v2.mq5"
        self.assertEqual(p9_committed.read_text(encoding="utf-8"), p9_assembled)

    def test_single_model_standalone_assembly_is_isolated(self) -> None:
        registry = load_and_validate_registry(REPO_ROOT)
        standalone = assemble_single_model_mq5(registry, "impulse_efficiency_s1", default_lot=0.05)

        self.assertIn("input bool   Enable_Impulse1 = true;", standalone)
        self.assertIn("input double Lot_Impulse1    = 0.05;", standalone)
        self.assertIn("#define MAGIC_IMPULSE1             20261101", standalone)
        self.assertIn("Process_Impulse1(Enable_Impulse1, Lot_Impulse1);", standalone)

        # Must NOT include other models
        self.assertNotIn("Enable_Impulse2", standalone)
        self.assertNotIn("Enable_Alpha005", standalone)
        self.assertNotIn("MAGIC_DAY20", standalone)

    def test_rejects_duplicate_magic_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _copy_models_fixture(root)
            reg_path = root / "models" / "registry.json"
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
            reg["models"][1]["magic_number"] = reg["models"][0]["magic_number"]
            reg_path.write_text(json.dumps(reg), encoding="utf-8")

            with self.assertRaisesRegex(ModelRegistryError, "duplicate magic_number"):
                load_and_validate_registry(root)

    def test_rejects_magic_mismatch_between_spec_and_mqh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _copy_models_fixture(root)
            mod_path = root / "models" / "alpha" / "monthly_day20" / "module.mqh"
            text = mod_path.read_text(encoding="utf-8").replace("20261120", "99999999")
            mod_path.write_text(text, encoding="utf-8")

            with self.assertRaisesRegex(ModelRegistryError, "does not match spec/registry magic_number"):
                load_and_validate_registry(root)

    def test_rejects_missing_mql5_lifecycle_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _copy_models_fixture(root)
            mod_path = root / "models" / "alpha" / "alpha010" / "module.mqh"
            text = mod_path.read_text(encoding="utf-8").replace("void Process_Alpha010", "void Broken_Alpha010")
            mod_path.write_text(text, encoding="utf-8")

            with self.assertRaisesRegex(ModelRegistryError, "missing required MQL5 lifecycle hook 'Process_Alpha010'"):
                load_and_validate_registry(root)

    def test_rejects_unbalanced_braces_in_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _copy_models_fixture(root)
            mod_path = root / "models" / "alpha" / "alpha005" / "module.mqh"
            mod_path.write_text(mod_path.read_text(encoding="utf-8") + "\n}\n", encoding="utf-8")

            with self.assertRaisesRegex(ModelRegistryError, "unbalanced"):
                load_and_validate_registry(root)

    def test_rejects_orphan_unregistered_model_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _copy_models_fixture(root)
            orphan_dir = root / "models" / "beta" / "unregistered_beta_01"
            orphan_dir.mkdir(parents=True)
            (orphan_dir / "spec.json").write_text('{"schema_version":"1.0"}', encoding="utf-8")

            with self.assertRaisesRegex(ModelRegistryError, "unregistered orphan model spec"):
                load_and_validate_registry(root)

    def test_rejects_invalid_evidence_status_and_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _copy_models_fixture(root)
            spec_path = root / "models" / "alpha" / "alpha005" / "spec.json"
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            spec["evidence_status"] = "production_guaranteed"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            with self.assertRaisesRegex(ModelRegistryError, "invalid evidence_status"):
                load_and_validate_registry(root)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _copy_models_fixture(root)
            reg_path = root / "models" / "registry.json"
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
            reg["models"][0]["spec_path"] = "../outside.json"
            reg_path.write_text(json.dumps(reg), encoding="utf-8")

            with self.assertRaisesRegex(ModelRegistryError, "escapes repository root"):
                load_and_validate_registry(root)

    def test_portfolio_rejects_duplicate_and_unknown_models(self) -> None:
        registry = load_and_validate_registry(REPO_ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            p_dup = Path(tmp) / "dup.json"
            p_dup.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "portfolio_id": "dup_test",
                        "ea_name": "DupTest",
                        "description": "Duplicate test",
                        "models": [
                            {"model_id": "alpha005", "enabled": True, "default_lot": 0.1},
                            {"model_id": "alpha005", "enabled": True, "default_lot": 0.1},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ModelRegistryError, "duplicate model_id"):
                load_portfolio_spec(p_dup, registry)

            p_unknown = Path(tmp) / "unknown.json"
            p_unknown.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "portfolio_id": "unk_test",
                        "ea_name": "UnkTest",
                        "description": "Unknown test",
                        "models": [{"model_id": "omega_missing", "enabled": True, "default_lot": 0.1}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ModelRegistryError, "unknown model_id"):
                load_portfolio_spec(p_unknown, registry)

    def test_cli_validate_list_check_and_build_single(self) -> None:
        cli = [sys.executable, str(REPO_ROOT / "scripts" / "build_ea_portfolio.py")]

        val_res = subprocess.run(
            [*cli, "validate", "--check-assembled"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(val_res.returncode, 0, msg=val_res.stderr)
        val_json = json.loads(val_res.stdout)
        self.assertEqual(val_json["models_validated"], 12)

        list_res = subprocess.run(
            [*cli, "list", "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(list_res.returncode, 0, msg=list_res.stderr)
        rows = json.loads(list_res.stdout)
        self.assertEqual(len(rows), 12)

        with tempfile.TemporaryDirectory() as tmp:
            out_single = Path(tmp) / "Day20_Standalone.mq5"
            single_res = subprocess.run(
                [*cli, "build-single", "--model", "monthly_day20", "--out", str(out_single)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(single_res.returncode, 0, msg=single_res.stderr)
            content = out_single.read_text(encoding="utf-8")
            self.assertIn("Enable_Day20", content)
            self.assertNotIn("Enable_Alpha005", content)


if __name__ == "__main__":
    unittest.main()
