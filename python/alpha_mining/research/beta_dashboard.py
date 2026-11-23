"""Daily Beta Mining Summary Markdown & Self-Contained Offline HTML Dashboard Generator.

Produces two deliverables per daily 5-model mining run:
1. `daily_summary.md` — Crisp Thai/English report for GitHub/Katherine Morning Digest.
2. `dashboard.html`   — 100% self-contained interactive HTML Dashboard (zero CDN / zero
   external dependencies; opens directly in any browser online or offline) with:
   - Top-9 Cashflow -> DD Ranking Board (with live DD Gate slider defaulted to 40% and
     mode switcher: Cashflow->DD, CF/DD Efficiency, Total MTM Return)
   - Daily Batch 5-Model Side-by-Side Comparison Cards & Cashflow-vs-DD Visual Bars
   - Isolated Per-Model Inspector Drawer (folder path, fees/funding drag, crash stress,
     and 1-line CLI / Python load commands)
"""

from __future__ import annotations

import html
import json
from typing import Any, Sequence


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
        "| Model ID | Signal | Realized Cashflow | Max DD (%) | CF / DD | MTM Return | Unrealized End | Fees + Funding | Crash -46% DD | Trades (Win%) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for m in batch_metrics:
        crash = m.get("crash_stress") or {}
        crash_dd = f"{crash['max_drawdown_pct']:.2f}%" if "max_drawdown_pct" in crash else "N/A"
        lines.append(
            f"| `{m['model_id']}` | `{m['signal_name']}` "
            f"| {m['cashflow_net_usd']:+.2f} ({m['cashflow_pct']:+.2f}%) "
            f"| {m['max_drawdown_pct']:.2f}% | {m['cashflow_to_dd_ratio']:.2f}x "
            f"| {m['mtm_return_pct']:+.2f}% | {m['unrealized_end_usd']:+.2f} "
            f"| -{m['total_fees_paid']:.2f} / {m['total_funding_pnl']:+.2f} "
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


def render_dashboard_html(
    *,
    batch_date: str,
    batch_metrics: Sequence[dict[str, Any]],
    all_models_metrics: Sequence[dict[str, Any]],
    ranking_board: dict[str, Any],
) -> str:
    """Render a 100% self-contained offline-ready interactive HTML Dashboard (zero CDN dependencies)."""
    rule = ranking_board.get("ranking_rule", {})
    default_dd_cap = float(rule.get("hard_gates", {}).get("max_drawdown_pct_limit", 40.0))
    top_n = int(rule.get("top_n", 9))

    embedded_data = {
        "batch_date": batch_date,
        "generated_at_utc": ranking_board.get("generated_at_utc", ""),
        "total_trials": int(ranking_board.get("total_trials", len(all_models_metrics))),
        "top_n": top_n,
        "default_dd_cap": default_dd_cap,
        "batch_ids": [m["model_id"] for m in batch_metrics],
        "models": list(all_models_metrics),
    }
    safe_json = json.dumps(embedded_data, ensure_ascii=False).replace("</", "<\\/")
    safe_date = html.escape(batch_date)

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Alpha_mining — Beta Mining Dashboard ({safe_date})</title>
  <style>
    :root {{
      --bg: #0f1419;
      --card: #161d26;
      --surface: #1d2633;
      --border: #2a3545;
      --fg: #e7edf5;
      --muted: #93a3b8;
      --primary: #3b82f6;
      --primary-fg: #ffffff;
      --success: #22c55e;
      --warning: #f59e0b;
      --error: #ef4444;
      --code-fg: #93c5fd;
    }}
    body.light {{
      --bg: #f6f8fb;
      --card: #ffffff;
      --surface: #f1f5f9;
      --border: #dce3ec;
      --fg: #0f172a;
      --muted: #526277;
      --primary: #2563eb;
      --primary-fg: #ffffff;
      --success: #16a34a;
      --warning: #d97706;
      --error: #dc2626;
      --code-fg: #1d4ed8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 20px;
      background: var(--bg);
      color: var(--fg);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 13px;
      line-height: 1.45;
    }}
    .wrap {{ max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }}
    .header {{
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
      gap: 12px; padding-bottom: 14px; border-bottom: 1px solid var(--border);
    }}
    .title {{ margin: 0; font-size: 19px; font-weight: 700; }}
    .subtitle {{ margin: 4px 0 0; color: var(--muted); font-size: 12px; }}
    .tabs {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    button {{
      cursor: pointer; border: 1px solid var(--border); border-radius: 8px;
      padding: 7px 12px; font-size: 12px; font-weight: 600;
      background: var(--card); color: var(--fg);
    }}
    button.active {{ background: var(--primary); color: var(--primary-fg); border-color: var(--primary); }}
    .grid-4 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }}
    .card {{
      background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 14px;
    }}
    .kpi-label {{ font-size: 12px; color: var(--muted); }}
    .kpi-val {{ font-size: 20px; font-weight: 700; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin: 4px 0; }}
    .controls {{
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px;
      background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px;
    }}
    select, input[type="range"] {{
      background: var(--surface); color: var(--fg); border: 1px solid var(--border);
      border-radius: 6px; padding: 5px 8px; font-size: 12px;
    }}
    .split {{ display: grid; grid-template-columns: 2fr 1fr; gap: 14px; align-items: start; }}
    @media (max-width: 960px) {{ .split {{ grid-template-columns: 1fr; }} }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--border); text-align: left; }}
    th {{ color: var(--muted); font-weight: 600; white-space: nowrap; }}
    td.num, th.num {{ text-align: right; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    tr.data-row {{ cursor: pointer; }}
    tr.data-row:hover, tr.data-row.selected {{ background: var(--surface); }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .pos {{ color: var(--success); }}
    .warn {{ color: var(--warning); }}
    .neg {{ color: var(--error); }}
    .muted {{ color: var(--muted); }}
    .badge {{
      display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 700;
    }}
    .badge-pass {{ background: rgba(34, 197, 94, 0.16); color: var(--success); }}
    .badge-fail {{ background: rgba(239, 68, 68, 0.18); color: var(--error); }}
    .badge-today {{ background: rgba(59, 130, 246, 0.18); color: var(--code-fg); }}
    .kv-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 10px 0; }}
    .kv-box {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; }}
    pre {{
      background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
      padding: 10px; overflow-x: auto; font-size: 12px; color: var(--code-fg); margin: 6px 0 0;
    }}
    .batch-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }}
    .bar-track {{ height: 10px; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }}
    .bar-fill {{ height: 100%; border-radius: 6px; }}
    .stack {{ display: flex; flex-direction: column; gap: 14px; }}
    .hidden {{ display: none !important; }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="header">
      <div>
        <h1 class="title">Alpha_mining — Beta Mining Daily Dashboard ({safe_date})</h1>
        <p id="hdr-sub" class="subtitle"></p>
      </div>
      <div class="tabs">
        <button data-tab="ranking" class="tab-btn active">Top-{top_n} Ranking Board</button>
        <button data-tab="daily" class="tab-btn">Daily Batch Compare</button>
        <button data-tab="all" class="tab-btn">All Isolated Models</button>
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

    <!-- TAB 1: TOP-9 RANKING BOARD -->
    <section id="view-ranking" class="stack">
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
          <div style="padding:10px 14px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;">
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
          <div style="border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:8px;">
            <div class="muted" style="font-size:11px;">Isolated Model Inspector</div>
            <div id="insp-id" class="mono" style="font-size:15px;font-weight:700;">-</div>
            <div id="insp-meta" class="muted" style="font-size:12px;">-</div>
          </div>
          <div class="kv-grid">
            <div class="kv-box"><div class="kpi-label">Realized Cashflow</div><div id="insp-cf" class="mono pos" style="font-weight:700;">-</div></div>
            <div class="kv-box"><div class="kpi-label">Max MTM DD</div><div id="insp-dd" class="mono warn" style="font-weight:700;">-</div></div>
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

    <!-- TAB 2: DAILY BATCH COMPARE -->
    <section id="view-daily" class="stack hidden">
      <div class="card">
        <strong style="display:block;margin-bottom:10px;">Daily Mining Batch ({safe_date}) — Side-by-Side Compare</strong>
        <div id="daily-cards" class="batch-grid"></div>
      </div>
      <div class="card">
        <strong style="display:block;margin-bottom:10px;">Cashflow (Green) vs Max Drawdown % (Amber)</strong>
        <div id="daily-bars" style="display:flex;flex-direction:column;gap:10px;"></div>
      </div>
    </section>

    <!-- TAB 3: ALL ISOLATED MODELS -->
    <section id="view-all" class="hidden card" style="padding:0;overflow:hidden;">
      <div style="padding:10px 14px;border-bottom:1px solid var(--border);font-weight:700;">All Isolated Models in Store</div>
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
              <th class="num">Max DD</th>
              <th class="num">MTM %</th>
              <th class="num">Trades</th>
            </tr>
          </thead>
          <tbody id="all-body"></tbody>
        </table>
      </div>
    </section>
  </div>

  <script>
    const PAYLOAD = {safe_json};
    const BATCH_SET = new Set(PAYLOAD.batch_ids || []);
    let selectedId = (PAYLOAD.models[0] && PAYLOAD.models[0].model_id) || "";

    function fmtUsd(v) {{
      return (v >= 0 ? "+$" : "-$") + Math.abs(Number(v || 0)).toLocaleString("en-US", {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
    }}

    function renderInspector(m) {{
      if (!m) return;
      selectedId = m.model_id;
      document.getElementById("insp-id").textContent = m.model_id;
      document.getElementById("insp-meta").textContent =
        `Trial #${{m.trial_number}} · ${{m.signal_name}} · ${{m.symbol}} (${{m.zone_high}}→${{m.zone_low}}) · ${{m.bar_count.toLocaleString()}} bars`;
      document.getElementById("insp-cf").textContent = `${{fmtUsd(m.cashflow_net_usd)}} (+${{Number(m.cashflow_pct).toFixed(2)}}%)`;
      document.getElementById("insp-dd").textContent = `${{Number(m.max_drawdown_pct).toFixed(2)}}% ($${{Number(m.max_drawdown_abs).toLocaleString()}})`;
      document.getElementById("insp-unr").textContent = fmtUsd(m.unrealized_end_usd);
      document.getElementById("insp-cost").textContent = `-$${{Number(m.total_fees_paid).toFixed(0)}} / ${{fmtUsd(m.total_funding_pnl)}}`;
      document.getElementById("insp-tr").textContent = `${{Number(m.closed_trades_count).toLocaleString()}} (${{Number(m.win_rate_pct).toFixed(1)}}%)`;
      document.getElementById("insp-qty").textContent = `${{m.max_open_qty}} / ${{m.ending_open_qty}}`;
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
          <td class="num warn" style="font-weight:700;">${{Number(m.max_drawdown_pct).toFixed(2)}}%</td>
          <td class="num">${{Number(m.cashflow_to_dd_ratio).toFixed(2)}}x</td>
          <td class="num ${{m.mtm_return_pct >= 0 ? 'pos' : 'neg'}}">${{m.mtm_return_pct >= 0 ? "+" : ""}}${{Number(m.mtm_return_pct).toFixed(2)}}%</td>
          <td class="num">${{crashDd}}</td>
          <td style="text-align:center;">${{gateTag}}</td>
        `;
        tbody.appendChild(tr);
      }});

      const sel = rows.find(r => r.model_id === selectedId) || rows[0];
      if (sel) renderInspector(sel);
    }}

    function renderDailyAndAll() {{
      const today = (PAYLOAD.models || []).filter(m => BATCH_SET.has(m.model_id));
      const cards = document.getElementById("daily-cards");
      cards.innerHTML = "";
      today.forEach((m, i) => {{
        const pass = !m.would_liquidate && Number(m.max_drawdown_pct) <= PAYLOAD.default_dd_cap;
        const el = document.createElement("div");
        el.className = "kv-box";
        el.innerHTML = `
          <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
            <span class="muted mono">Model ${{i + 1}}/${{today.length}}</span>
            <span class="badge ${{pass ? 'badge-pass' : 'badge-fail'}}">${{pass ? 'PASS' : 'FAIL'}}</span>
          </div>
          <div class="mono" style="font-weight:700;margin-bottom:2px;">${{m.model_id}}</div>
          <div class="muted" style="font-size:11px;margin-bottom:6px;">${{m.signal_name}}</div>
          <div class="mono" style="font-size:12px;display:flex;flex-direction:column;gap:3px;">
            <div style="display:flex;justify-content:space-between;"><span>Cashflow</span><strong class="pos">${{fmtUsd(m.cashflow_net_usd)}}</strong></div>
            <div style="display:flex;justify-content:space-between;"><span>Max DD</span><strong class="warn">${{Number(m.max_drawdown_pct).toFixed(2)}}%</strong></div>
            <div style="display:flex;justify-content:space-between;"><span>CF / DD</span><span>${{Number(m.cashflow_to_dd_ratio).toFixed(2)}}x</span></div>
            <div style="display:flex;justify-content:space-between;"><span>MTM</span><span class="${{m.mtm_return_pct >= 0 ? 'pos' : 'neg'}}">${{Number(m.mtm_return_pct).toFixed(2)}}%</span></div>
            <div style="display:flex;justify-content:space-between;"><span>Trades</span><span>${{Number(m.closed_trades_count).toLocaleString()}}</span></div>
          </div>
        `;
        cards.appendChild(el);
      }});

      const bars = document.getElementById("daily-bars");
      bars.innerHTML = "";
      const maxCf = Math.max(100, ...today.map(m => Math.abs(Number(m.cashflow_net_usd || 0))));
      today.forEach(m => {{
        const cfW = Math.min(100, (Math.max(0, Number(m.cashflow_net_usd)) / maxCf) * 100);
        const ddW = Math.min(100, (Number(m.max_drawdown_pct) / 50) * 100);
        const row = document.createElement("div");
        row.innerHTML = `
          <div style="display:flex;justify-content:space-between;margin-bottom:4px;" class="mono">
            <strong>${{m.model_id}}</strong>
            <span class="muted">Cashflow ${{fmtUsd(m.cashflow_net_usd)}} · Max DD ${{Number(m.max_drawdown_pct).toFixed(2)}}%</span>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <div class="bar-track"><div class="bar-fill" style="width:${{cfW.toFixed(1)}}%;background:var(--success);"></div></div>
            <div class="bar-track"><div class="bar-fill" style="width:${{ddW.toFixed(1)}}%;background:var(--warning);"></div></div>
          </div>
        `;
        bars.appendChild(row);
      }});

      const allBody = document.getElementById("all-body");
      allBody.innerHTML = "";
      [...(PAYLOAD.models || [])].sort((a, b) => a.trial_number - b.trial_number).forEach(m => {{
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td class="mono">#${{m.trial_number}}</td>
          <td class="mono" style="font-weight:700;">${{m.model_id}}</td>
          <td class="mono">${{m.signal_name}}</td>
          <td class="mono">${{m.batch_date}}</td>
          <td class="mono">${{m.zone_high}}→${{m.zone_low}}</td>
          <td class="num pos">${{fmtUsd(m.cashflow_net_usd)}}</td>
          <td class="num warn">${{Number(m.max_drawdown_pct).toFixed(2)}}%</td>
          <td class="num ${{m.mtm_return_pct >= 0 ? 'pos' : 'neg'}}">${{Number(m.mtm_return_pct).toFixed(2)}}%</td>
          <td class="num">${{Number(m.closed_trades_count).toLocaleString()}}</td>
        `;
        allBody.appendChild(tr);
      }});
    }}

    document.getElementById("hdr-sub").textContent =
      `Generated ${{PAYLOAD.generated_at_utc}} · Hard Gate: No Liquidation & Max DD ≤ ${{PAYLOAD.default_dd_cap}}% · Self-contained Offline Report`;

    document.querySelectorAll(".tab-btn").forEach(btn => {{
      btn.addEventListener("click", () => {{
        const target = btn.dataset.tab;
        ["ranking", "daily", "all"].forEach(k => {{
          document.getElementById("view-" + k).classList.toggle("hidden", k !== target);
        }});
        document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === target));
      }});
    }});

    document.getElementById("theme-toggle").addEventListener("click", () => document.body.classList.toggle("light"));
    document.getElementById("rank-mode").addEventListener("change", renderRanking);
    document.getElementById("dd-slider").addEventListener("input", renderRanking);
    document.getElementById("only-today").addEventListener("change", renderRanking);

    renderRanking();
    renderDailyAndAll();
  </script>
</body>
</html>
"""
