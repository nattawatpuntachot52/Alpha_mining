"""Tests for the Python OVCA control-plane bridge and quant domain boundaries."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))

from alpha_mining.accounting import ReconciliationEntry
from alpha_mining.control_plane import EpistemicClaim, OvcaBridge, OvcaBridgeError, utc_now_z
from alpha_mining.execution import ExecutionReport
from alpha_mining.research import ExperimentRecord
from alpha_mining.risk import RiskDecision
from alpha_mining.strategy import SignalIntent


class TestOvcaBridge(unittest.TestCase):
    def setUp(self) -> None:
        self.bridge = OvcaBridge(repo_root=REPO_ROOT)
        self.example_brief = REPO_ROOT / "workflows" / "examples" / "quant_alpha_brief.example.json"
        self.example_stream = REPO_ROOT / "workflows" / "examples" / "quant_alpha_pass_stream.json"

    def test_validate_and_verify_synthetic_examples(self) -> None:
        brief_res = self.bridge.validate_brief(self.example_brief)
        self.assertTrue(brief_res["valid"])
        self.assertEqual(brief_res["brief_id"], "brief-synth-microstructure-001")

        stream_res = self.bridge.verify_stream(self.example_stream, brief_path=self.example_brief)
        self.assertEqual(stream_res["snapshot"]["phase"], "completed")
        self.assertEqual(stream_res["snapshot"]["outcome"], "passed")
        self.assertEqual(stream_res["snapshot"]["evidence_count"], 2)

    def test_init_and_rejected_append_via_python_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            stream_file = tmp_dir / "events.json"
            bad_event_file = tmp_dir / "bad_event.json"

            init_res = self.bridge.init_workflow(
                brief_path=self.example_brief,
                workflow_id="wf-py-test",
                event_id="py-ev-0",
                occurred_at=utc_now_z(),
                out_path=stream_file,
            )
            self.assertEqual(
                init_res["snapshot"]["phase"], "awaiting_coordinator_dispatch"
            )

            # Wrong input_ref must be rejected by Rust WorkflowReducer
            bad_event = {
                "contract_version": "1.0",
                "workflow_id": "wf-py-test",
                "event_id": "py-ev-1",
                "sequence": 1,
                "previous_event_id": "py-ev-0",
                "occurred_at": utc_now_z(),
                "type": "coordinator_dispatched",
                "data": {
                    "invocation": {
                        "contract_version": "1.0",
                        "invocation_id": "inv-py-1",
                        "requested_by": "coordinator",
                        "role": "engineer",
                        "objective": "Bad ref test",
                        "authority_ref": "auth-synth-microstructure-001",
                        "input_refs": ["stale-or-wrong-ref"],
                        "attempt": 1,
                        "requested_at": utc_now_z(),
                    }
                },
            }
            bad_event_file.write_text(json.dumps(bad_event), encoding="utf-8")

            with self.assertRaises(OvcaBridgeError):
                self.bridge.append_event(
                    stream_file, bad_event_file, brief_path=self.example_brief
                )

            status_res = self.bridge.status(stream_file, brief_path=self.example_brief)
            self.assertEqual(status_res["snapshot"]["event_count"], 1)

    def test_epistemic_claim_guardrail(self) -> None:
        with self.assertRaises(ValueError):
            EpistemicClaim(
                kind="computed_result",
                statement="Backtest Sharpe 4.0",
                evidence_status="independently_replicated",
                source_ref="single-notebook",
            )

        claim = EpistemicClaim(
            kind="independently_verified_result",
            statement="OOS check verified by independent runner",
            evidence_status="reproducible",
            source_ref="ver-synth-1",
        )
        self.assertEqual(claim.to_dict()["kind"], "independently_verified_result")

    def test_domain_boundary_dataclasses_construct_cleanly(self) -> None:
        exp = ExperimentRecord(
            experiment_id="exp-001",
            hypothesis_ref="brief-synth-microstructure-001",
            trials_tested=3,
            evidence_status="proposed",
            oos_split_description="purged walk-forward",
            cost_model_summary="half-spread + 1bp",
            negative_result=False,
            reproduction_command="python3 -m unittest",
        )
        intent = SignalIntent(
            intent_id="int-001",
            strategy_id="strat-synth",
            instrument="SYNTH_PERP",
            target_exposure=0.1,
            generated_at_utc=utc_now_z(),
            research_evidence_ref=exp.experiment_id,
        )
        risk = RiskDecision(
            intent_id=intent.intent_id,
            approved=True,
            approved_exposure=0.1,
            rejection_reason=None,
            evaluated_at_utc=utc_now_z(),
        )
        fill = ExecutionReport(
            client_order_id="ord-001",
            intent_id=intent.intent_id,
            instrument=intent.instrument,
            side="buy",
            filled_qty=0.1,
            avg_fill_price=100.0,
            fee_paid=0.01,
            executed_at_utc=utc_now_z(),
        )
        acct = ReconciliationEntry(
            entry_id="rec-001",
            client_order_id=fill.client_order_id,
            realized_pnl=0.0,
            fee_paid=fill.fee_paid,
            slippage_cost=0.0,
            reconciled=True,
            reconciled_at_utc=utc_now_z(),
        )
        self.assertTrue(risk.approved and acct.reconciled)


if __name__ == "__main__":
    unittest.main()
