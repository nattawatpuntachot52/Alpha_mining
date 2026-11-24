"""Unified Central Research Portal HTML generator separating Alpha & Beta tracks cleanly.

Renders a 100% self-contained, zero-CDN root `index.html` for GitHub Pages that sits above
`/alpha/` (Directional Multi-Timeframe XAUUSD + ETHUSDT, 20 models/day) and `/beta/`
(LGB154 Grid Cashflow ETHUSDT 1m, 10 models/day), with side-by-side leaderboards, daily batch
archives, direct 9-panel dashboard links, and a persistent track switcher bar shared across all pages.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SAFE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


def _slim_alpha_rank(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": int(row.get("rank", 0)),
        "model_id": str(row.get("model_id", "")),
        "symbol": str(row.get("symbol", "")),
        "timeframe": str(row.get("timeframe", "")),
        "direction": str(row.get("direction", "")),
        "oos_sharpe_ann": round(float(row.get("oos_sharpe_ann", 0.0)), 2),
        "oos_return_pct": round(float(row.get("oos_return_pct", 0.0)), 2),
        "total_return_pct": round(float(row.get("total_return_pct", 0.0)), 2),
        "max_drawdown_pct": round(float(row.get("max_drawdown_pct", 0.0)), 2),
        "trades": int(row.get("trades", 0)),
        "dsr_approx": round(float(row.get("dsr_approx", 0.0)), 2),
        "batch_date": str(row.get("batch_date", "")),
    }


def _slim_beta_rank(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": int(row.get("rank", 0)),
        "model_id": str(row.get("model_id", "")),
        "signal_name": str(row.get("signal_name", "")),
        "cashflow_net_usd": round(float(row.get("cashflow_net_usd", 0.0)), 2),
        "cashflow_pct": round(float(row.get("cashflow_pct", 0.0)), 2),
        "max_drawdown_pct": round(float(row.get("max_drawdown_pct", 0.0)), 2),
        "cashflow_to_dd_ratio": round(float(row.get("cashflow_to_dd_ratio", 0.0)), 2),
        "mtm_return_pct": round(float(row.get("mtm_return_pct", 0.0)), 2),
        "avg_weekly_cf_usd": round(float(row.get("avg_weekly_cf_usd", 0.0)), 2),
        "batch_date": str(row.get("batch_date", "")),
    }


def _clean_days(raw_days: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_days, list):
        return []
    out: list[dict[str, Any]] = []
    for d in raw_days:
        if not isinstance(d, dict):
            continue
        bdate = str(d.get("batch_date", "")).strip()
        if not _SAFE_DATE_RE.fullmatch(bdate):
            continue
        out.append(dict(d))
    out.sort(key=lambda x: str(x["batch_date"]), reverse=True)
    return out


def collect_unified_portal_payload(
    *,
    alpha_dir: Path,
    beta_dir: Path,
    alpha_prefix: str = "alpha",
    beta_prefix: str = "beta",
) -> dict[str, Any]:
    """Collect compact summary payloads from both `alpha_mining/` and `beta_mining/` stores."""
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
            "disqualified_count": int(alpha_rank.get("disqualified_count", 0)),
            "top_ranked": [_slim_alpha_rank(r) for r in (alpha_rank.get("top_ranked") or [])[:9]],
            "days": alpha_days,
        },
        "beta": {
            "prefix": beta_prefix.strip("/"),
            "latest_date": beta_latest,
            "total_days": len(beta_days),
            "total_trials": int(beta_rank.get("total_trials", 0)),
            "total_models": int(beta_rank.get("total_models", 0)),
            "qualified_count": int(beta_rank.get("qualified_count", 0)),
            "disqualified_count": int(beta_rank.get("disqualified_count", 0)),
            "top_ranked": [_slim_beta_rank(r) for r in (beta_rank.get("top_ranked") or [])[:9]],
            "days": beta_days,
        },
    }


def render_unified_portal_html(payload: dict[str, Any]) -> str:
    """Render the zero-CDN unified central portal HTML (`index.html`)."""
    safe_json = _safe_inline_json(payload)
    alpha = payload.get("alpha") or {}
    beta = payload.get("beta") or {}
    a_pref = html.escape(str(alpha.get("prefix", "alpha")))
    b_pref = html.escape(str(beta.get("prefix", "beta")))
    a_latest = html.escape(str(alpha.get("latest_date", "")))
    b_latest = html.escape(str(beta.get("latest_date", "")))
    a_dash = f"{a_pref}/daily/{a_latest}/dashboard.html" if a_latest else f"{a_pref}/index.html"
    b_dash = f"{b_pref}/daily/{b_latest}/dashboard.html" if b_latest else f"{b_pref}/index.html"

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Alpha_mining — Unified Research Portal (Alpha &amp; Beta)</title>
  <style>
    :root {{
      --bg: #080d14;
      --bg2: #0f1722;
      --card: #121b28;
      --surf: #182334;
      --bd: #253347;
      --fg: #eaf0f8;
      --mut: #8fa3bc;
      --alpha: #f59e0b;
      --alpha-bg: rgba(245, 158, 11, 0.13);
      --alpha-bd: rgba(245, 158, 11, 0.45);
      --beta: #3b82f6;
      --beta-bg: rgba(59, 130, 246, 0.13);
      --beta-bd: rgba(59, 130, 246, 0.45);
      --ok: #22c55e;
      --err: #ef4444;
    }}
    body.light {{
      --bg: #f3f6fb;
      --bg2: #ffffff;
      --card: #ffffff;
      --surf: #eef3f9;
      --bd: #d5dfec;
      --fg: #0f172a;
      --mut: #52637a;
      --alpha: #d97706;
      --alpha-bg: rgba(217, 119, 6, 0.10);
      --alpha-bd: rgba(217, 119, 6, 0.42);
      --beta: #2563eb;
      --beta-bg: rgba(37, 99, 235, 0.10);
      --beta-bd: rgba(37, 99, 235, 0.42);
      --ok: #16a34a;
      --err: #dc2626;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 0 0 42px;
      background: var(--bg);
      color: var(--fg);
      font: 13px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    .topbar {{
      position: sticky; top: 0; z-index: 20;
      background: var(--bg2);
      border-bottom: 1px solid var(--bd);
      padding: 10px 20px;
    }}
    .topbar-in {{
      max-width: 1460px; margin: 0 auto;
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px;
    }}
    .brand {{
      display: flex; align-items: center; gap: 10px;
      font-weight: 800; font-size: 15px; letter-spacing: -0.01em; color: var(--fg); text-decoration: none;
    }}
    .brand-dot {{
      width: 10px; height: 10px; border-radius: 50%;
      background: linear-gradient(135deg, var(--alpha), var(--beta));
    }}
    .nav-links {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    .nav-pill {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 6px 12px; border-radius: 999px; border: 1px solid var(--bd);
      background: var(--surf); color: var(--fg); text-decoration: none;
      font-size: 12px; font-weight: 700; transition: border-color .15s, background .15s;
    }}
    .nav-pill:hover {{ border-color: var(--fg); }}
    .nav-pill.active {{ background: var(--fg); color: var(--bg); border-color: var(--fg); }}
    .nav-pill.alpha {{ border-color: var(--alpha-bd); color: var(--alpha); background: var(--alpha-bg); }}
    .nav-pill.beta {{ border-color: var(--beta-bd); color: var(--beta); background: var(--beta-bg); }}
    .btn-theme {{
      cursor: pointer; padding: 6px 11px; border-radius: 8px;
      border: 1px solid var(--bd); background: var(--card); color: var(--fg);
      font-size: 12px; font-weight: 600;
    }}
    .wrap {{ max-width: 1460px; margin: 18px auto 0; padding: 0 20px; display: flex; flex-direction: column; gap: 16px; }}
    .hero {{
      background: var(--card); border: 1px solid var(--bd); border-radius: 14px;
      padding: 18px 20px; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 14px;
    }}
    .hero h1 {{ margin: 0; font-size: 21px; font-weight: 800; letter-spacing: -0.02em; }}
    .hero p {{ margin: 4px 0 0; color: var(--mut); font-size: 13px; }}
    .mode-switch {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .mode-btn {{
      cursor: pointer; padding: 7px 12px; border-radius: 9px;
      border: 1px solid var(--bd); background: var(--surf); color: var(--fg);
      font-size: 12px; font-weight: 700;
    }}
    .mode-btn.active {{ background: var(--fg); color: var(--bg); border-color: var(--fg); }}
    .mode-btn.m-alpha.active {{ background: var(--alpha); color: #0b1017; border-color: var(--alpha); }}
    .mode-btn.m-beta.active {{ background: var(--beta); color: #ffffff; border-color: var(--beta); }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }}
    .kpi {{
      background: var(--card); border: 1px solid var(--bd); border-radius: 12px; padding: 13px 15px;
    }}
    .kl {{ color: var(--mut); font-size: 12px; }}
    .kv {{ font-size: 21px; font-weight: 800; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin-top: 2px; }}
    .ks {{ color: var(--mut); font-size: 11px; margin-top: 2px; }}
    .tracks {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: start; }}
    .tracks.single {{ grid-template-columns: 1fr; }}
    @media (max-width: 1060px) {{ .tracks {{ grid-template-columns: 1fr; }} }}
    .track {{
      background: var(--card); border: 1px solid var(--bd); border-radius: 14px;
      overflow: hidden; display: flex; flex-direction: column;
    }}
    .track.alpha-track {{ border-top: 4px solid var(--alpha); }}
    .track.beta-track {{ border-top: 4px solid var(--beta); }}
    .track-hdr {{
      padding: 16px 18px 14px; border-bottom: 1px solid var(--bd);
      display: flex; flex-direction: column; gap: 10px;
    }}
    .track-top {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-start; gap: 10px; }}
    .tag {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 800; letter-spacing: 0.04em;
    }}
    .tag-alpha {{ background: var(--alpha-bg); color: var(--alpha); border: 1px solid var(--alpha-bd); }}
    .tag-beta {{ background: var(--beta-bg); color: var(--beta); border: 1px solid var(--beta-bd); }}
    .track-title {{ margin: 4px 0 0; font-size: 18px; font-weight: 800; }}
    .track-desc {{ margin: 2px 0 0; color: var(--mut); font-size: 12px; }}
    .cta-row {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .btn {{
      display: inline-flex; align-items: center; justify-content: center; gap: 6px;
      padding: 8px 14px; border-radius: 9px; text-decoration: none;
      font-size: 12px; font-weight: 700; border: 1px solid var(--bd); background: var(--surf); color: var(--fg);
    }}
    .btn:hover {{ filter: brightness(1.08); }}
    .btn-alpha {{ background: var(--alpha); color: #0b1017; border-color: var(--alpha); }}
    .btn-beta {{ background: var(--beta); color: #ffffff; border-color: var(--beta); }}
    .mini-kpis {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
    .mk {{
      background: var(--surf); border: 1px solid var(--bd); border-radius: 10px; padding: 9px 11px;
    }}
    .mk-l {{ color: var(--mut); font-size: 11px; }}
    .mk-v {{ font-size: 16px; font-weight: 800; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin-top: 2px; }}
    .sec {{ padding: 14px 18px; border-bottom: 1px solid var(--bd); }}
    .sec:last-child {{ border-bottom: none; }}
    .sec-title {{ font-size: 13px; font-weight: 800; margin: 0 0 8px; display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
    .sec-sub {{ color: var(--mut); font-weight: 500; font-size: 11px; }}
    .tw {{ overflow-x: auto; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
    th, td {{ padding: 6px 8px; border-bottom: 1px solid var(--bd); text-align: right; white-space: nowrap; }}
    th {{ color: var(--mut); font-weight: 700; font-size: 11px; }}
    th:first-child, td:first-child, th.l, td.l {{ text-align: left; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .pos {{ color: var(--ok); font-weight: 700; }}
    .neg {{ color: var(--err); font-weight: 700; }}
    .mut {{ color: var(--mut); }}
    .sym {{
      display: inline-block; padding: 1px 6px; border-radius: 5px;
      font-size: 10px; font-weight: 800; border: 1px solid var(--bd); background: var(--surf);
    }}
    .sym-xau {{ color: var(--alpha); border-color: var(--alpha-bd); }}
    .sym-eth {{ color: var(--beta); border-color: var(--beta-bd); }}
    .tbl-link {{
      display: inline-block; padding: 3px 8px; border-radius: 6px; text-decoration: none;
      font-size: 11px; font-weight: 700; border: 1px solid var(--bd); background: var(--surf); color: var(--fg);
      margin-left: 4px;
    }}
    .tbl-link.a {{ border-color: var(--alpha-bd); color: var(--alpha); }}
    .tbl-link.b {{ border-color: var(--beta-bd); color: var(--beta); }}
    .hidden {{ display: none !important; }}
    .foot {{ color: var(--mut); font-size: 11px; text-align: center; padding-top: 6px; }}
  </style>
</head>
<body>
  <nav class="topbar" aria-label="Unified Alpha and Beta Navigation">
    <div class="topbar-in">
      <a class="brand" href="index.html"><span class="brand-dot"></span>Alpha_mining · Central Research Portal</a>
      <div class="nav-links">
        <a class="nav-pill active" href="index.html">Central Hub (ฐานกลาง)</a>
        <a class="nav-pill alpha" href="{a_pref}/index.html">ALPHA Track · XAUUSD + ETH</a>
        <a class="nav-pill beta" href="{b_pref}/index.html">BETA Track · ETH Grid</a>
        <button id="theme-toggle" type="button" class="btn-theme">Theme</button>
      </div>
    </div>
  </nav>

  <main class="wrap">
    <section class="hero">
      <div>
        <h1>Alpha_mining — ฐานกลางวิจัยและทดสอบโมเดล (Alpha / Beta)</h1>
        <p id="hero-sub">ศูนย์รวม Dashboard, Top-9 Ranking Board และผลทดสอบรายวัน แยกสาย Alpha (Directional Multi-TF) กับ Beta (Grid Cashflow) ชัดเจน</p>
      </div>
      <div class="mode-switch" role="group" aria-label="Track View Switcher">
        <button type="button" class="mode-btn active" data-view="split">แสดงคู่ (Alpha + Beta)</button>
        <button type="button" class="mode-btn m-alpha" data-view="alpha">โฟกัส ALPHA</button>
        <button type="button" class="mode-btn m-beta" data-view="beta">โฟกัส BETA</button>
      </div>
    </section>

    <section class="kpis" id="global-kpis"></section>

    <section class="tracks" id="tracks-grid">
      <!-- ALPHA TRACK -->
      <article class="track alpha-track" id="panel-alpha">
        <div class="track-hdr">
          <div class="track-top">
            <div>
              <span class="tag tag-alpha">ALPHA TRACK · DIRECTIONAL &amp; TACTICAL</span>
              <h2 class="track-title">Alpha Mining Factory (XAUUSD + ETHUSDT)</h2>
              <p class="track-desc">Multi-Timeframe (M5–D1) · 20 โมเดล/วัน (10 XAUUSD + 10 ETH) · แบ่ง 2 รอบ (07:15 &amp; 19:15 ICT)</p>
            </div>
          </div>
          <div class="cta-row">
            <a id="cta-alpha-dash" class="btn btn-alpha" href="{a_dash}">เปิด Alpha Dashboard ล่าสุด ({a_latest or "–"})</a>
            <a class="btn" href="{a_pref}/index.html">Alpha Hub รวมทุกวัน</a>
          </div>
          <div class="mini-kpis" id="alpha-kpis"></div>
        </div>
        <div class="sec">
          <h3 class="sec-title">Alpha Top-9 Leaderboard <span class="sec-sub">OOS Sharpe DESC → Max DD ASC (หัก DSR≈)</span></h3>
          <div class="tw" id="alpha-top"></div>
        </div>
        <div class="sec">
          <h3 class="sec-title">Alpha ผลทดสอบรายวัน (Archive) <span class="sec-sub">สะสมรอบ 1 + รอบ 2</span></h3>
          <div class="tw" id="alpha-days"></div>
        </div>
      </article>

      <!-- BETA TRACK -->
      <article class="track beta-track" id="panel-beta">
        <div class="track-hdr">
          <div class="track-top">
            <div>
              <span class="tag tag-beta">BETA TRACK · LGB154 GRID CASHFLOW</span>
              <h2 class="track-title">Beta Mining Factory (ETHUSDT 1m Grid)</h2>
              <p class="track-desc">1,000-Day Backtest + Crash -46% Stress · 10 โมเดล/วัน (รอบละ 5) · แบ่ง 2 รอบ (07:30 &amp; 19:30 ICT)</p>
            </div>
          </div>
          <div class="cta-row">
            <a id="cta-beta-dash" class="btn btn-beta" href="{b_dash}">เปิด Beta Dashboard ล่าสุด ({b_latest or "–"})</a>
            <a class="btn" href="{b_pref}/index.html">Beta Hub รวมทุกวัน</a>
          </div>
          <div class="mini-kpis" id="beta-kpis"></div>
        </div>
        <div class="sec">
          <h3 class="sec-title">Beta Top-9 Leaderboard <span class="sec-sub">Realized Cashflow DESC → Max DD ASC (DD ≤ 40%)</span></h3>
          <div class="tw" id="beta-top"></div>
        </div>
        <div class="sec">
          <h3 class="sec-title">Beta ผลทดสอบรายวัน (Archive) <span class="sec-sub">สะสมรอบ 1 + รอบ 2</span></h3>
          <div class="tw" id="beta-days"></div>
        </div>
      </article>
    </section>

    <div class="foot" id="portal-foot"></div>
  </main>

  <script>
    const DATA = {safe_json};
    const $ = (id) => document.getElementById(id);
    const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
    const num = (v, d = 2) => (v == null || Number.isNaN(Number(v))) ? "–" : Number(v).toFixed(d);
    const sgn = (v, d = 1, suf = "%") => {{
      const n = Number(v);
      if (Number.isNaN(n)) return "–";
      return `<span class="${{n >= 0 ? "pos" : "neg"}}">${{n >= 0 ? "+" : ""}}${{n.toFixed(d)}}${{suf}}</span>`;
    }};
    const symBadge = (s) => `<span class="sym ${{s === "XAUUSD" ? "sym-xau" : "sym-eth"}}">${{esc(s)}}</span>`;

    function renderGlobalKpis() {{
      const a = DATA.alpha || {{}};
      const b = DATA.beta || {{}};
      const totalTrials = (a.total_trials || 0) + (b.total_trials || 0);
      const totalQual = (a.qualified_count || 0) + (b.qualified_count || 0);
      const items = [
        ["Daily Capacity (2 รอบ/วัน)", "30 Models", "20 Alpha (10 XAU + 10 ETH) · 10 Beta"],
        ["Cumulative Mined Trials", String(totalTrials), `Alpha ${{a.total_trials || 0}} · Beta ${{b.total_trials || 0}}`],
        ["Qualified Top-9 Models", String(totalQual), `Alpha ${{a.qualified_count || 0}} ผ่านเกณฑ์ · Beta ${{b.qualified_count || 0}} ผ่านเกณฑ์`],
        ["Latest Mining Date", DATA.latest_date || "–", `UTC updated ${{DATA.generated_at_utc || "–"}}`]
      ];
      $("global-kpis").innerHTML = items.map(([l, v, s]) =>
        `<div class="kpi"><div class="kl">${{esc(l)}}</div><div class="kv">${{esc(v)}}</div><div class="ks">${{esc(s)}}</div></div>`
      ).join("");
    }}

    function renderAlpha() {{
      const a = DATA.alpha || {{}};
      const pref = a.prefix || "alpha";
      const top1 = (a.top_ranked || [])[0];
      $("alpha-kpis").innerHTML = [
        ["Cumulative Trials", a.total_trials || 0],
        ["Qualified Top-9", `${{a.qualified_count || 0}} / ${{a.total_models || 0}}`],
        ["#1 OOS Sharpe", top1 ? `${{num(top1.oos_sharpe_ann)}} (${{top1.symbol}})` : "–"]
      ].map(([l, v]) => `<div class="mk"><div class="mk-l">${{esc(l)}}</div><div class="mk-v">${{esc(v)}}</div></div>`).join("");

      const topRows = (a.top_ranked || []).slice(0, 6).map((r) => `
        <tr>
          <td class="mono">#${{r.rank}}</td>
          <td class="l mono" title="${{esc(r.model_id)}}">${{esc(r.model_id.length > 34 ? r.model_id.slice(0, 34) + "…" : r.model_id)}}</td>
          <td>${{symBadge(r.symbol)}}</td>
          <td class="mono">${{esc(r.timeframe)}}</td>
          <td class="mono pos">${{num(r.oos_sharpe_ann)}}</td>
          <td class="mono">${{sgn(r.oos_return_pct)}}</td>
          <td class="mono">${{num(r.max_drawdown_pct, 1)}}%</td>
          <td class="mono">${{num(r.dsr_approx)}}</td>
        </tr>`).join("") || '<tr><td colspan="8" class="l mut">ยังไม่มีโมเดล Alpha ที่ผ่านเกณฑ์</td></tr>';
      $("alpha-top").innerHTML = `<table><thead><tr><th>#</th><th class="l">Model ID</th><th>Sym</th><th>TF</th><th>OOS Sh</th><th>OOS Ret</th><th>Max DD</th><th>DSR≈</th></tr></thead><tbody>${{topRows}}</tbody></table>`;

      const dayRows = (a.days || []).slice(0, 10).map((d) => {{
        const bySym = Object.entries(d.by_symbol || {{}}).map(([k, v]) => `${{k}}:${{v}}`).join(" ");
        const rds = (d.rounds || [1]).join("+");
        return `<tr>
          <td class="l mono">${{esc(d.batch_date)}}</td>
          <td class="mono">${{d.model_count || 0}}</td>
          <td class="mono">R${{esc(rds)}}</td>
          <td class="l mono mut">${{esc(bySym)}}</td>
          <td class="mono pos">${{num(d.best_oos_sharpe)}}</td>
          <td><a class="tbl-link a" href="${{esc(pref)}}/daily/${{esc(d.batch_date)}}/dashboard.html">9-Panel</a></td>
        </tr>`;
      }}).join("") || '<tr><td colspan="6" class="l mut">ยังไม่มีข้อมูลรายวัน</td></tr>';
      $("alpha-days").innerHTML = `<table><thead><tr><th class="l">Date</th><th>Models</th><th>Rounds</th><th class="l">Assets</th><th>Best OOS Sh</th><th>Open</th></tr></thead><tbody>${{dayRows}}</tbody></table>`;
    }}

    function renderBeta() {{
      const b = DATA.beta || {{}};
      const pref = b.prefix || "beta";
      const top1 = (b.top_ranked || [])[0];
      $("beta-kpis").innerHTML = [
        ["Cumulative Trials", b.total_trials || 0],
        ["Qualified Top-9", `${{b.qualified_count || 0}} / ${{b.total_models || 0}}`],
        ["#1 Cashflow", top1 ? `+$${{num(top1.cashflow_net_usd, 0)}}` : "–"]
      ].map(([l, v]) => `<div class="mk"><div class="mk-l">${{esc(l)}}</div><div class="mk-v">${{esc(v)}}</div></div>`).join("");

      const topRows = (b.top_ranked || []).slice(0, 6).map((r) => `
        <tr>
          <td class="mono">#${{r.rank}}</td>
          <td class="l mono">${{esc(r.model_id)}}</td>
          <td class="mono pos">${{r.cashflow_net_usd >= 0 ? "+" : ""}}$${{num(r.cashflow_net_usd, 2)}}</td>
          <td class="mono">${{num(r.max_drawdown_pct, 2)}}%</td>
          <td class="mono">${{num(r.cashflow_to_dd_ratio, 2)}}x</td>
          <td class="mono">${{sgn(r.mtm_return_pct, 2)}}</td>
        </tr>`).join("") || '<tr><td colspan="6" class="l mut">ยังไม่มีโมเดล Beta ที่ผ่านเกณฑ์</td></tr>';
      $("beta-top").innerHTML = `<table><thead><tr><th>#</th><th class="l">Model ID</th><th>Cashflow</th><th>Max DD</th><th>CF/DD</th><th>MTM Ret</th></tr></thead><tbody>${{topRows}}</tbody></table>`;

      const dayRows = (b.days || []).slice(0, 10).map((d) => `
        <tr>
          <td class="l mono">${{esc(d.batch_date)}}</td>
          <td class="mono">${{d.model_count || 0}}</td>
          <td class="mono">${{d.qualified_count || 0}}/${{d.model_count || 0}}</td>
          <td class="mono pos">+$${{num(d.best_cashflow_usd, 0)}}</td>
          <td class="mono">${{num(d.lowest_dd_pct, 1)}}%</td>
          <td><a class="tbl-link b" href="${{esc(pref)}}/daily/${{esc(d.batch_date)}}/dashboard.html">9-Panel</a></td>
        </tr>`).join("") || '<tr><td colspan="6" class="l mut">ยังไม่มีข้อมูลรายวัน</td></tr>';
      $("beta-days").innerHTML = `<table><thead><tr><th class="l">Date</th><th>Models</th><th>Pass</th><th>Best CF</th><th>Low DD</th><th>Open</th></tr></thead><tbody>${{dayRows}}</tbody></table>`;
    }}

    function setView(mode) {{
      const grid = $("tracks-grid");
      const pa = $("panel-alpha");
      const pb = $("panel-beta");
      document.querySelectorAll(".mode-btn").forEach((btn) => btn.classList.toggle("active", btn.dataset.view === mode));
      if (mode === "alpha") {{
        grid.classList.add("single");
        pa.classList.remove("hidden");
        pb.classList.add("hidden");
      }} else if (mode === "beta") {{
        grid.classList.add("single");
        pa.classList.add("hidden");
        pb.classList.remove("hidden");
      }} else {{
        grid.classList.remove("single");
        pa.classList.remove("hidden");
        pb.classList.remove("hidden");
      }}
    }}

    document.querySelectorAll(".mode-btn").forEach((btn) => btn.addEventListener("click", () => setView(btn.dataset.view)));
    $("theme-toggle").addEventListener("click", () => {{
      document.body.classList.toggle("light");
      try {{ localStorage.setItem("am_theme", document.body.classList.contains("light") ? "light" : "dark"); }} catch (_e) {{}}
    }});
    try {{ if (localStorage.getItem("am_theme") === "light") document.body.classList.add("light"); }} catch (_e) {{}}

    renderGlobalKpis();
    renderAlpha();
    renderBeta();
    $("portal-foot").textContent = `Alpha_mining Unified Central Portal · Zero CDN / Offline Ready · Generated ${{DATA.generated_at_utc || ""}} · Exploratory research only`;
  </script>
</body>
</html>
"""
