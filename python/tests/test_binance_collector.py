from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_SRC = REPO_ROOT / "python"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from alpha_mining.research.binance_collector import (  # noqa: E402
    DATASET_NAMES,
    DATASET_SCHEMAS,
    Binance1mCollector,
    BinanceHttpClient,
    CollectorConfig,
    DailySpoolWriter,
    FuturesMarketConfig,
    OptionsMarketConfig,
    SpotMarketConfig,
    StorageConfig,
    build_day_manifest,
    compact_day_to_parquet,
    load_collector_config,
    normalize_and_dedupe_records,
    parse_option_symbol_fallback,
    prune_uploaded_local_parquet,
    read_spool_records,
    upload_day_to_drive,
    upload_pending_days,
)

HAS_PYARROW = importlib.util.find_spec("pyarrow") is not None


def _make_config(
    spool_dir: Path,
    output_dir: Path,
    *,
    upload_enabled: bool = True,
    delete_spool_after_compact: bool = True,
    retention_local_days: int = 3,
) -> CollectorConfig:
    return CollectorConfig(
        schema_version="1.0",
        collector_id="test_sg_vps",
        interval_seconds=60,
        tick_offset_seconds=2,
        exchange_info_refresh_seconds=600,
        http_timeout_seconds=5.0,
        http_max_retries=2,
        underlyings=("BTC", "ETH"),
        spot_symbols=("BTCUSDT", "ETHUSDT"),
        options=OptionsMarketConfig(enabled=True, collect_open_interest=True),
        spot=SpotMarketConfig(enabled=True, collect_closed_kline_1m=True),
        futures_usdm=FuturesMarketConfig(
            enabled=True,
            base_url="https://fapi.binance.com",
            contract_types=("CURRENT_QUARTER", "NEXT_QUARTER", "PERPETUAL"),
            collect_open_interest=True,
        ),
        futures_coinm=FuturesMarketConfig(
            enabled=True,
            base_url="https://dapi.binance.com",
            contract_types=("CURRENT_QUARTER", "NEXT_QUARTER", "PERPETUAL"),
            collect_open_interest=True,
        ),
        storage=StorageConfig(
            spool_dir=str(spool_dir),
            output_dir=str(output_dir),
            parquet_compression="zstd",
            parquet_compression_level=6,
            rclone_remote="gdrive:00_Katherine_Workspace/01_Alpha_Mining/datasets/binance_1m",
            upload_enabled=upload_enabled,
            delete_spool_after_compact=delete_spool_after_compact,
            retention_local_days=retention_local_days,
        ),
    )


def _mock_binance_transport(
    *,
    fail_paths: set[str] | None = None,
    retry_once_paths: set[str] | None = None,
) -> tuple[Any, list[str]]:
    """Return deterministic offline Binance REST transport + call log."""
    calls: list[str] = []
    seen_retry: set[str] = set()
    fail_set = fail_paths or set()
    retry_set = retry_once_paths or set()

    # Fixed UTC timestamp reference: 2026-11-22T12:00:02Z = 1795348802000 ms
    # Expiry: 2026-12-25T08:00:00Z = 1798185600000 ms (~32.83 days out)
    expiry_dec_ms = 1_798_185_600_000

    def _json_resp(obj: Any, *, weight: int = 12) -> tuple[int, dict[str, str], bytes]:
        return 200, {"x-mbx-used-weight-1m": str(weight)}, json.dumps(obj).encode("utf-8")

    def transport(url: str, _timeout: float) -> tuple[int, dict[str, str], bytes]:
        calls.append(url)
        parts = urlsplit(url)
        host, path, qs = parts.netloc, parts.path, parse_qs(parts.query)

        if path in fail_set:
            return 500, {}, b'{"code":-1000,"msg":"simulated failure"}'
        if path in retry_set and path not in seen_retry:
            seen_retry.add(path)
            return 429, {"retry-after": "0.1"}, b'{"code":-1003,"msg":"rate limited"}'

        # 1. Binance Options (eapi.binance.com)
        if host == "eapi.binance.com":
            if path == "/eapi/v1/exchangeInfo":
                return _json_resp(
                    {
                        "optionSymbols": [
                            {
                                "symbol": "BTC-261225-100000-C",
                                "underlying": "BTCUSDT",
                                "expiryDate": expiry_dec_ms,
                                "strikePrice": "100000",
                                "side": "CALL",
                                "status": "TRADING",
                            },
                            {
                                "symbol": "ETH-261225-3500-P",
                                "underlying": "ETHUSDT",
                                "expiryDate": expiry_dec_ms,
                                "strikePrice": "3500",
                                "side": "PUT",
                                "status": "TRADING",
                            },
                            {
                                "symbol": "SOL-261225-200-C",
                                "underlying": "SOLUSDT",
                                "expiryDate": expiry_dec_ms,
                                "strikePrice": "200",
                                "side": "CALL",
                                "status": "TRADING",
                            },
                        ]
                    },
                    weight=5,
                )
            if path == "/eapi/v1/mark":
                return _json_resp(
                    [
                        {
                            "symbol": "BTC-261225-100000-C",
                            "markPrice": "4120.5",
                            "bidIV": "0.61",
                            "askIV": "0.64",
                            "markIV": "0.625",
                            "delta": "0.48",
                            "gamma": "0.00002",
                            "vega": "115.2",
                            "theta": "-68.4",
                            "highPriceLimit": "6000.0",
                            "lowPriceLimit": "2000.0",
                        },
                        {
                            "symbol": "ETH-261225-3500-P",
                            "markPrice": "210.25",
                            "bidIV": "0.70",
                            "askIV": "0.74",
                            "markIV": "0.72",
                            "delta": "-0.42",
                            "gamma": "0.0005",
                            "vega": "4.2",
                            "theta": "-3.1",
                            "highPriceLimit": "400.0",
                            "lowPriceLimit": "50.0",
                        },
                        {
                            "symbol": "SOL-261225-200-C",
                            "markPrice": "12.0",
                            "markIV": "0.85",
                        },
                    ],
                    weight=10,
                )
            if path == "/eapi/v1/ticker":
                return _json_resp(
                    [
                        {
                            "symbol": "BTC-261225-100000-C",
                            "bidPrice": "4100.0",
                            "askPrice": "4140.0",
                            "bidQty": "2.5",
                            "askQty": "3.0",
                            "lastPrice": "4125.0",
                            "volume": "142.5",
                            "amount": "587000.0",
                            "strikePrice": "100000",
                        },
                        {
                            "symbol": "ETH-261225-3500-P",
                            "bidPrice": "205.0",
                            "askPrice": "215.0",
                            "bidQty": "10.0",
                            "askQty": "8.0",
                            "lastPrice": "210.0",
                            "volume": "320.0",
                            "amount": "67200.0",
                            "strikePrice": "3500",
                        },
                    ],
                    weight=15,
                )
            if path == "/eapi/v1/index":
                u = qs.get("underlying", [""])[0]
                px = "98500.50" if u == "BTCUSDT" else "3620.10"
                return _json_resp({"time": 1_795_348_802_000, "indexPrice": px}, weight=16)
            if path == "/eapi/v1/openInterest":
                asset = qs.get("underlyingAsset", [""])[0]
                if asset == "BTC":
                    return _json_resp(
                        [{"symbol": "BTC-261225-100000-C", "sumOpenInterest": "55.2", "sumOpenInterestUsd": "5437200.0"}],
                        weight=16,
                    )
                return _json_resp(
                    [{"symbol": "ETH-261225-3500-P", "sumOpenInterest": "120.0", "sumOpenInterestUsd": "434400.0"}],
                    weight=16,
                )

        # 2. Binance Spot (data-api.binance.vision)
        if host == "data-api.binance.vision":
            if path == "/api/v3/ticker/bookTicker":
                return _json_resp(
                    [
                        {"symbol": "BTCUSDT", "bidPrice": "98500.0", "bidQty": "1.2", "askPrice": "98501.0", "askQty": "1.5"},
                        {"symbol": "ETHUSDT", "bidPrice": "3620.0", "bidQty": "12.0", "askPrice": "3620.5", "askQty": "14.0"},
                    ],
                    weight=4,
                )
            if path == "/api/v3/ticker/24hr":
                return _json_resp(
                    [
                        {"symbol": "BTCUSDT", "lastPrice": "98500.5", "volume": "25000.0", "quoteVolume": "2462500000.0"},
                        {"symbol": "ETHUSDT", "lastPrice": "3620.2", "volume": "180000.0", "quoteVolume": "651600000.0"},
                    ],
                    weight=8,
                )
            if path == "/api/v3/klines":
                sym = qs.get("symbol", [""])[0]
                base_px = "98490.0" if sym == "BTCUSDT" else "3618.0"
                close_px = "98500.0" if sym == "BTCUSDT" else "3620.0"
                # Return [closed_bar (11:59-11:59:59.999), open_bar (12:00-12:00:59.999)]
                return _json_resp(
                    [
                        [1_795_348_740_000, base_px, close_px, base_px, close_px, "12.5", 1_795_348_799_999, "1231250.0", 310, "6.0", "591000.0", "0"],
                        [1_795_348_800_000, close_px, close_px, close_px, close_px, "0.4", 1_795_348_859_999, "39400.0", 11, "0.2", "19700.0", "0"],
                    ],
                    weight=10,
                )

        # 3. Binance USD-M Futures (fapi.binance.com)
        if host == "fapi.binance.com":
            if path == "/fapi/v1/exchangeInfo":
                return _json_resp(
                    {
                        "symbols": [
                            {
                                "symbol": "BTCUSDT_261225",
                                "pair": "BTCUSDT",
                                "baseAsset": "BTC",
                                "quoteAsset": "USDT",
                                "contractType": "CURRENT_QUARTER",
                                "deliveryDate": expiry_dec_ms,
                                "status": "TRADING",
                            },
                            {
                                "symbol": "ETHUSDT_261225",
                                "pair": "ETHUSDT",
                                "baseAsset": "ETH",
                                "quoteAsset": "USDT",
                                "contractType": "CURRENT_QUARTER",
                                "deliveryDate": expiry_dec_ms,
                                "status": "TRADING",
                            },
                            {
                                "symbol": "BTCUSDT",
                                "pair": "BTCUSDT",
                                "baseAsset": "BTC",
                                "quoteAsset": "USDT",
                                "contractType": "PERPETUAL",
                                "deliveryDate": 4_133_404_800_000,
                                "status": "TRADING",
                            },
                            {
                                "symbol": "DOGEUSDT",
                                "pair": "DOGEUSDT",
                                "baseAsset": "DOGE",
                                "quoteAsset": "USDT",
                                "contractType": "PERPETUAL",
                                "deliveryDate": 4_133_404_800_000,
                                "status": "TRADING",
                            },
                        ]
                    },
                    weight=1,
                )
            if path == "/fapi/v1/premiumIndex":
                return _json_resp(
                    [
                        {
                            "symbol": "BTCUSDT_261225",
                            "markPrice": "99800.0",
                            "indexPrice": "98500.0",
                            "estimatedSettlePrice": "98495.0",
                            "lastFundingRate": "",
                            "nextFundingTime": 0,
                        },
                        {
                            "symbol": "ETHUSDT_261225",
                            "markPrice": "3680.0",
                            "indexPrice": "3620.0",
                            "estimatedSettlePrice": "3619.0",
                            "lastFundingRate": "",
                            "nextFundingTime": 0,
                        },
                        {
                            "symbol": "BTCUSDT",
                            "markPrice": "98510.0",
                            "indexPrice": "98500.0",
                            "estimatedSettlePrice": "98502.0",
                            "lastFundingRate": "0.00010000",
                            "nextFundingTime": 1_795_363_200_000,
                        },
                    ],
                    weight=11,
                )
            if path == "/fapi/v1/ticker/bookTicker":
                return _json_resp(
                    [
                        {"symbol": "BTCUSDT_261225", "bidPrice": "99795.0", "bidQty": "4.0", "askPrice": "99805.0", "askQty": "3.5"},
                        {"symbol": "ETHUSDT_261225", "bidPrice": "3679.0", "bidQty": "25.0", "askPrice": "3681.0", "askQty": "20.0"},
                        {"symbol": "BTCUSDT", "bidPrice": "98509.0", "bidQty": "15.0", "askPrice": "98510.0", "askQty": "12.0"},
                    ],
                    weight=16,
                )
            if path == "/fapi/v1/ticker/24hr":
                sym = qs.get("symbol", [""])[0]
                return _json_resp({"symbol": sym, "lastPrice": "99800.0", "volume": "1400.0", "quoteVolume": "139720000.0"})
            if path == "/fapi/v1/openInterest":
                sym = qs.get("symbol", [""])[0]
                return _json_resp({"symbol": sym, "openInterest": "850.5"})

        # 4. Binance COIN-M Futures (dapi.binance.com)
        if host == "dapi.binance.com":
            if path == "/dapi/v1/exchangeInfo":
                return _json_resp(
                    {
                        "symbols": [
                            {
                                "symbol": "BTCUSD_261225",
                                "pair": "BTCUSD",
                                "baseAsset": "BTC",
                                "quoteAsset": "USD",
                                "contractType": "CURRENT_QUARTER",
                                "deliveryDate": expiry_dec_ms,
                                "contractStatus": "TRADING",
                                "contractSize": 100,
                            },
                            {
                                "symbol": "ETHUSD_261225",
                                "pair": "ETHUSD",
                                "baseAsset": "ETH",
                                "quoteAsset": "USD",
                                "contractType": "CURRENT_QUARTER",
                                "deliveryDate": expiry_dec_ms,
                                "contractStatus": "TRADING",
                                "contractSize": 10,
                            },
                            {
                                "symbol": "BTCUSD_260925",
                                "pair": "BTCUSD",
                                "baseAsset": "BTC",
                                "quoteAsset": "USD",
                                "contractType": "CURRENT_QUARTER",
                                "deliveryDate": 1_790_323_200_000,
                                "contractStatus": "SETTLING",
                                "contractSize": 100,
                            },
                        ]
                    },
                    weight=1,
                )
            if path == "/dapi/v1/premiumIndex":
                return _json_resp(
                    [
                        {
                            "symbol": "BTCUSD_261225",
                            "pair": "BTCUSD",
                            "markPrice": "99950.0",
                            "indexPrice": "98500.0",
                            "estimatedSettlePrice": "98490.0",
                            "lastFundingRate": "",
                            "nextFundingTime": 0,
                        },
                        {
                            "symbol": "ETHUSD_261225",
                            "pair": "ETHUSD",
                            "markPrice": "3690.0",
                            "indexPrice": "3620.0",
                            "estimatedSettlePrice": "3618.0",
                            "lastFundingRate": "",
                            "nextFundingTime": 0,
                        },
                    ],
                    weight=11,
                )
            if path == "/dapi/v1/ticker/bookTicker":
                return _json_resp(
                    [
                        {"symbol": "BTCUSD_261225", "bidPrice": "99940.0", "bidQty": "250", "askPrice": "99960.0", "askQty": "180"},
                        {"symbol": "ETHUSD_261225", "bidPrice": "3688.0", "bidQty": "400", "askPrice": "3692.0", "askQty": "350"},
                    ],
                    weight=16,
                )
            if path == "/dapi/v1/ticker/24hr":
                sym = qs.get("symbol", [""])[0]
                return _json_resp([{"symbol": sym, "lastPrice": "99950.0", "volume": "95000", "baseVolume": "95.2"}])
            if path == "/dapi/v1/openInterest":
                sym = qs.get("symbol", [""])[0]
                return _json_resp({"symbol": sym, "openInterest": "42000"})

        return 404, {}, f"unmocked url: {url}".encode("utf-8")

    return transport, calls


class TestBinance1mCollector(unittest.TestCase):
    def test_repo_default_config_and_cli_validate(self) -> None:
        cfg_path = REPO_ROOT / "config" / "collector" / "binance_1m_collector.json"
        cfg = load_collector_config(cfg_path)
        self.assertEqual(cfg.interval_seconds, 60)
        self.assertEqual(cfg.underlyings, ("BTC", "ETH"))
        self.assertEqual(cfg.spot_symbols, ("BTCUSDT", "ETHUSDT"))
        self.assertEqual(cfg.storage.parquet_compression, "zstd")
        self.assertTrue(cfg.options.enabled)
        self.assertTrue(cfg.spot.enabled)
        self.assertTrue(cfg.futures_usdm.enabled)
        self.assertTrue(cfg.futures_coinm.enabled)
        self.assertIn("CURRENT_QUARTER", cfg.futures_usdm.contract_types)
        self.assertIn("CURRENT_QUARTER", cfg.futures_coinm.contract_types)

        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "collect_binance_1m.py"), "validate-config"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["parquet_compression"], "zstd")

    def test_config_rejects_unsafe_paths_and_bad_settings(self) -> None:
        with self.assertRaises(ValueError):
            StorageConfig(spool_dir="../escape")
        with self.assertRaises(ValueError):
            StorageConfig(parquet_compression="lzma")
        with self.assertRaises(ValueError):
            StorageConfig(rclone_remote="gdrive:bad;rm -rf /")
        with self.assertRaises(ValueError):
            FuturesMarketConfig(contract_types=("INVALID_TYPE",))
        with self.assertRaises(ValueError):
            SpotMarketConfig(base_url="http://insecure.example.com")

    def test_parse_option_symbol_fallback(self) -> None:
        self.assertEqual(
            parse_option_symbol_fallback("BTC-261225-100000-C"),
            ("BTC", "261225", 100000.0, "C"),
        )
        self.assertEqual(parse_option_symbol_fallback("BAD"), (None, None, None, None))

    def test_collect_once_captures_all_four_markets_and_derived_metrics(self) -> None:
        ts_ms = 1_795_348_802_000  # 2026-11-22T12:00:02Z
        transport, _ = _mock_binance_transport(retry_once_paths={"/eapi/v1/mark"})
        sleeps: list[float] = []

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = _make_config(base / "spool", base / "parquet")
            http = BinanceHttpClient(timeout=5.0, max_retries=2, transport=transport, sleep_fn=sleeps.append)
            collector = Binance1mCollector(cfg, base_dir=base, http_client=http, clock_ms_fn=lambda: ts_ms, sleep_fn=sleeps.append)

            summary = collector.collect_once(ts_utc_ms=ts_ms)
            self.assertEqual(summary["error_count"], 0, summary["errors"])
            self.assertEqual(summary["rows_written"]["options_chain"], 2)  # BTC + ETH only; SOL filtered out
            self.assertEqual(summary["rows_written"]["spot_1m"], 2)  # BTCUSDT + ETHUSDT
            self.assertEqual(summary["rows_written"]["futures_delivery_usdm"], 3)  # BTCUSDT_261225 + ETHUSDT_261225 + BTCUSDT
            self.assertEqual(summary["rows_written"]["futures_delivery_coinm"], 2)  # BTCUSD_261225 + ETHUSD_261225 (SETTLING excluded)
            self.assertEqual(sleeps, [0.1])  # Honored Retry-After on HTTP 429

            # Verify Options joined fields
            opt_rows, corrupt = read_spool_records(base / "spool" / "2026-11-22" / "options_chain.jsonl")
            self.assertEqual(corrupt, 0)
            self.assertEqual({r["underlying"] for r in opt_rows}, {"BTC", "ETH"})
            btc_opt = next(r for r in opt_rows if r["symbol"] == "BTC-261225-100000-C")
            self.assertAlmostEqual(btc_opt["mid_price"], 4120.0)
            self.assertAlmostEqual(btc_opt["mark_iv"], 0.625)
            self.assertAlmostEqual(btc_opt["delta"], 0.48)
            self.assertAlmostEqual(btc_opt["open_interest"], 55.2)
            self.assertAlmostEqual(btc_opt["index_price"], 98500.5)
            self.assertGreater(btc_opt["dte_days"], 32.0)

            # Verify Spot captured CLOSED 1m bar (close_time 11:59:59.999 < 12:00:02)
            spot_rows, _ = read_spool_records(base / "spool" / "2026-11-22" / "spot_1m.jsonl")
            self.assertEqual({r["symbol"] for r in spot_rows}, {"BTCUSDT", "ETHUSDT"})
            btc_spot = next(r for r in spot_rows if r["symbol"] == "BTCUSDT")
            self.assertEqual(btc_spot["kline_close_time_ms"], 1_795_348_799_999)
            self.assertAlmostEqual(btc_spot["kline_close"], 98500.0)
            self.assertAlmostEqual(btc_spot["mid_price"], 98500.5)

            # Verify Futures Delivery USD-M basis & annualized carry vs Perpetual (BTC + ETH)
            usdm_rows, _ = read_spool_records(base / "spool" / "2026-11-22" / "futures_delivery_usdm.jsonl")
            self.assertEqual({r["base_asset"] for r in usdm_rows}, {"BTC", "ETH"})
            qtr = next(r for r in usdm_rows if r["symbol"] == "BTCUSDT_261225")
            eth_qtr = next(r for r in usdm_rows if r["symbol"] == "ETHUSDT_261225")
            perp = next(r for r in usdm_rows if r["symbol"] == "BTCUSDT")
            self.assertAlmostEqual(qtr["basis"], 1300.0)
            self.assertAlmostEqual(eth_qtr["basis"], 60.0)
            self.assertGreater(qtr["annualized_basis"], 0.10)
            self.assertIsNotNone(qtr["delivery_utc_ms"])
            self.assertIsNone(perp["delivery_utc_ms"])
            self.assertIsNone(perp["dte_days"])
            self.assertIsNone(perp["annualized_basis"])
            self.assertAlmostEqual(perp["last_funding_rate"], 0.0001)

            # Verify Futures Delivery COIN-M contract_size & annualized basis (BTC + ETH)
            coinm_rows, _ = read_spool_records(base / "spool" / "2026-11-22" / "futures_delivery_coinm.jsonl")
            self.assertEqual(len(coinm_rows), 2)
            self.assertEqual({r["base_asset"] for r in coinm_rows}, {"BTC", "ETH"})
            btc_coinm = next(r for r in coinm_rows if r["symbol"] == "BTCUSD_261225")
            eth_coinm = next(r for r in coinm_rows if r["symbol"] == "ETHUSD_261225")
            self.assertEqual(btc_coinm["venue"], "coinm")
            self.assertAlmostEqual(btc_coinm["contract_size"], 100.0)
            self.assertAlmostEqual(btc_coinm["basis"], 1450.0)
            self.assertAlmostEqual(eth_coinm["contract_size"], 10.0)
            self.assertAlmostEqual(eth_coinm["basis"], 70.0)

            # Verify health.json written
            health = json.loads((base / "spool" / "health.json").read_text(encoding="utf-8"))
            self.assertEqual(health["collector_id"], "test_sg_vps")
            self.assertEqual(health["used_weight_1m"]["eapi.binance.com"], 16)

    def test_partial_failure_isolation_preserves_other_markets(self) -> None:
        ts_ms = 1_795_348_802_000
        transport, _ = _mock_binance_transport(fail_paths={"/eapi/v1/mark"})

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = _make_config(base / "spool", base / "parquet")
            http = BinanceHttpClient(timeout=5.0, max_retries=0, transport=transport, sleep_fn=lambda _: None)
            collector = Binance1mCollector(cfg, base_dir=base, http_client=http, clock_ms_fn=lambda: ts_ms)

            summary = collector.collect_once(ts_utc_ms=ts_ms)
            self.assertEqual(summary["rows_written"]["options_chain"], 0)
            self.assertEqual(summary["rows_written"]["spot_1m"], 2)
            self.assertEqual(summary["rows_written"]["futures_delivery_usdm"], 3)
            self.assertEqual(summary["rows_written"]["futures_delivery_coinm"], 2)
            self.assertGreaterEqual(summary["error_count"], 1)

    def test_crash_recovery_corrupt_spool_line_and_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spool = DailySpoolWriter(Path(tmp) / "spool")
            spool.append_records(
                "2026-11-22",
                "spot_1m",
                [
                    {"ts_utc_ms": 1_795_348_862_000, "symbol": "BTCUSDT", "mid_price": 98510.0},
                    {"ts_utc_ms": 1_795_348_802_000, "symbol": "BTCUSDT", "mid_price": 98500.0},
                    {"ts_utc_ms": 1_795_348_802_000, "symbol": "BTCUSDT", "mid_price": 98501.0},  # duplicate ts -> latest wins
                ],
            )
            # Append simulated truncated crash line
            with spool.spool_file("2026-11-22", "spot_1m").open("a", encoding="utf-8") as fh:
                fh.write('{"ts_utc_ms": 1795348922000, "symbol": "BTCUS')

            raw, corrupt = read_spool_records(spool.spool_file("2026-11-22", "spot_1m"))
            self.assertEqual(corrupt, 1)
            clean = normalize_and_dedupe_records("spot_1m", raw)
            self.assertEqual(len(clean), 2)
            # Deterministically sorted ascending by ts_utc_ms
            self.assertEqual(clean[0]["ts_utc_ms"], 1_795_348_802_000)
            self.assertAlmostEqual(clean[0]["mid_price"], 98501.0)
            self.assertEqual(clean[1]["ts_utc_ms"], 1_795_348_862_000)

    def test_upload_pending_retry_and_safe_retention_pruning_stdlib(self) -> None:
        """Exercises rclone upload, pending retry after transient error, and SHA-256-verified retention pruning without requiring pyarrow."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = _make_config(base / "spool", base / "parquet", retention_local_days=3)
            old_day = "2026-11-15"
            out_dir = base / "parquet" / "spot_1m" / "2026-11"
            out_dir.mkdir(parents=True, exist_ok=True)
            pq_file = out_dir / f"spot_1m_{old_day}.parquet"
            pq_file.write_bytes(b"SYNTHETIC-PARQUET-BYTES")
            manifest = build_day_manifest(
                dataset="spot_1m",
                date_utc=old_day,
                parquet_path=pq_file,
                records=[{"ts_utc_ms": 1_794_700_800_000, "symbol": "BTCUSDT"}],
                corrupt_lines_skipped=0,
                compression="zstd",
                compression_level=6,
                interval_seconds=60,
            )
            (out_dir / f"spot_1m_{old_day}.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            # Before upload: prune MUST refuse to delete un-uploaded local parquet
            pruned_before = prune_uploaded_local_parquet(cfg, base_dir=base, today_utc=date(2026, 11, 22))
            self.assertEqual(pruned_before, [])
            self.assertTrue(pq_file.is_file())

            # Simulate failed rclone upload first -> no receipt created
            def fail_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(list(cmd), 1, "", "transient network error")

            with self.assertRaises(RuntimeError):
                upload_day_to_drive(cfg, base_dir=base, date_utc=old_day, datasets=["spot_1m"], runner=fail_runner)
            self.assertFalse((out_dir / f"spot_1m_{old_day}.uploaded.json").exists())

            # Pending upload sweep succeeds on retry and invokes `rclone copy` (non-destructive)
            recorded_cmds: list[list[str]] = []

            def ok_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
                recorded_cmds.append(list(cmd))
                return subprocess.CompletedProcess(list(cmd), 0, "ok", "")

            retried = upload_pending_days(cfg, base_dir=base, before_date_utc="2026-11-22", runner=ok_runner)
            self.assertIn(old_day, retried)
            self.assertEqual(len(recorded_cmds), 2)  # .parquet + .manifest.json
            self.assertEqual(recorded_cmds[0][:2], ["rclone", "copy"])
            self.assertTrue(recorded_cmds[0][3].endswith("/spot_1m/2026-11"))

            # Now prune deletes old uploaded file cleanly
            pruned_after = prune_uploaded_local_parquet(cfg, base_dir=base, today_utc=date(2026, 11, 22))
            self.assertEqual(pruned_after, [str(pq_file)])
            self.assertFalse(pq_file.exists())

    @unittest.skipUnless(HAS_PYARROW, "pyarrow not installed in current stdlib environment")
    def test_real_parquet_zstd_compaction_rollover_and_schema_roundtrip(self) -> None:
        import pyarrow.parquet as pq  # type: ignore[import-not-found]

        day1_ms = 1_795_348_802_000  # 2026-11-22T12:00:02Z
        day2_ms = 1_795_392_002_000  # 2026-11-23T00:00:02Z (UTC rollover)
        transport, _ = _mock_binance_transport()
        rclone_cmds: list[list[str]] = []

        def ok_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            rclone_cmds.append(list(cmd))
            return subprocess.CompletedProcess(list(cmd), 0, "", "")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg = _make_config(base / "spool", base / "parquet", delete_spool_after_compact=True)
            http = BinanceHttpClient(timeout=5.0, max_retries=1, transport=transport, sleep_fn=lambda _: None)

            times = iter([day1_ms, day1_ms + 1000, day2_ms, day2_ms + 1000])
            collector = Binance1mCollector(
                cfg,
                base_dir=base,
                http_client=http,
                subprocess_runner=ok_runner,
                clock_ms_fn=lambda: next(times),
                sleep_fn=lambda _: None,
            )

            # Tick 1 on 2026-11-22 -> spooled; Tick 2 on 2026-11-23 -> triggers midnight compaction & upload of 2026-11-22
            history = collector.run_forever(max_ticks=2)
            self.assertEqual(len(history), 2)
            self.assertFalse((base / "spool" / "2026-11-22").exists())  # cleaned after compaction
            self.assertTrue((base / "spool" / "2026-11-23").is_dir())

            # Verify all 4 datasets compacted to real ZSTD Parquet with exact schemas + receipts
            for ds in DATASET_NAMES:
                pq_path = base / "parquet" / ds / "2026-11" / f"{ds}_2026-11-22.parquet"
                manifest_path = pq_path.with_suffix(".manifest.json")
                receipt_path = pq_path.with_suffix(".uploaded.json")
                self.assertTrue(pq_path.is_file(), f"missing {pq_path}")
                self.assertTrue(manifest_path.is_file())
                self.assertTrue(receipt_path.is_file())

                pf = pq.ParquetFile(pq_path)
                self.assertEqual(pf.metadata.row_group(0).column(0).compression, "ZSTD")
                table = pf.read()
                expected_cols = [col for col, _ in DATASET_SCHEMAS[ds]]
                self.assertEqual(table.column_names, expected_cols)
                self.assertGreater(table.num_rows, 0)

                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["row_count"], table.num_rows)
                self.assertEqual(manifest["compression"], "zstd")
                self.assertEqual(manifest["unique_minutes"], 1)

            # 4 datasets * 2 files (.parquet + .manifest.json) = 8 rclone copy calls
            self.assertEqual(len(rclone_cmds), 8)


if __name__ == "__main__":
    unittest.main()
