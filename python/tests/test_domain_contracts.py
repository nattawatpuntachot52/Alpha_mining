"""Boundary and determinism tests across NL->JSON translator, Meta-Labeling, Risk, Execution, and Accounting."""

from __future__ import annotations

import math
import sys
import unittest
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))

from alpha_mining.accounting import (
    AccountedOutcome,
    ReconciliationEntry,
    account_for_reconciliation,
)
from alpha_mining.execution import ExecutionOrderRequest, build_order_from_risk_decision
from alpha_mining.research import ExperimentRecord, RuleCondition, validate_translator_payload
from alpha_mining.risk import MarketRiskSnapshot, RiskDecision, RiskLimits, evaluate_pre_trade_risk
from alpha_mining.strategy import (
    MetaLabelScore,
    SignalIntent,
    StrategyDecision,
    evaluate_meta_label_gate,
)


class TestDomainContracts(unittest.TestCase):
    def test_translator_rejects_execution_keys_nan_and_invalid_roles(self) -> None:
        valid_payload = {
            "spec_id": "rule-owner-001",
            "natural_language_rule": "Only consider entry when volatility regime ratio > 1.2",
            "translator_role": "nl_to_json_only",
            "conditions": [{"feature": "atr_ratio", "op": ">", "value": 1.2}],
            "horizon_bars": 6,
            "direction_bias": "long",
            "human_confirmed": True,
            "created_at_utc": "2026-11-18T05:00:00Z",
            "notes": None,
        }
        spec = validate_translator_payload(valid_payload)
        self.assertEqual(spec.spec_id, "rule-owner-001")
        self.assertEqual(spec.notes, "")
        self.assertEqual(len(spec.conditions), 1)

        with self.assertRaises(ValueError):
            validate_translator_payload({**valid_payload, "notes": 123})

        with self.assertRaises(ValueError):
            validate_translator_payload({**valid_payload, "translator_role": "decision_maker"})

        with self.assertRaises(ValueError):
            validate_translator_payload({**valid_payload, "submit_order": True})

        with self.assertRaises(ValueError):
            validate_translator_payload(
                {**valid_payload, "conditions": [{"feature": "x", "op": "exec", "value": 1}]}
            )

        with self.assertRaises(ValueError):
            validate_translator_payload(
                {**valid_payload, "conditions": [{"feature": "x", "op": "=="}]}
            )

        with self.assertRaises(ValueError):
            validate_translator_payload(
                {**valid_payload, "conditions": [{"feature": "x", "op": "in", "value": [1.0, float("nan")]}]}
            )

        with self.assertRaises(ValueError):
            validate_translator_payload(
                {**valid_payload, "conditions": [{"feature": "x", "op": "in", "value": ["ok", "override_risk"]}]}
            )

        with self.assertRaises(ValueError):
            RuleCondition(feature="x", op=">", value=True)

        with self.assertRaises(ValueError):
            RuleCondition(feature="x", op="==", value=float("inf"))

    def test_deterministic_pipeline_and_rejection_gates(self) -> None:
        exp = ExperimentRecord(
            experiment_id="exp-struct-001",
            hypothesis_ref="brief-brain-memory-001",
            trials_tested=1,
            evidence_status="proposed",
            oos_split_description="chronological purged walk-forward",
            cost_model_summary="spread + commission + slippage",
            negative_result=False,
            reproduction_command="python3 -m unittest discover -s python/tests",
        )
        intent = SignalIntent(
            intent_id="int-001",
            strategy_id="owner-rule-v1",
            instrument="SYNTH_ASSET",
            target_exposure=1.5,
            generated_at_utc="2026-11-18T05:00:00Z",
            research_evidence_ref=exp.experiment_id,
        )

        # Uncalibrated Meta-Label model must be rejected deterministically
        uncal = MetaLabelScore(
            intent_id="int-001",
            model_id="ml-0",
            prob_net_positive=0.90,
            suggested_size_multiplier=1.0,
            out_of_sample_calibrated=False,
            evaluated_at_utc="2026-11-18T05:00:01Z",
        )
        uncal_dec = evaluate_meta_label_gate(intent, uncal)
        self.assertFalse(uncal_dec.execute)
        self.assertEqual(uncal_dec.reason, "uncalibrated_meta_label_model")

        # Below probability threshold must be rejected
        low_prob = MetaLabelScore(
            intent_id="int-001",
            model_id="ml-1",
            prob_net_positive=0.45,
            suggested_size_multiplier=0.8,
            out_of_sample_calibrated=True,
            evaluated_at_utc="2026-11-18T05:00:01Z",
        )
        low_dec = evaluate_meta_label_gate(intent, low_prob, min_prob_net_positive=0.55)
        self.assertFalse(low_dec.execute)

        # Calibrated above-threshold approval scales size deterministically
        good_score = MetaLabelScore(
            intent_id="int-001",
            model_id="ml-1",
            prob_net_positive=0.72,
            suggested_size_multiplier=0.8,
            out_of_sample_calibrated=True,
            evaluated_at_utc="2026-11-18T05:00:01Z",
        )
        strat_dec1 = evaluate_meta_label_gate(intent, good_score)
        strat_dec2 = evaluate_meta_label_gate(intent, good_score)
        self.assertEqual(strat_dec1, strat_dec2)
        self.assertTrue(strat_dec1.execute)
        self.assertAlmostEqual(strat_dec1.target_exposure, 1.2)

        limits = RiskLimits(
            max_abs_exposure=1.0,
            max_daily_loss_r=3.0,
            max_spread_bps=25.0,
            max_data_age_sec=10.0,
        )

        # Spread limit exceeded -> Risk rejects and Execution refuses order build
        high_spread = MarketRiskSnapshot(
            observed_at_utc="2026-11-18T05:00:00Z",
            evaluated_at_utc="2026-11-18T05:00:02Z",
            current_daily_loss_r=0.5,
            spread_bps=35.0,
        )
        rejected_risk = evaluate_pre_trade_risk(strat_dec1, limits, high_spread)
        self.assertFalse(rejected_risk.approved)
        self.assertEqual(rejected_risk.rejection_reason, "spread_limit_exceeded")
        with self.assertRaises(ValueError):
            build_order_from_risk_decision("ord-blocked", rejected_risk, intent.instrument)

        # Raw SignalIntent passed directly into Execution must fail TypeError
        with self.assertRaises(TypeError):
            build_order_from_risk_decision("ord-bypass", intent, intent.instrument)  # type: ignore[arg-type]

        # Healthy risk snapshot clips exposure 1.2 -> 1.0 and builds order cleanly
        clean_snap = MarketRiskSnapshot(
            observed_at_utc="2026-11-18T05:00:00Z",
            evaluated_at_utc="2026-11-18T05:00:02Z",
            current_daily_loss_r=0.5,
            spread_bps=10.0,
        )
        approved_risk: RiskDecision = evaluate_pre_trade_risk(strat_dec1, limits, clean_snap)
        self.assertTrue(approved_risk.approved)
        self.assertAlmostEqual(approved_risk.approved_exposure, 1.0)

        order = build_order_from_risk_decision("ord-001", approved_risk, intent.instrument)
        self.assertEqual(order.side, "buy")
        self.assertAlmostEqual(order.abs_exposure, 1.0)

        # Reconcile execution and compute cost-adjusted net R
        recon = ReconciliationEntry(
            entry_id="rec-001",
            client_order_id=order.client_order_id,
            realized_pnl=160.0,
            fee_paid=10.0,
            slippage_cost=5.0,
            reconciled=True,
            reconciled_at_utc="2026-11-18T05:45:00Z",
        )
        accounted = account_for_reconciliation(recon, risk_unit_value=100.0, spread_cost_r=0.05)
        self.assertAlmostEqual(accounted.gross_r, 1.6)
        self.assertAlmostEqual(accounted.total_cost_r, 0.2)
        self.assertAlmostEqual(accounted.net_r, 1.4)

    def test_high1_execution_capability_seal_blocks_forged_risk_and_direct_orders(self) -> None:
        limits = RiskLimits(
            max_abs_exposure=1.0,
            max_daily_loss_r=3.0,
            max_spread_bps=25.0,
            max_data_age_sec=10.0,
        )
        snap = MarketRiskSnapshot(
            observed_at_utc="2026-11-18T05:00:00Z",
            evaluated_at_utc="2026-11-18T05:00:02Z",
            current_daily_loss_r=0.0,
            spread_bps=5.0,
        )
        dec = StrategyDecision(
            intent_id="int-seal",
            execute=True,
            target_exposure=0.5,
            decision_mode="primary_rule_only",
            reason="approved",
        )
        sealed_risk = evaluate_pre_trade_risk(dec, limits, snap)
        valid_order = build_order_from_risk_decision("ord-sealed", sealed_risk, "SYNTH_ASSET")

        # Direct ExecutionOrderRequest construction without Risk seal must raise PermissionError
        with self.assertRaises(PermissionError):
            ExecutionOrderRequest(
                client_order_id="ord-direct",
                intent_id="int-seal",
                instrument="SYNTH_ASSET",
                side="buy",
                abs_exposure=1.0,
                risk_evaluated_at_utc="2026-11-18T05:00:02Z",
            )

        with self.assertRaises(PermissionError):
            ExecutionOrderRequest(
                client_order_id="ord-forged",
                intent_id="int-seal",
                instrument="SYNTH_ASSET",
                side="buy",
                abs_exposure=1.0,
                risk_evaluated_at_utc="2026-11-18T05:00:02Z",
                _seal="deadbeef" * 8,
            )

        # dataclasses.replace mutation on ExecutionOrderRequest must fail HMAC seal check
        with self.assertRaises(PermissionError):
            replace(valid_order, abs_exposure=999.0)

        # Unsealed direct RiskDecision (even with valid fields for backward compatibility) cannot authorize order
        unsealed_risk = RiskDecision(
            intent_id="int-forged",
            approved=True,
            approved_exposure=1.0,
            rejection_reason=None,
            evaluated_at_utc="2026-11-18T05:00:02Z",
        )
        with self.assertRaises(PermissionError):
            build_order_from_risk_decision("ord-unsealed", unsealed_risk, "SYNTH_ASSET")

        forged_risk = RiskDecision(
            intent_id="int-forged",
            approved=True,
            approved_exposure=1.0,
            rejection_reason=None,
            evaluated_at_utc="2026-11-18T05:00:02Z",
            _seal="deadbeef" * 8,
        )
        with self.assertRaises(PermissionError):
            build_order_from_risk_decision("ord-forged-seal", forged_risk, "SYNTH_ASSET")

        # dataclasses.replace mutation on sealed RiskDecision must fail seal verification
        tampered_risk = replace(sealed_risk, approved_exposure=50.0)
        with self.assertRaises(PermissionError):
            build_order_from_risk_decision("ord-tampered", tampered_risk, "SYNTH_ASSET")

    def test_high2_strategy_decision_and_risk_reject_nan_inf_bool(self) -> None:
        limits = RiskLimits(
            max_abs_exposure=1.0,
            max_daily_loss_r=3.0,
            max_spread_bps=25.0,
            max_data_age_sec=10.0,
        )
        snap = MarketRiskSnapshot(
            observed_at_utc="2026-11-18T05:00:00Z",
            evaluated_at_utc="2026-11-18T05:00:02Z",
            current_daily_loss_r=0.0,
            spread_bps=5.0,
        )

        for bad_exp in (float("nan"), float("inf"), float("-inf"), True, "1.0", 0.0):
            with self.assertRaises(ValueError):
                StrategyDecision(
                    intent_id="int-bad",
                    execute=True,
                    target_exposure=bad_exp,  # type: ignore[arg-type]
                    decision_mode="primary_rule_only",
                    reason="test",
                )

        # Even if __post_init__ were bypassed via object.__new__, Risk must reject NaN/bool instead of clamping to 1.0
        for bad_exp in (float("nan"), float("inf"), True, "1.0"):
            bypassed = object.__new__(StrategyDecision)
            object.__setattr__(bypassed, "intent_id", "int-bypass")
            object.__setattr__(bypassed, "execute", True)
            object.__setattr__(bypassed, "target_exposure", bad_exp)
            object.__setattr__(bypassed, "decision_mode", "primary_rule_only")
            object.__setattr__(bypassed, "reason", "bypass")
            with self.assertRaises(ValueError):
                evaluate_pre_trade_risk(bypassed, limits, snap)

    def test_nanosecond_temporal_guards_and_accounting_invariants(self) -> None:
        with self.assertRaises(ValueError):
            SignalIntent(
                intent_id="int-unicode-ts",
                strategy_id="strat",
                instrument="SYNTH",
                target_exposure=0.5,
                generated_at_utc="2026-11-18T05:00:00.\u0661Z",
                research_evidence_ref="exp-1",
            )

        with self.assertRaises(ValueError):
            SignalIntent(
                intent_id="int-bad-ts",
                strategy_id="strat",
                instrument="SYNTH",
                target_exposure=0.5,
                generated_at_utc="not-a-timestamp",
                research_evidence_ref="exp-1",
            )

        with self.assertRaises(ValueError):
            SignalIntent(
                intent_id="int-nan",
                strategy_id="strat",
                instrument="SYNTH",
                target_exposure=float("nan"),
                generated_at_utc="2026-11-18T05:00:00Z",
                research_evidence_ref="exp-1",
            )

        # Nanosecond lookahead (difference in 9th fractional digit) must fail meta-label gate
        intent_ns = SignalIntent(
            intent_id="int-ns",
            strategy_id="strat",
            instrument="SYNTH",
            target_exposure=0.5,
            generated_at_utc="2026-11-18T05:00:00.000000002Z",
            research_evidence_ref="exp-1",
        )
        early_meta = MetaLabelScore(
            intent_id="int-ns",
            model_id="ml-1",
            prob_net_positive=0.9,
            suggested_size_multiplier=1.0,
            out_of_sample_calibrated=True,
            evaluated_at_utc="2026-11-18T05:00:00.000000001Z",
        )
        with self.assertRaises(ValueError):
            evaluate_meta_label_gate(intent_ns, early_meta)

        # Nanosecond clock inversion and staleness in Risk
        with self.assertRaises(ValueError):
            MarketRiskSnapshot(
                observed_at_utc="2026-11-18T05:00:00.000000002Z",
                evaluated_at_utc="2026-11-18T05:00:00.000000001Z",
                current_daily_loss_r=0.0,
                spread_bps=5.0,
            )

        stale_ns_snap = MarketRiskSnapshot(
            observed_at_utc="2026-11-18T05:00:00.000000000Z",
            evaluated_at_utc="2026-11-18T05:00:10.000000001Z",
            current_daily_loss_r=0.0,
            spread_bps=5.0,
        )
        limits = RiskLimits(
            max_abs_exposure=1.0,
            max_daily_loss_r=3.0,
            max_spread_bps=25.0,
            max_data_age_sec=10.0,
        )
        dec = StrategyDecision(
            intent_id="int-ns",
            execute=True,
            target_exposure=0.5,
            decision_mode="primary_rule_only",
            reason="ok",
        )
        stale_res = evaluate_pre_trade_risk(dec, limits, stale_ns_snap)
        self.assertFalse(stale_res.approved)
        self.assertEqual(stale_res.rejection_reason, "stale_observation")

        # Accounting field & division overflow checks
        with self.assertRaises(ValueError):
            AccountedOutcome(
                entry_id="",
                gross_r=1.0,
                total_cost_r=0.1,
                net_r=0.9,
                realized_at_utc="2026-11-18T05:00:00Z",
            )
        with self.assertRaises(ValueError):
            AccountedOutcome(
                entry_id="rec-1",
                gross_r=1.0,
                total_cost_r=0.1,
                net_r=math.nan,
                realized_at_utc="2026-11-18T05:00:00Z",
            )
        overflow_recon = ReconciliationEntry(
            entry_id="rec-ovf",
            client_order_id="ord-1",
            realized_pnl=1e308,
            fee_paid=0.0,
            slippage_cost=0.0,
            reconciled=True,
            reconciled_at_utc="2026-11-18T05:00:00Z",
        )
        with self.assertRaises(ValueError):
            account_for_reconciliation(overflow_recon, risk_unit_value=1e-10)

        empty_id_recon = ReconciliationEntry(
            entry_id="  ",
            client_order_id="ord-1",
            realized_pnl=10.0,
            fee_paid=0.0,
            slippage_cost=0.0,
            reconciled=True,
            reconciled_at_utc="2026-11-18T05:00:00Z",
        )
        with self.assertRaises(ValueError):
            account_for_reconciliation(empty_id_recon, risk_unit_value=10.0)


if __name__ == "__main__":
    unittest.main()
