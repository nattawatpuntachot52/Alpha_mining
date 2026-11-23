"""Lightweight 1-minute Binance multi-market collector (Options, Spot, Delivery Futures).

Designed for low-memory 24/7 execution on a Singapore VPS:
- Captures synchronized 1-minute UTC snapshots across:
  1. Binance Options Chain (`eapi.binance.com`: mark, IV, Greeks, bid/ask, OI, index)
  2. Binance Spot (`data-api.binance.vision`: live bookTicker + 24h stats + closed 1m kline)
  3. Binance USD-M Futures Delivery + optional Perpetual (`fapi.binance.com`)
  4. Binance COIN-M Futures Delivery + optional Perpetual (`dapi.binance.com`)
- Crash-safe append-only daily JSONL spool (never holds a full day in RAM).
- Deterministic UTC-midnight compaction into Parquet (Zstd) + SHA-256 quality manifests.
- Verified non-destructive upload to Google Drive via `rclone copy`.

Core module stays importable on Python stdlib alone (`pyarrow` is imported lazily
when compacting/reading Parquet files) so repository CI runs cleanly without extra deps.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

SCHEMA_VERSION = "1.0"
VALID_CONTRACT_TYPES = frozenset({"CURRENT_QUARTER", "NEXT_QUARTER", "PERPETUAL"})
VALID_COMPRESSIONS = frozenset({"zstd", "snappy", "gzip", "none"})
PERPETUAL_DELIVERY_SENTINEL_MS = 4_000_000_000_000  # ~year 2096+ sentinel used by Binance

DATASET_NAMES = (
    "options_chain",
    "spot_1m",
    "futures_delivery_usdm",
    "futures_delivery_coinm",
)

# Explicit ordered typed schemas for Parquet compaction: (column_name, type_tag)
# type_tag in {"int64", "float64", "string"}
DATASET_SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "options_chain": (
        ("ts_utc_ms", "int64"),
        ("snapshot_utc", "string"),
        ("underlying", "string"),
        ("symbol", "string"),
        ("expiry_utc_ms", "int64"),
        ("expiry_code", "string"),
        ("dte_days", "float64"),
        ("strike", "float64"),
        ("right", "string"),
        ("index_price", "float64"),
        ("bid_price", "float64"),
        ("ask_price", "float64"),
        ("bid_qty", "float64"),
        ("ask_qty", "float64"),
        ("mid_price", "float64"),
        ("spread_pct", "float64"),
        ("last_price", "float64"),
        ("mark_price", "float64"),
        ("bid_iv", "float64"),
        ("ask_iv", "float64"),
        ("mark_iv", "float64"),
        ("delta", "float64"),
        ("gamma", "float64"),
        ("vega", "float64"),
        ("theta", "float64"),
        ("open_interest", "float64"),
        ("open_interest_usd", "float64"),
        ("volume_24h", "float64"),
        ("amount_24h", "float64"),
        ("high_price_limit", "float64"),
        ("low_price_limit", "float64"),
    ),
    "spot_1m": (
        ("ts_utc_ms", "int64"),
        ("snapshot_utc", "string"),
        ("symbol", "string"),
        ("bid_price", "float64"),
        ("bid_qty", "float64"),
        ("ask_price", "float64"),
        ("ask_qty", "float64"),
        ("mid_price", "float64"),
        ("spread_bps", "float64"),
        ("last_price", "float64"),
        ("volume_24h", "float64"),
        ("quote_volume_24h", "float64"),
        ("kline_open_time_ms", "int64"),
        ("kline_close_time_ms", "int64"),
        ("kline_open", "float64"),
        ("kline_high", "float64"),
        ("kline_low", "float64"),
        ("kline_close", "float64"),
        ("kline_volume", "float64"),
        ("kline_quote_volume", "float64"),
        ("kline_trades", "int64"),
    ),
    "futures_delivery_usdm": (
        ("ts_utc_ms", "int64"),
        ("snapshot_utc", "string"),
        ("venue", "string"),
        ("symbol", "string"),
        ("pair", "string"),
        ("base_asset", "string"),
        ("quote_asset", "string"),
        ("contract_type", "string"),
        ("delivery_utc_ms", "int64"),
        ("dte_days", "float64"),
        ("contract_size", "float64"),
        ("bid_price", "float64"),
        ("bid_qty", "float64"),
        ("ask_price", "float64"),
        ("ask_qty", "float64"),
        ("mid_price", "float64"),
        ("last_price", "float64"),
        ("mark_price", "float64"),
        ("index_price", "float64"),
        ("estimated_settle_price", "float64"),
        ("basis", "float64"),
        ("basis_bps", "float64"),
        ("annualized_basis", "float64"),
        ("last_funding_rate", "float64"),
        ("next_funding_utc_ms", "int64"),
        ("open_interest", "float64"),
        ("volume_24h", "float64"),
        ("quote_volume_24h", "float64"),
    ),
    "futures_delivery_coinm": (
        ("ts_utc_ms", "int64"),
        ("snapshot_utc", "string"),
        ("venue", "string"),
        ("symbol", "string"),
        ("pair", "string"),
        ("base_asset", "string"),
        ("quote_asset", "string"),
        ("contract_type", "string"),
        ("delivery_utc_ms", "int64"),
        ("dte_days", "float64"),
        ("contract_size", "float64"),
        ("bid_price", "float64"),
        ("bid_qty", "float64"),
        ("ask_price", "float64"),
        ("ask_qty", "float64"),
        ("mid_price", "float64"),
        ("last_price", "float64"),
        ("mark_price", "float64"),
        ("index_price", "float64"),
        ("estimated_settle_price", "float64"),
        ("basis", "float64"),
        ("basis_bps", "float64"),
        ("annualized_basis", "float64"),
        ("last_funding_rate", "float64"),
        ("next_funding_utc_ms", "int64"),
        ("open_interest", "float64"),
        ("volume_24h", "float64"),
        ("quote_volume_24h", "float64"),
    ),
}

HttpTransport = Callable[[str, float], tuple[int, dict[str, str], bytes]]
SubprocessRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _to_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _to_int(val: Any) -> int | None:
    if val is None or val == "" or isinstance(val, bool):
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        try:
            f = float(val)
            return int(f) if math.isfinite(f) else None
        except (TypeError, ValueError):
            return None


def _utc_iso_from_ms(ts_ms: int) -> str:
    return (
        datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _utc_date_from_ms(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def _validate_safe_path_str(raw: str, field_name: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field_name} must be a non-empty path string")
    if ".." in Path(raw).parts:
        raise ValueError(f"{field_name} must not contain '..' traversal segments: {raw!r}")
    return raw.strip()


def _validate_base_url(raw: str, field_name: str) -> str:
    if not isinstance(raw, str) or not raw.strip().startswith("https://"):
        raise ValueError(f"{field_name} must start with 'https://': {raw!r}")
    return raw.strip().rstrip("/")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class OptionsMarketConfig:
    enabled: bool = True
    base_url: str = "https://eapi.binance.com"
    collect_open_interest: bool = True
    max_dte_days: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", _validate_base_url(self.base_url, "options.base_url"))
        if self.max_dte_days is not None:
            if isinstance(self.max_dte_days, bool) or not isinstance(self.max_dte_days, (int, float)):
                raise ValueError("options.max_dte_days must be numeric or null")
            if not math.isfinite(float(self.max_dte_days)) or float(self.max_dte_days) <= 0:
                raise ValueError("options.max_dte_days must be > 0")


@dataclass(frozen=True)
class SpotMarketConfig:
    enabled: bool = True
    base_url: str = "https://data-api.binance.vision"
    collect_closed_kline_1m: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", _validate_base_url(self.base_url, "spot.base_url"))


@dataclass(frozen=True)
class FuturesMarketConfig:
    enabled: bool = True
    base_url: str = "https://fapi.binance.com"
    contract_types: tuple[str, ...] = ("CURRENT_QUARTER", "NEXT_QUARTER", "PERPETUAL")
    collect_open_interest: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", _validate_base_url(self.base_url, "futures.base_url"))
        normalized = tuple(str(ct).strip().upper() for ct in self.contract_types)
        if self.enabled and not normalized:
            raise ValueError("futures.contract_types must not be empty when enabled")
        invalid = set(normalized) - VALID_CONTRACT_TYPES
        if invalid:
            raise ValueError(f"unsupported futures contract_types: {sorted(invalid)}")
        object.__setattr__(self, "contract_types", normalized)


@dataclass(frozen=True)
class StorageConfig:
    spool_dir: str = "data/collector_spool"
    output_dir: str = "data/collector_parquet"
    parquet_compression: str = "zstd"
    parquet_compression_level: int = 6
    rclone_remote: str = "gdrive:00_Katherine_Workspace/01_Alpha_Mining/datasets/binance_1m"
    upload_enabled: bool = True
    delete_spool_after_compact: bool = True
    retention_local_days: int = 3

    def __post_init__(self) -> None:
        object.__setattr__(self, "spool_dir", _validate_safe_path_str(self.spool_dir, "storage.spool_dir"))
        object.__setattr__(self, "output_dir", _validate_safe_path_str(self.output_dir, "storage.output_dir"))
        comp = str(self.parquet_compression).strip().lower()
        if comp not in VALID_COMPRESSIONS:
            raise ValueError(f"unsupported parquet_compression {comp!r}; expected one of {sorted(VALID_COMPRESSIONS)}")
        object.__setattr__(self, "parquet_compression", comp)
        if comp == "zstd":
            if isinstance(self.parquet_compression_level, bool) or not (1 <= int(self.parquet_compression_level) <= 22):
                raise ValueError("storage.parquet_compression_level must be in 1..22 for zstd")
        remote = str(self.rclone_remote).strip()
        if self.upload_enabled and (":" not in remote or any(c in remote for c in ";|&$`\n\r")):
            raise ValueError(f"invalid storage.rclone_remote: {remote!r}")
        object.__setattr__(self, "rclone_remote", remote.rstrip("/"))
        if isinstance(self.retention_local_days, bool) or int(self.retention_local_days) < 1:
            raise ValueError("storage.retention_local_days must be >= 1")


@dataclass(frozen=True)
class CollectorConfig:
    schema_version: str
    collector_id: str
    interval_seconds: int
    tick_offset_seconds: int
    exchange_info_refresh_seconds: int
    http_timeout_seconds: float
    http_max_retries: int
    underlyings: tuple[str, ...]
    spot_symbols: tuple[str, ...]
    options: OptionsMarketConfig
    spot: SpotMarketConfig
    futures_usdm: FuturesMarketConfig
    futures_coinm: FuturesMarketConfig
    storage: StorageConfig

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {self.schema_version!r}; expected {SCHEMA_VERSION!r}")
        if not isinstance(self.collector_id, str) or not self.collector_id.strip():
            raise ValueError("collector_id must be non-empty")
        if isinstance(self.interval_seconds, bool) or not (10 <= int(self.interval_seconds) <= 3600):
            raise ValueError("interval_seconds must be in 10..3600")
        if isinstance(self.tick_offset_seconds, bool) or not (0 <= int(self.tick_offset_seconds) < int(self.interval_seconds)):
            raise ValueError("tick_offset_seconds must satisfy 0 <= offset < interval_seconds")
        if isinstance(self.exchange_info_refresh_seconds, bool) or int(self.exchange_info_refresh_seconds) < 60:
            raise ValueError("exchange_info_refresh_seconds must be >= 60")
        if not math.isfinite(float(self.http_timeout_seconds)) or float(self.http_timeout_seconds) <= 0:
            raise ValueError("http_timeout_seconds must be > 0")
        if isinstance(self.http_max_retries, bool) or not (0 <= int(self.http_max_retries) <= 10):
            raise ValueError("http_max_retries must be in 0..10")

        u_norm = tuple(str(u).strip().upper() for u in self.underlyings if str(u).strip())
        if not u_norm or any(not u.isalnum() for u in u_norm):
            raise ValueError(f"underlyings must be non-empty alphanumeric tokens: {self.underlyings!r}")
        object.__setattr__(self, "underlyings", u_norm)

        s_norm = tuple(str(s).strip().upper() for s in self.spot_symbols if str(s).strip())
        if self.spot.enabled and (not s_norm or any(not s.isalnum() for s in s_norm)):
            raise ValueError(f"spot_symbols must be non-empty alphanumeric tokens when spot enabled: {self.spot_symbols!r}")
        object.__setattr__(self, "spot_symbols", s_norm)

        if not any(
            (
                self.options.enabled,
                self.spot.enabled,
                self.futures_usdm.enabled,
                self.futures_coinm.enabled,
            )
        ):
            raise ValueError("at least one market must be enabled")

    def resolve_spool_dir(self, base_dir: Path) -> Path:
        p = Path(self.storage.spool_dir)
        return p if p.is_absolute() else (base_dir / p)

    def resolve_output_dir(self, base_dir: Path) -> Path:
        p = Path(self.storage.output_dir)
        return p if p.is_absolute() else (base_dir / p)


def load_collector_config(path: Path) -> CollectorConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("collector config root must be a JSON object")
    markets = raw.get("markets")
    if not isinstance(markets, dict):
        raise ValueError("collector config missing 'markets' object")
    storage_raw = raw.get("storage")
    if not isinstance(storage_raw, dict):
        raise ValueError("collector config missing 'storage' object")

    opt_raw = markets.get("options", {})
    spot_raw = markets.get("spot", {})
    usdm_raw = markets.get("futures_usdm", {})
    coinm_raw = markets.get("futures_coinm", {})

    return CollectorConfig(
        schema_version=str(raw.get("schema_version", "")),
        collector_id=str(raw.get("collector_id", "")),
        interval_seconds=int(raw.get("interval_seconds", 60)),
        tick_offset_seconds=int(raw.get("tick_offset_seconds", 2)),
        exchange_info_refresh_seconds=int(raw.get("exchange_info_refresh_seconds", 600)),
        http_timeout_seconds=float(raw.get("http_timeout_seconds", 15.0)),
        http_max_retries=int(raw.get("http_max_retries", 3)),
        underlyings=tuple(raw.get("underlyings", ())),
        spot_symbols=tuple(raw.get("spot_symbols", ())),
        options=OptionsMarketConfig(
            enabled=bool(opt_raw.get("enabled", True)),
            base_url=str(opt_raw.get("base_url", "https://eapi.binance.com")),
            collect_open_interest=bool(opt_raw.get("collect_open_interest", True)),
            max_dte_days=opt_raw.get("max_dte_days"),
        ),
        spot=SpotMarketConfig(
            enabled=bool(spot_raw.get("enabled", True)),
            base_url=str(spot_raw.get("base_url", "https://data-api.binance.vision")),
            collect_closed_kline_1m=bool(spot_raw.get("collect_closed_kline_1m", True)),
        ),
        futures_usdm=FuturesMarketConfig(
            enabled=bool(usdm_raw.get("enabled", True)),
            base_url=str(usdm_raw.get("base_url", "https://fapi.binance.com")),
            contract_types=tuple(usdm_raw.get("contract_types", ("CURRENT_QUARTER", "NEXT_QUARTER", "PERPETUAL"))),
            collect_open_interest=bool(usdm_raw.get("collect_open_interest", True)),
        ),
        futures_coinm=FuturesMarketConfig(
            enabled=bool(coinm_raw.get("enabled", True)),
            base_url=str(coinm_raw.get("base_url", "https://dapi.binance.com")),
            contract_types=tuple(coinm_raw.get("contract_types", ("CURRENT_QUARTER", "NEXT_QUARTER", "PERPETUAL"))),
            collect_open_interest=bool(coinm_raw.get("collect_open_interest", True)),
        ),
        storage=StorageConfig(
            spool_dir=str(storage_raw.get("spool_dir", "data/collector_spool")),
            output_dir=str(storage_raw.get("output_dir", "data/collector_parquet")),
            parquet_compression=str(storage_raw.get("parquet_compression", "zstd")),
            parquet_compression_level=int(storage_raw.get("parquet_compression_level", 6)),
            rclone_remote=str(
                storage_raw.get(
                    "rclone_remote",
                    "gdrive:00_Katherine_Workspace/01_Alpha_Mining/datasets/binance_1m",
                )
            ),
            upload_enabled=bool(storage_raw.get("upload_enabled", True)),
            delete_spool_after_compact=bool(storage_raw.get("delete_spool_after_compact", True)),
            retention_local_days=int(storage_raw.get("retention_local_days", 3)),
        ),
    )


def _default_urllib_transport(url: str, timeout: float) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "alpha-mining-binance-1m-collector/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return int(resp.status), headers, resp.read()
    except urllib.error.HTTPError as exc:
        headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        body = exc.read() if exc.fp is not None else b""
        return int(exc.code), headers, body


class BinanceHttpError(RuntimeError):
    def __init__(self, status: int, url: str, body_preview: str) -> None:
        super().__init__(f"HTTP {status} for {url}: {body_preview[:240]}")
        self.status = status
        self.url = url
        self.body_preview = body_preview[:240]


class BinanceHttpClient:
    """Minimal stdlib HTTP client with retry, Retry-After support, and rate-weight tracking."""

    RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        max_retries: int = 3,
        transport: HttpTransport | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.timeout = float(timeout)
        self.max_retries = int(max_retries)
        self._transport = transport or _default_urllib_transport
        self._sleep = sleep_fn
        self.last_used_weight: dict[str, int] = {}

    def get_json(self, base_url: str, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{base_url.rstrip('/')}{path}"
        if params:
            query = urllib.parse.urlencode(
                [(k, v) for k, v in params.items() if v is not None],
                safe='[]",',
            )
            if query:
                url = f"{url}?{query}"

        host = urllib.parse.urlsplit(url).netloc
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                status, headers, body = self._transport(url, self.timeout)
                weight_hdr = headers.get("x-mbx-used-weight-1m")
                if weight_hdr is not None and weight_hdr.isdigit():
                    self.last_used_weight[host] = int(weight_hdr)

                if status == 200:
                    return json.loads(body.decode("utf-8"))

                preview = body.decode("utf-8", errors="replace")[:240]
                if status in self.RETRYABLE_STATUSES and attempt < self.max_retries:
                    retry_after = _to_float(headers.get("retry-after"))
                    delay = retry_after if (retry_after is not None and retry_after > 0) else min(float(2**attempt), 30.0)
                    self._sleep(delay)
                    continue
                raise BinanceHttpError(status, url, preview)
            except BinanceHttpError:
                raise
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    self._sleep(min(float(2**attempt), 30.0))
                    continue
                raise RuntimeError(f"GET {url} failed after {attempt + 1} attempts: {exc}") from exc

        assert last_exc is not None
        raise last_exc


def parse_option_symbol_fallback(symbol: str) -> tuple[str | None, str | None, float | None, str | None]:
    """Parse Binance option symbol `BTC-261225-100000-C` -> (underlying, expiry_code, strike, right)."""
    parts = symbol.strip().upper().split("-")
    if len(parts) != 4:
        return None, None, None, None
    underlying, expiry_code, strike_str, right = parts
    strike = _to_float(strike_str)
    if right not in ("C", "P"):
        right = None
    return underlying or None, expiry_code or None, strike, right


@dataclass
class _MetadataCache:
    options_symbols: dict[str, dict[str, Any]] = field(default_factory=dict)
    options_refreshed_at: float = 0.0
    usdm_symbols: dict[str, dict[str, Any]] = field(default_factory=dict)
    usdm_refreshed_at: float = 0.0
    coinm_symbols: dict[str, dict[str, Any]] = field(default_factory=dict)
    coinm_refreshed_at: float = 0.0


class DailySpoolWriter:
    """Append-only crash-safe JSONL daily spooler (one file per UTC date & dataset)."""

    def __init__(self, spool_root: Path) -> None:
        self.spool_root = spool_root
        self.spool_root.mkdir(parents=True, exist_ok=True)

    def day_dir(self, date_utc: str) -> Path:
        return self.spool_root / date_utc

    def spool_file(self, date_utc: str, dataset: str) -> Path:
        return self.day_dir(date_utc) / f"{dataset}.jsonl"

    def append_records(self, date_utc: str, dataset: str, records: Sequence[dict[str, Any]]) -> int:
        if not records:
            return 0
        target = self.spool_file(date_utc, dataset)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, separators=(",", ":"), ensure_ascii=False))
                fh.write("\n")
            fh.flush()
        return len(records)

    def write_health(self, payload: dict[str, Any]) -> Path:
        target = self.spool_root / "health.json"
        tmp = self.spool_root / "health.json.tmp"
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, target)
        return target

    def list_spool_dates(self) -> list[str]:
        if not self.spool_root.exists():
            return []
        dates: list[str] = []
        for entry in sorted(self.spool_root.iterdir()):
            if entry.is_dir() and len(entry.name) == 10:
                try:
                    date.fromisoformat(entry.name)
                    dates.append(entry.name)
                except ValueError:
                    continue
        return dates


def read_spool_records(spool_file: Path) -> tuple[list[dict[str, Any]], int]:
    """Read JSONL spool file, tolerating/counting any truncated corrupt lines from abrupt crashes."""
    records: list[dict[str, Any]] = []
    corrupt_lines = 0
    if not spool_file.is_file():
        return records, corrupt_lines
    with spool_file.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    records.append(obj)
                else:
                    corrupt_lines += 1
            except json.JSONDecodeError:
                corrupt_lines += 1
    return records, corrupt_lines


def normalize_and_dedupe_records(dataset: str, records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate by (ts_utc_ms, symbol) keeping latest write, sort deterministically, and project schema."""
    schema = DATASET_SCHEMAS[dataset]
    by_key: dict[tuple[int, str], dict[str, Any]] = {}
    for rec in records:
        ts_ms = _to_int(rec.get("ts_utc_ms"))
        sym = str(rec.get("symbol", "")).strip()
        if ts_ms is None or not sym:
            continue
        projected: dict[str, Any] = {}
        for col, typ in schema:
            raw = rec.get(col)
            if typ == "int64":
                projected[col] = _to_int(raw)
            elif typ == "float64":
                projected[col] = _to_float(raw)
            else:
                projected[col] = None if raw is None else str(raw)
        by_key[(ts_ms, sym)] = projected

    return [by_key[k] for k in sorted(by_key.keys())]


def _require_pyarrow() -> tuple[Any, Any]:
    try:
        import pyarrow as pa  # type: ignore[import-not-found]
        import pyarrow.parquet as pq  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "pyarrow is required for Parquet Zstd compaction. "
            "Install dependencies via: pip install -r deploy/vps/requirements-collector.txt"
        ) from exc
    return pa, pq


def build_arrow_schema(dataset: str) -> Any:
    pa, _ = _require_pyarrow()
    type_map = {
        "int64": pa.int64(),
        "float64": pa.float64(),
        "string": pa.string(),
    }
    return pa.schema([pa.field(col, type_map[typ], nullable=True) for col, typ in DATASET_SCHEMAS[dataset]])


def write_parquet_zstd(
    dataset: str,
    records: Sequence[dict[str, Any]],
    out_path: Path,
    *,
    compression: str = "zstd",
    compression_level: int | None = 6,
) -> Path:
    """Atomically write sorted typed records to Parquet with Zstd compression."""
    pa, pq = _require_pyarrow()
    schema = build_arrow_schema(dataset)
    cols = {col: [r.get(col) for r in records] for col, _ in DATASET_SCHEMAS[dataset]}
    table = pa.table(cols, schema=schema)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    write_kwargs: dict[str, Any] = {
        "compression": None if compression == "none" else compression,
        "use_dictionary": True,
        "write_statistics": True,
    }
    if compression == "zstd" and compression_level is not None:
        write_kwargs["compression_level"] = int(compression_level)
    pq.write_table(table, tmp_path, **write_kwargs)
    os.replace(tmp_path, out_path)
    return out_path


def build_day_manifest(
    *,
    dataset: str,
    date_utc: str,
    parquet_path: Path,
    records: Sequence[dict[str, Any]],
    corrupt_lines_skipped: int,
    compression: str,
    compression_level: int | None,
    interval_seconds: int,
    compacted_at_utc: str | None = None,
) -> dict[str, Any]:
    unique_minutes = {int(r["ts_utc_ms"]) // 60_000 for r in records if r.get("ts_utc_ms") is not None}
    unique_symbols = {str(r["symbol"]) for r in records if r.get("symbol")}
    ts_vals = [int(r["ts_utc_ms"]) for r in records if r.get("ts_utc_ms") is not None]
    expected_ticks = max(1, 86_400 // max(1, interval_seconds))
    coverage_pct = round(100.0 * len(unique_minutes) / float(expected_ticks), 2)
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset": dataset,
        "date_utc": date_utc,
        "parquet_file": parquet_path.name,
        "parquet_size_bytes": parquet_path.stat().st_size,
        "parquet_sha256": _sha256_file(parquet_path),
        "compression": compression,
        "compression_level": compression_level if compression == "zstd" else None,
        "row_count": len(records),
        "unique_minutes": len(unique_minutes),
        "expected_ticks_per_day": expected_ticks,
        "minute_coverage_pct": coverage_pct,
        "unique_symbols": len(unique_symbols),
        "min_ts_utc_ms": min(ts_vals) if ts_vals else None,
        "max_ts_utc_ms": max(ts_vals) if ts_vals else None,
        "corrupt_lines_skipped": corrupt_lines_skipped,
        "compacted_at_utc": compacted_at_utc or _utc_iso_from_ms(int(time.time() * 1000)),
    }


def compact_day_to_parquet(
    config: CollectorConfig,
    *,
    base_dir: Path,
    date_utc: str,
    datasets: Sequence[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Compact all spooled datasets for `date_utc` into daily Parquet Zstd + SHA-256 manifests."""
    date.fromisoformat(date_utc)
    month_part = date_utc[:7]
    spool_root = config.resolve_spool_dir(base_dir)
    out_root = config.resolve_output_dir(base_dir)
    target_datasets = tuple(datasets) if datasets is not None else DATASET_NAMES
    results: dict[str, dict[str, Any]] = {}

    for dataset in target_datasets:
        if dataset not in DATASET_SCHEMAS:
            raise ValueError(f"unknown dataset: {dataset!r}")
        spool_file = spool_root / date_utc / f"{dataset}.jsonl"
        if not spool_file.is_file():
            continue
        raw_records, corrupt_lines = read_spool_records(spool_file)
        clean_records = normalize_and_dedupe_records(dataset, raw_records)
        if not clean_records:
            continue

        parquet_path = out_root / dataset / month_part / f"{dataset}_{date_utc}.parquet"
        write_parquet_zstd(
            dataset,
            clean_records,
            parquet_path,
            compression=config.storage.parquet_compression,
            compression_level=config.storage.parquet_compression_level,
        )
        manifest = build_day_manifest(
            dataset=dataset,
            date_utc=date_utc,
            parquet_path=parquet_path,
            records=clean_records,
            corrupt_lines_skipped=corrupt_lines,
            compression=config.storage.parquet_compression,
            compression_level=config.storage.parquet_compression_level,
            interval_seconds=config.interval_seconds,
        )
        manifest_path = out_root / dataset / month_part / f"{dataset}_{date_utc}.manifest.json"
        tmp_manifest = manifest_path.with_suffix(".json.tmp")
        tmp_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp_manifest, manifest_path)

        results[dataset] = {
            "parquet_path": str(parquet_path),
            "manifest_path": str(manifest_path),
            "manifest": manifest,
        }

        if config.storage.delete_spool_after_compact:
            spool_file.unlink(missing_ok=True)

    day_spool_dir = spool_root / date_utc
    if config.storage.delete_spool_after_compact and day_spool_dir.is_dir():
        try:
            next(day_spool_dir.iterdir())
        except StopIteration:
            day_spool_dir.rmdir()

    return results


def _default_subprocess_runner(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(cmd), capture_output=True, text=True, check=False)


def upload_day_to_drive(
    config: CollectorConfig,
    *,
    base_dir: Path,
    date_utc: str,
    datasets: Sequence[str] | None = None,
    runner: SubprocessRunner | None = None,
) -> dict[str, dict[str, Any]]:
    """Upload daily Parquet + manifest files non-destructively via `rclone copy`."""
    date.fromisoformat(date_utc)
    month_part = date_utc[:7]
    out_root = config.resolve_output_dir(base_dir)
    run_cmd = runner or _default_subprocess_runner
    target_datasets = tuple(datasets) if datasets is not None else DATASET_NAMES
    receipts: dict[str, dict[str, Any]] = {}

    for dataset in target_datasets:
        parquet_path = out_root / dataset / month_part / f"{dataset}_{date_utc}.parquet"
        manifest_path = out_root / dataset / month_part / f"{dataset}_{date_utc}.manifest.json"
        if not parquet_path.is_file() or not manifest_path.is_file():
            continue

        remote_dir = f"{config.storage.rclone_remote}/{dataset}/{month_part}"
        for local_file in (parquet_path, manifest_path):
            cmd = [
                "rclone",
                "copy",
                str(local_file),
                remote_dir,
                "--transfers",
                "2",
                "--retries",
                "3",
                "--low-level-retries",
                "5",
            ]
            proc = run_cmd(cmd)
            if proc.returncode != 0:
                raise RuntimeError(
                    f"rclone copy failed for {local_file} -> {remote_dir} "
                    f"(exit={proc.returncode}): {(proc.stderr or proc.stdout).strip()[:300]}"
                )

        receipt = {
            "schema_version": SCHEMA_VERSION,
            "dataset": dataset,
            "date_utc": date_utc,
            "remote_dir": remote_dir,
            "parquet_file": parquet_path.name,
            "parquet_sha256": _sha256_file(parquet_path),
            "uploaded_at_utc": _utc_iso_from_ms(int(time.time() * 1000)),
        }
        receipt_path = out_root / dataset / month_part / f"{dataset}_{date_utc}.uploaded.json"
        tmp_receipt = receipt_path.with_suffix(".json.tmp")
        tmp_receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp_receipt, receipt_path)
        receipts[dataset] = receipt

    return receipts


def upload_pending_days(
    config: CollectorConfig,
    *,
    base_dir: Path,
    before_date_utc: str,
    runner: SubprocessRunner | None = None,
) -> dict[str, dict[str, Any]]:
    """Retry Google Drive upload for any compacted day strictly before `before_date_utc` lacking a `.uploaded.json` receipt."""
    date.fromisoformat(before_date_utc)
    out_root = config.resolve_output_dir(base_dir)
    if not out_root.exists():
        return {}

    pending_by_day: dict[str, list[str]] = {}
    for dataset in DATASET_NAMES:
        ds_dir = out_root / dataset
        if not ds_dir.is_dir():
            continue
        for parquet_path in sorted(ds_dir.rglob("*.parquet")):
            stem = parquet_path.stem
            if len(stem) < 11:
                continue
            day_str = stem[-10:]
            try:
                date.fromisoformat(day_str)
            except ValueError:
                continue
            if day_str >= before_date_utc:
                continue
            manifest_path = parquet_path.with_suffix(".manifest.json")
            receipt_path = parquet_path.with_suffix(".uploaded.json")
            if manifest_path.is_file() and not receipt_path.is_file():
                pending_by_day.setdefault(day_str, []).append(dataset)

    uploaded_all: dict[str, dict[str, Any]] = {}
    for day_str, ds_list in sorted(pending_by_day.items()):
        receipts = upload_day_to_drive(
            config,
            base_dir=base_dir,
            date_utc=day_str,
            datasets=ds_list,
            runner=runner,
        )
        if receipts:
            uploaded_all[day_str] = receipts
    return uploaded_all


def prune_uploaded_local_parquet(
    config: CollectorConfig,
    *,
    base_dir: Path,
    today_utc: date | None = None,
) -> list[str]:
    """Delete local Parquet files older than retention_local_days ONLY when upload receipt matches SHA-256."""
    ref_day = today_utc or datetime.now(timezone.utc).date()
    cutoff = ref_day - timedelta(days=int(config.storage.retention_local_days))
    out_root = config.resolve_output_dir(base_dir)
    removed: list[str] = []
    if not out_root.exists():
        return removed

    for parquet_path in sorted(out_root.rglob("*.parquet")):
        stem = parquet_path.stem  # <dataset>_YYYY-MM-DD
        if len(stem) < 11:
            continue
        date_str = stem[-10:]
        try:
            file_day = date.fromisoformat(date_str)
        except ValueError:
            continue
        if file_day >= cutoff:
            continue
        receipt_path = parquet_path.with_suffix(".uploaded.json")
        if not receipt_path.is_file():
            continue
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if receipt.get("parquet_sha256") != _sha256_file(parquet_path):
            continue
        parquet_path.unlink()
        removed.append(str(parquet_path))

    return removed


class Binance1mCollector:
    """Synchronized 1-minute collector for Binance Options, Spot, and Delivery Futures."""

    def __init__(
        self,
        config: CollectorConfig,
        *,
        base_dir: Path,
        http_client: BinanceHttpClient | None = None,
        subprocess_runner: SubprocessRunner | None = None,
        clock_ms_fn: Callable[[], int] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.base_dir = base_dir
        self.http = http_client or BinanceHttpClient(
            timeout=config.http_timeout_seconds,
            max_retries=config.http_max_retries,
            sleep_fn=sleep_fn,
        )
        self.runner = subprocess_runner or _default_subprocess_runner
        self._clock_ms = clock_ms_fn or (lambda: int(time.time() * 1000))
        self._sleep = sleep_fn
        self.spool = DailySpoolWriter(config.resolve_spool_dir(base_dir))
        self._cache = _MetadataCache()
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def _refresh_options_exchange_info(self, now_sec: float) -> dict[str, dict[str, Any]]:
        if (
            self._cache.options_symbols
            and (now_sec - self._cache.options_refreshed_at) < self.config.exchange_info_refresh_seconds
        ):
            return self._cache.options_symbols
        data = self.http.get_json(self.config.options.base_url, "/eapi/v1/exchangeInfo")
        items = data.get("optionSymbols") or data.get("symbols") or []
        underlyings_set = set(self.config.underlyings)
        parsed: dict[str, dict[str, Any]] = {}
        for item in items:
            symbol = str(item.get("symbol", "")).strip().upper()
            if not symbol:
                continue
            status = str(item.get("status") or item.get("contractStatus") or "TRADING").upper()
            if status not in ("TRADING", ""):
                continue
            fb_u, fb_exp, fb_strike, fb_right = parse_option_symbol_fallback(symbol)
            underlying_raw = str(item.get("underlying", "")).strip().upper()
            underlying_asset = fb_u or underlying_raw.removesuffix("USDT").removesuffix("USD")
            if underlying_asset not in underlyings_set:
                continue
            expiry_ms = _to_int(item.get("expiryDate"))
            expiry_code = fb_exp
            if not expiry_code and expiry_ms is not None:
                expiry_code = datetime.fromtimestamp(expiry_ms / 1000.0, tz=timezone.utc).strftime("%y%m%d")
            side_raw = str(item.get("side", "")).strip().upper()
            right = "C" if side_raw.startswith("C") else ("P" if side_raw.startswith("P") else fb_right)
            strike = _to_float(item.get("strikePrice"))
            if strike is None:
                strike = fb_strike
            parsed[symbol] = {
                "symbol": symbol,
                "underlying_asset": underlying_asset,
                "underlying": underlying_raw or f"{underlying_asset}USDT",
                "expiry_utc_ms": expiry_ms,
                "expiry_code": expiry_code,
                "strike": strike,
                "right": right,
            }
        self._cache.options_symbols = parsed
        self._cache.options_refreshed_at = now_sec
        return parsed

    def _refresh_futures_exchange_info(self, venue: str, now_sec: float) -> dict[str, dict[str, Any]]:
        if venue == "usdm":
            cfg = self.config.futures_usdm
            cached, refreshed_at = self._cache.usdm_symbols, self._cache.usdm_refreshed_at
            path = "/fapi/v1/exchangeInfo"
            status_key = "status"
        else:
            cfg = self.config.futures_coinm
            cached, refreshed_at = self._cache.coinm_symbols, self._cache.coinm_refreshed_at
            path = "/dapi/v1/exchangeInfo"
            status_key = "contractStatus"

        if cached and (now_sec - refreshed_at) < self.config.exchange_info_refresh_seconds:
            return cached

        data = self.http.get_json(cfg.base_url, path)
        items = data.get("symbols") or []
        underlyings_set = set(self.config.underlyings)
        allowed_types = set(cfg.contract_types)
        parsed: dict[str, dict[str, Any]] = {}
        for item in items:
            symbol = str(item.get("symbol", "")).strip().upper()
            if not symbol:
                continue
            status = str(item.get(status_key) or item.get("status") or "").upper()
            if status != "TRADING":
                continue
            base_asset = str(item.get("baseAsset", "")).strip().upper()
            contract_type = str(item.get("contractType", "")).strip().upper()
            if base_asset not in underlyings_set or contract_type not in allowed_types:
                continue
            parsed[symbol] = {
                "symbol": symbol,
                "pair": str(item.get("pair", "")).strip().upper() or None,
                "base_asset": base_asset,
                "quote_asset": str(item.get("quoteAsset", "")).strip().upper() or None,
                "contract_type": contract_type,
                "delivery_utc_ms": _to_int(item.get("deliveryDate")),
                "contract_size": _to_float(item.get("contractSize")),
            }

        if venue == "usdm":
            self._cache.usdm_symbols = parsed
            self._cache.usdm_refreshed_at = now_sec
        else:
            self._cache.coinm_symbols = parsed
            self._cache.coinm_refreshed_at = now_sec
        return parsed

    def collect_options_chain(self, ts_utc_ms: int) -> tuple[list[dict[str, Any]], list[str]]:
        errors: list[str] = []
        now_sec = ts_utc_ms / 1000.0
        snapshot_utc = _utc_iso_from_ms(ts_utc_ms)
        meta_by_sym = self._refresh_options_exchange_info(now_sec)

        mark_list = self.http.get_json(self.config.options.base_url, "/eapi/v1/mark")
        ticker_list = self.http.get_json(self.config.options.base_url, "/eapi/v1/ticker")
        mark_by_sym = {str(x.get("symbol", "")).strip().upper(): x for x in mark_list if isinstance(x, dict)}
        ticker_by_sym = {str(x.get("symbol", "")).strip().upper(): x for x in ticker_list if isinstance(x, dict)}

        # Index price per underlying (e.g., BTCUSDT, ETHUSDT)
        index_by_asset: dict[str, float | None] = {}
        for asset in self.config.underlyings:
            underlying_pair = f"{asset}USDT"
            try:
                idx_resp = self.http.get_json(
                    self.config.options.base_url,
                    "/eapi/v1/index",
                    {"underlying": underlying_pair},
                )
                index_by_asset[asset] = _to_float(idx_resp.get("indexPrice"))
            except Exception as exc:  # noqa: BLE001
                index_by_asset[asset] = None
                errors.append(f"options.index[{underlying_pair}]: {exc}")

        # Open Interest per (underlying_asset, expiry_code)
        oi_by_sym: dict[str, tuple[float | None, float | None]] = {}
        if self.config.options.collect_open_interest:
            expiry_pairs = sorted(
                {
                    (m["underlying_asset"], m["expiry_code"])
                    for m in meta_by_sym.values()
                    if m.get("underlying_asset") and m.get("expiry_code")
                }
            )
            for asset, exp_code in expiry_pairs:
                try:
                    oi_resp = self.http.get_json(
                        self.config.options.base_url,
                        "/eapi/v1/openInterest",
                        {"underlyingAsset": asset, "expiration": exp_code},
                    )
                    if isinstance(oi_resp, list):
                        for item in oi_resp:
                            sym = str(item.get("symbol", "")).strip().upper()
                            if sym:
                                oi_by_sym[sym] = (
                                    _to_float(item.get("sumOpenInterest")),
                                    _to_float(item.get("sumOpenInterestUsd")),
                                )
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"options.openInterest[{asset}-{exp_code}]: {exc}")

        all_syms = sorted(set(meta_by_sym.keys()) | {s for s in mark_by_sym if parse_option_symbol_fallback(s)[0] in self.config.underlyings})
        records: list[dict[str, Any]] = []
        max_dte = self.config.options.max_dte_days

        for sym in all_syms:
            meta = meta_by_sym.get(sym, {})
            fb_u, fb_exp, fb_strike, fb_right = parse_option_symbol_fallback(sym)
            asset = meta.get("underlying_asset") or fb_u
            if asset not in self.config.underlyings:
                continue
            expiry_ms = meta.get("expiry_utc_ms")
            dte_days = ((expiry_ms - ts_utc_ms) / 86_400_000.0) if expiry_ms is not None else None
            if max_dte is not None and dte_days is not None and dte_days > max_dte:
                continue

            mk = mark_by_sym.get(sym, {})
            tk = ticker_by_sym.get(sym, {})
            bid_p = _to_float(tk.get("bidPrice"))
            ask_p = _to_float(tk.get("askPrice"))
            mid_p = ((bid_p + ask_p) / 2.0) if (bid_p is not None and ask_p is not None and bid_p > 0 and ask_p > 0) else None
            spread_pct = ((ask_p - bid_p) / mid_p) if (mid_p is not None and mid_p > 0 and bid_p is not None and ask_p is not None) else None
            oi_qty, oi_usd = oi_by_sym.get(sym, (None, None))

            records.append(
                {
                    "ts_utc_ms": ts_utc_ms,
                    "snapshot_utc": snapshot_utc,
                    "underlying": asset,
                    "symbol": sym,
                    "expiry_utc_ms": expiry_ms,
                    "expiry_code": meta.get("expiry_code") or fb_exp,
                    "dte_days": dte_days,
                    "strike": meta.get("strike") if meta.get("strike") is not None else (_to_float(tk.get("strikePrice")) or fb_strike),
                    "right": meta.get("right") or fb_right,
                    "index_price": index_by_asset.get(asset),
                    "bid_price": bid_p,
                    "ask_price": ask_p,
                    "bid_qty": _to_float(tk.get("bidQty")),
                    "ask_qty": _to_float(tk.get("askQty")),
                    "mid_price": mid_p,
                    "spread_pct": spread_pct,
                    "last_price": _to_float(tk.get("lastPrice")),
                    "mark_price": _to_float(mk.get("markPrice")),
                    "bid_iv": _to_float(mk.get("bidIV")),
                    "ask_iv": _to_float(mk.get("askIV")),
                    "mark_iv": _to_float(mk.get("markIV")),
                    "delta": _to_float(mk.get("delta")),
                    "gamma": _to_float(mk.get("gamma")),
                    "vega": _to_float(mk.get("vega")),
                    "theta": _to_float(mk.get("theta")),
                    "open_interest": oi_qty,
                    "open_interest_usd": oi_usd,
                    "volume_24h": _to_float(tk.get("volume")),
                    "amount_24h": _to_float(tk.get("amount")),
                    "high_price_limit": _to_float(mk.get("highPriceLimit")),
                    "low_price_limit": _to_float(mk.get("lowPriceLimit")),
                }
            )

        return records, errors

    def collect_spot(self, ts_utc_ms: int) -> tuple[list[dict[str, Any]], list[str]]:
        errors: list[str] = []
        snapshot_utc = _utc_iso_from_ms(ts_utc_ms)
        symbols_json = json.dumps(list(self.config.spot_symbols), separators=(",", ":"))

        book_raw = self.http.get_json(
            self.config.spot.base_url,
            "/api/v3/ticker/bookTicker",
            {"symbols": symbols_json},
        )
        t24_raw = self.http.get_json(
            self.config.spot.base_url,
            "/api/v3/ticker/24hr",
            {"symbols": symbols_json},
        )
        book_by_sym = {str(x.get("symbol", "")).upper(): x for x in book_raw if isinstance(x, dict)}
        t24_by_sym = {str(x.get("symbol", "")).upper(): x for x in t24_raw if isinstance(x, dict)}

        records: list[dict[str, Any]] = []
        for sym in self.config.spot_symbols:
            bk = book_by_sym.get(sym, {})
            t24 = t24_by_sym.get(sym, {})
            bid_p = _to_float(bk.get("bidPrice"))
            ask_p = _to_float(bk.get("askPrice"))
            mid_p = ((bid_p + ask_p) / 2.0) if (bid_p is not None and ask_p is not None and bid_p > 0 and ask_p > 0) else None
            spread_bps = (
                ((ask_p - bid_p) / mid_p) * 10_000.0
                if (mid_p is not None and mid_p > 0 and bid_p is not None and ask_p is not None)
                else None
            )

            kline: list[Any] | None = None
            if self.config.spot.collect_closed_kline_1m:
                try:
                    klines = self.http.get_json(
                        self.config.spot.base_url,
                        "/api/v3/klines",
                        {"symbol": sym, "interval": "1m", "limit": 2},
                    )
                    if isinstance(klines, list) and klines:
                        closed = [bar for bar in klines if isinstance(bar, list) and len(bar) >= 9 and (_to_int(bar[6]) or 0) < ts_utc_ms]
                        kline = closed[-1] if closed else klines[0]
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"spot.klines[{sym}]: {exc}")

            records.append(
                {
                    "ts_utc_ms": ts_utc_ms,
                    "snapshot_utc": snapshot_utc,
                    "symbol": sym,
                    "bid_price": bid_p,
                    "bid_qty": _to_float(bk.get("bidQty")),
                    "ask_price": ask_p,
                    "ask_qty": _to_float(bk.get("askQty")),
                    "mid_price": mid_p,
                    "spread_bps": spread_bps,
                    "last_price": _to_float(t24.get("lastPrice")),
                    "volume_24h": _to_float(t24.get("volume")),
                    "quote_volume_24h": _to_float(t24.get("quoteVolume")),
                    "kline_open_time_ms": _to_int(kline[0]) if kline else None,
                    "kline_close_time_ms": _to_int(kline[6]) if kline else None,
                    "kline_open": _to_float(kline[1]) if kline else None,
                    "kline_high": _to_float(kline[2]) if kline else None,
                    "kline_low": _to_float(kline[3]) if kline else None,
                    "kline_close": _to_float(kline[4]) if kline else None,
                    "kline_volume": _to_float(kline[5]) if kline else None,
                    "kline_quote_volume": _to_float(kline[7]) if kline else None,
                    "kline_trades": _to_int(kline[8]) if kline else None,
                }
            )
        return records, errors

    def collect_futures_venue(self, venue: str, ts_utc_ms: int) -> tuple[list[dict[str, Any]], list[str]]:
        if venue not in ("usdm", "coinm"):
            raise ValueError(f"invalid futures venue: {venue!r}")
        cfg = self.config.futures_usdm if venue == "usdm" else self.config.futures_coinm
        prefix = "/fapi/v1" if venue == "usdm" else "/dapi/v1"
        errors: list[str] = []
        snapshot_utc = _utc_iso_from_ms(ts_utc_ms)
        meta_by_sym = self._refresh_futures_exchange_info(venue, ts_utc_ms / 1000.0)
        if not meta_by_sym:
            return [], errors

        prem_raw = self.http.get_json(cfg.base_url, f"{prefix}/premiumIndex")
        book_raw = self.http.get_json(cfg.base_url, f"{prefix}/ticker/bookTicker")
        prem_by_sym = {str(x.get("symbol", "")).upper(): x for x in prem_raw if isinstance(x, dict)}
        book_by_sym = {str(x.get("symbol", "")).upper(): x for x in book_raw if isinstance(x, dict)}

        records: list[dict[str, Any]] = []
        for sym in sorted(meta_by_sym.keys()):
            meta = meta_by_sym[sym]
            pm = prem_by_sym.get(sym, {})
            bk = book_by_sym.get(sym, {})

            t24: dict[str, Any] = {}
            try:
                t24_resp = self.http.get_json(cfg.base_url, f"{prefix}/ticker/24hr", {"symbol": sym})
                if isinstance(t24_resp, list) and t24_resp:
                    t24 = t24_resp[0] if isinstance(t24_resp[0], dict) else {}
                elif isinstance(t24_resp, dict):
                    t24 = t24_resp
            except Exception as exc:  # noqa: BLE001
                errors.append(f"futures_{venue}.ticker24hr[{sym}]: {exc}")

            oi_val: float | None = None
            if cfg.collect_open_interest:
                try:
                    oi_resp = self.http.get_json(cfg.base_url, f"{prefix}/openInterest", {"symbol": sym})
                    if isinstance(oi_resp, dict):
                        oi_val = _to_float(oi_resp.get("openInterest"))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"futures_{venue}.openInterest[{sym}]: {exc}")

            delivery_ms = meta.get("delivery_utc_ms")
            is_delivery = meta["contract_type"] != "PERPETUAL" and delivery_ms is not None and delivery_ms < PERPETUAL_DELIVERY_SENTINEL_MS
            dte_days = ((delivery_ms - ts_utc_ms) / 86_400_000.0) if is_delivery and delivery_ms is not None else None

            bid_p = _to_float(bk.get("bidPrice"))
            ask_p = _to_float(bk.get("askPrice"))
            mid_p = ((bid_p + ask_p) / 2.0) if (bid_p is not None and ask_p is not None and bid_p > 0 and ask_p > 0) else None
            mark_p = _to_float(pm.get("markPrice"))
            index_p = _to_float(pm.get("indexPrice"))
            basis = (mark_p - index_p) if (mark_p is not None and index_p is not None) else None
            basis_bps = ((basis / index_p) * 10_000.0) if (basis is not None and index_p is not None and index_p > 0) else None
            ann_basis = (
                (basis / index_p) * (365.0 / dte_days)
                if (basis is not None and index_p is not None and index_p > 0 and dte_days is not None and dte_days > 0)
                else None
            )

            records.append(
                {
                    "ts_utc_ms": ts_utc_ms,
                    "snapshot_utc": snapshot_utc,
                    "venue": venue,
                    "symbol": sym,
                    "pair": meta.get("pair") or pm.get("pair"),
                    "base_asset": meta.get("base_asset"),
                    "quote_asset": meta.get("quote_asset"),
                    "contract_type": meta.get("contract_type"),
                    "delivery_utc_ms": delivery_ms if is_delivery else None,
                    "dte_days": dte_days,
                    "contract_size": meta.get("contract_size"),
                    "bid_price": bid_p,
                    "bid_qty": _to_float(bk.get("bidQty")),
                    "ask_price": ask_p,
                    "ask_qty": _to_float(bk.get("askQty")),
                    "mid_price": mid_p,
                    "last_price": _to_float(t24.get("lastPrice")),
                    "mark_price": mark_p,
                    "index_price": index_p,
                    "estimated_settle_price": _to_float(pm.get("estimatedSettlePrice")),
                    "basis": basis,
                    "basis_bps": basis_bps,
                    "annualized_basis": ann_basis,
                    "last_funding_rate": _to_float(pm.get("lastFundingRate")),
                    "next_funding_utc_ms": _to_int(pm.get("nextFundingTime")),
                    "open_interest": oi_val,
                    "volume_24h": _to_float(t24.get("volume")),
                    "quote_volume_24h": _to_float(t24.get("quoteVolume") or t24.get("baseVolume")),
                }
            )

        return records, errors

    def collect_once(self, *, ts_utc_ms: int | None = None) -> dict[str, Any]:
        """Collect 1 synchronized tick across all enabled markets and append to daily spool."""
        t0 = time.monotonic()
        snap_ms = ts_utc_ms if ts_utc_ms is not None else self._clock_ms()
        date_utc = _utc_date_from_ms(snap_ms)
        counts: dict[str, int] = {}
        errors: list[str] = []

        jobs: list[tuple[str, bool, Callable[[int], tuple[list[dict[str, Any]], list[str]]]]] = [
            ("options_chain", self.config.options.enabled, self.collect_options_chain),
            ("spot_1m", self.config.spot.enabled, self.collect_spot),
            ("futures_delivery_usdm", self.config.futures_usdm.enabled, lambda ms: self.collect_futures_venue("usdm", ms)),
            ("futures_delivery_coinm", self.config.futures_coinm.enabled, lambda ms: self.collect_futures_venue("coinm", ms)),
        ]

        for dataset, enabled, fn in jobs:
            if not enabled:
                continue
            try:
                rows, sub_errors = fn(snap_ms)
                written = self.spool.append_records(date_utc, dataset, rows)
                counts[dataset] = written
                errors.extend(sub_errors)
            except Exception as exc:  # noqa: BLE001
                counts[dataset] = 0
                errors.append(f"{dataset}: {exc}")

        elapsed_ms = round((time.monotonic() - t0) * 1000.0, 1)
        summary = {
            "collector_id": self.config.collector_id,
            "date_utc": date_utc,
            "ts_utc_ms": snap_ms,
            "snapshot_utc": _utc_iso_from_ms(snap_ms),
            "elapsed_ms": elapsed_ms,
            "rows_written": counts,
            "used_weight_1m": dict(self.http.last_used_weight),
            "error_count": len(errors),
            "errors": errors[:20],
        }
        self.spool.write_health(summary)
        return summary

    def finalize_completed_days(self, *, current_date_utc: str) -> dict[str, Any]:
        """Compact and optionally upload any spooled UTC day strictly earlier than `current_date_utc`."""
        report: dict[str, Any] = {"compacted": {}, "uploaded": {}, "pruned": [], "errors": []}
        for spooled_day in self.spool.list_spool_dates():
            if spooled_day >= current_date_utc:
                continue
            try:
                compacted = compact_day_to_parquet(self.config, base_dir=self.base_dir, date_utc=spooled_day)
                report["compacted"][spooled_day] = {k: v["manifest"] for k, v in compacted.items()}
            except Exception as exc:  # noqa: BLE001
                report["errors"].append(f"compact[{spooled_day}]: {exc}")

        if self.config.storage.upload_enabled:
            try:
                uploaded = upload_pending_days(
                    self.config,
                    base_dir=self.base_dir,
                    before_date_utc=current_date_utc,
                    runner=self.runner,
                )
                report["uploaded"].update(uploaded)
            except Exception as exc:  # noqa: BLE001
                report["errors"].append(f"upload_pending[{current_date_utc}]: {exc}")

            report["pruned"] = prune_uploaded_local_parquet(
                self.config,
                base_dir=self.base_dir,
                today_utc=date.fromisoformat(current_date_utc),
            )
        return report

    def run_forever(self, *, max_ticks: int | None = None) -> list[dict[str, Any]]:
        """Run UTC-aligned periodic collection loop with automatic midnight rollover & upload."""
        history: list[dict[str, Any]] = []
        interval = int(self.config.interval_seconds)
        offset = int(self.config.tick_offset_seconds)
        last_finalized_day = ""

        def _handle_sig(_signum: int, _frame: Any) -> None:
            self._stop_requested = True

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, _handle_sig)
            except ValueError:
                pass  # Not in main thread

        tick_idx = 0
        while not self._stop_requested:
            now_ms = self._clock_ms()
            current_day = _utc_date_from_ms(now_ms)
            if current_day != last_finalized_day:
                self.finalize_completed_days(current_date_utc=current_day)
                last_finalized_day = current_day

            summary = self.collect_once(ts_utc_ms=now_ms)
            history.append(summary)
            tick_idx += 1
            if max_ticks is not None and tick_idx >= max_ticks:
                break

            after_ms = self._clock_ms()
            after_sec = after_ms / 1000.0
            next_slot = (math.floor((after_sec - offset) / interval) + 1) * interval + offset
            sleep_sec = max(0.2, next_slot - after_sec)
            self._sleep(sleep_sec)

        return history
