"""Daily Beta Mining Summary Markdown & Self-Contained Offline 9-Panel HTML Dashboard Generator.

Produces two deliverables per daily mining run:
1. `daily_summary.md` — Crisp Thai/English report for GitHub/Katherine Morning Digest.
2. `dashboard.html`   — 100% self-contained interactive HTML Dashboard (zero CDN / zero
   external dependencies; opens directly in any browser online or offline) with:
   - Tab 1 (`Daily Batch — 9 Panels`): Compares ALL models in the daily batch simultaneously
     (no 2-model restriction) across all 9 interactive Canvas research panels:
       01 / Weekly Realized CF (USDT · Grouped Bars + Dashed Mean)
       02 / Accumulated Realized CF (USDT · Realized Profit Only)
       03 / Equity Returns vs ETH Benchmark (% · Daily MTM + Dashed ETH Buy & Hold)
       04 / Equity Drawdown (% · 1m Running Peak, Daily Snapshots + DD Gate Line)
       05 / Remaining Inventory (ETH · Daily Lookback)
       06 / Capital Utilization (USD · Inventory Cost + Pending)
       07 / Executed Trading Volume (ETH · Total BUY and SELL + USD Turnover Hover)
       08 / Beta & Correlation vs ETH (Daily Simple Returns)
       09 / Return Correlation Matrix (All Daily Models + ETH · RdBu Heatmap)
     plus clickable multi-model legend filter pills and Full Performance Summary Table.
   - Tab 2 (`Top-9 Ranking Board`): Cumulative leaderboard (Net Realized Cashflow DESC ->
     Max MTM DD ASC, Hard Gate: No Liquidation + live Max DD slider defaulted to 40%) +
     Isolated Model Inspector Drawer.
   - Tab 3 (`All Isolated Models`): Complete cumulative catalog table across all mined days.
"""

from __future__ import annotations

import html
import json
from typing import Any, Sequence

from .beta_store import compute_return_correlation_matrix


def render_daily_summary_markdown(
    *,
    batch_date: str,
    batch_metrics: Sequence[dict[str, Any]],
    ranking_board: dict[str, Any],
) -> str:
    """Render concise Thai/English daily Beta Mining summary + cumulative Top-9 Ranking Board."""
    rule = ranking_board.get("ranking_rule", {})
    gates = rule.get("hard_gates", {})
    max_dd = gates.get("max_drawdown_pct_limit", 40.0)
    top_n = rule.get("top_n", 9)

    lines = [
        f"# Alpha_mining — Beta Mining Daily Summary ({batch_date})",
        "",
        f"- **Generated (UTC):** `{ranking_board.get('generated_at_utc', '')}`",
        f"- **Batch Models Tested Today:** `{len(batch_metrics)}` | **Cumulative Total Trials (`N_trials`):** `{ranking_board.get('total_trials', 0)}`",
        f"- **Top-{top_n} Ranking Rule:** `Net Realized Cashflow DESC -> Max MTM DD % ASC` | **Hard Gate:** `No Liquidation` & `Max DD <= {max_dd:g}%`",
        "",
        f"## 1. สรุปโมเดลที่ Mine วันนี้ ({batch_date} — {len(batch_metrics)} โมเดล)",
        "",
        "| Model ID | Signal | Realized Cashflow | AVG Weekly | Max DD (%) | CF / DD | MTM Return | Beta / Corr | Crash -46% DD | Trades (Win%) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for m in batch_metrics:
        crash = m.get("crash_stress") or {}
        crash_dd = f"{crash['max_drawdown_pct']:.2f}%" if "max_drawdown_pct" in crash else "N/A"
        avg_wk = float(m.get("avg_weekly_cf_usd", 0.0))
        beta_v = float(m.get("beta_to_eth", 0.0))
        corr_v = float(m.get("corr_to_eth", 0.0))
        lines.append(
            f"| `{m['model_id']}` | `{m['signal_name']}` "
            f"| {m['cashflow_net_usd']:+.2f} ({m['cashflow_pct']:+.2f}%) "
            f"| {avg_wk:+.2f} "
            f"| {m['max_drawdown_pct']:.2f}% | {m['cashflow_to_dd_ratio']:.2f}x "
            f"| {m['mtm_return_pct']:+.2f}% "
            f"| {beta_v:.2f} / {corr_v:.2f} "
            f"| {crash_dd} | {m['closed_trades_count']:,} ({m['win_rate_pct']:.1f}%) |"
        )

    lines.extend(
        [
            "",
            f"## 2. Cumulative Top-{top_n} Ranking Board (Cashflow สูงสุด → DD ต่ำสุด)",
            "",
            "| Rank | Model ID | Trial # | Batch Date | Realized Cashflow | Max DD (%) | CF / DD | MTM Return | Liquidated? |",
            "|---:|---|---:|---|---:|---:|---:|---:|---|",
        ]
    )

    top_rows = ranking_board.get("top_ranked", [])
    if not top_rows:
        lines.append("| - | ไม่มีโมเดลที่ผ่าน Hard Gate ในรอบนี้ | - | - | - | - | - | - | - |")
    else:
        for r in top_rows:
            liq = "YES" if r.get("would_liquidate") else "NO"
            lines.append(
                f"| **#{r['rank']}** | `{r['model_id']}` | #{r.get('trial_number', '?')} "
                f"| `{r.get('batch_date', '')}` | **{r['cashflow_net_usd']:+.2f}** "
                f"| {r['max_drawdown_pct']:.2f}% | {r['cashflow_to_dd_ratio']:.2f}x "
                f"| {r['mtm_return_pct']:+.2f}% | {liq} |"
            )

    disq = ranking_board.get("disqualified", [])
    if disq:
        lines.extend(["", "### โมเดลที่ไม่ผ่าน Hard Gate (Disqualified)", ""])
        for d in disq:
            reasons = ", ".join(d.get("disqualify_reasons", []))
            lines.append(
                f"- `{d['model_id']}`: Cashflow `{d['cashflow_net_usd']:+.2f}`, "
                f"Max DD `{d['max_drawdown_pct']:.2f}%` — เหตุผล: `{reasons}`"
            )

    lines.append("")
    return "\n".join(lines)


def _compact_series_for_html(
    batch_ids: Sequence[str],
    batch_series: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build compact shared-axis time-series bundle for embedding in offline HTML (zero bloat)."""
    if not batch_series:
        return {"dates": [], "eth_return": [], "weeks": [], "by_model": {}}

    ordered_with_series = [mid for mid in batch_ids if mid in batch_series and batch_series[mid]]
    if not ordered_with_series:
        return {"dates": [], "eth_return": [], "weeks": [], "by_model": {}}

    ref = batch_series[ordered_with_series[0]]
    shared_dates = list(ref.get("dates") or [])
    shared_eth = list(ref.get("eth_return") or [])
    shared_weeks = list(ref.get("weeks") or [])

    by_model: dict[str, dict[str, Any]] = {}
    for mid in ordered_with_series:
        s = batch_series[mid]
        entry: dict[str, Any] = {
            "equity": s.get("equity") or [],
            "cf": s.get("cf") or [],
            "dd": s.get("dd") or [],
            "inventory": s.get("inventory") or [],
            "capital": s.get("capital") or [],
            "weekly": s.get("weekly") or [],
        }
        if (s.get("dates") or []) != shared_dates:
            entry["dates"] = s.get("dates") or []
        if (s.get("weeks") or []) != shared_weeks:
            entry["weeks"] = s.get("weeks") or []
        by_model[mid] = entry

    return {
        "dates": shared_dates,
        "eth_return": shared_eth,
        "weeks": shared_weeks,
        "by_model": by_model,
    }


def render_dashboard_html(
    *,
    batch_date: str,
    batch_metrics: Sequence[dict[str, Any]],
    all_models_metrics: Sequence[dict[str, Any]],
    ranking_board: dict[str, Any],
    batch_series: dict[str, dict[str, Any]] | None = None,
    corr_matrix: dict[str, Any] | None = None,
    default_tab: str = "daily",
) -> str:
    """Render a 100% self-contained offline-ready 9-panel interactive HTML Dashboard (zero CDN dependencies)."""
    rule = ranking_board.get("ranking_rule", {})
    default_dd_cap = float(rule.get("hard_gates", {}).get("max_drawdown_pct_limit", 40.0))
    top_n = int(rule.get("top_n", 9))
    batch_ids = [m["model_id"] for m in batch_metrics]
    active_tab = default_tab if default_tab in {"daily", "ranking", "all"} else "daily"

    resolved_corr = corr_matrix
    if resolved_corr is None and batch_series:
        resolved_corr = compute_return_correlation_matrix(batch_ids, batch_series)
    if resolved_corr is None:
        resolved_corr = {"labels": [], "matrix": []}

    embedded_data = {
        "batch_date": batch_date,
        "generated_at_utc": ranking_board.get("generated_at_utc", ""),
        "total_trials": int(ranking_board.get("total_trials", len(all_models_metrics))),
        "top_n": top_n,
        "default_dd_cap": default_dd_cap,
        "default_tab": active_tab,
        "batch_ids": batch_ids,
        "models": list(all_models_metrics),
        "series": _compact_series_for_html(batch_ids, batch_series),
        "corr_matrix": resolved_corr,
    }
    safe_json = json.dumps(embedded_data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    safe_date = html.escape(batch_date)

    daily_active = " active" if active_tab == "daily" else ""
    ranking_active = " active" if active_tab == "ranking" else ""
    all_active = " active" if active_tab == "all" else ""
    daily_cls = "stack" if active_tab == "daily" else "stack hidden"
    ranking_cls = "stack" if active_tab == "ranking" else "stack hidden"
    all_cls = "card" if active_tab == "all" else "card hidden"

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Alpha_mining — Beta Mining 9-Panel Dashboard ({safe_date})</title>
  <style>
    :root {{
      --bm-bg: #0b1017;
      --bm-card: #121923;
      --bm-surface: #192331;
      --bm-border: #263244;
      --bm-fg: #e6edf6;
      --bm-muted: #8ea0b8;
      --bm-primary: #3b82f6;
      --bm-primary-fg: #ffffff;
      --bm-success: #22c55e;
      --bm-warning: #f59e0b;
      --bm-error: #ef4444;
      --bm-code-fg: #93c5fd;
      --bm-grid: rgba(148, 163, 184, 0.14);
      --bm-axis: #94a3b8;
      --bm-tooltip-bg: rgba(11, 16, 23, 0.96);
    }}
    body.light {{
      --bm-bg: #f4f7fb;
      --bm-card: #ffffff;
      --bm-surface: #eef2f7;
      --bm-border: #d7e0eb;
      --bm-fg: #0f172a;
      --bm-muted: #526277;
      --bm-primary: #2563eb;
      --bm-primary-fg: #ffffff;
      --bm-success: #16a34a;
      --bm-warning: #d97706;
      --bm-error: #dc2626;
      --bm-code-fg: #1d4ed8;
      --bm-grid: rgba(15, 23, 42, 0.10);
      --bm-axis: #475569;
      --bm-tooltip-bg: rgba(255, 255, 255, 0.97);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 18px 20px 36px;
      background: var(--bm-bg);
      color: var(--bm-fg);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 13px;
      line-height: 1.45;
    }}
    .wrap {{ max-width: 1460px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }}
    .header {{
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
      gap: 12px; padding-bottom: 12px; border-bottom: 1px solid var(--bm-border);
    }}
    .title {{ margin: 0; font-size: 19px; font-weight: 700; letter-spacing: -0.01em; }}
    .subtitle {{ margin: 3px 0 0; color: var(--bm-muted); font-size: 12px; }}
    .tabs {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    button {{
      cursor: pointer; border: 1px solid var(--bm-border); border-radius: 8px;
      padding: 7px 12px; font-size: 12px; font-weight: 600;
      background: var(--bm-card); color: var(--bm-fg); transition: border-color 0.15s, background 0.15s;
    }}
    button:hover {{ border-color: var(--bm-primary); }}
    button.active {{ background: var(--bm-primary); color: var(--bm-primary-fg); border-color: var(--bm-primary); }}
    .grid-4 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .card {{
      background: var(--bm-card); border: 1px solid var(--bm-border); border-radius: 12px; padding: 14px;
    }}
    .kpi-label {{ font-size: 12px; color: var(--bm-muted); }}
    .kpi-val {{ font-size: 20px; font-weight: 700; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin: 3px 0; }}
    .controls {{
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px;
      background: var(--bm-card); border: 1px solid var(--bm-border); border-radius: 12px; padding: 11px 14px;
    }}
    select, input[type="range"] {{
      background: var(--bm-surface); color: var(--bm-fg); border: 1px solid var(--bm-border);
      border-radius: 6px; padding: 5px 8px; font-size: 12px;
    }}
    .split {{ display: grid; grid-template-columns: 2fr 1fr; gap: 14px; align-items: start; }}
    .dash-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .panel-wide {{ grid-column: 1 / -1; }}
    @media (max-width: 980px) {{
      .split {{ grid-template-columns: 1fr; }}
      .dash-grid {{ grid-template-columns: 1fr; }}
    }}
    .panel {{
      background: var(--bm-card); border: 1px solid var(--bm-border); border-radius: 12px;
      padding: 12px 14px 10px; display: flex; flex-direction: column; gap: 6px; min-width: 0;
    }}
    .panel-hdr {{
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 6px;
      border-bottom: 1px solid var(--bm-border); padding-bottom: 7px;
    }}
    .panel-title {{ font-size: 13px; font-weight: 700; letter-spacing: 0.01em; }}
    .panel-sub {{ font-size: 11px; color: var(--bm-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .canvas-box {{ position: relative; width: 100%; height: 290px; }}
    .canvas-box.tall {{ height: 340px; }}
    .canvas-box canvas {{ display: block; width: 100%; height: 100%; cursor: crosshair; }}
    .legend-bar {{
      display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
      background: var(--bm-card); border: 1px solid var(--bm-border); border-radius: 12px; padding: 10px 14px;
    }}
    .pill {{
      display: inline-flex; align-items: center; gap: 7px; padding: 5px 10px; border-radius: 999px;
      border: 1px solid var(--bm-border); background: var(--bm-surface); color: var(--bm-fg);
      font-size: 12px; font-weight: 600; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      cursor: pointer; user-select: none; transition: opacity 0.15s, border-color 0.15s;
    }}
    .pill.off {{ opacity: 0.35; }}
    .pill .dot {{ width: 9px; height: 9px; border-radius: 50%; flex: none; }}
    .pill-mini {{
      padding: 4px 9px; font-size: 11px; border-radius: 7px; background: var(--bm-card);
      border: 1px solid var(--bm-border); color: var(--bm-muted); font-weight: 600;
    }}
    .pill-mini:hover {{ color: var(--bm-fg); border-color: var(--bm-primary); }}
    .batch-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(215px, 1fr)); gap: 10px; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--bm-border); text-align: left; white-space: nowrap; }}
    th {{ color: var(--bm-muted); font-weight: 600; }}
    td.num, th.num {{ text-align: right; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    tr.data-row {{ cursor: pointer; }}
    tr.data-row:hover, tr.data-row.selected {{ background: var(--bm-surface); }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .pos {{ color: var(--bm-success); }}
    .warn {{ color: var(--bm-warning); }}
    .neg {{ color: var(--bm-error); }}
    .muted {{ color: var(--bm-muted); }}
    .badge {{
      display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 700;
    }}
    .badge-pass {{ background: rgba(34, 197, 94, 0.16); color: var(--bm-success); }}
    .badge-fail {{ background: rgba(239, 68, 68, 0.18); color: var(--bm-error); }}
    .badge-today {{ background: rgba(59, 130, 246, 0.18); color: var(--bm-code-fg); }}
    .kv-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 10px 0; }}
    .kv-box {{ background: var(--bm-surface); border: 1px solid var(--bm-border); border-radius: 8px; padding: 9px 11px; }}
    pre {{
      background: var(--bm-surface); border: 1px solid var(--bm-border); border-radius: 8px;
      padding: 10px; overflow-x: auto; font-size: 12px; color: var(--bm-code-fg); margin: 6px 0 0;
    }}
    .stack {{ display: flex; flex-direction: column; gap: 14px; }}
    .hidden {{ display: none !important; }}
    .chart-tooltip {{
      position: fixed; z-index: 9999; pointer-events: none; display: none;
      background: var(--bm-tooltip-bg); color: var(--bm-fg);
      border: 1px solid var(--bm-border); border-radius: 9px; padding: 9px 11px;
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.35); font-size: 12px; min-width: 210px; max-width: 340px;
    }}
    .tt-title {{
      font-weight: 700; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      margin-bottom: 5px; padding-bottom: 4px; border-bottom: 1px solid var(--bm-border);
    }}
    .tt-row {{
      display: flex; justify-content: space-between; align-items: center; gap: 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin: 2px 0;
    }}
    .tt-lbl {{ display: inline-flex; align-items: center; gap: 6px; overflow: hidden; text-overflow: ellipsis; }}
    .tt-dot {{ width: 8px; height: 8px; border-radius: 50%; flex: none; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="header">
      <div>
        <h1 class="title">Alpha_mining — Beta Mining 9-Panel Research Dashboard ({safe_date})</h1>
        <p id="hdr-sub" class="subtitle"></p>
      </div>
      <div class="tabs">
        <button data-tab="daily" class="tab-btn{daily_active}">Daily Batch — 9 Panels</button>
        <button data-tab="ranking" class="tab-btn{ranking_active}">Top-{top_n} Ranking Board</button>
        <button data-tab="all" class="tab-btn{all_active}">All Isolated Models</button>
        <button id="theme-toggle" type="button" title="Toggle Light/Dark">Theme</button>
      </div>
    </header>

    <section class="grid-4">
      <div class="card">
        <div class="kpi-label">Total Mined Trials (N_trials)</div>
        <div id="kpi-trials" class="kpi-val">-</div>
        <div id="kpi-today" class="kpi-label">-</div>
      </div>
      <div class="card">
        <div class="kpi-label">Qualified for Top-{top_n}</div>
        <div id="kpi-qual" class="kpi-val pos">-</div>
        <div id="kpi-gate" class="kpi-label">-</div>
      </div>
      <div class="card">
        <div class="kpi-label">#1 Top Cashflow Leader</div>
        <div id="kpi-top1" class="kpi-val" style="font-size:16px">-</div>
        <div id="kpi-top1-sub" class="kpi-label pos mono">-</div>
      </div>
      <div class="card">
        <div class="kpi-label">Lowest Max DD (Qualified)</div>
        <div id="kpi-lowdd" class="kpi-val" style="font-size:16px">-</div>
        <div id="kpi-lowdd-sub" class="kpi-label warn mono">-</div>
      </div>
    </section>

    <!-- TAB 1: DAILY BATCH 9-PANEL MULTI-MODEL RESEARCH DASHBOARD -->
    <section id="view-daily" class="{daily_cls}">
      <div class="legend-bar">
        <span class="muted" style="font-weight:700;margin-right:4px;">Models ({safe_date}):</span>
        <div id="daily-legend-pills" style="display:flex;flex-wrap:wrap;gap:7px;flex:1;"></div>
        <div style="display:flex;gap:6px;align-items:center;">
          <button id="btn-show-all" type="button" class="pill-mini">Show All</button>
          <button id="btn-top3" type="button" class="pill-mini">Top 3 CF</button>
          <span class="muted" style="font-size:11px;">คลิกเปิด/ปิด · ดับเบิลคลิกดูเดี่ยว</span>
        </div>
      </div>

      <div id="daily-cards" class="batch-grid"></div>

      <div class="dash-grid">
        <div class="panel">
          <div class="panel-hdr">
            <span class="panel-title">01 / Weekly Realized CF</span>
            <span class="panel-sub">USDT · Grouped Bars + Dashed Mean</span>
          </div>
          <div class="canvas-box"><canvas id="chart-weekly"></canvas></div>
        </div>

        <div class="panel">
          <div class="panel-hdr">
            <span class="panel-title">02 / Accumulated Realized CF</span>
            <span class="panel-sub">USDT · Realized Profit Only</span>
          </div>
          <div class="canvas-box"><canvas id="chart-cumulative"></canvas></div>
        </div>

        <div class="panel">
          <div class="panel-hdr">
            <span class="panel-title">03 / Equity Returns vs ETH Benchmark</span>
            <span class="panel-sub">% · Daily MTM + Dashed ETH Buy &amp; Hold</span>
          </div>
          <div class="canvas-box"><canvas id="chart-equity"></canvas></div>
        </div>

        <div class="panel">
          <div class="panel-hdr">
            <span class="panel-title">04 / Equity Drawdown</span>
            <span class="panel-sub">% · 1m Running Peak, Daily Snapshots</span>
          </div>
          <div class="canvas-box"><canvas id="chart-drawdown"></canvas></div>
        </div>

        <div class="panel">
          <div class="panel-hdr">
            <span class="panel-title">05 / Remaining Inventory</span>
            <span class="panel-sub">ETH · Daily Lookback</span>
          </div>
          <div class="canvas-box"><canvas id="chart-inventory"></canvas></div>
        </div>

        <div class="panel">
          <div class="panel-hdr">
            <span class="panel-title">06 / Capital Utilization</span>
            <span class="panel-sub">USD · Inventory Cost + Pending</span>
          </div>
          <div class="canvas-box"><canvas id="chart-utilization"></canvas></div>
        </div>

        <div class="panel">
          <div class="panel-hdr">
            <span class="panel-title">07 / Executed Trading Volume</span>
            <span class="panel-sub">ETH · Total BUY (Green) &amp; SELL (Blue)</span>
          </div>
          <div class="canvas-box"><canvas id="chart-volume"></canvas></div>
        </div>

        <div class="panel">
          <div class="panel-hdr">
            <span class="panel-title">08 / Beta &amp; Correlation vs ETH</span>
            <span class="panel-sub">Daily Simple Returns · Beta (Amber) &amp; Corr (Violet)</span>
          </div>
          <div class="canvas-box"><canvas id="chart-betacorr"></canvas></div>
        </div>

        <div class="panel panel-wide">
          <div class="panel-hdr">
            <span class="panel-title">09 / Return Correlation Matrix</span>
            <span class="panel-sub">All Active Daily Models + ETH · RdBu Diverging [-1.0 .. +1.0]</span>
          </div>
          <div class="canvas-box tall"><canvas id="chart-heatmap"></canvas></div>
        </div>
      </div>

      <div class="card" style="padding:0;overflow:hidden;">
        <div style="padding:10px 14px;border-bottom:1px solid var(--bm-border);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
          <strong>Full Performance Summary — Daily Batch ({safe_date})</strong>
          <span class="muted">คลิกแถวเพื่อเปิดดูรายละเอียดโมเดลในแท็บ Top-{top_n} Inspector</span>
        </div>
        <div class="table-wrap">
          <table id="daily-perf-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Signal</th>
                <th class="num">Final Equity</th>
                <th class="num">Return %</th>
                <th class="num">Max DD %</th>
                <th class="num">Realized CF</th>
                <th class="num">Unrealized</th>
                <th class="num">AVG Weekly</th>
                <th class="num">Buy / Sell Fills</th>
                <th class="num">Buy / Sell ETH</th>
                <th class="num">End ETH</th>
                <th class="num">Max Util %</th>
                <th class="num">Beta / Corr</th>
                <th style="text-align:center;">Gate</th>
              </tr>
            </thead>
            <tbody id="daily-perf-body"></tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- TAB 2: TOP-9 RANKING BOARD -->
    <section id="view-ranking" class="{ranking_cls}">
      <div class="controls">
        <div style="display:flex;flex-wrap:wrap;gap:12px;align-items:center;">
          <label>
            <span class="muted">Ranking Mode:</span>
            <select id="rank-mode">
              <option value="cashflow_dd" selected>Cashflow สูงสุด → Max DD ต่ำสุด (Default)</option>
              <option value="efficiency">Cashflow / Max DD Efficiency</option>
              <option value="mtm">Total MTM Return</option>
            </select>
          </label>
          <label style="display:flex;align-items:center;gap:6px;">
            <input id="only-today" type="checkbox" />
            <span>เฉพาะ Batch วันนี้ ({safe_date})</span>
          </label>
        </div>
        <div style="display:flex;align-items:center;gap:10px;">
          <span class="muted">Max DD Gate:</span>
          <input id="dd-slider" type="range" min="10" max="50" step="1" value="{int(round(default_dd_cap))}" />
          <strong id="dd-label" class="mono">≤ {int(round(default_dd_cap))}%</strong>
        </div>
      </div>

      <div class="split">
        <div class="card" style="padding:0;overflow:hidden;">
          <div style="padding:10px 14px;border-bottom:1px solid var(--bm-border);display:flex;justify-content:space-between;">
            <strong>Top-{top_n} Cashflow → DD Ranking Board (คลิกแถวเพื่อดู Isolated Model)</strong>
            <span class="muted">Hard Gate: No Liq + Max DD</span>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Model ID / Signal</th>
                  <th class="num">Cashflow ($)</th>
                  <th class="num">AVG Wk ($)</th>
                  <th class="num">Max DD</th>
                  <th class="num">CF/DD</th>
                  <th class="num">MTM</th>
                  <th class="num">Crash DD</th>
                  <th style="text-align:center;">Gate</th>
                </tr>
              </thead>
              <tbody id="rank-body"></tbody>
            </table>
          </div>
        </div>

        <div class="card">
          <div style="border-bottom:1px solid var(--bm-border);padding-bottom:8px;margin-bottom:8px;">
            <div class="muted" style="font-size:11px;">Isolated Model Inspector</div>
            <div id="insp-id" class="mono" style="font-size:15px;font-weight:700;">-</div>
            <div id="insp-meta" class="muted" style="font-size:12px;">-</div>
          </div>
          <div class="kv-grid">
            <div class="kv-box"><div class="kpi-label">Realized Cashflow</div><div id="insp-cf" class="mono pos" style="font-weight:700;">-</div></div>
            <div class="kv-box"><div class="kpi-label">Max MTM DD</div><div id="insp-dd" class="mono warn" style="font-weight:700;">-</div></div>
            <div class="kv-box"><div class="kpi-label">AVG Weekly CF</div><div id="insp-wk" class="mono pos" style="font-weight:700;">-</div></div>
            <div class="kv-box"><div class="kpi-label">Beta / Corr vs ETH</div><div id="insp-bc" class="mono" style="font-weight:700;">-</div></div>
            <div class="kv-box"><div class="kpi-label">Unrealized End</div><div id="insp-unr" class="mono neg" style="font-weight:700;">-</div></div>
            <div class="kv-box"><div class="kpi-label">Fees / Funding</div><div id="insp-cost" class="mono" style="font-weight:700;">-</div></div>
            <div class="kv-box"><div class="kpi-label">Trades (Win%)</div><div id="insp-tr" class="mono" style="font-weight:700;">-</div></div>
            <div class="kv-box"><div class="kpi-label">Max / End Open</div><div id="insp-qty" class="mono" style="font-weight:700;">-</div></div>
          </div>
          <div style="margin-top:8px;">
            <div class="kpi-label">Isolated Path</div>
            <pre id="insp-path">-</pre>
          </div>
          <div style="margin-top:8px;">
            <div class="kpi-label">1-Line Reuse (CLI &amp; Python)</div>
            <pre id="insp-cmd">-</pre>
          </div>
        </div>
      </div>
    </section>

    <!-- TAB 3: ALL ISOLATED MODELS -->
    <section id="view-all" class="{all_cls}" style="padding:0;overflow:hidden;">
      <div style="padding:10px 14px;border-bottom:1px solid var(--bm-border);font-weight:700;">All Isolated Models in Store</div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Trial</th>
              <th>Model ID</th>
              <th>Signal</th>
              <th>Batch Date</th>
              <th>Zone</th>
              <th class="num">Cashflow ($)</th>
              <th class="num">AVG Wk ($)</th>
              <th class="num">Max DD</th>
              <th class="num">MTM %</th>
              <th class="num">Beta / Corr</th>
              <th class="num">Trades</th>
            </tr>
          </thead>
          <tbody id="all-body"></tbody>
        </table>
      </div>
    </section>
  </div>

  <div id="chart-tooltip" class="chart-tooltip"></div>

  <script>
    const PAYLOAD = {safe_json};
    const BATCH_IDS = PAYLOAD.batch_ids || [];
    const BATCH_SET = new Set(BATCH_IDS);
    const PALETTE = [
      "#22c55e", "#3b82f6", "#f59e0b", "#a855f7",
      "#06b6d4", "#f43f5e", "#84cc16", "#ec4899", "#fb923c"
    ];

    const MODEL_MAP = new Map((PAYLOAD.models || []).map(m => [m.model_id, m]));
    const DAILY_MODELS = BATCH_IDS.map(id => MODEL_MAP.get(id)).filter(Boolean);
    const MODEL_COLOR = new Map();
    DAILY_MODELS.forEach((m, idx) => MODEL_COLOR.set(m.model_id, PALETTE[idx % PALETTE.length]));

    const visibleIds = new Set(DAILY_MODELS.map(m => m.model_id));
    let selectedId = (DAILY_MODELS[0] && DAILY_MODELS[0].model_id) || (PAYLOAD.models[0] && PAYLOAD.models[0].model_id) || "";
    let currentTab = PAYLOAD.default_tab || "daily";

    const hoverState = {{}};
    const tooltipEl = document.getElementById("chart-tooltip");

    function shortLabel(modelId) {{
      return String(modelId || "").replace(/^beta_\\d+_/, "");
    }}

    function fmtUsd(v, signed = true) {{
      const n = Number(v || 0);
      const abs = Math.abs(n).toLocaleString("en-US", {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
      if (!signed) return "$" + abs;
      return (n >= 0 ? "+$" : "-$") + abs;
    }}

    function fmtPct(v, signed = true, digits = 2) {{
      const n = Number(v || 0);
      const s = Math.abs(n).toFixed(digits) + "%";
      if (!signed) return s;
      return (n >= 0 ? "+" : "-") + s;
    }}

    function fmtNum(v, digits = 2) {{
      return Number(v || 0).toLocaleString("en-US", {{ minimumFractionDigits: digits, maximumFractionDigits: digits }});
    }}

    function getThemeColors() {{
      const st = getComputedStyle(document.body);
      const isLight = document.body.classList.contains("light") || document.documentElement.classList.contains("light");
      return {{
        isLight,
        fg: (st.getPropertyValue("--bm-fg") || "#e6edf6").trim(),
        muted: (st.getPropertyValue("--bm-muted") || "#8ea0b8").trim(),
        grid: (st.getPropertyValue("--bm-grid") || "rgba(148,163,184,0.14)").trim(),
        axis: (st.getPropertyValue("--bm-axis") || "#94a3b8").trim(),
        border: (st.getPropertyValue("--bm-border") || "#263244").trim(),
        surface: (st.getPropertyValue("--bm-surface") || "#192331").trim(),
        eth: isLight ? "#475569" : "#94a3b8",
        gate: isLight ? "rgba(220, 38, 38, 0.55)" : "rgba(239, 68, 68, 0.55)"
      }};
    }}

    function getActiveModels() {{
      return DAILY_MODELS.filter(m => visibleIds.has(m.model_id));
    }}

    function showTooltip(clientX, clientY, title, rows) {{
      let htmlRows = rows.map(r => `
        <div class="tt-row">
          <span class="tt-lbl">
            ${{r.color ? `<span class="tt-dot" style="background:${{r.color}}"></span>` : ""}}
            <span>${{r.label}}</span>
          </span>
          <strong style="color:${{r.valColor || "inherit"}}">${{r.value}}</strong>
        </div>
      `).join("");
      tooltipEl.innerHTML = `<div class="tt-title">${{title}}</div>${{htmlRows}}`;
      tooltipEl.style.display = "block";
      const pad = 14;
      const rect = tooltipEl.getBoundingClientRect();
      let left = clientX + pad;
      let top = clientY + pad;
      if (left + rect.width > window.innerWidth - 10) left = clientX - rect.width - pad;
      if (top + rect.height > window.innerHeight - 10) top = clientY - rect.height - pad;
      tooltipEl.style.left = Math.max(8, left) + "px";
      tooltipEl.style.top = Math.max(8, top) + "px";
    }}

    function hideTooltip() {{
      tooltipEl.style.display = "none";
    }}

    function setupCanvas(canvas) {{
      if (!canvas) return null;
      const rect = canvas.getBoundingClientRect();
      const w = Math.floor(rect.width);
      const h = Math.floor(rect.height);
      if (w <= 10 || h <= 10) return null;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const pw = Math.round(w * dpr);
      const ph = Math.round(h * dpr);
      if (canvas.width !== pw || canvas.height !== ph) {{
        canvas.width = pw;
        canvas.height = ph;
      }}
      const ctx = canvas.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      return {{ ctx, w, h }};
    }}

    function drawEmptyMsg(ctx, w, h, text, theme) {{
      ctx.fillStyle = theme.muted;
      ctx.font = "12px -apple-system, BlinkMacSystemFont, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(text, w / 2, h / 2);
    }}

    function computeNiceTicks(minV, maxV, count = 5) {{
      if (!isFinite(minV) || !isFinite(maxV)) return {{ lo: 0, hi: 1, ticks: [0, 0.5, 1] }};
      if (Math.abs(maxV - minV) < 1e-9) {{
        const pad = Math.abs(maxV) > 1e-6 ? Math.abs(maxV) * 0.2 : 1;
        minV -= pad;
        maxV += pad;
      }}
      const range = maxV - minV;
      const rawStep = range / Math.max(2, count - 1);
      const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
      const norm = rawStep / mag;
      let step = mag;
      if (norm > 5) step = 10 * mag;
      else if (norm > 2) step = 5 * mag;
      else if (norm > 1) step = 2 * mag;
      const lo = Math.floor(minV / step) * step;
      const hi = Math.ceil(maxV / step) * step;
      const ticks = [];
      for (let v = lo; v <= hi + step * 0.25; v += step) {{
        ticks.push(Math.abs(v) < 1e-12 ? 0 : v);
      }}
      return {{ lo, hi, ticks }};
    }}

    function drawLineChart(canvasId, opts) {{
      const canvas = document.getElementById(canvasId);
      const setup = setupCanvas(canvas);
      if (!setup) return;
      const {{ ctx, w, h }} = setup;
      const theme = getThemeColors();
      const dates = opts.dates || [];
      const lines = opts.lines || [];

      if (!dates.length || !lines.length) {{
        drawEmptyMsg(ctx, w, h, "No daily series available — run beta_mining.py run-daily", theme);
        canvas._hitMeta = null;
        return;
      }}

      let minV = opts.forceMin !== undefined ? opts.forceMin : Infinity;
      let maxV = opts.forceMax !== undefined ? opts.forceMax : -Infinity;
      lines.forEach(s => {{
        (s.values || []).forEach(v => {{
          if (v !== null && v !== undefined && isFinite(v)) {{
            if (v < minV) minV = v;
            if (v > maxV) maxV = v;
          }}
        }});
      }});
      if (opts.refLine !== undefined && isFinite(opts.refLine)) {{
        if (opts.refLine < minV) minV = opts.refLine;
        if (opts.refLine > maxV) maxV = opts.refLine;
      }}
      if (opts.includeZero) {{
        if (0 < minV) minV = 0;
        if (0 > maxV) maxV = 0;
      }}
      const span = Math.max(1e-6, maxV - minV);
      const padTop = opts.forceMax !== undefined ? 0 : span * 0.06;
      const padBot = opts.forceMin !== undefined ? 0 : span * 0.06;
      const {{ lo, hi, ticks }} = computeNiceTicks(minV - padBot, maxV + padTop, 5);

      const padL = 62, padR = 14, padT = 12, padB = 26;
      const plotW = Math.max(20, w - padL - padR);
      const plotH = Math.max(20, h - padT - padB);
      const n = dates.length;
      const xAt = idx => (n <= 1 ? padL + plotW / 2 : padL + (idx / (n - 1)) * plotW);
      const yAt = val => padT + (1 - (val - lo) / Math.max(1e-9, hi - lo)) * plotH;

      // Grid & Y-axis labels
      ctx.font = "11px ui-monospace, SFMono-Regular, Menlo, monospace";
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ticks.forEach(t => {{
        const y = yAt(t);
        ctx.strokeStyle = Math.abs(t) < 1e-9 ? theme.axis : theme.grid;
        ctx.lineWidth = Math.abs(t) < 1e-9 ? 1 : 0.8;
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(w - padR, y);
        ctx.stroke();
        ctx.fillStyle = theme.axis;
        ctx.fillText(opts.yFmt(t), padL - 7, y);
      }});

      // Optional horizontal reference line (e.g. -40% DD Gate, Initial Capital, Max ETH Cap)
      if (opts.refLine !== undefined && opts.refLine >= lo && opts.refLine <= hi) {{
        const ry = yAt(opts.refLine);
        ctx.save();
        ctx.strokeStyle = opts.refColor || theme.gate;
        ctx.setLineDash([5, 4]);
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(padL, ry);
        ctx.lineTo(w - padR, ry);
        ctx.stroke();
        ctx.setLineDash([]);
        if (opts.refLabel) {{
          ctx.fillStyle = opts.refColor || theme.gate;
          ctx.textAlign = "right";
          ctx.textBaseline = "bottom";
          ctx.fillText(opts.refLabel, w - padR - 4, ry - 2);
        }}
        ctx.restore();
      }}

      // X-axis date ticks
      ctx.fillStyle = theme.axis;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      const xTicks = Math.min(n, Math.max(2, Math.floor(plotW / 105)));
      for (let k = 0; k < xTicks; k++) {{
        const idx = xTicks <= 1 ? 0 : Math.round((k / (xTicks - 1)) * (n - 1));
        const x = xAt(idx);
        const lbl = String(dates[idx] || "").slice(0, 10);
        ctx.fillText(lbl, Math.min(w - padR - 26, Math.max(padL + 26, x)), padT + plotH + 7);
      }}

      // Series lines (ETH benchmark drawn first behind strategy lines)
      const ordered = [...lines].sort((a, b) => (a.dashed ? -1 : 0) - (b.dashed ? -1 : 0));
      ordered.forEach(s => {{
        const vals = s.values || [];
        if (!vals.length) return;
        ctx.save();
        ctx.strokeStyle = s.color;
        ctx.lineWidth = s.dashed ? 1.7 : 2.0;
        if (s.dashed) ctx.setLineDash([6, 4]);
        if (opts.fillToZero && !s.dashed && vals.length > 1) {{
          const zeroY = yAt(Math.min(hi, Math.max(lo, 0)));
          ctx.beginPath();
          ctx.moveTo(xAt(0), zeroY);
          for (let i = 0; i < vals.length; i++) ctx.lineTo(xAt(i), yAt(vals[i]));
          ctx.lineTo(xAt(vals.length - 1), zeroY);
          ctx.closePath();
          ctx.fillStyle = s.color + "18";
          ctx.fill();
        }}
        ctx.beginPath();
        for (let i = 0; i < vals.length; i++) {{
          const x = xAt(i);
          const y = yAt(vals[i]);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }}
        ctx.stroke();
        if (vals.length === 1) {{
          ctx.fillStyle = s.color;
          ctx.beginPath();
          ctx.arc(xAt(0), yAt(vals[0]), 4, 0, Math.PI * 2);
          ctx.fill();
        }}
        ctx.restore();
      }});

      // Hover crosshair
      const hIdx = hoverState[canvasId];
      if (hIdx !== undefined && hIdx >= 0 && hIdx < n) {{
        const hx = xAt(hIdx);
        ctx.save();
        ctx.strokeStyle = theme.muted;
        ctx.setLineDash([3, 3]);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(hx, padT);
        ctx.lineTo(hx, padT + plotH);
        ctx.stroke();
        ctx.setLineDash([]);
        lines.forEach(s => {{
          const v = (s.values || [])[hIdx];
          if (v !== undefined && isFinite(v)) {{
            ctx.fillStyle = s.color;
            ctx.beginPath();
            ctx.arc(hx, yAt(v), 3.8, 0, Math.PI * 2);
            ctx.fill();
          }}
        }});
        ctx.restore();
      }}

      canvas._hitMeta = {{ type: "line", padL, padR, padT, plotW, plotH, n, dates, lines, valFmt: opts.valFmt }};
    }}

    function drawWeeklyGroupedBars(canvasId) {{
      const canvas = document.getElementById(canvasId);
      const setup = setupCanvas(canvas);
      if (!setup) return;
      const {{ ctx, w, h }} = setup;
      const theme = getThemeColors();
      const sBundle = PAYLOAD.series || {{}};
      const weeks = sBundle.weeks || [];
      const active = getActiveModels();
      const seriesList = active.map(m => ({{
        id: m.model_id,
        label: shortLabel(m.model_id),
        color: MODEL_COLOR.get(m.model_id) || "#22c55e",
        values: (sBundle.by_model && sBundle.by_model[m.model_id] && sBundle.by_model[m.model_id].weekly) || [],
        mean: Number(m.avg_weekly_cf_usd || 0)
      }})).filter(s => s.values.length > 0);

      if (!weeks.length || !seriesList.length) {{
        drawEmptyMsg(ctx, w, h, "No weekly cashflow series available", theme);
        canvas._hitMeta = null;
        return;
      }}

      let minV = 0, maxV = 0;
      seriesList.forEach(s => {{
        s.values.forEach(v => {{
          if (v < minV) minV = v;
          if (v > maxV) maxV = v;
        }});
        if (s.mean > maxV) maxV = s.mean;
      }});
      const {{ lo, hi, ticks }} = computeNiceTicks(minV, maxV * 1.08, 5);
      const padL = 62, padR = 14, padT = 12, padB = 26;
      const plotW = Math.max(20, w - padL - padR);
      const plotH = Math.max(20, h - padT - padB);
      const n = weeks.length;
      const mCount = seriesList.length;
      const groupW = plotW / n;
      const innerPad = Math.min(2, groupW * 0.14);
      const barW = Math.max(1, (groupW - innerPad) / mCount);
      const yAt = val => padT + (1 - (val - lo) / Math.max(1e-9, hi - lo)) * plotH;
      const zeroY = yAt(0);

      ctx.font = "11px ui-monospace, SFMono-Regular, Menlo, monospace";
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ticks.forEach(t => {{
        const y = yAt(t);
        ctx.strokeStyle = Math.abs(t) < 1e-9 ? theme.axis : theme.grid;
        ctx.lineWidth = Math.abs(t) < 1e-9 ? 1 : 0.8;
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(w - padR, y);
        ctx.stroke();
        ctx.fillStyle = theme.axis;
        ctx.fillText("$" + Math.round(t).toLocaleString("en-US"), padL - 7, y);
      }});

      // Hover week highlight band
      const hIdx = hoverState[canvasId];
      if (hIdx !== undefined && hIdx >= 0 && hIdx < n) {{
        ctx.fillStyle = theme.isLight ? "rgba(37, 99, 235, 0.10)" : "rgba(59, 130, 246, 0.16)";
        ctx.fillRect(padL + hIdx * groupW, padT, Math.max(4, groupW), plotH);
      }}

      // Grouped bars
      for (let i = 0; i < n; i++) {{
        const gx = padL + i * groupW + innerPad * 0.5;
        for (let j = 0; j < mCount; j++) {{
          const v = seriesList[j].values[i] || 0;
          if (Math.abs(v) < 1e-9) continue;
          const yTop = v >= 0 ? yAt(v) : zeroY;
          const bh = Math.max(1, Math.abs(yAt(v) - zeroY));
          ctx.fillStyle = seriesList[j].color;
          ctx.fillRect(gx + j * barW, yTop, Math.max(1, barW - (barW > 3 ? 0.6 : 0)), bh);
        }}
      }}

      // Dashed Mean lines per active model
      seriesList.forEach(s => {{
        const my = yAt(s.mean);
        ctx.save();
        ctx.strokeStyle = s.color;
        ctx.setLineDash([5, 4]);
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.moveTo(padL, my);
        ctx.lineTo(w - padR, my);
        ctx.stroke();
        ctx.restore();
      }});

      // X-axis ISO week ticks
      ctx.fillStyle = theme.axis;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      const xTicks = Math.min(n, Math.max(2, Math.floor(plotW / 100)));
      for (let k = 0; k < xTicks; k++) {{
        const idx = xTicks <= 1 ? 0 : Math.round((k / (xTicks - 1)) * (n - 1));
        const cx = padL + (idx + 0.5) * groupW;
        ctx.fillText(weeks[idx], Math.min(w - padR - 28, Math.max(padL + 28, cx)), padT + plotH + 7);
      }}

      canvas._hitMeta = {{ type: "weekly", padL, padR, padT, plotW, plotH, n, weeks, seriesList }};
    }}

    function drawCategoryGroupedBars(canvasId, opts) {{
      const canvas = document.getElementById(canvasId);
      const setup = setupCanvas(canvas);
      if (!setup) return;
      const {{ ctx, w, h }} = setup;
      const theme = getThemeColors();
      const items = opts.items || [];
      if (!items.length) {{
        drawEmptyMsg(ctx, w, h, "Select at least 1 model to compare", theme);
        canvas._hitMeta = null;
        return;
      }}

      let minV = 0, maxV = 0;
      items.forEach(it => {{
        [it.v1, it.v2].forEach(v => {{
          if (v < minV) minV = v;
          if (v > maxV) maxV = v;
        }});
      }});
      if (opts.minCap !== undefined) minV = Math.min(minV, opts.minCap);
      if (opts.maxCap !== undefined) maxV = Math.max(maxV, opts.maxCap);
      const {{ lo, hi, ticks }} = computeNiceTicks(minV < 0 ? minV * 1.12 : 0, maxV * 1.15, 5);
      const padL = 56, padR = 14, padT = 26, padB = 34;
      const plotW = Math.max(20, w - padL - padR);
      const plotH = Math.max(20, h - padT - padB);
      const yAt = val => padT + (1 - (val - lo) / Math.max(1e-9, hi - lo)) * plotH;
      const zeroY = yAt(0);

      // Top mini-legend
      ctx.font = "11px -apple-system, BlinkMacSystemFont, sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillStyle = opts.c1;
      ctx.fillRect(padL, 8, 10, 10);
      ctx.fillStyle = theme.fg;
      ctx.fillText(opts.k1, padL + 14, 13);
      const k1W = ctx.measureText(opts.k1).width;
      ctx.fillStyle = opts.c2;
      ctx.fillRect(padL + k1W + 28, 8, 10, 10);
      ctx.fillStyle = theme.fg;
      ctx.fillText(opts.k2, padL + k1W + 42, 13);

      // Grid & Y ticks
      ctx.font = "11px ui-monospace, SFMono-Regular, Menlo, monospace";
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ticks.forEach(t => {{
        const y = yAt(t);
        ctx.strokeStyle = Math.abs(t) < 1e-9 ? theme.axis : theme.grid;
        ctx.lineWidth = Math.abs(t) < 1e-9 ? 1 : 0.8;
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(w - padR, y);
        ctx.stroke();
        ctx.fillStyle = theme.axis;
        ctx.fillText(opts.yFmt(t), padL - 7, y);
      }});

      const n = items.length;
      const slotW = plotW / n;
      const bw = Math.min(34, Math.max(10, slotW * 0.30));
      const gap = Math.min(6, bw * 0.25);
      const hIdx = hoverState[canvasId];

      items.forEach((it, i) => {{
        const cx = padL + (i + 0.5) * slotW;
        if (hIdx === i) {{
          ctx.fillStyle = theme.isLight ? "rgba(37, 99, 235, 0.08)" : "rgba(59, 130, 246, 0.14)";
          ctx.fillRect(padL + i * slotW + 2, padT, slotW - 4, plotH);
        }}
        const x1 = cx - bw - gap * 0.5;
        const x2 = cx + gap * 0.5;

        [{{ x: x1, v: it.v1, c: opts.c1 }}, {{ x: x2, v: it.v2, c: opts.c2 }}].forEach(b => {{
          const yv = yAt(b.v);
          const top = Math.min(yv, zeroY);
          const bh = Math.max(1.5, Math.abs(yv - zeroY));
          ctx.fillStyle = b.c;
          ctx.fillRect(b.x, top, bw, bh);
          ctx.fillStyle = theme.fg;
          ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, monospace";
          ctx.textAlign = "center";
          ctx.textBaseline = b.v >= 0 ? "bottom" : "top";
          ctx.fillText(opts.lblFmt(b.v), b.x + bw / 2, b.v >= 0 ? top - 3 : top + bh + 3);
        }});

        // X category label with model dot
        ctx.font = "11px ui-monospace, SFMono-Regular, Menlo, monospace";
        const maxChars = Math.max(6, Math.floor(slotW / 7.5));
        const txt = it.short.length > maxChars ? it.short.slice(0, maxChars - 1) + "…" : it.short;
        const txtW = ctx.measureText(txt).width;
        ctx.fillStyle = it.modelColor;
        ctx.beginPath();
        ctx.arc(cx - txtW / 2 - 6, padT + plotH + 14, 3.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = theme.axis;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(txt, cx + 3, padT + plotH + 14);
      }});

      canvas._hitMeta = {{ type: "cat", padL, padR, padT, plotW, plotH, items, opts }};
    }}

    function rdbuColor(val, isLight) {{
      const v = Math.max(-1, Math.min(1, Number(val || 0)));
      const mid = isLight ? [246, 248, 251] : [36, 46, 62];
      const pos = [185, 28, 44];   // deep crimson for +1
      const neg = [29, 100, 178];  // deep ocean blue for -1
      const tgt = v >= 0 ? pos : neg;
      const t = Math.abs(v);
      const r = Math.round(mid[0] + (tgt[0] - mid[0]) * t);
      const g = Math.round(mid[1] + (tgt[1] - mid[1]) * t);
      const b = Math.round(mid[2] + (tgt[2] - mid[2]) * t);
      const text = t > 0.42 ? "#ffffff" : (isLight ? "#0f172a" : "#e6edf6");
      return {{ bg: `rgb(${{r}},${{g}},${{b}})`, text }};
    }}

    function drawCorrelationHeatmap(canvasId) {{
      const canvas = document.getElementById(canvasId);
      const setup = setupCanvas(canvas);
      if (!setup) return;
      const {{ ctx, w, h }} = setup;
      const theme = getThemeColors();
      const raw = PAYLOAD.corr_matrix || {{ labels: [], matrix: [] }};
      const allLabels = raw.labels || [];
      const allMat = raw.matrix || [];

      const keepIdx = [];
      allLabels.forEach((lbl, idx) => {{
        if (lbl === "ETH" || visibleIds.has(lbl)) keepIdx.push(idx);
      }});
      if (keepIdx.length < 2) {{
        drawEmptyMsg(ctx, w, h, "Correlation matrix requires at least 2 daily series (models + ETH)", theme);
        canvas._hitMeta = null;
        return;
      }}

      const labels = keepIdx.map(i => (allLabels[i] === "ETH" ? "ETH" : shortLabel(allLabels[i])));
      const fullLabels = keepIdx.map(i => allLabels[i]);
      const mat = keepIdx.map(r => keepIdx.map(c => Number((allMat[r] && allMat[r][c]) ?? 0)));
      const n = labels.length;

      const padL = Math.min(170, Math.max(95, w * 0.16));
      const padR = 54;
      const padT = 14;
      const padB = 46;
      const gridW = Math.max(40, w - padL - padR);
      const gridH = Math.max(40, h - padT - padB);
      const cellW = gridW / n;
      const cellH = gridH / n;
      const hCell = hoverState[canvasId];

      for (let r = 0; r < n; r++) {{
        for (let c = 0; c < n; c++) {{
          const val = mat[r][c];
          const x = padL + c * cellW;
          const y = padT + r * cellH;
          const col = rdbuColor(val, theme.isLight);
          ctx.fillStyle = col.bg;
          ctx.fillRect(x + 1, y + 1, cellW - 2, cellH - 2);
          if (hCell && hCell.r === r && hCell.c === c) {{
            ctx.strokeStyle = theme.fg;
            ctx.lineWidth = 2;
            ctx.strokeRect(x + 1.5, y + 1.5, cellW - 3, cellH - 3);
          }}
          ctx.fillStyle = col.text;
          ctx.font = `700 ${{Math.min(13, Math.max(10, Math.floor(Math.min(cellW, cellH) * 0.28)))}}px ui-monospace, SFMono-Regular, Menlo, monospace`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(val.toFixed(3), x + cellW / 2, y + cellH / 2);
        }}
      }}

      // Row & Col labels
      ctx.font = "11px ui-monospace, SFMono-Regular, Menlo, monospace";
      ctx.fillStyle = theme.fg;
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      for (let r = 0; r < n; r++) {{
        ctx.fillText(labels[r], padL - 8, padT + (r + 0.5) * cellH);
      }}
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      for (let c = 0; c < n; c++) {{
        const maxChars = Math.max(6, Math.floor(cellW / 7));
        const txt = labels[c].length > maxChars ? labels[c].slice(0, maxChars - 1) + "…" : labels[c];
        ctx.fillText(txt, padL + (c + 0.5) * cellW, padT + gridH + 10);
      }}

      // Right-hand RdBu color scale bar
      const barX = w - padR + 14;
      const barW = 12;
      for (let py = 0; py < gridH; py++) {{
        const v = 1 - (py / Math.max(1, gridH - 1)) * 2;
        ctx.fillStyle = rdbuColor(v, theme.isLight).bg;
        ctx.fillRect(barX, padT + py, barW, 1.5);
      }}
      ctx.strokeStyle = theme.border;
      ctx.strokeRect(barX, padT, barW, gridH);
      ctx.fillStyle = theme.axis;
      ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText("+1", barX + barW + 4, padT);
      ctx.textBaseline = "middle";
      ctx.fillText(" 0", barX + barW + 4, padT + gridH / 2);
      ctx.textBaseline = "bottom";
      ctx.fillText("-1", barX + barW + 4, padT + gridH);

      canvas._hitMeta = {{ type: "heatmap", padL, padT, gridW, gridH, cellW, cellH, n, labels, fullLabels, mat }};
    }}

    function drawAllDailyCharts() {{
      if (currentTab !== "daily") return;
      const sBundle = PAYLOAD.series || {{}};
      const byM = sBundle.by_model || {{}};
      const dates = sBundle.dates || [];
      const active = getActiveModels();
      const theme = getThemeColors();
      const ddCap = Number(PAYLOAD.default_dd_cap || 40);
      const initCap = (active[0] && Number(active[0].initial_capital)) || 10000;

      // 01 / Weekly Realized CF
      drawWeeklyGroupedBars("chart-weekly");

      // 02 / Accumulated Realized CF
      drawLineChart("chart-cumulative", {{
        dates,
        includeZero: true,
        lines: active.filter(m => byM[m.model_id]).map(m => ({{
          label: shortLabel(m.model_id),
          color: MODEL_COLOR.get(m.model_id),
          values: byM[m.model_id].cf || []
        }})),
        yFmt: v => "$" + Math.round(v).toLocaleString("en-US"),
        valFmt: v => fmtUsd(v)
      }});

      // 03 / Equity Returns vs ETH Benchmark
      const eqLines = active.filter(m => byM[m.model_id]).map(m => ({{
        label: shortLabel(m.model_id),
        color: MODEL_COLOR.get(m.model_id),
        values: byM[m.model_id].equity || []
      }}));
      if ((sBundle.eth_return || []).length) {{
        eqLines.push({{
          label: "ETH Benchmark",
          color: theme.eth,
          dashed: true,
          values: sBundle.eth_return
        }});
      }}
      drawLineChart("chart-equity", {{
        dates,
        includeZero: true,
        lines: eqLines,
        yFmt: v => (v >= 0 ? "+" : "") + v.toFixed(0) + "%",
        valFmt: v => fmtPct(v)
      }});

      // 04 / Equity Drawdown
      drawLineChart("chart-drawdown", {{
        dates,
        forceMax: 0,
        fillToZero: true,
        refLine: -ddCap,
        refColor: theme.gate,
        refLabel: `Hard Gate -${{ddCap}}%`,
        lines: active.filter(m => byM[m.model_id]).map(m => ({{
          label: shortLabel(m.model_id),
          color: MODEL_COLOR.get(m.model_id),
          values: byM[m.model_id].dd || []
        }})),
        yFmt: v => v.toFixed(0) + "%",
        valFmt: v => Number(v).toFixed(2) + "%"
      }});

      // 05 / Remaining Inventory
      drawLineChart("chart-inventory", {{
        dates,
        forceMin: 0,
        lines: active.filter(m => byM[m.model_id]).map(m => ({{
          label: shortLabel(m.model_id),
          color: MODEL_COLOR.get(m.model_id),
          values: byM[m.model_id].inventory || []
        }})),
        yFmt: v => v.toFixed(2),
        valFmt: v => Number(v).toFixed(4) + " ETH"
      }});

      // 06 / Capital Utilization
      drawLineChart("chart-utilization", {{
        dates,
        forceMin: 0,
        refLine: initCap,
        refColor: theme.eth,
        refLabel: `Init $${{initCap.toLocaleString("en-US")}}`,
        lines: active.filter(m => byM[m.model_id]).map(m => ({{
          label: shortLabel(m.model_id),
          color: MODEL_COLOR.get(m.model_id),
          values: byM[m.model_id].capital || []
        }})),
        yFmt: v => "$" + Math.round(v).toLocaleString("en-US"),
        valFmt: v => fmtUsd(v, false)
      }});

      // 07 / Executed Trading Volume
      drawCategoryGroupedBars("chart-volume", {{
        k1: "BUY ETH",
        k2: "SELL ETH",
        c1: "#22c55e",
        c2: "#3b82f6",
        yFmt: v => v.toFixed(1),
        lblFmt: v => v.toFixed(1),
        items: active.map(m => ({{
          id: m.model_id,
          short: shortLabel(m.model_id),
          modelColor: MODEL_COLOR.get(m.model_id),
          v1: Number(m.buy_volume_eth || 0),
          v2: Number(m.sell_volume_eth || 0),
          meta: m
        }}))
      }});

      // 08 / Beta & Correlation vs ETH
      drawCategoryGroupedBars("chart-betacorr", {{
        k1: "Beta to ETH",
        k2: "Corr to ETH",
        c1: "#f59e0b",
        c2: "#a855f7",
        maxCap: 1.0,
        yFmt: v => v.toFixed(2),
        lblFmt: v => v.toFixed(2),
        items: active.map(m => ({{
          id: m.model_id,
          short: shortLabel(m.model_id),
          modelColor: MODEL_COLOR.get(m.model_id),
          v1: Number(m.beta_to_eth || 0),
          v2: Number(m.corr_to_eth || 0),
          meta: m
        }}))
      }});

      // 09 / Return Correlation Matrix
      drawCorrelationHeatmap("chart-heatmap");
    }}

    const DAILY_SYNC_IDS = [
      "chart-cumulative", "chart-equity", "chart-drawdown", "chart-inventory", "chart-utilization"
    ];

    function bindCanvasHover(canvasId) {{
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      canvas.addEventListener("mousemove", ev => {{
        const meta = canvas._hitMeta;
        if (!meta) return;
        const rect = canvas.getBoundingClientRect();
        const mx = ev.clientX - rect.left;
        const my = ev.clientY - rect.top;

        if (meta.type === "line") {{
          if (mx < meta.padL || mx > meta.padL + meta.plotW || my < meta.padT || my > meta.padT + meta.plotH) {{
            DAILY_SYNC_IDS.forEach(id => delete hoverState[id]);
            hideTooltip();
            drawAllDailyCharts();
            return;
          }}
          const frac = (mx - meta.padL) / Math.max(1, meta.plotW);
          const idx = meta.n <= 1 ? 0 : Math.max(0, Math.min(meta.n - 1, Math.round(frac * (meta.n - 1))));
          if (hoverState[canvasId] !== idx) {{
            DAILY_SYNC_IDS.forEach(id => {{ hoverState[id] = idx; }});
            drawAllDailyCharts();
          }}
          const rows = meta.lines.map(s => ({{
            label: s.label,
            color: s.color,
            raw: (s.values || [])[idx],
            value: meta.valFmt((s.values || [])[idx] ?? 0)
          }})).sort((a, b) => Number(b.raw || 0) - Number(a.raw || 0));
          showTooltip(ev.clientX, ev.clientY, meta.dates[idx] || "", rows);
          return;
        }}

        if (meta.type === "weekly") {{
          if (mx < meta.padL || mx > meta.padL + meta.plotW || my < meta.padT || my > meta.padT + meta.plotH) {{
            delete hoverState[canvasId];
            hideTooltip();
            drawWeeklyGroupedBars(canvasId);
            return;
          }}
          const idx = Math.max(0, Math.min(meta.n - 1, Math.floor(((mx - meta.padL) / meta.plotW) * meta.n)));
          if (hoverState[canvasId] !== idx) {{
            hoverState[canvasId] = idx;
            drawWeeklyGroupedBars(canvasId);
          }}
          const rows = meta.seriesList.map(s => ({{
            label: `${{s.label}} (avg ${{fmtUsd(s.mean)}})`,
            color: s.color,
            raw: s.values[idx] || 0,
            value: fmtUsd(s.values[idx] || 0)
          }})).sort((a, b) => b.raw - a.raw);
          showTooltip(ev.clientX, ev.clientY, `ISO Week ${{meta.weeks[idx]}}`, rows);
          return;
        }}

        if (meta.type === "cat") {{
          if (mx < meta.padL || mx > meta.padL + meta.plotW || my < meta.padT || my > meta.padT + meta.plotH) {{
            delete hoverState[canvasId];
            hideTooltip();
            drawAllDailyCharts();
            return;
          }}
          const idx = Math.max(0, Math.min(meta.items.length - 1, Math.floor(((mx - meta.padL) / meta.plotW) * meta.items.length)));
          if (hoverState[canvasId] !== idx) {{
            hoverState[canvasId] = idx;
            drawAllDailyCharts();
          }}
          const it = meta.items[idx];
          const m = it.meta;
          if (canvasId === "chart-volume") {{
            showTooltip(ev.clientX, ev.clientY, it.id, [
              {{ label: "BUY Volume", color: "#22c55e", value: `${{fmtNum(it.v1, 3)}} ETH (${{Number(m.buy_fills || 0).toLocaleString()}} fills)` }},
              {{ label: "SELL Volume", color: "#3b82f6", value: `${{fmtNum(it.v2, 3)}} ETH (${{Number(m.sell_fills || 0).toLocaleString()}} fills)` }},
              {{ label: "Total Turnover", color: it.modelColor, value: fmtUsd(m.turnover_usd || 0, false) }}
            ]);
          }} else {{
            showTooltip(ev.clientX, ev.clientY, it.id, [
              {{ label: "Beta to ETH", color: "#f59e0b", value: Number(it.v1).toFixed(4) }},
              {{ label: "Corr to ETH", color: "#a855f7", value: Number(it.v2).toFixed(4) }},
              {{ label: "MTM Return", color: it.modelColor, value: fmtPct(m.mtm_return_pct || 0) }}
            ]);
          }}
          return;
        }}

        if (meta.type === "heatmap") {{
          const c = Math.floor((mx - meta.padL) / meta.cellW);
          const r = Math.floor((my - meta.padT) / meta.cellH);
          if (r < 0 || r >= meta.n || c < 0 || c >= meta.n) {{
            delete hoverState[canvasId];
            hideTooltip();
            drawCorrelationHeatmap(canvasId);
            return;
          }}
          const prev = hoverState[canvasId];
          if (!prev || prev.r !== r || prev.c !== c) {{
            hoverState[canvasId] = {{ r, c }};
            drawCorrelationHeatmap(canvasId);
          }}
          const val = meta.mat[r][c];
          showTooltip(ev.clientX, ev.clientY, "Daily Return Correlation", [
            {{ label: "Row", value: meta.fullLabels[r] }},
            {{ label: "Col", value: meta.fullLabels[c] }},
            {{ label: "Pearson r", value: val.toFixed(4) }}
          ]);
        }}
      }});

      canvas.addEventListener("mouseleave", () => {{
        if (DAILY_SYNC_IDS.includes(canvasId)) {{
          DAILY_SYNC_IDS.forEach(id => delete hoverState[id]);
        }} else {{
          delete hoverState[canvasId];
        }}
        hideTooltip();
        drawAllDailyCharts();
      }});
    }}

    function switchTab(target) {{
      currentTab = target;
      ["daily", "ranking", "all"].forEach(k => {{
        document.getElementById("view-" + k).classList.toggle("hidden", k !== target);
      }});
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === target));
      if (target === "daily") {{
        requestAnimationFrame(drawAllDailyCharts);
      }}
    }}

    function renderDailyPillsAndTables() {{
      const pillHost = document.getElementById("daily-legend-pills");
      pillHost.innerHTML = "";
      DAILY_MODELS.forEach(m => {{
        const color = MODEL_COLOR.get(m.model_id);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "pill" + (visibleIds.has(m.model_id) ? "" : " off");
        btn.innerHTML = `<span class="dot" style="background:${{color}}"></span><span>${{shortLabel(m.model_id)}}</span>`;
        btn.title = `${{m.model_id}} (${{m.signal_name}}) — คลิกสลับ / ดับเบิลคลิกดูเดี่ยว`;
        btn.addEventListener("click", () => {{
          if (visibleIds.has(m.model_id)) {{
            if (visibleIds.size > 1) visibleIds.delete(m.model_id);
          }} else {{
            visibleIds.add(m.model_id);
          }}
          renderDailyPillsAndTables();
          drawAllDailyCharts();
        }});
        btn.addEventListener("dblclick", () => {{
          if (visibleIds.size === 1 && visibleIds.has(m.model_id)) {{
            DAILY_MODELS.forEach(x => visibleIds.add(x.model_id));
          }} else {{
            visibleIds.clear();
            visibleIds.add(m.model_id);
          }}
          renderDailyPillsAndTables();
          drawAllDailyCharts();
        }});
        pillHost.appendChild(btn);
      }});

      const cards = document.getElementById("daily-cards");
      cards.innerHTML = "";
      DAILY_MODELS.forEach((m, i) => {{
        const color = MODEL_COLOR.get(m.model_id);
        const isOn = visibleIds.has(m.model_id);
        const pass = !m.would_liquidate && Number(m.max_drawdown_pct) <= Number(PAYLOAD.default_dd_cap || 40);
        const el = document.createElement("div");
        el.className = "kv-box";
        el.style.borderTop = `3px solid ${{color}}`;
        el.style.opacity = isOn ? "1" : "0.42";
        el.style.cursor = "pointer";
        el.addEventListener("click", () => {{
          if (visibleIds.has(m.model_id) && visibleIds.size > 1) visibleIds.delete(m.model_id);
          else visibleIds.add(m.model_id);
          renderDailyPillsAndTables();
          drawAllDailyCharts();
        }});
        el.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
            <span class="muted mono">Model ${{i + 1}}/${{DAILY_MODELS.length}}</span>
            <span class="badge ${{pass ? 'badge-pass' : 'badge-fail'}}">${{pass ? 'PASS' : 'FAIL'}}</span>
          </div>
          <div class="mono" style="font-weight:700;margin-bottom:1px;">${{m.model_id}}</div>
          <div class="muted" style="font-size:11px;margin-bottom:6px;">${{m.signal_name}}</div>
          <div class="mono" style="font-size:12px;display:flex;flex-direction:column;gap:2px;">
            <div style="display:flex;justify-content:space-between;"><span>Realized CF</span><strong class="pos">${{fmtUsd(m.cashflow_net_usd)}}</strong></div>
            <div style="display:flex;justify-content:space-between;"><span>AVG Weekly</span><span class="pos">${{fmtUsd(m.avg_weekly_cf_usd || 0)}}</span></div>
            <div style="display:flex;justify-content:space-between;"><span>Max DD</span><strong class="warn">${{Number(m.max_drawdown_pct).toFixed(2)}}%</strong></div>
            <div style="display:flex;justify-content:space-between;"><span>MTM Return</span><span class="${{m.mtm_return_pct >= 0 ? 'pos' : 'neg'}}">${{fmtPct(m.mtm_return_pct)}}</span></div>
            <div style="display:flex;justify-content:space-between;"><span>Beta / Corr</span><span>${{Number(m.beta_to_eth || 0).toFixed(2)}} / ${{Number(m.corr_to_eth || 0).toFixed(2)}}</span></div>
          </div>
        `;
        cards.appendChild(el);
      }});

      const perfBody = document.getElementById("daily-perf-body");
      perfBody.innerHTML = "";
      DAILY_MODELS.forEach(m => {{
        const color = MODEL_COLOR.get(m.model_id);
        const pass = !m.would_liquidate && Number(m.max_drawdown_pct) <= Number(PAYLOAD.default_dd_cap || 40);
        const finEq = Number(m.initial_capital || 10000) + Number(m.mtm_pnl_usd || 0);
        const tr = document.createElement("tr");
        tr.className = "data-row";
        if (!visibleIds.has(m.model_id)) tr.style.opacity = "0.45";
        tr.addEventListener("click", () => {{
          renderInspector(m);
          renderRanking();
          switchTab("ranking");
        }});
        tr.innerHTML = `
          <td class="mono" style="font-weight:700;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${{color}};margin-right:7px;"></span>${{m.model_id}}</td>
          <td class="mono muted">${{m.signal_name}}</td>
          <td class="num">${{fmtUsd(finEq, false)}}</td>
          <td class="num ${{m.mtm_return_pct >= 0 ? 'pos' : 'neg'}}">${{fmtPct(m.mtm_return_pct)}}</td>
          <td class="num warn" style="font-weight:700;">-${{Number(m.max_drawdown_pct).toFixed(2)}}%</td>
          <td class="num pos" style="font-weight:700;">${{fmtUsd(m.cashflow_net_usd)}}</td>
          <td class="num ${{m.unrealized_end_usd >= 0 ? 'pos' : 'neg'}}">${{fmtUsd(m.unrealized_end_usd)}}</td>
          <td class="num pos">${{fmtUsd(m.avg_weekly_cf_usd || 0)}}</td>
          <td class="num">${{Number(m.buy_fills || 0).toLocaleString()}} / ${{Number(m.sell_fills || 0).toLocaleString()}}</td>
          <td class="num">${{fmtNum(m.buy_volume_eth || 0, 2)}} / ${{fmtNum(m.sell_volume_eth || 0, 2)}}</td>
          <td class="num">${{fmtNum(m.ending_open_qty || 0, 3)}}</td>
          <td class="num">${{Number(m.max_utilization_pct || 0).toFixed(1)}}%</td>
          <td class="num">${{Number(m.beta_to_eth || 0).toFixed(2)}} / ${{Number(m.corr_to_eth || 0).toFixed(2)}}</td>
          <td style="text-align:center;"><span class="badge ${{pass ? 'badge-pass' : 'badge-fail'}}">${{pass ? 'PASS' : 'FAIL'}}</span></td>
        `;
        perfBody.appendChild(tr);
      }});
    }}

    function renderInspector(m) {{
      if (!m) return;
      selectedId = m.model_id;
      document.getElementById("insp-id").textContent = m.model_id;
      document.getElementById("insp-meta").textContent =
        `Trial #${{m.trial_number}} · ${{m.signal_name}} · ${{m.symbol}} (${{m.zone_high}}→${{m.zone_low}}) · ${{Number(m.bar_count || 0).toLocaleString()}} bars`;
      document.getElementById("insp-cf").textContent = `${{fmtUsd(m.cashflow_net_usd)}} (+${{Number(m.cashflow_pct).toFixed(2)}}%)`;
      document.getElementById("insp-dd").textContent = `${{Number(m.max_drawdown_pct).toFixed(2)}}% ($${{Number(m.max_drawdown_abs).toLocaleString()}})`;
      document.getElementById("insp-wk").textContent = `${{fmtUsd(m.avg_weekly_cf_usd || 0)}} / wk (${{m.weekly_count || 0}} wks)`;
      document.getElementById("insp-bc").textContent = `β ${{Number(m.beta_to_eth || 0).toFixed(3)}} · r ${{Number(m.corr_to_eth || 0).toFixed(3)}}`;
      document.getElementById("insp-unr").textContent = fmtUsd(m.unrealized_end_usd);
      document.getElementById("insp-cost").textContent = `-$${{Number(m.total_fees_paid).toFixed(0)}} / ${{fmtUsd(m.total_funding_pnl)}}`;
      document.getElementById("insp-tr").textContent = `${{Number(m.closed_trades_count).toLocaleString()}} (${{Number(m.win_rate_pct).toFixed(1)}}%)`;
      document.getElementById("insp-qty").textContent = `${{m.max_open_qty}} / ${{m.ending_open_qty}} ETH`;
      document.getElementById("insp-path").textContent = `beta_mining/models/${{m.model_id}}/`;
      document.getElementById("insp-cmd").textContent =
        `python3 scripts/beta_mining.py show ${{m.model_id}}\\n` +
        `# Python SDK:\\n` +
        `BetaModelStore(Path("beta_mining")).load_model("${{m.model_id}}")`;
    }}

    function renderRanking() {{
      const mode = document.getElementById("rank-mode").value;
      const ddCap = Number(document.getElementById("dd-slider").value);
      const onlyToday = document.getElementById("only-today").checked;
      document.getElementById("dd-label").textContent = `≤ ${{ddCap}}%`;

      const pool = (PAYLOAD.models || []).filter(m => !onlyToday || BATCH_SET.has(m.model_id));
      const rows = pool.map(m => ({{
        ...m,
        passGate: !m.would_liquidate && Number(m.max_drawdown_pct) <= ddCap
      }}));

      rows.sort((a, b) => {{
        if (a.passGate !== b.passGate) return a.passGate ? -1 : 1;
        if (mode === "cashflow_dd") {{
          if (Math.abs(b.cashflow_net_usd - a.cashflow_net_usd) > 1e-6) return b.cashflow_net_usd - a.cashflow_net_usd;
          return a.max_drawdown_pct - b.max_drawdown_pct;
        }}
        if (mode === "efficiency") {{
          if (Math.abs(b.cashflow_to_dd_ratio - a.cashflow_to_dd_ratio) > 1e-6) return b.cashflow_to_dd_ratio - a.cashflow_to_dd_ratio;
          return b.cashflow_net_usd - a.cashflow_net_usd;
        }}
        return b.mtm_return_pct - a.mtm_return_pct;
      }});

      const qual = rows.filter(r => r.passGate);
      document.getElementById("kpi-trials").textContent = String(PAYLOAD.total_trials);
      document.getElementById("kpi-today").textContent = `Today Batch: ${{BATCH_SET.size}} models · Stored: ${{(PAYLOAD.models || []).length}}`;
      document.getElementById("kpi-qual").textContent = `${{qual.length}} / ${{rows.length}}`;
      document.getElementById("kpi-gate").textContent = `No Liquidation · Max DD ≤ ${{ddCap}}%`;
      if (qual.length > 0) {{
        document.getElementById("kpi-top1").textContent = qual[0].model_id;
        document.getElementById("kpi-top1-sub").textContent = `CF ${{fmtUsd(qual[0].cashflow_net_usd)}} · DD ${{Number(qual[0].max_drawdown_pct).toFixed(2)}}%`;
        const low = [...qual].sort((a, b) => a.max_drawdown_pct - b.max_drawdown_pct)[0];
        document.getElementById("kpi-lowdd").textContent = low.model_id;
        document.getElementById("kpi-lowdd-sub").textContent = `DD ${{Number(low.max_drawdown_pct).toFixed(2)}}% · CF ${{fmtUsd(low.cashflow_net_usd)}}`;
      }} else {{
        document.getElementById("kpi-top1").textContent = "None";
        document.getElementById("kpi-top1-sub").textContent = "No model passes DD gate";
        document.getElementById("kpi-lowdd").textContent = "None";
        document.getElementById("kpi-lowdd-sub").textContent = "-";
      }}

      const tbody = document.getElementById("rank-body");
      tbody.innerHTML = "";
      let rk = 0;
      rows.slice(0, PAYLOAD.top_n).forEach(m => {{
        if (m.passGate) rk += 1;
        const tr = document.createElement("tr");
        tr.className = "data-row" + (m.model_id === selectedId ? " selected" : "");
        tr.addEventListener("click", () => {{ renderInspector(m); renderRanking(); }});
        const crashDd = m.crash_stress ? `${{Number(m.crash_stress.max_drawdown_pct).toFixed(2)}}%` : "N/A";
        const todayTag = BATCH_SET.has(m.model_id) ? ` <span class="badge badge-today">TODAY</span>` : "";
        const gateTag = m.passGate
          ? `<span class="badge badge-pass">PASS</span>`
          : `<span class="badge badge-fail">${{m.would_liquidate ? "LIQ" : "DD>" + ddCap + "%"}}</span>`;
        tr.innerHTML = `
          <td class="mono" style="font-weight:700;">${{m.passGate ? "#" + rk : "—"}}</td>
          <td>
            <div class="mono" style="font-weight:700;">${{m.model_id}}${{todayTag}}</div>
            <div class="muted" style="font-size:11px;">${{m.signal_name}} · Trial #${{m.trial_number}}</div>
          </td>
          <td class="num pos" style="font-weight:700;">${{fmtUsd(m.cashflow_net_usd)}}</td>
          <td class="num pos">${{fmtUsd(m.avg_weekly_cf_usd || 0)}}</td>
          <td class="num warn" style="font-weight:700;">${{Number(m.max_drawdown_pct).toFixed(2)}}%</td>
          <td class="num">${{Number(m.cashflow_to_dd_ratio).toFixed(2)}}x</td>
          <td class="num ${{m.mtm_return_pct >= 0 ? 'pos' : 'neg'}}">${{fmtPct(m.mtm_return_pct)}}</td>
          <td class="num">${{crashDd}}</td>
          <td style="text-align:center;">${{gateTag}}</td>
        `;
        tbody.appendChild(tr);
      }});

      const sel = rows.find(r => r.model_id === selectedId) || rows[0];
      if (sel) renderInspector(sel);
    }}

    function renderAllModelsTable() {{
      const allBody = document.getElementById("all-body");
      allBody.innerHTML = "";
      [...(PAYLOAD.models || [])].sort((a, b) => a.trial_number - b.trial_number).forEach(m => {{
        const tr = document.createElement("tr");
        tr.className = "data-row";
        tr.addEventListener("click", () => {{
          renderInspector(m);
          renderRanking();
          switchTab("ranking");
        }});
        tr.innerHTML = `
          <td class="mono">#${{m.trial_number}}</td>
          <td class="mono" style="font-weight:700;">${{m.model_id}}</td>
          <td class="mono">${{m.signal_name}}</td>
          <td class="mono">${{m.batch_date}}</td>
          <td class="mono">${{m.zone_high}}→${{m.zone_low}}</td>
          <td class="num pos">${{fmtUsd(m.cashflow_net_usd)}}</td>
          <td class="num pos">${{fmtUsd(m.avg_weekly_cf_usd || 0)}}</td>
          <td class="num warn">${{Number(m.max_drawdown_pct).toFixed(2)}}%</td>
          <td class="num ${{m.mtm_return_pct >= 0 ? 'pos' : 'neg'}}">${{fmtPct(m.mtm_return_pct)}}</td>
          <td class="num">${{Number(m.beta_to_eth || 0).toFixed(2)}} / ${{Number(m.corr_to_eth || 0).toFixed(2)}}</td>
          <td class="num">${{Number(m.closed_trades_count).toLocaleString()}}</td>
        `;
        allBody.appendChild(tr);
      }});
    }}

    document.getElementById("hdr-sub").textContent =
      `Generated ${{PAYLOAD.generated_at_utc}} · All ${{DAILY_MODELS.length}} Daily Models Compared (9 Panels) · Hard Gate: No Liq & Max DD ≤ ${{PAYLOAD.default_dd_cap}}% · Offline Zero-CDN`;

    document.querySelectorAll(".tab-btn").forEach(btn => {{
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    }});

    document.getElementById("btn-show-all").addEventListener("click", () => {{
      DAILY_MODELS.forEach(m => visibleIds.add(m.model_id));
      renderDailyPillsAndTables();
      drawAllDailyCharts();
    }});

    document.getElementById("btn-top3").addEventListener("click", () => {{
      const top3 = [...DAILY_MODELS]
        .sort((a, b) => Number(b.cashflow_net_usd) - Number(a.cashflow_net_usd))
        .slice(0, 3);
      visibleIds.clear();
      top3.forEach(m => visibleIds.add(m.model_id));
      renderDailyPillsAndTables();
      drawAllDailyCharts();
    }});

    document.getElementById("theme-toggle").addEventListener("click", () => {{
      document.body.classList.toggle("light");
      drawAllDailyCharts();
    }});
    window.addEventListener("themechange", () => {{
      const hostLight = document.documentElement.classList.contains("light");
      document.body.classList.toggle("light", hostLight);
      drawAllDailyCharts();
    }});

    document.getElementById("rank-mode").addEventListener("change", renderRanking);
    document.getElementById("dd-slider").addEventListener("input", renderRanking);
    document.getElementById("only-today").addEventListener("change", renderRanking);

    [
      "chart-weekly", "chart-cumulative", "chart-equity", "chart-drawdown",
      "chart-inventory", "chart-utilization", "chart-volume", "chart-betacorr", "chart-heatmap"
    ].forEach(bindCanvasHover);

    let resizeTimer = null;
    window.addEventListener("resize", () => {{
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(drawAllDailyCharts, 80);
    }});

    if (document.documentElement.classList.contains("light")) {{
      document.body.classList.add("light");
    }}
    renderRanking();
    renderAllModelsTable();
    renderDailyPillsAndTables();
    requestAnimationFrame(drawAllDailyCharts);
  </script>
</body>
</html>
"""
