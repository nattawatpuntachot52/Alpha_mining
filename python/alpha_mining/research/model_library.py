"""Model Library (`library.html`) — searchable archive of ALL mined Alpha & Beta models
with full backtest report metrics, stability measurements (Vol / Ulcer / R²),
human-readable + raw strategy conditions, mini equity curve preview, and direct report links.

100% self-contained / zero-CDN.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .portal_hub import humanize_alpha_model, humanize_beta_signal
from .stability import stability_from_alpha_series, stability_from_beta_series

_SAFE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_DIR_LABELS = {
    "long_only": "Buy อย่างเดียว (Long Only)",
    "short_only": "Sell อย่างเดียว (Short Only)",
    "long_short": "Buy & Sell (Long/Short)",
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
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _downsample(vals: list[float], max_pts: int = 90) -> list[float]:
    n = len(vals)
    if n <= max_pts:
        return [round(float(v), 2) for v in vals]
    step = (n - 1) / (max_pts - 1)
    return [round(float(vals[min(n - 1, round(i * step))]), 2) for i in range(max_pts)]


def _alpha_equity_spark(series_doc: dict[str, Any]) -> list[float]:
    bps = series_doc.get("strategy_bp")
    if not isinstance(bps, list) or not bps:
        return []
    eq = 1.0
    pts: list[float] = []
    for bp in bps:
        eq *= max(1e-6, 1.0 + float(bp) / 1e4)
        pts.append((eq - 1.0) * 100.0)
    return _downsample(pts, 90)


def _beta_equity_spark(series_doc: dict[str, Any]) -> list[float]:
    eq = series_doc.get("equity")
    if not isinstance(eq, list) or not eq:
        return []
    return _downsample([float(v) for v in eq], 90)


def _describe_alpha_conditions(spec: dict[str, Any], metrics: dict[str, Any]) -> list[str]:
    sym = str(spec.get("symbol") or metrics.get("symbol") or "")
    tf = str(spec.get("timeframe") or metrics.get("timeframe") or "").upper()
    fam = str(spec.get("family") or metrics.get("family") or "")
    direction = _DIR_LABELS.get(str(spec.get("direction") or metrics.get("direction") or ""), str(spec.get("direction") or ""))
    params = spec.get("params") if isinstance(spec.get("params"), dict) else {}
    param_str = ", ".join(f"{k}={v}" for k, v in params.items()) if params else "ค่ามาตรฐาน"
    sl = spec.get("sl_pct")
    tp = spec.get("tp_pct")
    ts = spec.get("time_stop_bars")
    risk_parts = []
    if sl:
        risk_parts.append(f"SL {sl}%")
    if tp:
        risk_parts.append(f"TP {tp}%")
    if ts:
        risk_parts.append(f"Time-Stop {ts} แท่ง")
    risk_txt = " · ".join(risk_parts) if risk_parts else "ออกตามสัญญาณกลับทิศ (Signal Exit)"
    cost = "2 bps/ขา (PAXG proxy)" if sym == "XAUUSD" else "5 bps/ขา (Binance USD-M Perp)"
    oos_pct = int(round(float(metrics.get("oos_fraction", 0.3)) * 100))
    return [
        f"สินทรัพย์ / Timeframe: {sym} · {tf} · {direction}",
        f"ตระกูลสัญญาณ: {fam} ({param_str})",
        f"การบริหารความเสี่ยง: {risk_txt}",
        f"สมมติฐานการทำงาน: Causal ปิดแท่งตัดสินใจ → เข้าที่ราคาเปิดแท่งถัดไป · ค่าธรรมเนียม {cost} · แบ่ง OOS {oos_pct}% ล่าสุด",
    ]


def _describe_beta_conditions(spec: dict[str, Any], metrics: dict[str, Any]) -> list[str]:
    sig = str(spec.get("signal_spec") or metrics.get("signal_name") or "")
    cfg = spec.get("config_snapshot") if isinstance(spec.get("config_snapshot"), dict) else {}
    high = cfg.get("high") or metrics.get("zone_high") or 5000
    low = cfg.get("low") or metrics.get("zone_low") or 500
    spacing = cfg.get("spacing_pct") or "0.20"
    max_pos = cfg.get("max_position_quantity") or "2.0"
    max_not = cfg.get("max_notional_usdt") or "10000"
    init_cap = cfg.get("initial_capital") or metrics.get("initial_capital") or 10000
    fill = cfg.get("fill_mode") or "strict_cross"
    rec = cfg.get("recovery_mode") or "partial_only"
    return [
        f"ระบบกริด: LGB154 ETHUSDT (1m) · โซนราคา {high} → {low} · ระยะห่างกริด {spacing}%",
        f"สัญญาณตัวกรองเข้า/หยุด: {sig} ({humanize_beta_signal(sig)})",
        f"เพดานความเสี่ยง: ทุนเริ่มต้น ${init_cap} · Max Position {max_pos} ETH · Max Notional ${max_not}",
        f"เงื่อนไขการแมตช์คำสั่ง: fill_mode={fill} · recovery_mode={rec} · รวม Funding 8h และค่าธรรมเนียมแล้ว",
    ]


def collect_model_library_payload(
    *,
    alpha_dir: Path,
    beta_dir: Path,
    alpha_prefix: str = "alpha",
    beta_prefix: str = "beta",
) -> dict[str, Any]:
    """Scan all isolated Alpha & Beta model folders and assemble the complete Library catalog."""
    a_pref = alpha_prefix.strip("/")
    b_pref = beta_prefix.strip("/")
    alpha_idx = _read_json(alpha_dir / "daily" / "index.json")
    beta_idx = _read_json(beta_dir / "daily" / "index.json")
    alpha_latest = str(alpha_idx.get("latest_date", "")).strip()
    beta_latest = str(beta_idx.get("latest_date", "")).strip()

    items: list[dict[str, Any]] = []

    # 1. Alpha models
    alpha_models_dir = alpha_dir / "models"
    if alpha_models_dir.is_dir():
        for mdir in sorted(alpha_models_dir.iterdir()):
            if not mdir.is_dir():
                continue
            metrics = _read_json(mdir / "latest_metrics.json")
            if not metrics:
                continue
            spec = _read_json(mdir / "spec.json")
            series = _read_json(mdir / "latest_series.json")
            stab = stability_from_alpha_series(series)
            bdate = str(metrics.get("batch_date", "")).strip()
            safe_bdate = bdate if _SAFE_DATE_RE.fullmatch(bdate) else alpha_latest
            sym = str(metrics.get("symbol") or spec.get("symbol") or "XAUUSD").upper()
            mid = str(metrics.get("model_id") or mdir.name)
            row_for_title = dict(metrics)
            if "params" not in row_for_title and isinstance(spec.get("params"), dict):
                row_for_title["params"] = spec["params"]
            items.append(
                {
                    "track": "alpha",
                    "category": f"ALPHA_{sym}",
                    "model_id": mid,
                    "title": humanize_alpha_model(row_for_title),
                    "symbol": sym,
                    "timeframe": str(metrics.get("timeframe") or spec.get("timeframe") or "").upper(),
                    "direction": str(metrics.get("direction") or spec.get("direction") or ""),
                    "family": str(metrics.get("family") or spec.get("family") or ""),
                    "batch_date": safe_bdate,
                    "trial_number": int(metrics.get("trial_number") or 0),
                    "hypothesis": str(spec.get("hypothesis") or metrics.get("hypothesis") or ""),
                    "conditions": _describe_alpha_conditions(spec, metrics),
                    "spec": spec,
                    "reuse_cmd": f"python3 scripts/alpha_mining.py show {mid}",
                    "dashboard_href": f"{a_pref}/daily/{safe_bdate}/dashboard.html#sym={sym}" if safe_bdate else f"{a_pref}/index.html",
                    "top9_href": f"{a_pref}/daily/{alpha_latest or safe_bdate}/dashboard.html#sym={sym}&tab=ranking" if (alpha_latest or safe_bdate) else f"{a_pref}/index.html",
                    "report_href": f"{a_pref}/daily/{safe_bdate}/daily_summary.md" if safe_bdate else "",
                    "spark": _alpha_equity_spark(series),
                    # Normalized comparison metrics
                    "primary_return_pct": round(float(metrics.get("oos_return_pct", 0.0)), 2),
                    "total_return_pct": round(float(metrics.get("total_return_pct", 0.0)), 2),
                    "cagr_pct": round(float(metrics.get("cagr_pct", 0.0)), 2),
                    "oos_sharpe_ann": round(float(metrics.get("oos_sharpe_ann", 0.0)), 2),
                    "is_sharpe_ann": round(float(metrics.get("is_sharpe_ann", 0.0)), 2),
                    "max_drawdown_pct": round(float(metrics.get("max_drawdown_pct", 0.0)), 2),
                    "ann_vol_pct": stab["ann_vol_pct"],
                    "ulcer_index_pct": stab["ulcer_index_pct"],
                    "equity_r2": stab["equity_r2"],
                    "trades": int(metrics.get("trades", 0)),
                    "win_rate_pct": round(float(metrics.get("win_rate_pct", 0.0)), 1),
                    "profit_factor": round(float(metrics.get("profit_factor", 0.0)), 2),
                    "exposure_pct": round(float(metrics.get("exposure_pct", 0.0)), 1),
                    "beta": round(float(metrics.get("beta_to_underlying", 0.0)), 2),
                    "corr": round(float(metrics.get("corr_to_underlying", 0.0)), 2),
                    "would_liquidate": False,
                    "cashflow_net_usd": 0.0,
                    "avg_weekly_cf_usd": 0.0,
                    "cashflow_to_dd_ratio": 0.0,
                }
            )

    # 2. Beta models
    beta_models_dir = beta_dir / "models"
    if beta_models_dir.is_dir():
        for mdir in sorted(beta_models_dir.iterdir()):
            if not mdir.is_dir():
                continue
            metrics = _read_json(mdir / "latest_metrics.json")
            if not metrics:
                continue
            spec = _read_json(mdir / "spec.json")
            series = _read_json(mdir / "latest_series.json")
            stab = stability_from_beta_series(series)
            bdate = str(metrics.get("batch_date", "")).strip()
            safe_bdate = bdate if _SAFE_DATE_RE.fullmatch(bdate) else beta_latest
            mid = str(metrics.get("model_id") or mdir.name)
            sig = str(metrics.get("signal_name") or spec.get("signal_spec") or "")
            items.append(
                {
                    "track": "beta",
                    "category": "BETA_ETH_GRID",
                    "model_id": mid,
                    "title": humanize_beta_signal(sig, mid),
                    "symbol": str(metrics.get("symbol") or "ETHUSDT").upper(),
                    "timeframe": "1M",
                    "direction": "Grid Cashflow",
                    "family": sig,
                    "batch_date": safe_bdate,
                    "trial_number": int(metrics.get("trial_number") or 0),
                    "hypothesis": str(spec.get("hypothesis") or metrics.get("hypothesis") or ""),
                    "conditions": _describe_beta_conditions(spec, metrics),
                    "spec": spec,
                    "reuse_cmd": f"python3 scripts/beta_mining.py show {mid}",
                    "dashboard_href": f"{b_pref}/daily/{safe_bdate}/dashboard.html" if safe_bdate else f"{b_pref}/index.html",
                    "top9_href": f"{b_pref}/daily/{beta_latest or safe_bdate}/dashboard.html#mode=top9" if (beta_latest or safe_bdate) else f"{b_pref}/index.html",
                    "report_href": f"{b_pref}/daily/{safe_bdate}/daily_summary.md" if safe_bdate else "",
                    "spark": _beta_equity_spark(series),
                    "primary_return_pct": round(float(metrics.get("cashflow_pct", 0.0)), 2),
                    "total_return_pct": round(float(metrics.get("mtm_return_pct", 0.0)), 2),
                    "cagr_pct": 0.0,
                    "oos_sharpe_ann": 0.0,
                    "is_sharpe_ann": 0.0,
                    "max_drawdown_pct": round(float(metrics.get("max_drawdown_pct", 0.0)), 2),
                    "ann_vol_pct": stab["ann_vol_pct"],
                    "ulcer_index_pct": stab["ulcer_index_pct"],
                    "equity_r2": stab["equity_r2"],
                    "trades": int(metrics.get("closed_trades_count", 0)),
                    "win_rate_pct": round(float(metrics.get("win_rate_pct", 0.0)), 1),
                    "profit_factor": 0.0,
                    "exposure_pct": round(float(metrics.get("max_utilization_pct", 0.0)), 1),
                    "beta": round(float(metrics.get("beta_to_eth", 0.0)), 2),
                    "corr": round(float(metrics.get("corr_to_eth", 0.0)), 2),
                    "would_liquidate": bool(metrics.get("would_liquidate", False)),
                    "cashflow_net_usd": round(float(metrics.get("cashflow_net_usd", 0.0)), 2),
                    "avg_weekly_cf_usd": round(float(metrics.get("avg_weekly_cf_usd", 0.0)), 2),
                    "cashflow_to_dd_ratio": round(float(metrics.get("cashflow_to_dd_ratio", 0.0)), 2),
                    "crash_dd_pct": round(float((metrics.get("crash_stress") or {}).get("max_drawdown_pct", 0.0)), 2)
                    if isinstance(metrics.get("crash_stress"), dict)
                    else None,
                    "fees_paid": round(float(metrics.get("total_fees_paid", 0.0)), 2),
                    "funding_pnl": round(float(metrics.get("total_funding_pnl", 0.0)), 2),
                }
            )

    return {
        "generated_at_utc": _now_utc_iso(),
        "alpha_prefix": a_pref,
        "beta_prefix": b_pref,
        "alpha_latest": alpha_latest,
        "beta_latest": beta_latest,
        "total_models": len(items),
        "alpha_count": sum(1 for x in items if x["track"] == "alpha"),
        "beta_count": sum(1 for x in items if x["track"] == "beta"),
        "models": items,
    }


def render_model_library_html(payload: dict[str, Any]) -> str:
    """Render self-contained offline Model Library (`library.html`) with reports, stability gates & conditions."""
    safe_json = _safe_inline_json(payload)
    a_pref = html.escape(str(payload.get("alpha_prefix", "alpha")))
    b_pref = html.escape(str(payload.get("beta_prefix", "beta")))
    a_latest = html.escape(str(payload.get("alpha_latest", "")))
    b_latest = html.escape(str(payload.get("beta_latest", "")))
    a_base = f"{a_pref}/daily/{a_latest}/dashboard.html" if a_latest else f"{a_pref}/index.html"
    b_base = f"{b_pref}/daily/{b_latest}/dashboard.html" if b_latest else f"{b_pref}/index.html"

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Alpha_mining — ห้องสมุดโมเดล (Model Library · Reports &amp; Conditions)</title>
  <style>
    :root {{
      --bg: #0b1017; --nav: #111824; --card: #131c2a; --surf: #1a2638;
      --bd: #27364b; --fg: #ecf2f9; --mut: #8fa3bc;
      --gold: #f59e0b; --gold-soft: rgba(245, 158, 11, 0.14);
      --cyan: #06b6d4; --cyan-soft: rgba(6, 182, 212, 0.14);
      --blue: #3b82f6; --blue-soft: rgba(59, 130, 246, 0.14);
      --ok: #22c55e; --ok-soft: rgba(34, 197, 94, 0.14);
      --err: #ef4444; --err-soft: rgba(239, 68, 68, 0.14);
    }}
    body.light {{
      --bg: #f3f6fb; --nav: #ffffff; --card: #ffffff; --surf: #eef3f9;
      --bd: #d5dfec; --fg: #0f172a; --mut: #52637a;
      --gold: #d97706; --cyan: #0891b2; --blue: #2563eb;
      --ok: #16a34a; --err: #dc2626;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--fg); font: 13.5px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    .topnav {{ position: sticky; top: 0; z-index: 20; background: var(--nav); border-bottom: 1px solid var(--bd); padding: 12px 20px; }}
    .topnav-in {{ max-width: 1440px; margin: 0 auto; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px; }}
    .brand {{ font-size: 16px; font-weight: 800; color: var(--fg); text-decoration: none; }}
    .menu {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    .m-link {{ padding: 7px 14px; border-radius: 999px; border: 1px solid var(--bd); background: var(--surf); color: var(--fg); text-decoration: none; font-size: 13px; font-weight: 700; }}
    .m-link.active {{ background: var(--fg); color: var(--bg); border-color: var(--fg); }}
    .theme-btn {{ cursor: pointer; padding: 7px 12px; border-radius: 999px; border: 1px solid var(--bd); background: transparent; color: var(--mut); font-weight: 700; font-size: 12px; }}
    .wrap {{ max-width: 1440px; margin: 20px auto 48px; padding: 0 20px; display: flex; flex-direction: column; gap: 16px; }}
    h1 {{ margin: 0; font-size: 21px; font-weight: 800; }}
    .sub {{ margin: 3px 0 0; color: var(--mut); font-size: 13px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }}
    .card {{ background: var(--card); border: 1px solid var(--bd); border-radius: 14px; padding: 14px 16px; }}
    .kl {{ color: var(--mut); font-size: 12px; }}
    .kv {{ font-size: 19px; font-weight: 800; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin-top: 3px; }}
    .toolbar {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; }}
    .grp {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    .pill {{ cursor: pointer; padding: 6px 12px; border-radius: 999px; border: 1px solid var(--bd); background: var(--surf); color: var(--fg); font-size: 12px; font-weight: 700; }}
    .pill.on {{ background: var(--blue); border-color: var(--blue); color: #fff; }}
    .pill.on.gold {{ background: var(--gold); border-color: var(--gold); color: #0b1017; }}
    .pill.on.cyan {{ background: var(--cyan); border-color: var(--cyan); color: #061318; }}
    input[type="search"], select {{ padding: 7px 10px; border-radius: 8px; border: 1px solid var(--bd); background: var(--surf); color: var(--fg); font-size: 12.5px; }}
    input[type="search"] {{ min-width: 240px; }}
    input[type="range"] {{ width: 110px; accent-color: var(--blue); }}
    .lbl {{ display: inline-flex; align-items: center; gap: 6px; font-size: 12px; }}
    .split {{ display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(360px, 0.95fr); gap: 16px; align-items: start; }}
    @media (max-width: 1080px) {{ .split {{ grid-template-columns: 1fr; }} }}
    .tw {{ overflow-x: auto; max-height: 740px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 12.5px; }}
    th, td {{ padding: 8px 9px; border-bottom: 1px solid var(--bd); text-align: right; white-space: nowrap; }}
    th {{ position: sticky; top: 0; background: var(--card); color: var(--mut); cursor: pointer; z-index: 2; }}
    th.l, td.l {{ text-align: left; white-space: normal; }}
    tbody tr {{ cursor: pointer; }}
    tbody tr:hover {{ background: rgba(59, 130, 246, 0.08); }}
    tbody tr.sel {{ background: rgba(59, 130, 246, 0.18); }}
    .badge {{ display: inline-block; padding: 2px 7px; border-radius: 6px; font-size: 11px; font-weight: 700; }}
    .b-xau {{ background: var(--gold-soft); color: var(--gold); }}
    .b-eth {{ background: var(--cyan-soft); color: var(--cyan); }}
    .b-beta {{ background: var(--blue-soft); color: var(--blue); }}
    .b-pass {{ background: var(--ok-soft); color: var(--ok); }}
    .b-fail {{ background: var(--err-soft); color: var(--err); }}
    .pos {{ color: var(--ok); font-weight: 700; }}
    .neg {{ color: var(--err); font-weight: 700; }}
    .mut {{ color: var(--mut); }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .dossier {{ position: sticky; top: 72px; display: flex; flex-direction: column; gap: 12px; }}
    .d-head {{ border-bottom: 1px solid var(--bd); padding-bottom: 10px; }}
    .d-title {{ font-size: 17px; font-weight: 800; margin: 4px 0 2px; }}
    .spark-box {{ width: 100%; height: 150px; background: var(--surf); border: 1px solid var(--bd); border-radius: 10px; padding: 6px; }}
    .spark-box canvas {{ width: 100%; height: 100%; display: block; }}
    .mgrid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
    .mbox {{ background: var(--surf); border: 1px solid var(--bd); border-radius: 9px; padding: 8px 10px; }}
    .ml {{ color: var(--mut); font-size: 11px; }}
    .mv {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 800; font-size: 14px; margin-top: 2px; }}
    .cond-list {{ margin: 4px 0 0; padding-left: 18px; display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; }}
    pre.code {{ margin: 0; padding: 9px 11px; border-radius: 8px; background: var(--surf); border: 1px solid var(--bd); font: 11.5px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; overflow-x: auto; max-height: 180px; white-space: pre-wrap; word-break: break-word; }}
    .btn-row {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .btn {{ display: inline-block; padding: 8px 12px; border-radius: 9px; text-decoration: none; font-size: 12.5px; font-weight: 700; border: 1px solid var(--bd); background: var(--surf); color: var(--fg); }}
    .btn.pri {{ background: var(--blue); border-color: var(--blue); color: #fff; }}
    .btn:hover {{ filter: brightness(1.08); }}
  </style>
</head>
<body>
  <nav class="topnav">
    <div class="topnav-in">
      <a class="brand" href="index.html">Alpha_mining</a>
      <div class="menu">
        <a class="m-link" href="index.html">หน้าหลัก</a>
        <a class="m-link active" href="library.html">ห้องสมุดโมเดล</a>
        <a class="m-link" href="{a_base}#sym=XAUUSD">ALPHA · ทองคำ (XAUUSD)</a>
        <a class="m-link" href="{a_base}#sym=ETHUSDT">ALPHA · ETH</a>
        <a class="m-link" href="{b_base}">BETA · ETH Grid</a>
        <button id="theme-toggle" type="button" class="theme-btn">สลับสีพื้นหลัง</button>
      </div>
    </div>
  </nav>

  <main class="wrap">
    <div>
      <h1>ห้องสมุดโมเดล (Model Library)</h1>
      <p class="sub">รวมผลการทดสอบทุกโมเดลทั้ง Alpha &amp; Beta พร้อมค่าความแกว่ง/ความนิ่งพอร์ต (Volatility &amp; R²), เงื่อนไขกลยุทธ์ฉบับเต็ม และลิงก์เปิด Report 9-Panel</p>
    </div>

    <section class="kpis" id="kpis"></section>

    <section class="card">
      <div class="toolbar">
        <div class="grp" id="cat-pills">
          <button type="button" class="pill on" data-cat="ALL">ทั้งหมด</button>
          <button type="button" class="pill gold" data-cat="ALPHA_XAUUSD">ALPHA · XAUUSD</button>
          <button type="button" class="pill cyan" data-cat="ALPHA_ETHUSDT">ALPHA · ETHUSDT</button>
          <button type="button" class="pill" data-cat="BETA_ETH_GRID">BETA · ETH Grid</button>
        </div>
        <div class="grp">
          <input id="q-search" type="search" placeholder="ค้นหาชื่อโมเดล, family, signal, TF, สมมติฐาน..." />
          <select id="q-sort">
            <option value="stability" selected>เรียงตามความนิ่ง (R² สูง → Vol ต่ำ)</option>
            <option value="primary">เรียงตามกำไรหลัก / Cashflow</option>
            <option value="dd">เรียงตาม Max DD ต่ำสุด</option>
            <option value="vol">เรียงตามความแกว่ง (Vol/ปี) ต่ำสุด</option>
            <option value="newest">เรียงตามวันที่ทดสอบล่าสุด</option>
          </select>
        </div>
      </div>
      <div class="toolbar" style="margin-top:10px;padding-top:10px;border-top:1px solid var(--bd);">
        <div class="grp">
          <label class="lbl"><span class="mut">Max DD ≤</span><input id="f-dd" type="range" min="5" max="100" step="1" value="50" /><b id="f-dd-v" class="mono">50%</b></label>
          <label class="lbl"><span class="mut">ความแกว่ง Vol ≤</span><input id="f-vol" type="range" min="5" max="100" step="1" value="60" /><b id="f-vol-v" class="mono">60%</b></label>
          <label class="lbl"><span class="mut">ความนิ่ง R² ≥</span><input id="f-r2" type="range" min="0" max="0.95" step="0.05" value="0" /><b id="f-r2-v" class="mono">0.00</b></label>
          <label class="lbl"><input id="f-pass" type="checkbox" /><span>แสดงเฉพาะที่ผ่าน Gate</span></label>
        </div>
        <div class="grp">
          <span id="f-count" class="mut mono" style="font-size:12px;"></span>
          <button id="f-reset" type="button" class="pill">รีเซ็ตตัวกรอง</button>
        </div>
      </div>
    </section>

    <section class="split">
      <div class="card" style="padding:0;overflow:hidden;">
        <div class="tw">
          <table>
            <thead>
              <tr>
                <th class="l">หมวด</th>
                <th class="l">โมเดล / กลยุทธ์</th>
                <th>วันที่</th>
                <th>ผลตอบแทน / CF</th>
                <th>Max DD</th>
                <th>Vol/ปี</th>
                <th>R² นิ่ง</th>
                <th>Gate</th>
              </tr>
            </thead>
            <tbody id="lib-body"></tbody>
          </table>
        </div>
      </div>

      <aside class="card dossier" id="dossier">
        <div class="mut">คลิกที่โมเดลด้านซ้ายเพื่อดูแฟ้มรายงานและเงื่อนไขฉบับเต็ม</div>
      </aside>
    </section>
  </main>

  <script>
    const DATA = {safe_json};
    const MODELS = DATA.models || [];
    const $ = (id) => document.getElementById(id);
    const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
    const num = (v, d = 2) => (v == null || Number.isNaN(Number(v))) ? "–" : Number(v).toFixed(d);

    const ST = {{
      cat: "ALL",
      q: "",
      sort: "stability",
      maxDd: 50,
      maxVol: 60,
      minR2: 0,
      onlyPass: false,
      selectedId: (MODELS[0] && MODELS[0].model_id) || ""
    }};

    function catBadge(m) {{
      if (m.category === "ALPHA_XAUUSD") return `<span class="badge b-xau">ALPHA · XAU</span>`;
      if (m.category === "ALPHA_ETHUSDT") return `<span class="badge b-eth">ALPHA · ETH</span>`;
      return `<span class="badge b-beta">BETA · Grid</span>`;
    }}

    function evalGate(m) {{
      const reasons = [];
      if (m.would_liquidate) reasons.push("LIQ");
      if (Number(m.max_drawdown_pct || 0) > ST.maxDd) reasons.push(`DD>${{ST.maxDd}}%`);
      if (ST.maxVol < 100 && Number(m.ann_vol_pct || 0) > ST.maxVol) reasons.push(`VOL>${{ST.maxVol}}%`);
      if (ST.minR2 > 0 && Number(m.equity_r2 || 0) < ST.minR2) reasons.push(`R2<${{ST.minR2.toFixed(2)}}`);
      if (m.track === "alpha" && Number(m.primary_return_pct || 0) <= 0) reasons.push("OOS<=0%");
      if (m.track === "beta" && Number(m.cashflow_net_usd || 0) <= 0) reasons.push("CF<=0");
      return {{ pass: reasons.length === 0, reasons }};
    }}

    function drawSpark(canvas, pts, color) {{
      if (!canvas) return;
      const r = canvas.getBoundingClientRect();
      const d = window.devicePixelRatio || 1;
      canvas.width = Math.max(20, r.width * d);
      canvas.height = Math.max(20, r.height * d);
      const c = canvas.getContext("2d");
      c.setTransform(d, 0, 0, d, 0, 0);
      const w = r.width, h = r.height;
      c.clearRect(0, 0, w, h);
      if (!pts || pts.length < 2) {{
        c.fillStyle = "#8fa3bc";
        c.font = "12px sans-serif";
        c.fillText("ไม่มีข้อมูลเส้นกราฟ Equity", 14, h / 2);
        return;
      }}
      let y0 = Math.min(0, ...pts), y1 = Math.max(0, ...pts);
      if (y0 === y1) {{ y0 -= 1; y1 += 1; }}
      const pad = (y1 - y0) * 0.08; y0 -= pad; y1 += pad;
      const ml = 46, mr = 10, mt = 10, mb = 18;
      const X = (i) => ml + (i / (pts.length - 1)) * (w - ml - mr);
      const Y = (v) => h - mb - ((v - y0) / (y1 - y0)) * (h - mt - mb);
      c.strokeStyle = "rgba(148,163,184,0.2)"; c.lineWidth = 1;
      for (let k = 0; k <= 3; k++) {{
        const v = y0 + (y1 - y0) * k / 3, y = Y(v);
        c.beginPath(); c.moveTo(ml, y); c.lineTo(w - mr, y); c.stroke();
        c.fillStyle = "#8fa3bc"; c.font = "10px ui-monospace, Menlo, monospace"; c.textAlign = "right";
        c.fillText(v.toFixed(0) + "%", ml - 5, y + 3);
      }}
      c.strokeStyle = "rgba(148,163,184,0.45)"; c.setLineDash([4, 4]);
      c.beginPath(); c.moveTo(ml, Y(0)); c.lineTo(w - mr, Y(0)); c.stroke(); c.setLineDash([]);
      c.strokeStyle = color; c.lineWidth = 2; c.beginPath();
      pts.forEach((v, i) => {{ const px = X(i), py = Y(v); i ? c.lineTo(px, py) : c.moveTo(px, py); }});
      c.stroke();
    }}

    function renderDossier(m) {{
      if (!m) {{
        $("dossier").innerHTML = `<div class="mut">ไม่พบโมเดลตามเงื่อนไขที่กรอง</div>`;
        return;
      }}
      const g = evalGate(m);
      const isAlpha = m.track === "alpha";
      const sparkColor = m.category === "ALPHA_XAUUSD" ? "#f59e0b" : (m.category === "ALPHA_ETHUSDT" ? "#06b6d4" : "#3b82f6");
      const metricsHtml = isAlpha ? `
        <div class="mbox"><div class="ml">กำไร OOS</div><div class="mv ${{m.primary_return_pct >= 0 ? 'pos' : 'neg'}}">${{m.primary_return_pct >= 0 ? '+' : ''}}${{num(m.primary_return_pct, 1)}}%</div></div>
        <div class="mbox"><div class="ml">OOS / IS Sharpe</div><div class="mv">${{num(m.oos_sharpe_ann)}} / ${{num(m.is_sharpe_ann)}}</div></div>
        <div class="mbox"><div class="ml">กำไรรวม / CAGR</div><div class="mv">${{num(m.total_return_pct, 1)}}% / ${{num(m.cagr_pct, 1)}}%</div></div>
        <div class="mbox"><div class="ml">Max DD</div><div class="mv neg">-${{num(m.max_drawdown_pct, 1)}}%</div></div>
        <div class="mbox"><div class="ml">ความแกว่งพอร์ต (Vol/ปี)</div><div class="mv">${{num(m.ann_vol_pct, 1)}}%</div></div>
        <div class="mbox"><div class="ml">ความนิ่ง R² / Ulcer</div><div class="mv">${{num(m.equity_r2, 2)}} / ${{num(m.ulcer_index_pct, 1)}}%</div></div>
        <div class="mbox"><div class="ml">จำนวนเทรด / Win%</div><div class="mv">${{m.trades}} (${{num(m.win_rate_pct, 1)}}%)</div></div>
        <div class="mbox"><div class="ml">Profit Factor</div><div class="mv">${{num(m.profit_factor, 2)}}</div></div>
        <div class="mbox"><div class="ml">Beta / Corr</div><div class="mv">${{num(m.beta, 2)}} / ${{num(m.corr, 2)}}</div></div>
      ` : `
        <div class="mbox"><div class="ml">Realized Cashflow</div><div class="mv pos">+$${{num(m.cashflow_net_usd, 0)}}</div></div>
        <div class="mbox"><div class="ml">AVG Weekly CF</div><div class="mv pos">+$${{num(m.avg_weekly_cf_usd, 1)}}/wk</div></div>
        <div class="mbox"><div class="ml">MTM Return / CF÷DD</div><div class="mv">${{num(m.total_return_pct, 1)}}% · ${{num(m.cashflow_to_dd_ratio, 2)}}x</div></div>
        <div class="mbox"><div class="ml">Max MTM DD</div><div class="mv neg">-${{num(m.max_drawdown_pct, 1)}}%</div></div>
        <div class="mbox"><div class="ml">ความแกว่งพอร์ต (Vol/ปี)</div><div class="mv">${{num(m.ann_vol_pct, 1)}}%</div></div>
        <div class="mbox"><div class="ml">ความนิ่ง R² / Ulcer</div><div class="mv">${{num(m.equity_r2, 2)}} / ${{num(m.ulcer_index_pct, 1)}}%</div></div>
        <div class="mbox"><div class="ml">Crash Stress DD</div><div class="mv">${{m.crash_dd_pct != null ? num(m.crash_dd_pct, 1) + "%" : "N/A"}}</div></div>
        <div class="mbox"><div class="ml">Trades (Win%)</div><div class="mv">${{Number(m.trades || 0).toLocaleString()}} (${{num(m.win_rate_pct, 1)}}%)</div></div>
        <div class="mbox"><div class="ml">Beta / Corr vs ETH</div><div class="mv">${{num(m.beta, 2)}} / ${{num(m.corr, 2)}}</div></div>
      `;

      const conds = (m.conditions || []).map((c) => `<li>${{esc(c)}}</li>`).join("");
      const hypBlock = m.hypothesis
        ? `<div class="mbox"><div class="ml">สมมติฐานกลยุทธ์ (Hypothesis)</div><div style="margin-top:3px;font-size:12.5px;">${{esc(m.hypothesis)}}</div></div>`
        : "";
      const repBtn = m.report_href
        ? `<a class="btn" href="${{esc(m.report_href)}}" target="_blank" rel="noopener">📄 เปิด Report (.md)</a>`
        : "";

      $("dossier").innerHTML = `
        <div class="d-head">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
            <div>${{catBadge(m)}} <span class="badge ${{g.pass ? 'b-pass' : 'b-fail'}}">${{g.pass ? 'PASS GATE' : 'FAIL: ' + esc(g.reasons.join(', '))}}</span></div>
            <span class="mut mono" style="font-size:11.5px;">Trial #${{m.trial_number}} · ${{esc(m.batch_date)}}</span>
          </div>
          <div class="d-title">${{esc(m.title)}}</div>
          <div class="mut mono" style="font-size:11.5px;">${{esc(m.model_id)}}</div>
        </div>
        <div class="spark-box"><canvas id="lib-spark"></canvas></div>
        <div class="btn-row">
          <a class="btn pri" href="${{esc(m.dashboard_href)}}">📊 เปิด Dashboard 9-Panel วันทดสอบ</a>
          <a class="btn" href="${{esc(m.top9_href)}}">🏆 ดู Top-9 9-Panel</a>
          ${{repBtn}}
        </div>
        <div class="mgrid">${{metricsHtml}}</div>
        ${{hypBlock}}
        <div>
          <div style="font-weight:700;font-size:13px;">เงื่อนไขกลยุทธ์และพารามิเตอร์ (Conditions)</div>
          <ul class="cond-list">${{conds}}</ul>
        </div>
        <div>
          <div class="ml" style="margin-bottom:4px;">Spec JSON &amp; CLI</div>
          <pre class="code">${{esc(m.reuse_cmd)}}\n\n${{esc(JSON.stringify(m.spec || {{}}, null, 2))}}</pre>
        </div>
      `;
      requestAnimationFrame(() => drawSpark($("lib-spark"), m.spark, sparkColor));
    }}

    function render() {{
      const q = ST.q.trim().toLowerCase();
      let list = MODELS.filter((m) => {{
        if (ST.cat !== "ALL" && m.category !== ST.cat) return false;
        if (q) {{
          const hay = `${{m.model_id}} ${{m.title}} ${{m.family}} ${{m.symbol}} ${{m.timeframe}} ${{m.hypothesis}} ${{(m.conditions || []).join(" ")}}`.toLowerCase();
          if (!hay.includes(q)) return false;
        }}
        if (ST.onlyPass && !evalGate(m).pass) return false;
        return true;
      }});

      list.sort((a, b) => {{
        if (ST.sort === "stability") {{
          if (Math.abs(b.equity_r2 - a.equity_r2) > 1e-4) return b.equity_r2 - a.equity_r2;
          return a.ann_vol_pct - b.ann_vol_pct;
        }}
        if (ST.sort === "primary") {{
          const va = a.track === "beta" ? a.cashflow_net_usd : a.primary_return_pct * 100;
          const vb = b.track === "beta" ? b.cashflow_net_usd : b.primary_return_pct * 100;
          return vb - va;
        }}
        if (ST.sort === "dd") return a.max_drawdown_pct - b.max_drawdown_pct;
        if (ST.sort === "vol") return a.ann_vol_pct - b.ann_vol_pct;
        return String(b.batch_date).localeCompare(String(a.batch_date)) || (b.trial_number - a.trial_number);
      }});

      const passAll = list.filter((m) => evalGate(m).pass);
      const avgVol = list.length ? list.reduce((s, m) => s + Number(m.ann_vol_pct || 0), 0) / list.length : 0;
      const bestStab = list.reduce((a, m) => (!a || m.equity_r2 > a.equity_r2) ? m : a, null);
      $("kpis").innerHTML = `
        <div class="card"><div class="kl">โมเดลในห้องสมุด (Alpha ${{DATA.alpha_count}} · Beta ${{DATA.beta_count}})</div><div class="kv">${{DATA.total_models}} โมเดล</div></div>
        <div class="card"><div class="kl">ผ่าน Gate ปัจจุบัน (ในชุดที่แสดง)</div><div class="kv pos">${{passAll.length}} / ${{list.length}}</div></div>
        <div class="card"><div class="kl">ความแกว่งพอร์ตเฉลี่ย (Vol/ปี)</div><div class="kv">${{avgVol.toFixed(1)}}%</div></div>
        <div class="card"><div class="kl">ความนิ่งสูงสุด (Equity R²)</div><div class="kv" style="font-size:15px;">${{bestStab ? num(bestStab.equity_r2, 2) + " · " + esc(bestStab.title) : "–"}}</div></div>
      `;
      $("f-count").textContent = `แสดง ${{list.length}} จาก ${{MODELS.length}} โมเดล`;

      if (!list.some((m) => m.model_id === ST.selectedId)) {{
        ST.selectedId = (list[0] && list[0].model_id) || "";
      }}
      const tbody = $("lib-body");
      tbody.innerHTML = list.map((m) => {{
        const g = evalGate(m);
        const perf = m.track === "beta"
          ? `<span class="pos">+$${{num(m.cashflow_net_usd, 0)}}</span>`
          : `<span class="${{m.primary_return_pct >= 0 ? 'pos' : 'neg'}}">${{m.primary_return_pct >= 0 ? '+' : ''}}${{num(m.primary_return_pct, 1)}}% OOS</span>`;
        return `<tr data-id="${{esc(m.model_id)}}" class="${{m.model_id === ST.selectedId ? 'sel' : ''}}">
          <td class="l">${{catBadge(m)}}</td>
          <td class="l"><b>${{esc(m.title)}}</b><div class="mut mono" style="font-size:11px;">${{esc(m.model_id)}}</div></td>
          <td class="mono">${{esc(m.batch_date)}}</td>
          <td class="mono">${{perf}}</td>
          <td class="mono">-${{num(m.max_drawdown_pct, 1)}}%</td>
          <td class="mono">${{num(m.ann_vol_pct, 1)}}%</td>
          <td class="mono">${{num(m.equity_r2, 2)}}</td>
          <td><span class="badge ${{g.pass ? 'b-pass' : 'b-fail'}}">${{g.pass ? 'PASS' : 'FAIL'}}</span></td>
        </tr>`;
      }}).join("") || `<tr><td colspan="8" class="l mut" style="padding:18px;">ไม่พบโมเดลที่ตรงกับตัวกรอง</td></tr>`;

      tbody.querySelectorAll("tr[data-id]").forEach((tr) => {{
        tr.onclick = () => {{
          ST.selectedId = tr.dataset.id;
          tbody.querySelectorAll("tr").forEach((r) => r.classList.toggle("sel", r.dataset.id === ST.selectedId));
          renderDossier(MODELS.find((x) => x.model_id === ST.selectedId));
        }};
      }});
      renderDossier(list.find((x) => x.model_id === ST.selectedId) || list[0] || null);
    }}

    document.querySelectorAll("#cat-pills .pill").forEach((b) => {{
      b.onclick = () => {{
        ST.cat = b.dataset.cat;
        document.querySelectorAll("#cat-pills .pill").forEach((x) => x.classList.toggle("on", x === b));
        render();
      }};
    }});
    $("q-search").addEventListener("input", (e) => {{ ST.q = e.target.value; render(); }});
    $("q-sort").addEventListener("change", (e) => {{ ST.sort = e.target.value; render(); }});
    $("f-dd").addEventListener("input", (e) => {{ ST.maxDd = Number(e.target.value); $("f-dd-v").textContent = ST.maxDd + "%"; render(); }});
    $("f-vol").addEventListener("input", (e) => {{ ST.maxVol = Number(e.target.value); $("f-vol-v").textContent = ST.maxVol >= 100 ? "ไม่จำกัด" : (ST.maxVol + "%"); render(); }});
    $("f-r2").addEventListener("input", (e) => {{ ST.minR2 = Number(e.target.value); $("f-r2-v").textContent = ST.minR2.toFixed(2); render(); }});
    $("f-pass").addEventListener("change", (e) => {{ ST.onlyPass = e.target.checked; render(); }});
    $("f-reset").onclick = () => {{
      ST.cat = "ALL"; ST.q = ""; ST.sort = "stability"; ST.maxDd = 50; ST.maxVol = 60; ST.minR2 = 0; ST.onlyPass = false;
      $("q-search").value = ""; $("q-sort").value = "stability";
      $("f-dd").value = "50"; $("f-dd-v").textContent = "50%";
      $("f-vol").value = "60"; $("f-vol-v").textContent = "60%";
      $("f-r2").value = "0"; $("f-r2-v").textContent = "0.00";
      $("f-pass").checked = false;
      document.querySelectorAll("#cat-pills .pill").forEach((x) => x.classList.toggle("on", x.dataset.cat === "ALL"));
      render();
    }};
    $("theme-toggle").addEventListener("click", () => {{
      document.body.classList.toggle("light");
      try {{ localStorage.setItem("am_theme", document.body.classList.contains("light") ? "light" : "dark"); }} catch (_e) {{}}
    }});
    try {{ if (localStorage.getItem("am_theme") === "light") document.body.classList.add("light"); }} catch (_e) {{}}
    window.addEventListener("resize", () => {{
      const cur = MODELS.find((x) => x.model_id === ST.selectedId);
      if (cur) renderDossier(cur);
    }});
    render();
  </script>
</body>
</html>
"""
