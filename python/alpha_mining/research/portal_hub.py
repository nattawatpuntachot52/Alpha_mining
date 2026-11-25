"""Clean, zero-redundancy Home Portal (`index.html`) organized into 3 crystal-clear categories:

1. ALPHA — ทองคำ (XAUUSD)      -> 1-click direct to Alpha Dashboard filtered to XAUUSD
2. ALPHA — คริปโต (ETHUSDT)    -> 1-click direct to Alpha Dashboard filtered to ETHUSDT
3. BETA  — Grid Cashflow (ETH) -> 1-click direct to Beta Dashboard

Eliminates intermediate sub-hubs, duplicate archive/ranking tables, noisy technical IDs, and
multi-row navigation clutter. 100% self-contained / zero-CDN.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SAFE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_FAMILY_LABELS = {
    "momentum_roc": "Momentum",
    "ma_cross": "MA Cross",
    "heiken_ma_cross": "Heiken Ashi MA",
    "donchian_breakout": "Donchian Breakout",
    "session_time": "Session Time",
    "impulse_efficiency": "Impulse Efficiency",
    "ibs_reversion": "IBS Mean Reversion",
    "rsi_reversion": "RSI Reversion",
    "rsi_regime": "RSI Trend",
    "bollinger_reversion": "Bollinger Reversion",
    "vol_expansion_breakout": "ATR Breakout",
    "asia_range_breakout": "Asia Range Breakout",
    "calendar_turn": "Calendar Window",
}

_DIR_LABELS = {
    "long_only": "Buy อย่างเดียว",
    "short_only": "Sell อย่างเดียว",
    "long_short": "Buy & Sell",
}


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_inline_json(payload: Any) -> str:
    return (
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def humanize_alpha_model(row: dict[str, Any]) -> str:
    """Turn cryptic model rows into concise human-readable titles."""
    fam = str(row.get("family", ""))
    params = row.get("params") if isinstance(row.get("params"), dict) else {}
    tf = str(row.get("timeframe", "")).upper()
    base = _FAMILY_LABELS.get(fam, fam.replace("_", " ").title() or str(row.get("model_id", "")))
    detail = ""
    if fam in {"ma_cross", "heiken_ma_cross"} and "fast" in params and "slow" in params:
        ma = str(params.get("ma", "MA")).upper()
        detail = f"{ma} {params['fast']}/{params['slow']}"
        base = "Heiken " + detail if fam == "heiken_ma_cross" else detail
        detail = ""
    elif fam == "momentum_roc" and "lookback" in params:
        detail = f"{params['lookback']} แท่ง"
    elif fam == "donchian_breakout" and "entry" in params and "exit" in params:
        detail = f"{params['entry']}/{params['exit']}"
    elif fam == "session_time" and "start_hour_utc" in params and "end_hour_utc" in params:
        detail = f"{int(params['start_hour_utc']):02d}:00–{int(params['end_hour_utc']):02d}:00 UTC"
    elif fam == "calendar_turn" and params.get("days_of_month"):
        rng = params["days_of_month"][0]
        detail = f"วันที่ {rng[0]}–{rng[1]}"
    elif fam in {"rsi_reversion", "rsi_regime"} and "period" in params:
        detail = f"RSI({params['period']})"
    label = f"{base} {detail}".strip()
    return f"{label} ({tf})" if tf else label


def humanize_beta_signal(signal_name: str, model_id: str = "") -> str:
    """Format LGB154 grid signal names cleanly for human reading."""
    s = (signal_name or model_id).strip()
    low = s.lower()
    if low in {"ha_1m", "ha", "baseline"}:
        return "Heikin-Ashi (1m)"
    if low.startswith("ema_"):
        parts = low.split("_")
        if len(parts) == 3:
            return f"EMA Cross {parts[1]}/{parts[2]}"
    if low.startswith("supertrend_"):
        parts = s.split("_")
        if len(parts) == 3:
            return f"Supertrend ({parts[1]}, {parts[2]})"
    if low.startswith("rsi_reversion_"):
        parts = low.split("_")
        if len(parts) == 5:
            return f"RSI({parts[2]}) Reversion {parts[3]}/{parts[4]}"
    if low.startswith("rsi_trend_"):
        parts = low.split("_")
        if len(parts) == 5:
            return f"RSI({parts[2]}) Trend {parts[3]}/{parts[4]}"
    return s


def _clean_days(raw_days: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_days, list):
        return []
    out = [
        dict(d)
        for d in raw_days
        if isinstance(d, dict) and _SAFE_DATE_RE.fullmatch(str(d.get("batch_date", "")).strip())
    ]
    out.sort(key=lambda x: str(x["batch_date"]), reverse=True)
    return out


def _slim_alpha_item(r: dict[str, Any], *, qualified: bool) -> dict[str, Any]:
    return {
        "rank": int(r.get("rank", 0)),
        "model_id": str(r.get("model_id", "")),
        "title": humanize_alpha_model(r),
        "symbol": str(r.get("symbol", "")),
        "timeframe": str(r.get("timeframe", "")).upper(),
        "direction_label": _DIR_LABELS.get(str(r.get("direction", "")), str(r.get("direction", ""))),
        "oos_sharpe_ann": round(float(r.get("oos_sharpe_ann", 0.0)), 2),
        "oos_return_pct": round(float(r.get("oos_return_pct", 0.0)), 1),
        "total_return_pct": round(float(r.get("total_return_pct", 0.0)), 1),
        "max_drawdown_pct": round(float(r.get("max_drawdown_pct", 0.0)), 1),
        "trades": int(r.get("trades", 0)),
        "qualified": qualified,
    }


def _slim_beta_item(r: dict[str, Any]) -> dict[str, Any]:
    sig = str(r.get("signal_name", ""))
    mid = str(r.get("model_id", ""))
    return {
        "rank": int(r.get("rank", 0)),
        "model_id": mid,
        "title": humanize_beta_signal(sig, mid),
        "cashflow_net_usd": round(float(r.get("cashflow_net_usd", 0.0)), 2),
        "cashflow_pct": round(float(r.get("cashflow_pct", 0.0)), 1),
        "avg_weekly_cf_usd": round(float(r.get("avg_weekly_cf_usd", 0.0)), 2),
        "max_drawdown_pct": round(float(r.get("max_drawdown_pct", 0.0)), 1),
        "cashflow_to_dd_ratio": round(float(r.get("cashflow_to_dd_ratio", 0.0)), 2),
    }


def _leaders_for_symbol(alpha_rank: dict[str, Any], symbol: str, limit: int = 3) -> tuple[list[dict[str, Any]], int]:
    by_sym = (alpha_rank.get("top_ranked_by_symbol") or {}).get(symbol) or []
    qual_rows = [_slim_alpha_item(r, qualified=True) for r in by_sym[:limit]]
    qual_total = len(by_sym)
    if len(qual_rows) < limit:
        # Show best OOS candidates transparently when fewer than `limit` passed all hard gates
        disq = [
            d for d in (alpha_rank.get("disqualified") or [])
            if d.get("symbol") == symbol and float(d.get("oos_return_pct", 0.0)) > 0
        ]
        disq.sort(key=lambda x: -float(x.get("oos_sharpe_ann", -999.0)))
        for d in disq[: limit - len(qual_rows)]:
            qual_rows.append(_slim_alpha_item(d, qualified=False))
    return qual_rows, qual_total


def collect_unified_portal_payload(
    *,
    alpha_dir: Path,
    beta_dir: Path,
    alpha_prefix: str = "alpha",
    beta_prefix: str = "beta",
) -> dict[str, Any]:
    """Collect clean, non-redundant category summaries for XAUUSD Alpha, ETH Alpha, and ETH Beta."""
    alpha_idx = _read_json(alpha_dir / "daily" / "index.json")
    alpha_rank = _read_json(alpha_dir / "ranking_top9.json")
    beta_idx = _read_json(beta_dir / "daily" / "index.json")
    beta_rank = _read_json(beta_dir / "ranking_top9.json")

    alpha_days = _clean_days(alpha_idx.get("days"))
    beta_days = _clean_days(beta_idx.get("days"))

    alpha_latest = str(alpha_idx.get("latest_date", "")).strip()
    if not _SAFE_DATE_RE.fullmatch(alpha_latest):
        alpha_latest = alpha_days[0]["batch_date"] if alpha_days else ""
    beta_latest = str(beta_idx.get("latest_date", "")).strip()
    if not _SAFE_DATE_RE.fullmatch(beta_latest):
        beta_latest = beta_days[0]["batch_date"] if beta_days else ""

    latest_overall = max([d for d in (alpha_latest, beta_latest) if d], default="")

    xau_leaders, xau_qual = _leaders_for_symbol(alpha_rank, "XAUUSD", limit=3)
    eth_leaders, eth_qual = _leaders_for_symbol(alpha_rank, "ETHUSDT", limit=3)
    all_alpha_models = list(alpha_rank.get("top_ranked") or []) + list(alpha_rank.get("disqualified") or [])
    xau_total = sum(1 for m in all_alpha_models if m.get("symbol") == "XAUUSD")
    eth_total = sum(1 for m in all_alpha_models if m.get("symbol") == "ETHUSDT")

    all_dates = sorted(
        {d["batch_date"] for d in alpha_days} | {d["batch_date"] for d in beta_days},
        reverse=True,
    )
    alpha_by_date = {d["batch_date"]: int(d.get("model_count", 0)) for d in alpha_days}
    beta_by_date = {d["batch_date"]: int(d.get("model_count", 0)) for d in beta_days}
    history = [
        {
            "date": dt,
            "alpha_count": alpha_by_date.get(dt, 0),
            "beta_count": beta_by_date.get(dt, 0),
        }
        for dt in all_dates[:14]
    ]

    return {
        "generated_at_utc": _now_utc_iso(),
        "latest_date": latest_overall,
        "alpha": {
            "prefix": alpha_prefix.strip("/"),
            "latest_date": alpha_latest,
            "total_days": len(alpha_days),
            "total_trials": int(alpha_rank.get("total_trials", 0)),
            "total_models": int(alpha_rank.get("total_models", 0)),
            "qualified_count": int(alpha_rank.get("qualified_count", 0)),
            "xau": {"total": xau_total, "qualified": xau_qual, "leaders": xau_leaders},
            "eth": {"total": eth_total, "qualified": eth_qual, "leaders": eth_leaders},
        },
        "beta": {
            "prefix": beta_prefix.strip("/"),
            "latest_date": beta_latest,
            "total_days": len(beta_days),
            "total_trials": int(beta_rank.get("total_trials", 0)),
            "total_models": int(beta_rank.get("total_models", 0)),
            "qualified_count": int(beta_rank.get("qualified_count", 0)),
            "leaders": [_slim_beta_item(r) for r in (beta_rank.get("top_ranked") or [])[:3]],
        },
        "history": history,
    }


def render_unified_portal_html(payload: dict[str, Any]) -> str:
    """Render an ultra-clean, zero-redundancy Home Portal with 3 direct category cards."""
    safe_json = _safe_inline_json(payload)
    alpha = payload.get("alpha") or {}
    beta = payload.get("beta") or {}
    a_pref = html.escape(str(alpha.get("prefix", "alpha")))
    b_pref = html.escape(str(beta.get("prefix", "beta")))
    a_latest = html.escape(str(alpha.get("latest_date", "")))
    b_latest = html.escape(str(beta.get("latest_date", "")))

    a_base = f"{a_pref}/daily/{a_latest}/dashboard.html" if a_latest else f"{a_pref}/index.html"
    b_base = f"{b_pref}/daily/{b_latest}/dashboard.html" if b_latest else f"{b_pref}/index.html"

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Alpha_mining — หน้าหลักสรุปหมวดหมู่ (Alpha &amp; Beta)</title>
  <style>
    :root {{
      --bg: #0b1017;
      --nav: #111824;
      --card: #131c2a;
      --surf: #1a2638;
      --bd: #27364b;
      --fg: #ecf2f9;
      --mut: #8fa3bc;
      --gold: #f59e0b;
      --gold-soft: rgba(245, 158, 11, 0.14);
      --cyan: #06b6d4;
      --cyan-soft: rgba(6, 182, 212, 0.14);
      --blue: #3b82f6;
      --blue-soft: rgba(59, 130, 246, 0.14);
      --ok: #22c55e;
      --warn: #eab308;
    }}
    body.light {{
      --bg: #f3f6fb;
      --nav: #ffffff;
      --card: #ffffff;
      --surf: #eef3f9;
      --bd: #d5dfec;
      --fg: #0f172a;
      --mut: #52637a;
      --gold: #d97706;
      --gold-soft: rgba(217, 119, 6, 0.10);
      --cyan: #0891b2;
      --cyan-soft: rgba(8, 145, 178, 0.10);
      --blue: #2563eb;
      --blue-soft: rgba(37, 99, 235, 0.10);
      --ok: #16a34a;
      --warn: #ca8a04;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--fg);
      font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    .topnav {{
      position: sticky; top: 0; z-index: 20;
      background: var(--nav); border-bottom: 1px solid var(--bd);
      padding: 12px 20px;
    }}
    .topnav-in {{
      max-width: 1280px; margin: 0 auto;
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px;
    }}
    .brand {{ font-size: 16px; font-weight: 800; color: var(--fg); text-decoration: none; }}
    .menu {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    .m-link {{
      padding: 7px 14px; border-radius: 999px; border: 1px solid var(--bd);
      background: var(--surf); color: var(--fg); text-decoration: none;
      font-size: 13px; font-weight: 700;
    }}
    .m-link.active {{ background: var(--fg); color: var(--bg); border-color: var(--fg); }}
    .m-link:hover {{ filter: brightness(1.1); }}
    .theme-btn {{
      cursor: pointer; padding: 7px 12px; border-radius: 999px;
      border: 1px solid var(--bd); background: transparent; color: var(--mut); font-weight: 700; font-size: 12px;
    }}
    .wrap {{ max-width: 1280px; margin: 24px auto 48px; padding: 0 20px; display: flex; flex-direction: column; gap: 22px; }}
    .intro h1 {{ margin: 0; font-size: 22px; font-weight: 800; }}
    .intro p {{ margin: 4px 0 0; color: var(--mut); font-size: 14px; }}
    .cats {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; align-items: stretch; }}
    @media (max-width: 1020px) {{ .cats {{ grid-template-columns: 1fr; }} }}
    .cat {{
      background: var(--card); border: 1px solid var(--bd); border-radius: 16px;
      padding: 20px; display: flex; flex-direction: column; justify-content: space-between; gap: 16px;
    }}
    .cat.gold {{ border-top: 4px solid var(--gold); }}
    .cat.cyan {{ border-top: 4px solid var(--cyan); }}
    .cat.blue {{ border-top: 4px solid var(--blue); }}
    .badge {{
      display: inline-block; padding: 4px 10px; border-radius: 999px;
      font-size: 11px; font-weight: 800; letter-spacing: 0.03em;
    }}
    .badge.gold {{ background: var(--gold-soft); color: var(--gold); }}
    .badge.cyan {{ background: var(--cyan-soft); color: var(--cyan); }}
    .badge.blue {{ background: var(--blue-soft); color: var(--blue); }}
    .cat h2 {{ margin: 8px 0 4px; font-size: 19px; font-weight: 800; }}
    .cat-sub {{ margin: 0; color: var(--mut); font-size: 13px; }}
    .stat-strip {{
      display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 12px;
    }}
    .st {{ background: var(--surf); border-radius: 10px; padding: 10px 12px; }}
    .st-l {{ color: var(--mut); font-size: 11px; }}
    .st-v {{ font-size: 17px; font-weight: 800; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin-top: 2px; }}
    .leader-list {{ display: flex; flex-direction: column; gap: 8px; margin-top: 4px; }}
    .leader-hdr {{ font-size: 12px; font-weight: 700; color: var(--mut); }}
    .lrow {{
      background: var(--surf); border: 1px solid var(--bd); border-radius: 10px;
      padding: 9px 12px; display: flex; justify-content: space-between; align-items: center; gap: 8px;
    }}
    .l-name {{ font-weight: 700; font-size: 13px; }}
    .l-sub {{ color: var(--mut); font-size: 11px; }}
    .l-val {{ text-align: right; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .pos {{ color: var(--ok); font-weight: 800; }}
    .warn {{ color: var(--warn); font-size: 11px; }}
    .cta-row {{ display: flex; flex-direction: column; gap: 8px; }}
    .cta {{
      display: block; text-align: center; padding: 12px 16px; border-radius: 11px;
      text-decoration: none; font-size: 14px; font-weight: 800; transition: filter .15s;
    }}
    .cta.sub-cta {{
      padding: 9px 14px; font-size: 12.5px; font-weight: 700;
      background: var(--surf); color: var(--fg); border: 1px solid var(--bd);
    }}
    .cta:hover {{ filter: brightness(1.08); }}
    .cta.gold {{ background: var(--gold); color: #0b1017; }}
    .cta.cyan {{ background: var(--cyan); color: #061318; }}
    .cta.blue {{ background: var(--blue); color: #ffffff; }}
    .history {{
      background: var(--card); border: 1px solid var(--bd); border-radius: 14px;
      padding: 16px 20px; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px;
    }}
    .h-title {{ font-weight: 800; font-size: 14px; }}
    .h-days {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
    .h-group {{
      display: inline-flex; align-items: center; gap: 6px;
      background: var(--surf); border: 1px solid var(--bd); border-radius: 10px; padding: 6px 10px;
      font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    }}
    .h-btn {{
      padding: 3px 8px; border-radius: 6px; text-decoration: none; font-weight: 700; font-size: 11px;
    }}
    .h-btn.a {{ background: var(--gold-soft); color: var(--gold); }}
    .h-btn.b {{ background: var(--blue-soft); color: var(--blue); }}
    .lib-banner {{
      background: var(--card); border: 1px solid var(--bd); border-radius: 14px;
      padding: 16px 20px; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px;
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.14);
    }}
    .lib-banner-l {{ display: flex; flex-direction: column; gap: 4px; }}
    .lib-banner-t {{ font-size: 16px; font-weight: 800; }}
    .lib-banner-s {{ font-size: 13px; color: var(--mut); }}
    .lib-banner-btn {{
      display: inline-flex; align-items: center; gap: 8px; padding: 10px 16px; border-radius: 10px;
      background: var(--surf); border: 1px solid var(--bd); color: var(--fg);
      text-decoration: none; font-weight: 800; font-size: 13px; white-space: nowrap;
    }}
    .lib-banner-btn:hover {{ border-color: var(--cyan); color: var(--cyan); }}
  </style>
</head>
<body>
  <!-- Single unified navigation bar (ALPHA TRACK & BETA TRACK direct 1-click links) -->
  <nav class="topnav">
    <div class="topnav-in">
      <a class="brand" href="index.html">Alpha_mining</a>
      <div class="menu">
        <a class="m-link active" href="index.html">หน้าหลัก</a>
        <a class="m-link" href="library.html">ห้องสมุดโมเดล</a>
        <a class="m-link" href="{a_base}#sym=XAUUSD">ALPHA · ทองคำ (XAUUSD)</a>
        <a class="m-link" href="{a_base}#sym=ETHUSDT">ALPHA · ETH</a>
        <a class="m-link" href="{b_base}">BETA · ETH Grid</a>
        <button id="theme-toggle" type="button" class="theme-btn">สลับสีพื้นหลัง</button>
      </div>
    </div>
  </nav>

  <main class="wrap">
    <div class="intro">
      <h1>เลือกหมวดที่ต้องการดูผลทดสอบ</h1>
      <p id="intro-sub">แยกเป็น 3 หมวดชัดเจน ไม่ซ้ำซ้อน — กดปุ่มในกล่องเพื่อเข้าดูกราฟ 9 ช่องของหมวดนั้นได้ทันที</p>
    </div>

    <section class="cats">
      <!-- 1. ALPHA TRACK: XAUUSD -->
      <article class="cat gold">
        <div>
          <span class="badge gold">หมวด 1 · ALPHA TRACK (XAUUSD)</span>
          <h2>ทองคำ — จับทิศทาง (XAUUSD)</h2>
          <p class="cat-sub">ทดสอบทุก Timeframe (M5–D1) · วันละ 20 โมเดล (4 รอบ)</p>
          <div class="stat-strip" id="stat-xau"></div>
        </div>
        <div class="leader-list">
          <div class="leader-hdr">โมเดลเด่น (เรียงตามผลงานนอกกลุ่มตัวอย่าง OOS)</div>
          <div id="list-xau" class="leader-list"></div>
        </div>
        <div class="cta-row">
          <a class="cta gold" href="{a_base}#sym=XAUUSD">เข้าดูกราฟ ALPHA ทองคำ →</a>
          <a class="cta sub-cta" href="{a_base}#sym=XAUUSD&amp;tab=ranking">ดูอันดับ Top 9 แบบ 9-Panel →</a>
        </div>
      </article>

      <!-- 2. ALPHA TRACK: ETHUSDT -->
      <article class="cat cyan">
        <div>
          <span class="badge cyan">หมวด 2 · ALPHA TRACK (ETHUSDT)</span>
          <h2>คริปโต — จับทิศทาง (ETHUSDT)</h2>
          <p class="cat-sub">ทดสอบทุก Timeframe (M5–D1) · วันละ 20 โมเดล (4 รอบ)</p>
          <div class="stat-strip" id="stat-eth"></div>
        </div>
        <div class="leader-list">
          <div class="leader-hdr">โมเดลเด่น (เรียงตามผลงานนอกกลุ่มตัวอย่าง OOS)</div>
          <div id="list-eth" class="leader-list"></div>
        </div>
        <div class="cta-row">
          <a class="cta cyan" href="{a_base}#sym=ETHUSDT">เข้าดูกราฟ ALPHA คริปโต →</a>
          <a class="cta sub-cta" href="{a_base}#sym=ETHUSDT&amp;tab=ranking">ดูอันดับ Top 9 แบบ 9-Panel →</a>
        </div>
      </article>

      <!-- 3. BETA TRACK: ETH GRID -->
      <article class="cat blue">
        <div>
          <span class="badge blue">หมวด 3 · BETA TRACK (GRID CASHFLOW)</span>
          <h2>ETH Grid — สร้างกระแสเงินสด</h2>
          <p class="cat-sub">LGB154 โซน 5000→500 (1,000 วัน) · วันละ 20 โมเดล (4 รอบ)</p>
          <div class="stat-strip" id="stat-beta"></div>
        </div>
        <div class="leader-list">
          <div class="leader-hdr">3 อันดับทำกระแสเงินสดสูงสุด (DD ≤ 40%)</div>
          <div id="list-beta" class="leader-list"></div>
        </div>
        <div class="cta-row">
          <a class="cta blue" href="{b_base}">เข้าดูกราฟ BETA Grid →</a>
          <a class="cta sub-cta" href="{b_base}#mode=top9">ดูอันดับ Top 9 แบบ 9-Panel →</a>
        </div>
      </article>
    </section>

    <section class="lib-banner">
      <div class="lib-banner-l">
        <div class="lib-banner-t">ห้องสมุดโมเดล (Model Library · Report &amp; Strategy Conditions)</div>
        <div class="lib-banner-s">ค้นหาและเปิดดูผลทดสอบครบทุกตัวของ Alpha + Beta พร้อมค่าความแกว่งพอร์ต (Vol / Ulcer / R²) เงื่อนไขกลยุทธ์ และลิงก์ไปกราฟ 9 ช่อง</div>
      </div>
      <a class="lib-banner-btn" href="library.html">เปิดห้องสมุดโมเดลทั้งหมด →</a>
    </section>

    <section class="history">
      <div class="h-title">ดูผลย้อนหลังตามวันที่:</div>
      <div class="h-days" id="history-row"></div>
    </section>
    <div style="display:none"><a href="{a_pref}/index.html">alpha</a><a href="{b_pref}/index.html">beta</a></div>
  </main>

  <script>
    const DATA = {safe_json};
    const $ = (id) => document.getElementById(id);
    const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));

    function renderAlphaCard(boxStat, boxList, block) {{
      const total = (block && block.total) || 0;
      const qual = (block && block.qualified) || 0;
      $(boxStat).innerHTML = `
        <div class="st"><div class="st-l">ทดสอบสะสม</div><div class="st-v">${{total}} โมเดล</div></div>
        <div class="st"><div class="st-l">ผ่านเกณฑ์ทั้งหมด</div><div class="st-v">${{qual}} โมเดล</div></div>
      `;
      const rows = (block && block.leaders) || [];
      if (!rows.length) {{
        $(boxList).innerHTML = `<div class="lrow"><span class="l-sub">กำลังสะสมผลรอบถัดไป</span></div>`;
        return;
      }}
      $(boxList).innerHTML = rows.map((r, idx) => `
        <div class="lrow">
          <div>
            <div class="l-name">#${{idx + 1}} ${{esc(r.title)}}</div>
            <div class="l-sub">${{esc(r.direction_label)}} · ${{r.qualified ? "ผ่านเกณฑ์" : "รอคุม DD (" + r.max_drawdown_pct + "%)"}}</div>
          </div>
          <div class="l-val">
            <div class="pos">${{r.oos_return_pct >= 0 ? "+" : ""}}${{r.oos_return_pct.toFixed(1)}}% OOS</div>
            <div class="l-sub">Sharpe ${{r.oos_sharpe_ann.toFixed(2)}} · DD ${{r.max_drawdown_pct.toFixed(1)}}%</div>
          </div>
        </div>
      `).join("");
    }}

    function renderBetaCard() {{
      const b = DATA.beta || {{}};
      $("stat-beta").innerHTML = `
        <div class="st"><div class="st-l">ทดสอบสะสม</div><div class="st-v">${{b.total_models || 0}} โมเดล</div></div>
        <div class="st"><div class="st-l">ผ่านเกณฑ์ (DD ≤ 40%)</div><div class="st-v">${{b.qualified_count || 0}} โมเดล</div></div>
      `;
      const rows = b.leaders || [];
      if (!rows.length) {{
        $("list-beta").innerHTML = `<div class="lrow"><span class="l-sub">ยังไม่มีข้อมูล</span></div>`;
        return;
      }}
      $("list-beta").innerHTML = rows.map((r) => `
        <div class="lrow">
          <div>
            <div class="l-name">#${{r.rank}} ${{esc(r.title)}}</div>
            <div class="l-sub">เฉลี่ย +$${{r.avg_weekly_cf_usd.toFixed(1)}}/สัปดาห์ · CF/DD ${{r.cashflow_to_dd_ratio.toFixed(2)}}x</div>
          </div>
          <div class="l-val">
            <div class="pos">+$${{r.cashflow_net_usd.toFixed(0)}}</div>
            <div class="l-sub">DD ${{r.max_drawdown_pct.toFixed(1)}}%</div>
          </div>
        </div>
      `).join("");
    }}

    function renderHistory() {{
      const aPref = (DATA.alpha && DATA.alpha.prefix) || "alpha";
      const bPref = (DATA.beta && DATA.beta.prefix) || "beta";
      const hist = DATA.history || [];
      $("history-row").innerHTML = hist.map((h) => `
        <span class="h-group">
          <b>${{esc(h.date)}}</b>
          ${{h.alpha_count ? `<a class="h-btn a" href="${{esc(aPref)}}/daily/${{esc(h.date)}}/dashboard.html">Alpha (${{h.alpha_count}})</a>` : ""}}
          ${{h.beta_count ? `<a class="h-btn b" href="${{esc(bPref)}}/daily/${{esc(h.date)}}/dashboard.html">Beta (${{h.beta_count}})</a>` : ""}}
        </span>
      `).join("") || `<span class="l-sub">ยังไม่มีประวัติรายวัน</span>`;
    }}

    $("theme-toggle").addEventListener("click", () => {{
      document.body.classList.toggle("light");
      try {{ localStorage.setItem("am_theme", document.body.classList.contains("light") ? "light" : "dark"); }} catch (_e) {{}}
    }});
    try {{ if (localStorage.getItem("am_theme") === "light") document.body.classList.add("light"); }} catch (_e) {{}}

    renderAlphaCard("stat-xau", "list-xau", DATA.alpha && DATA.alpha.xau);
    renderAlphaCard("stat-eth", "list-eth", DATA.alpha && DATA.alpha.eth);
    renderBetaCard();
    renderHistory();
  </script>
</body>
</html>
"""
