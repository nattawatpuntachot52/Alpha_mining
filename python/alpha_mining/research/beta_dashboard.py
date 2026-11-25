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
import re
from typing import Any, Sequence

from .beta_store import compute_return_correlation_matrix

_SAFE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


def _safe_inline_json(payload: Any) -> str:
    """Serialize JSON safely for embedding inside HTML <script> tags (escapes < to neutralize </script> and <!--)."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c")


def _normalize_available_dates(
    batch_date: str,
    available_dates: Sequence[Any] | None,
    *,
    current_batch_metrics: Sequence[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Normalize available historical daily batch metadata (deduplicated, strict YYYY-MM-DD, sorted newest-first)."""
    by_date: dict[str, dict[str, Any]] = {}
    for entry in available_dates or ():
        if isinstance(entry, str):
            d = entry.strip()
            if _SAFE_DATE_RE.fullmatch(d):
                by_date[d] = {"batch_date": d, "has_dashboard": True}
        elif isinstance(entry, dict):
            d = str(entry.get("batch_date", "")).strip()
            has_dash = entry.get("has_dashboard", True) is not False
            if _SAFE_DATE_RE.fullmatch(d) and (has_dash or d == batch_date):
                by_date[d] = {
                    "batch_date": d,
                    "model_count": int(entry.get("model_count", 0)),
                    "qualified_count": int(entry.get("qualified_count", 0)),
                    "best_cashflow_usd": round(float(entry.get("best_cashflow_usd", 0.0)), 2),
                    "lowest_dd_pct": round(float(entry.get("lowest_dd_pct", 0.0)), 2),
                    "has_dashboard": has_dash,
                }
    if _SAFE_DATE_RE.fullmatch(batch_date) and (batch_date not in by_date or current_batch_metrics):
        best_cf = (
            max(float(m.get("cashflow_net_usd", 0.0)) for m in current_batch_metrics)
            if current_batch_metrics
            else 0.0
        )
        low_dd = (
            min(float(m.get("max_drawdown_pct", 0.0)) for m in current_batch_metrics)
            if current_batch_metrics
            else 0.0
        )
        by_date[batch_date] = {
            "batch_date": batch_date,
            "model_count": len(current_batch_metrics),
            "best_cashflow_usd": round(best_cf, 2),
            "lowest_dd_pct": round(low_dd, 2),
            "has_dashboard": True,
        }
    return [by_date[d] for d in sorted(by_date.keys(), reverse=True)]


def render_dashboard_html(
    *,
    batch_date: str,
    batch_metrics: Sequence[dict[str, Any]],
    all_models_metrics: Sequence[dict[str, Any]],
    ranking_board: dict[str, Any],
    batch_series: dict[str, dict[str, Any]] | None = None,
    corr_matrix: dict[str, Any] | None = None,
    default_tab: str = "daily",
    available_dates: Sequence[Any] | None = None,
) -> str:
    """Render a 100% self-contained offline-ready 9-panel interactive HTML Dashboard (zero CDN dependencies)."""
    rule = ranking_board.get("ranking_rule", {})
    default_dd_cap = float(rule.get("hard_gates", {}).get("max_drawdown_pct_limit", 40.0))
    top_n = int(rule.get("top_n", 9))
    batch_ids = [m["model_id"] for m in batch_metrics]
    top_ids = [m["model_id"] for m in (ranking_board.get("top_ranked") or []) if m.get("model_id")]
    series_ids = list(dict.fromkeys([*batch_ids, *top_ids]))
    active_tab = default_tab if default_tab in {"daily", "ranking", "all"} else "daily"

    resolved_corr = corr_matrix
    if resolved_corr is None and batch_series:
        resolved_corr = compute_return_correlation_matrix(batch_ids, batch_series)
    if resolved_corr is None:
        resolved_corr = {"labels": [], "matrix": []}

    top_corr_matrix = (
        compute_return_correlation_matrix(top_ids, batch_series)
        if (top_ids and batch_series)
        else {"labels": [], "matrix": []}
    )

    normalized_dates = _normalize_available_dates(
        batch_date,
        available_dates,
        current_batch_metrics=batch_metrics,
    )

    embedded_data = {
        "batch_date": batch_date,
        "generated_at_utc": ranking_board.get("generated_at_utc", ""),
        "total_trials": int(ranking_board.get("total_trials", len(all_models_metrics))),
        "top_n": top_n,
        "default_dd_cap": default_dd_cap,
        "default_tab": active_tab,
        "batch_ids": batch_ids,
        "top_ranked_ids": top_ids,
        "batch_models": list(batch_metrics),
        "available_dates": normalized_dates,
        "models": list(all_models_metrics),
        "series": _compact_series_for_html(series_ids, batch_series),
        "corr_matrix": resolved_corr,
        "top_corr_matrix": top_corr_matrix,
    }
    safe_json = _safe_inline_json(embedded_data)
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
    select, input[type="range"], input[type="date"] {{
      background: var(--bm-surface); color: var(--bm-fg); border: 1px solid var(--bm-border);
      border-radius: 6px; padding: 5px 8px; font-size: 12px; font-family: inherit;
    }}
    .date-nav {{
      display: inline-flex; flex-wrap: wrap; align-items: center; gap: 6px;
      padding: 4px 8px; border-radius: 10px; background: var(--bm-card); border: 1px solid var(--bm-border);
    }}
    .nav-btn {{
      display: inline-flex; align-items: center; justify-content: center;
      padding: 5px 9px; border-radius: 7px; border: 1px solid var(--bm-border);
      background: var(--bm-surface); color: var(--bm-fg); text-decoration: none;
      font-size: 11px; font-weight: 600; transition: border-color 0.15s, background 0.15s;
    }}
    .nav-btn:hover {{ border-color: var(--bm-primary); }}
    .nav-btn.disabled {{ opacity: 0.4; pointer-events: none; }}
    .range-bar {{
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px;
      background: var(--bm-card); border: 1px solid var(--bm-border); border-radius: 12px; padding: 10px 14px;
    }}
    .range-group {{ display: flex; flex-wrap: wrap; align-items: center; gap: 7px; }}
    .preset-group {{ display: inline-flex; flex-wrap: wrap; gap: 5px; }}
    .range-lbl {{ display: inline-flex; align-items: center; gap: 5px; font-size: 12px; }}
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
    .pill-mini.active {{ background: var(--bm-primary); color: var(--bm-primary-fg); border-color: var(--bm-primary); }}
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
    .portal-bar {{
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px;
      background: var(--bm-card); border: 1px solid var(--bm-border); border-left: 4px solid var(--bm-primary);
      border-radius: 12px; padding: 9px 14px;
    }}
    .portal-brand {{ font-weight: 800; font-size: 13px; color: var(--bm-fg); text-decoration: none; }}
    .portal-pills {{ display: flex; flex-wrap: wrap; gap: 7px; align-items: center; }}
    .pp {{
      display: inline-flex; align-items: center; padding: 5px 11px; border-radius: 999px;
      font-size: 12px; font-weight: 700; text-decoration: none;
      border: 1px solid var(--bm-border); background: var(--bm-surface); color: var(--bm-fg);
    }}
    .pp:hover {{ border-color: var(--bm-primary); }}
    .pp.b-on {{ background: var(--bm-primary); color: #ffffff; border-color: var(--bm-primary); }}
    .pp.a-go {{ color: #f59e0b; border-color: rgba(245, 158, 11, 0.45); background: rgba(245, 158, 11, 0.12); }}
  </style>
</head>
<body>
  <div class="wrap">
    <nav class="portal-bar" aria-label="Unified Research Portal Navigation">
      <div class="portal-pills">
        <a class="pp" href="../../../index.html">หน้าหลัก</a>
        <a class="pp a-go" href="../../../alpha/index.html#sym=XAUUSD">ALPHA · ทองคำ (XAUUSD)</a>
        <a class="pp a-go" href="../../../alpha/index.html#sym=ETHUSDT">ALPHA · ETH</a>
        <a class="pp b-on" href="#">BETA · ETH Grid</a>
      </div>
    </nav>
    <header class="header">
      <div>
        <h1 class="title">Alpha_mining — Beta Mining 9-Panel Research Dashboard ({safe_date})</h1>
        <p id="hdr-sub" class="subtitle"></p>
      </div>
      <div class="tabs">
        <div class="date-nav" aria-label="Historical Batch Date Switcher">
          <a id="btn-prev-day" class="nav-btn disabled" href="#" title="วัน Mine ก่อนหน้า">◀ Prev</a>
          <select id="batch-date-select" aria-label="Select Daily Mining Batch Date" class="mono"></select>
          <a id="btn-next-day" class="nav-btn disabled" href="#" title="วัน Mine ถัดไป">Next ▶</a>
          <a id="btn-all-days" class="nav-btn" href="../../index.html" title="หน้ารวมผล Mine ทุกวันย้อนหลัง">All Days</a>
        </div>
        <button data-tab="daily" class="tab-btn{daily_active}">Daily Batch — 9 Panels</button>
        <button data-tab="top9" class="tab-btn">Top-{top_n} — 9 Panels</button>
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
      <div class="range-bar" id="lookback-bar">
        <div class="range-group">
          <span class="muted" style="font-weight:700;">ช่วงวันย้อนหลัง (Lookback):</span>
          <div id="lookback-presets" class="preset-group">
            <button type="button" class="pill-mini range-preset" data-days="30">30D</button>
            <button type="button" class="pill-mini range-preset" data-days="90">90D</button>
            <button type="button" class="pill-mini range-preset" data-days="180">180D</button>
            <button type="button" class="pill-mini range-preset" data-days="365">365D</button>
            <button type="button" class="pill-mini range-preset active" data-days="0">ALL</button>
          </div>
        </div>
        <div class="range-group">
          <label class="range-lbl"><span class="muted">From</span><input id="range-start" type="date" aria-label="Lookback Start Date" /></label>
          <label class="range-lbl"><span class="muted">To</span><input id="range-end" type="date" aria-label="Lookback End Date" /></label>
          <button id="btn-range-reset" type="button" class="pill-mini">Reset</button>
          <span id="range-badge" class="badge badge-today">Full Window</span>
        </div>
      </div>

      <div class="legend-bar">
        <span id="legend-scope-label" class="muted" style="font-weight:700;margin-right:4px;">Models ({safe_date}):</span>
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
            <span id="sub-weekly" class="panel-sub">USDT · Grouped Bars + Dashed Mean</span>
          </div>
          <div class="canvas-box"><canvas id="chart-weekly"></canvas></div>
        </div>

        <div class="panel">
          <div class="panel-hdr">
            <span class="panel-title">02 / Accumulated Realized CF</span>
            <span id="sub-cumulative" class="panel-sub">USDT · Realized Profit Only</span>
          </div>
          <div class="canvas-box"><canvas id="chart-cumulative"></canvas></div>
        </div>

        <div class="panel">
          <div class="panel-hdr">
            <span class="panel-title">03 / Equity Returns vs ETH Benchmark</span>
            <span id="sub-equity" class="panel-sub">% · Daily MTM + Dashed ETH Buy &amp; Hold</span>
          </div>
          <div class="canvas-box"><canvas id="chart-equity"></canvas></div>
        </div>

        <div class="panel">
          <div class="panel-hdr">
            <span class="panel-title">04 / Equity Drawdown</span>
            <span id="sub-drawdown" class="panel-sub">% · 1m Running Peak, Daily Snapshots</span>
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
            <span id="sub-volume" class="panel-sub">ETH · Total BUY (Green) &amp; SELL (Blue)</span>
          </div>
          <div class="canvas-box"><canvas id="chart-volume"></canvas></div>
        </div>

        <div class="panel">
          <div class="panel-hdr">
            <span class="panel-title">08 / Beta &amp; Correlation vs ETH</span>
            <span id="sub-betacorr" class="panel-sub">Daily Simple Returns · Beta (Amber) &amp; Corr (Violet)</span>
          </div>
          <div class="canvas-box"><canvas id="chart-betacorr"></canvas></div>
        </div>

        <div class="panel panel-wide">
          <div class="panel-hdr">
            <span class="panel-title">09 / Return Correlation Matrix</span>
            <span id="sub-heatmap" class="panel-sub">All Active Daily Models + ETH · RdBu Diverging [-1.0 .. +1.0]</span>
          </div>
          <div class="canvas-box tall"><canvas id="chart-heatmap"></canvas></div>
        </div>
      </div>

      <div class="card" style="padding:0;overflow:hidden;">
        <div style="padding:10px 14px;border-bottom:1px solid var(--bm-border);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
          <strong id="perf-table-title">Full Performance Summary — Daily Batch ({safe_date})</strong>
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
                <th id="th-dd" class="num">Max DD %</th>
                <th class="num">Realized CF</th>
                <th class="num">Unrealized</th>
                <th class="num">AVG Weekly</th>
                <th class="num">Buy / Sell Fills</th>
                <th class="num">Buy / Sell ETH</th>
                <th class="num">End ETH</th>
                <th id="th-util" class="num">Max Util %</th>
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
          <div style="padding:10px 14px;border-bottom:1px solid var(--bm-border);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
            <strong>Top-{top_n} Cashflow → DD Ranking Board (คลิกแถวเพื่อดู Isolated Model)</strong>
            <div style="display:flex;align-items:center;gap:10px;">
              <span class="muted">Hard Gate: No Liq + Max DD</span>
              <button id="btn-open-top9-panels" type="button" class="pill-mini active">ดูกราฟ 9-Panel ของ Top-{top_n}</button>
            </div>
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
    const DAILY_MODELS = (Array.isArray(PAYLOAD.batch_models) && PAYLOAD.batch_models.length)
      ? PAYLOAD.batch_models
      : BATCH_IDS.map(id => MODEL_MAP.get(id)).filter(Boolean);
    const TOP_RANK_IDS = Array.isArray(PAYLOAD.top_ranked_ids) ? PAYLOAD.top_ranked_ids : [];
    const TOP_RANK_MODELS = (TOP_RANK_IDS.length
      ? TOP_RANK_IDS.map(id => MODEL_MAP.get(id)).filter(Boolean)
      : (PAYLOAD.models || [])
          .filter(m => !m.would_liquidate && Number(m.max_drawdown_pct) <= Number(PAYLOAD.default_dd_cap || 40))
          .sort((a, b) => Number(b.cashflow_net_usd || 0) - Number(a.cashflow_net_usd || 0))
          .slice(0, Number(PAYLOAD.top_n || 9)));

    const MODEL_COLOR = new Map();
    [...DAILY_MODELS, ...TOP_RANK_MODELS].forEach((m, idx) => {{
      if (!MODEL_COLOR.has(m.model_id)) MODEL_COLOR.set(m.model_id, PALETTE[idx % PALETTE.length]);
    }});

    let activePanelScope = "daily"; // "daily" | "top9"
    function getPoolModels() {{
      return (activePanelScope === "top9" && TOP_RANK_MODELS.length) ? TOP_RANK_MODELS : DAILY_MODELS;
    }}

    const visibleIds = new Set(DAILY_MODELS.map(m => m.model_id));
    let selectedId = (DAILY_MODELS[0] && DAILY_MODELS[0].model_id) || (PAYLOAD.models[0] && PAYLOAD.models[0].model_id) || "";
    let currentTab = PAYLOAD.default_tab || "daily";

    const RAW_SERIES = PAYLOAD.series || {{}};
    const ALL_DATES = RAW_SERIES.dates || [];
    const ALL_WEEKS = RAW_SERIES.weeks || [];
    let rangeStartIdx = 0;
    let rangeEndIdx = Math.max(0, ALL_DATES.length - 1);
    let activePresetDays = 0; // 0 = ALL, >0 = preset N days, -1 = custom date range
    let cachedWindowKey = "";
    let cachedWindowData = null;

    const hoverState = {{}};
    const tooltipEl = document.getElementById("chart-tooltip");

    function escHtml(v) {{
      return String(v ?? "").replace(/[&<>"']/g, ch => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[ch]));
    }}

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

    function toIsoWeekKey(ymd) {{
      const parts = String(ymd || "").split("-").map(Number);
      if (parts.length !== 3 || parts.some(isNaN)) return "";
      const d = new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
      const dayNum = d.getUTCDay() || 7;
      d.setUTCDate(d.getUTCDate() + 4 - dayNum);
      const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
      const wkNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
      return `${{d.getUTCFullYear()}}-W${{String(wkNo).padStart(2, "0")}}`;
    }}

    function computeBetaAndCorr(seriesY, seriesX) {{
      const n = Math.min(seriesY.length, seriesX.length);
      if (n < 2) return {{ beta: 0, corr: 0 }};
      let sy = 0, sx = 0;
      for (let i = 0; i < n; i++) {{
        sy += seriesY[i];
        sx += seriesX[i];
      }}
      const my = sy / n;
      const mx = sx / n;
      let cov = 0, vx = 0, vy = 0;
      for (let i = 0; i < n; i++) {{
        const dy = seriesY[i] - my;
        const dx = seriesX[i] - mx;
        cov += dy * dx;
        vx += dx * dx;
        vy += dy * dy;
      }}
      const beta = vx > 1e-18 ? cov / vx : 0;
      const denom = Math.sqrt(vx * vy);
      const corr = denom > 1e-18 ? cov / denom : 0;
      return {{ beta, corr }};
    }}

    function deriveSimpleReturns(pctSeries, startIdx, endIdx) {{
      const out = [];
      const rStart = startIdx > 0 ? startIdx : 1;
      for (let i = rStart; i <= endIdx; i++) {{
        if (i - 1 < 0 || i >= pctSeries.length) continue;
        const prev = 1 + Number(pctSeries[i - 1] || 0) / 100;
        const curr = 1 + Number(pctSeries[i] || 0) / 100;
        out.push(prev > 1e-9 ? (curr / prev - 1) : 0);
      }}
      return out;
    }}

    function getWindowData() {{
      const pool = getPoolModels();
      const nAll = ALL_DATES.length;
      const s = nAll ? Math.max(0, Math.min(rangeStartIdx, nAll - 1)) : 0;
      const e = nAll ? Math.max(s, Math.min(rangeEndIdx, nAll - 1)) : -1;
      const key = `${{activePanelScope}}:${{s}}:${{e}}`;
      if (cachedWindowData && cachedWindowKey === key) return cachedWindowData;

      const byMRaw = RAW_SERIES.by_model || {{}};
      const isFull = nAll === 0 || (s === 0 && e === nAll - 1);
      const dates = nAll ? ALL_DATES.slice(s, e + 1) : [];

      let ethReturn = [];
      let ethRets = [];
      const rawEth = RAW_SERIES.eth_return || [];
      if (isFull) {{
        ethReturn = rawEth;
      }} else if (rawEth.length) {{
        const baseEth = s > 0 && rawEth[s - 1] !== undefined ? (1 + Number(rawEth[s - 1]) / 100) : 1;
        for (let i = s; i <= e; i++) {{
          const f = 1 + Number(rawEth[i] || 0) / 100;
          ethReturn.push(baseEth > 1e-9 ? ((f / baseEth - 1) * 100) : 0);
        }}
        ethRets = deriveSimpleReturns(rawEth, s, e);
      }}

      let weeks = ALL_WEEKS;
      let wkIndices = null;
      if (!isFull && dates.length && ALL_WEEKS.length) {{
        const startWk = toIsoWeekKey(dates[0]);
        const endWk = toIsoWeekKey(dates[dates.length - 1]);
        wkIndices = [];
        for (let w = 0; w < ALL_WEEKS.length; w++) {{
          if (ALL_WEEKS[w] >= startWk && ALL_WEEKS[w] <= endWk) wkIndices.push(w);
        }}
        weeks = wkIndices.map(w => ALL_WEEKS[w]);
      }}

      const byModel = {{}};
      const stats = {{}};
      const modelRetsMap = {{}};

      pool.forEach(m => {{
        const mid = m.model_id;
        const initCap = Number(m.initial_capital || 10000);
        const ms = byMRaw[mid];
        if (isFull || !ms || !nAll) {{
          if (ms) {{
            byModel[mid] = {{
              cf: ms.cf || [],
              equity: ms.equity || [],
              dd: ms.dd || [],
              inventory: ms.inventory || [],
              capital: ms.capital || [],
              weekly: ms.weekly || []
            }};
          }}
          stats[mid] = {{
            isFull: true,
            cashflow: Number(m.cashflow_net_usd || 0),
            avgWeekly: Number(m.avg_weekly_cf_usd || 0),
            maxDdPct: Number(m.max_drawdown_pct || 0),
            returnPct: Number(m.mtm_return_pct || 0),
            finalEquity: initCap + Number(m.mtm_pnl_usd || 0),
            endEth: Number(m.ending_open_qty || 0),
            maxUtilPct: Number(m.max_utilization_pct || 0),
            beta: Number(m.beta_to_eth || 0),
            corr: Number(m.corr_to_eth || 0)
          }};
          return;
        }}

        const rawCf = ms.cf || [];
        const baseCf = s > 0 && rawCf[s - 1] !== undefined ? Number(rawCf[s - 1]) : 0;
        const cfSlice = [];
        for (let i = s; i <= e; i++) cfSlice.push(Number(rawCf[i] || 0) - baseCf);

        const rawEq = ms.equity || [];
        const baseEq = s > 0 && rawEq[s - 1] !== undefined ? (1 + Number(rawEq[s - 1]) / 100) : 1;
        const eqSlice = [];
        const ddSlice = [];
        let runPeak = baseEq;
        let maxWinDd = 0;
        for (let i = s; i <= e; i++) {{
          const f = 1 + Number(rawEq[i] || 0) / 100;
          eqSlice.push(baseEq > 1e-9 ? ((f / baseEq - 1) * 100) : 0);
          if (f > runPeak) runPeak = f;
          const ddVal = runPeak > 1e-9 ? Math.min(0, (f / runPeak - 1) * 100) : 0;
          ddSlice.push(ddVal);
          if (-ddVal > maxWinDd) maxWinDd = -ddVal;
        }}

        const invSlice = (ms.inventory || []).slice(s, e + 1);
        const capSlice = (ms.capital || []).slice(s, e + 1);
        const rawWk = ms.weekly || [];
        const wkSlice = wkIndices ? wkIndices.map(w => Number(rawWk[w] || 0)) : rawWk;
        const avgWk = wkSlice.length ? (wkSlice.reduce((a, b) => a + b, 0) / wkSlice.length) : 0;

        const mRets = deriveSimpleReturns(rawEq, s, e);
        modelRetsMap[mid] = mRets;
        const bc = computeBetaAndCorr(mRets, ethRets);
        const maxUtilUsd = capSlice.length ? Math.max(...capSlice.map(Number)) : 0;
        const endEqFactor = 1 + Number(rawEq[e] || 0) / 100;

        byModel[mid] = {{
          cf: cfSlice,
          equity: eqSlice,
          dd: ddSlice,
          inventory: invSlice,
          capital: capSlice,
          weekly: wkSlice
        }};
        stats[mid] = {{
          isFull: false,
          cashflow: cfSlice.length ? cfSlice[cfSlice.length - 1] : 0,
          avgWeekly: avgWk,
          maxDdPct: maxWinDd,
          returnPct: eqSlice.length ? eqSlice[eqSlice.length - 1] : 0,
          finalEquity: initCap * endEqFactor,
          endEth: invSlice.length ? Number(invSlice[invSlice.length - 1]) : 0,
          maxUtilPct: initCap > 0 ? (maxUtilUsd / initCap * 100) : 0,
          beta: bc.beta,
          corr: bc.corr
        }};
      }});

      let corrMatrix = (activePanelScope === "top9" && PAYLOAD.top_corr_matrix && (PAYLOAD.top_corr_matrix.labels || []).length)
        ? PAYLOAD.top_corr_matrix
        : (PAYLOAD.corr_matrix || {{ labels: [], matrix: [] }});
      if (!isFull) {{
        const vecs = [];
        pool.forEach(m => {{
          const r = modelRetsMap[m.model_id];
          if (r && r.length >= 2) vecs.push([m.model_id, r]);
        }});
        if (ethRets.length >= 2) vecs.push(["ETH", ethRets]);
        const labels = vecs.map(v => v[0]);
        const matrix = vecs.map((vi, r) => vecs.map((vj, c) => (
          r === c ? 1.0 : Number(computeBetaAndCorr(vi[1], vj[1]).corr.toFixed(3))
        )));
        corrMatrix = {{ labels, matrix }};
      }}

      cachedWindowKey = key;
      cachedWindowData = {{
        isFull,
        startIdx: s,
        endIdx: e,
        daysCount: dates.length,
        startDate: dates.length ? dates[0] : "",
        endDate: dates.length ? dates[dates.length - 1] : "",
        dates,
        ethReturn,
        weeks,
        byModel,
        stats,
        corrMatrix
      }};
      return cachedWindowData;
    }}

    function findStartIndexForDate(ymd) {{
      if (!ALL_DATES.length || !ymd) return 0;
      for (let i = 0; i < ALL_DATES.length; i++) {{
        if (ALL_DATES[i] >= ymd) return i;
      }}
      return ALL_DATES.length - 1;
    }}

    function findEndIndexForDate(ymd) {{
      if (!ALL_DATES.length || !ymd) return Math.max(0, ALL_DATES.length - 1);
      for (let i = ALL_DATES.length - 1; i >= 0; i--) {{
        if (ALL_DATES[i] <= ymd) return i;
      }}
      return 0;
    }}

    function updateLookbackUi() {{
      const startInput = document.getElementById("range-start");
      const endInput = document.getElementById("range-end");
      const badge = document.getElementById("range-badge");
      const resetBtn = document.getElementById("btn-range-reset");
      const presetBtns = document.querySelectorAll(".range-preset");

      if (!ALL_DATES.length) {{
        if (startInput) startInput.disabled = true;
        if (endInput) endInput.disabled = true;
        if (resetBtn) resetBtn.disabled = true;
        presetBtns.forEach(b => {{ b.disabled = true; }});
        if (badge) badge.textContent = "No Daily Series";
        return;
      }}

      const win = getWindowData();
      startInput.min = ALL_DATES[0];
      startInput.max = ALL_DATES[ALL_DATES.length - 1];
      endInput.min = ALL_DATES[0];
      endInput.max = ALL_DATES[ALL_DATES.length - 1];
      startInput.value = win.startDate;
      endInput.value = win.endDate;

      presetBtns.forEach(b => {{
        const d = Number(b.dataset.days || 0);
        const isAct = (activePresetDays === d) || (win.isFull && d === 0);
        b.classList.toggle("active", isAct);
      }});

      if (badge) {{
        badge.textContent = win.isFull
          ? `${{win.startDate}} → ${{win.endDate}} (${{win.daysCount}}d · Full)`
          : `${{win.startDate}} → ${{win.endDate}} (${{win.daysCount}}d · Window)`;
      }}

      const setSub = (id, txt) => {{
        const el = document.getElementById(id);
        if (el) el.textContent = txt;
      }};
      setSub(
        "sub-weekly",
        win.isFull
          ? `USDT · Grouped Bars + Dashed Mean (${{win.weeks.length}} wks)`
          : `USDT · Overlapping ISO Weeks + Dashed Mean (${{win.weeks.length}} wks)`
      );
      setSub("sub-cumulative", win.isFull ? "USDT · Realized Profit Only" : "USDT · Window Realized CF (Rebased to $0)");
      setSub("sub-equity", win.isFull ? "% · Daily MTM + Dashed ETH Buy & Hold" : "% · Window Rebased to 0% + Dashed ETH");
      setSub("sub-drawdown", win.isFull ? "% · 1m Running Peak, Daily Snapshots" : "% · Window Peak-to-Trough (Daily-Close Snapshots)");
      setSub("sub-volume", win.isFull ? "ETH · Total BUY (Green) & SELL (Blue)" : "ETH · Full-Run Totals (per-day fills not stored)");
      setSub("sub-betacorr", win.isFull ? "Daily Simple Returns · Beta (Amber) & Corr (Violet)" : "Window Daily Returns · Beta (Amber) & Corr (Violet)");
      setSub("sub-heatmap", win.isFull ? "All Active Daily Models + ETH · RdBu Diverging [-1.0 .. +1.0]" : "Window Daily Returns (Active Models + ETH) · RdBu [-1.0 .. +1.0]");
      setSub("th-dd", win.isFull ? "Max DD %" : "Win DD % (Daily)");
      setSub("th-util", win.isFull ? "Max Util %" : "Win Util % (Daily)");
      const tblTitle = document.getElementById("perf-table-title");
      const scopeTag = activePanelScope === "top9"
        ? `Top-${{PAYLOAD.top_n}} Cumulative Leaders`
        : `Daily Batch (${{PAYLOAD.batch_date}})`;
      if (tblTitle) {{
        tblTitle.textContent = win.isFull
          ? `Full Performance Summary — ${{scopeTag}}`
          : `Window Performance Summary (${{win.startDate}} → ${{win.endDate}} · ${{win.daysCount}}d) — ${{scopeTag}}`;
      }}
      const legLbl = document.getElementById("legend-scope-label");
      if (legLbl) {{
        legLbl.textContent = activePanelScope === "top9"
          ? `Top-${{PAYLOAD.top_n}} Leaders:`
          : `Models (${{PAYLOAD.batch_date}}):`;
      }}
    }}

    function applyDateRange(sIdx, eIdx, presetDays) {{
      if (!ALL_DATES.length) return;
      const maxIdx = ALL_DATES.length - 1;
      rangeStartIdx = Math.max(0, Math.min(sIdx, maxIdx));
      rangeEndIdx = Math.max(rangeStartIdx, Math.min(eIdx, maxIdx));
      activePresetDays = (rangeStartIdx === 0 && rangeEndIdx === maxIdx) ? 0 : presetDays;
      cachedWindowData = null;
      cachedWindowKey = "";
      Object.keys(hoverState).forEach(k => delete hoverState[k]);
      hideTooltip();
      updateLookbackUi();
      renderDailyPillsAndTables();
      drawAllDailyCharts();
    }}

    function isSafeDate(d) {{
      return /^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(String(d || ""));
    }}

    function renderBatchDateSwitcher(entries) {{
      const sel = document.getElementById("batch-date-select");
      const prevBtn = document.getElementById("btn-prev-day");
      const nextBtn = document.getElementById("btn-next-day");
      if (!sel) return;

      const byDate = new Map();
      (entries || []).forEach(it => {{
        const d = typeof it === "string" ? it : (it && it.batch_date);
        const hasDash = typeof it === "string" || !it || it.has_dashboard !== false;
        if (isSafeDate(d) && (hasDash || d === PAYLOAD.batch_date)) {{
          byDate.set(String(d), typeof it === "object" ? it : {{ batch_date: String(d) }});
        }}
      }});
      if (isSafeDate(PAYLOAD.batch_date) && !byDate.has(PAYLOAD.batch_date)) {{
        byDate.set(PAYLOAD.batch_date, {{ batch_date: PAYLOAD.batch_date, model_count: DAILY_MODELS.length }});
      }}
      const sortedDates = [...byDate.keys()].sort((a, b) => b.localeCompare(a));
      sel.innerHTML = "";
      sortedDates.forEach(d => {{
        const meta = byDate.get(d) || {{}};
        const opt = document.createElement("option");
        opt.value = d;
        const cnt = Number(meta.model_count || 0);
        opt.textContent = cnt > 0 ? `${{d}} (${{cnt}}m)` : d;
        if (d === PAYLOAD.batch_date) opt.selected = true;
        sel.appendChild(opt);
      }});

      const curIdx = sortedDates.indexOf(PAYLOAD.batch_date);
      const olderDate = curIdx >= 0 && curIdx + 1 < sortedDates.length ? sortedDates[curIdx + 1] : "";
      const newerDate = curIdx > 0 ? sortedDates[curIdx - 1] : "";

      if (prevBtn) {{
        if (olderDate) {{
          prevBtn.href = `../${{olderDate}}/dashboard.html`;
          prevBtn.classList.remove("disabled");
          prevBtn.title = `ย้อนกลับไปวันก่อนหน้า (${{olderDate}})`;
        }} else {{
          prevBtn.href = "#";
          prevBtn.classList.add("disabled");
          prevBtn.title = "ไม่มีวัน Mine ก่อนหน้า";
        }}
      }}
      if (nextBtn) {{
        if (newerDate) {{
          nextBtn.href = `../${{newerDate}}/dashboard.html`;
          nextBtn.classList.remove("disabled");
          nextBtn.title = `ไปวันถัดไป (${{newerDate}})`;
        }} else {{
          nextBtn.href = "#";
          nextBtn.classList.add("disabled");
          nextBtn.title = "อยู่ที่วันล่าสุดแล้ว";
        }}
      }}
    }}

    function initBatchDateSwitcher() {{
      renderBatchDateSwitcher(PAYLOAD.available_dates || []);
      const sel = document.getElementById("batch-date-select");
      if (sel) {{
        sel.addEventListener("change", () => {{
          const target = sel.value;
          if (isSafeDate(target) && target !== PAYLOAD.batch_date) {{
            window.location.href = `../${{target}}/dashboard.html`;
          }}
        }});
      }}
      if (window.location && window.location.protocol !== "file:" && typeof fetch === "function") {{
        fetch("../index.json", {{ cache: "no-cache" }})
          .then(r => (r.ok ? r.json() : null))
          .then(idx => {{
            if (idx && Array.isArray(idx.days) && idx.days.length) {{
              renderBatchDateSwitcher(idx.days);
            }}
          }})
          .catch(() => {{}});
      }}
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
      return getPoolModels().filter(m => visibleIds.has(m.model_id));
    }}

    function showTooltip(clientX, clientY, title, rows) {{
      let htmlRows = rows.map(r => `
        <div class="tt-row">
          <span class="tt-lbl">
            ${{r.color ? `<span class="tt-dot" style="background:${{escHtml(r.color)}}"></span>` : ""}}
            <span>${{escHtml(r.label)}}</span>
          </span>
          <strong style="color:${{escHtml(r.valColor || "inherit")}}">${{escHtml(r.value)}}</strong>
        </div>
      `).join("");
      tooltipEl.innerHTML = `<div class="tt-title">${{escHtml(title)}}</div>${{htmlRows}}`;
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
      const win = getWindowData();
      const weeks = win.weeks || [];
      const active = getActiveModels();
      const seriesList = active.map(m => ({{
        id: m.model_id,
        label: shortLabel(m.model_id),
        color: MODEL_COLOR.get(m.model_id) || "#22c55e",
        values: (win.byModel[m.model_id] && win.byModel[m.model_id].weekly) || [],
        mean: Number((win.stats[m.model_id] && win.stats[m.model_id].avgWeekly) ?? m.avg_weekly_cf_usd ?? 0)
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
      const win = getWindowData();
      const raw = win.corrMatrix || PAYLOAD.corr_matrix || {{ labels: [], matrix: [] }};
      const allLabels = raw.labels || [];
      const allMat = raw.matrix || [];

      const keepIdx = [];
      allLabels.forEach((lbl, idx) => {{
        if (lbl === "ETH" || visibleIds.has(lbl)) keepIdx.push(idx);
      }});
      if (keepIdx.length < 2) {{
        drawEmptyMsg(ctx, w, h, "Correlation matrix requires >= 2 daily return points across >= 2 series (models + ETH)", theme);
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
      const win = getWindowData();
      const byM = win.byModel || {{}};
      const dates = win.dates || [];
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
      if ((win.ethReturn || []).length) {{
        eqLines.push({{
          label: "ETH Benchmark",
          color: theme.eth,
          dashed: true,
          values: win.ethReturn
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

      // 07 / Executed Trading Volume (Full-Run Totals)
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

      // 08 / Beta & Correlation vs ETH (Window-Scoped)
      drawCategoryGroupedBars("chart-betacorr", {{
        k1: "Beta to ETH",
        k2: "Corr to ETH",
        c1: "#f59e0b",
        c2: "#a855f7",
        maxCap: 1.0,
        yFmt: v => v.toFixed(2),
        lblFmt: v => v.toFixed(2),
        items: active.map(m => {{
          const st = win.stats[m.model_id] || {{}};
          return {{
            id: m.model_id,
            short: shortLabel(m.model_id),
            modelColor: MODEL_COLOR.get(m.model_id),
            v1: Number(st.beta ?? m.beta_to_eth ?? 0),
            v2: Number(st.corr ?? m.corr_to_eth ?? 0),
            meta: m,
            winStats: st
          }};
        }})
      }});

      // 09 / Return Correlation Matrix (Window-Scoped)
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
              {{ label: "BUY Volume (Full)", color: "#22c55e", value: `${{fmtNum(it.v1, 3)}} ETH (${{Number(m.buy_fills || 0).toLocaleString()}} fills)` }},
              {{ label: "SELL Volume (Full)", color: "#3b82f6", value: `${{fmtNum(it.v2, 3)}} ETH (${{Number(m.sell_fills || 0).toLocaleString()}} fills)` }},
              {{ label: "Total Turnover", color: it.modelColor, value: fmtUsd(m.turnover_usd || 0, false) }}
            ]);
          }} else {{
            const ws = it.winStats || {{}};
            const retLabel = ws.isFull === false ? "Window Return" : "MTM Return";
            const retVal = ws.returnPct !== undefined ? ws.returnPct : (m.mtm_return_pct || 0);
            showTooltip(ev.clientX, ev.clientY, it.id, [
              {{ label: "Beta to ETH", color: "#f59e0b", value: Number(it.v1).toFixed(4) }},
              {{ label: "Corr to ETH", color: "#a855f7", value: Number(it.v2).toFixed(4) }},
              {{ label: retLabel, color: it.modelColor, value: fmtPct(retVal) }}
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
      const isPanelView = (target === "daily" || target === "top9");
      if (isPanelView) {{
        const nextScope = target === "top9" ? "top9" : "daily";
        if (activePanelScope !== nextScope) {{
          activePanelScope = nextScope;
          cachedWindowData = null;
          cachedWindowKey = "";
          visibleIds.clear();
          getPoolModels().forEach(m => visibleIds.add(m.model_id));
          updateLookbackUi();
          renderDailyPillsAndTables();
        }}
      }}
      document.getElementById("view-daily").classList.toggle("hidden", !isPanelView);
      document.getElementById("view-ranking").classList.toggle("hidden", target !== "ranking");
      document.getElementById("view-all").classList.toggle("hidden", target !== "all");
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === target));
      if (isPanelView) {{
        requestAnimationFrame(drawAllDailyCharts);
      }}
    }}

    function renderDailyPillsAndTables() {{
      const pool = getPoolModels();
      const win = getWindowData();
      const pillHost = document.getElementById("daily-legend-pills");
      pillHost.innerHTML = "";
      pool.forEach((m, idx) => {{
        const color = MODEL_COLOR.get(m.model_id);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "pill" + (visibleIds.has(m.model_id) ? "" : " off");
        const prefix = activePanelScope === "top9" ? `#${{idx + 1}} ` : "";
        btn.innerHTML = `<span class="dot" style="background:${{escHtml(color)}}"></span><span>${{prefix}}${{escHtml(shortLabel(m.model_id))}}</span>`;
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
            pool.forEach(x => visibleIds.add(x.model_id));
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
      pool.forEach((m, i) => {{
        const color = MODEL_COLOR.get(m.model_id);
        const isOn = visibleIds.has(m.model_id);
        const pass = !m.would_liquidate && Number(m.max_drawdown_pct) <= Number(PAYLOAD.default_dd_cap || 40);
        const st = win.stats[m.model_id] || {{
          isFull: true,
          cashflow: Number(m.cashflow_net_usd || 0),
          avgWeekly: Number(m.avg_weekly_cf_usd || 0),
          maxDdPct: Number(m.max_drawdown_pct || 0),
          returnPct: Number(m.mtm_return_pct || 0),
          beta: Number(m.beta_to_eth || 0),
          corr: Number(m.corr_to_eth || 0)
        }};
        const cfLbl = win.isFull ? "Realized CF" : "Win CF";
        const ddLbl = win.isFull ? "Max DD" : "Win DD (Daily)";
        const retLbl = win.isFull ? "MTM Return" : "Win Return";
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
        const cardBadge = activePanelScope === "top9" ? `Top #${{i + 1}}/${{pool.length}}` : `Model ${{i + 1}}/${{pool.length}}`;
        el.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
            <span class="muted mono">${{cardBadge}}</span>
            <span class="badge ${{pass ? 'badge-pass' : 'badge-fail'}}" title="Full-run Hard Gate (No Liq + Max DD ≤ ${{Number(PAYLOAD.default_dd_cap || 40)}}%)">${{pass ? 'PASS' : 'FAIL'}}</span>
          </div>
          <div class="mono" style="font-weight:700;margin-bottom:1px;">${{escHtml(m.model_id)}}</div>
          <div class="muted" style="font-size:11px;margin-bottom:6px;">${{escHtml(m.signal_name)}}</div>
          <div class="mono" style="font-size:12px;display:flex;flex-direction:column;gap:2px;">
            <div style="display:flex;justify-content:space-between;"><span>${{cfLbl}}</span><strong class="${{st.cashflow >= 0 ? 'pos' : 'neg'}}">${{fmtUsd(st.cashflow)}}</strong></div>
            <div style="display:flex;justify-content:space-between;"><span>AVG Weekly</span><span class="${{st.avgWeekly >= 0 ? 'pos' : 'neg'}}">${{fmtUsd(st.avgWeekly)}}</span></div>
            <div style="display:flex;justify-content:space-between;"><span>${{ddLbl}}</span><strong class="warn">${{Number(st.maxDdPct).toFixed(2)}}%</strong></div>
            <div style="display:flex;justify-content:space-between;"><span>${{retLbl}}</span><span class="${{st.returnPct >= 0 ? 'pos' : 'neg'}}">${{fmtPct(st.returnPct)}}</span></div>
            <div style="display:flex;justify-content:space-between;"><span>Beta / Corr</span><span>${{Number(st.beta).toFixed(2)}} / ${{Number(st.corr).toFixed(2)}}</span></div>
          </div>
        `;
        cards.appendChild(el);
      }});

      const perfBody = document.getElementById("daily-perf-body");
      perfBody.innerHTML = "";
      pool.forEach(m => {{
        const color = MODEL_COLOR.get(m.model_id);
        const pass = !m.would_liquidate && Number(m.max_drawdown_pct) <= Number(PAYLOAD.default_dd_cap || 40);
        const st = win.stats[m.model_id] || {{
          isFull: true,
          cashflow: Number(m.cashflow_net_usd || 0),
          avgWeekly: Number(m.avg_weekly_cf_usd || 0),
          maxDdPct: Number(m.max_drawdown_pct || 0),
          returnPct: Number(m.mtm_return_pct || 0),
          finalEquity: Number(m.initial_capital || 10000) + Number(m.mtm_pnl_usd || 0),
          endEth: Number(m.ending_open_qty || 0),
          maxUtilPct: Number(m.max_utilization_pct || 0),
          beta: Number(m.beta_to_eth || 0),
          corr: Number(m.corr_to_eth || 0)
        }};
        const fullNote = win.isFull ? "" : ' title="Full-run total (per-day breakdown not stored)"';
        const ddNote = win.isFull ? "" : ' title="Window peak-to-trough DD computed from daily-close snapshots (lower bound vs 1m intra-bar DD)"';
        const utilNote = win.isFull ? "" : ' title="Window peak capital utilization from daily-close snapshots"';
        const gateTitle = `Full-run Hard Gate (No Liq + Max DD ≤ ${{Number(PAYLOAD.default_dd_cap || 40)}}%)`;
        const tr = document.createElement("tr");
        tr.className = "data-row";
        if (!visibleIds.has(m.model_id)) tr.style.opacity = "0.45";
        tr.addEventListener("click", () => {{
          renderInspector(m);
          renderRanking();
          switchTab("ranking");
        }});
        tr.innerHTML = `
          <td class="mono" style="font-weight:700;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${{escHtml(color)}};margin-right:7px;"></span>${{escHtml(m.model_id)}}</td>
          <td class="mono muted">${{escHtml(m.signal_name)}}</td>
          <td class="num">${{fmtUsd(st.finalEquity, false)}}</td>
          <td class="num ${{st.returnPct >= 0 ? 'pos' : 'neg'}}">${{fmtPct(st.returnPct)}}</td>
          <td class="num warn" style="font-weight:700;"${{ddNote}}>-${{Number(st.maxDdPct).toFixed(2)}}%</td>
          <td class="num ${{st.cashflow >= 0 ? 'pos' : 'neg'}}" style="font-weight:700;">${{fmtUsd(st.cashflow)}}</td>
          <td class="num ${{m.unrealized_end_usd >= 0 ? 'pos' : 'neg'}}"${{fullNote}}>${{fmtUsd(m.unrealized_end_usd)}}</td>
          <td class="num ${{st.avgWeekly >= 0 ? 'pos' : 'neg'}}">${{fmtUsd(st.avgWeekly)}}</td>
          <td class="num"${{fullNote}}>${{Number(m.buy_fills || 0).toLocaleString()}} / ${{Number(m.sell_fills || 0).toLocaleString()}}</td>
          <td class="num"${{fullNote}}>${{fmtNum(m.buy_volume_eth || 0, 2)}} / ${{fmtNum(m.sell_volume_eth || 0, 2)}}</td>
          <td class="num">${{fmtNum(st.endEth, 3)}}</td>
          <td class="num"${{utilNote}}>${{Number(st.maxUtilPct).toFixed(1)}}%</td>
          <td class="num">${{Number(st.beta).toFixed(2)}} / ${{Number(st.corr).toFixed(2)}}</td>
          <td style="text-align:center;"><span class="badge ${{pass ? 'badge-pass' : 'badge-fail'}}" title="${{escHtml(gateTitle)}}">${{pass ? 'PASS' : 'FAIL'}}</span></td>
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
            <div class="mono" style="font-weight:700;">${{escHtml(m.model_id)}}${{todayTag}}</div>
            <div class="muted" style="font-size:11px;">${{escHtml(m.signal_name)}} · Trial #${{Number(m.trial_number || 0)}}</div>
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
          <td class="mono">#${{Number(m.trial_number || 0)}}</td>
          <td class="mono" style="font-weight:700;">${{escHtml(m.model_id)}}</td>
          <td class="mono">${{escHtml(m.signal_name)}}</td>
          <td class="mono">${{escHtml(m.batch_date)}}</td>
          <td class="mono">${{escHtml(m.zone_high)}}→${{escHtml(m.zone_low)}}</td>
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

    document.querySelectorAll(".range-preset").forEach(btn => {{
      btn.addEventListener("click", () => {{
        if (!ALL_DATES.length) return;
        const days = Number(btn.dataset.days || 0);
        const last = ALL_DATES.length - 1;
        if (days <= 0) {{
          applyDateRange(0, last, 0);
        }} else {{
          applyDateRange(Math.max(0, ALL_DATES.length - days), last, days);
        }}
      }});
    }});

    document.getElementById("range-start").addEventListener("change", ev => {{
      if (!ALL_DATES.length) return;
      const sIdx = findStartIndexForDate(ev.target.value);
      const eIdx = Math.max(sIdx, rangeEndIdx);
      applyDateRange(sIdx, eIdx, -1);
    }});

    document.getElementById("range-end").addEventListener("change", ev => {{
      if (!ALL_DATES.length) return;
      const eIdx = findEndIndexForDate(ev.target.value);
      const sIdx = Math.min(rangeStartIdx, eIdx);
      applyDateRange(sIdx, eIdx, -1);
    }});

    document.getElementById("btn-range-reset").addEventListener("click", () => {{
      if (!ALL_DATES.length) return;
      applyDateRange(0, ALL_DATES.length - 1, 0);
    }});

    document.getElementById("btn-show-all").addEventListener("click", () => {{
      getPoolModels().forEach(m => visibleIds.add(m.model_id));
      renderDailyPillsAndTables();
      drawAllDailyCharts();
    }});

    document.getElementById("btn-top3").addEventListener("click", () => {{
      const win = getWindowData();
      const top3 = [...getPoolModels()]
        .sort((a, b) => Number((win.stats[b.model_id] && win.stats[b.model_id].cashflow) ?? b.cashflow_net_usd) - Number((win.stats[a.model_id] && win.stats[a.model_id].cashflow) ?? a.cashflow_net_usd))
        .slice(0, 3);
      visibleIds.clear();
      top3.forEach(m => visibleIds.add(m.model_id));
      renderDailyPillsAndTables();
      drawAllDailyCharts();
    }});

    const btnOpenTop9Panels = document.getElementById("btn-open-top9-panels");
    if (btnOpenTop9Panels) {{
      btnOpenTop9Panels.addEventListener("click", () => switchTab("top9"));
    }}

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
    initBatchDateSwitcher();
    updateLookbackUi();
    renderRanking();
    renderAllModelsTable();
    renderDailyPillsAndTables();
    if (/mode=top9|tab=top9/i.test(location.hash || "")) {{
      switchTab("top9");
    }} else if (/tab=ranking/i.test(location.hash || "")) {{
      switchTab("ranking");
    }} else {{
      requestAnimationFrame(drawAllDailyCharts);
    }}
    window.addEventListener("hashchange", () => {{
      if (/mode=top9|tab=top9/i.test(location.hash || "")) switchTab("top9");
      else if (/tab=ranking/i.test(location.hash || "")) switchTab("ranking");
      else if (/tab=daily/i.test(location.hash || "")) switchTab("daily");
    }});
  </script>
</body>
</html>
"""


def render_portal_index_html(
    *,
    daily_days: Sequence[dict[str, Any]],
    ranking_board: dict[str, Any],
    latest_date: str | None = None,
) -> str:
    """Render 100% self-contained zero-CDN archive hub `beta_mining/index.html` linking all historical daily batches."""
    valid_days = [
        d for d in daily_days if isinstance(d, dict) and _SAFE_DATE_RE.fullmatch(str(d.get("batch_date", "")).strip())
    ]
    sorted_days = sorted(valid_days, key=lambda d: str(d.get("batch_date", "")), reverse=True)
    dash_days = [d for d in sorted_days if d.get("has_dashboard", True) is not False]
    cand_latest = str(latest_date or "").strip()
    if cand_latest and _SAFE_DATE_RE.fullmatch(cand_latest):
        resolved_latest = cand_latest
    elif dash_days:
        resolved_latest = str(dash_days[0]["batch_date"])
    elif sorted_days:
        resolved_latest = str(sorted_days[0]["batch_date"])
    else:
        resolved_latest = ""
    top_ranked = list(ranking_board.get("top_ranked") or [])
    rule = ranking_board.get("ranking_rule", {})
    top_n = int(rule.get("top_n", 9))
    dd_cap = float(rule.get("hard_gates", {}).get("max_drawdown_pct_limit", 40.0))

    portal_payload = {
        "generated_at_utc": str(ranking_board.get("generated_at_utc", "")),
        "latest_date": resolved_latest,
        "total_days": len(sorted_days),
        "total_trials": int(ranking_board.get("total_trials", 0)),
        "total_models": int(ranking_board.get("total_models", 0)),
        "qualified_count": int(ranking_board.get("qualified_count", 0)),
        "top_n": top_n,
        "dd_cap": dd_cap,
        "days": sorted_days,
        "top_ranked": top_ranked,
    }
    safe_json = _safe_inline_json(portal_payload)
    has_latest_dash = bool(resolved_latest) and (
        not sorted_days
        or any(str(d.get("batch_date")) == resolved_latest and d.get("has_dashboard", True) is not False for d in sorted_days)
    )
    latest_href = f"daily/{resolved_latest}/dashboard.html" if has_latest_dash else "#"
    latest_btn_label = (
        f"Open Latest 9-Panel Dashboard ({resolved_latest})"
        if has_latest_dash
        else "No Daily Batch Available Yet"
    )
    latest_btn_cls = "btn-primary" if has_latest_dash else "btn-primary disabled"

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Alpha_mining — Beta Mining Daily Archive Hub</title>
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
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 20px 22px 40px;
      background: var(--bm-bg); color: var(--bm-fg);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 13px; line-height: 1.45;
    }}
    .wrap {{ max-width: 1380px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }}
    .header {{
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
      gap: 12px; padding-bottom: 12px; border-bottom: 1px solid var(--bm-border);
    }}
    .title {{ margin: 0; font-size: 20px; font-weight: 700; }}
    .subtitle {{ margin: 3px 0 0; color: var(--bm-muted); font-size: 12px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    .btn-primary, .btn-ghost {{
      display: inline-flex; align-items: center; justify-content: center;
      padding: 8px 13px; border-radius: 8px; font-size: 12px; font-weight: 600;
      text-decoration: none; cursor: pointer; border: 1px solid var(--bm-border);
    }}
    .btn-primary {{ background: var(--bm-primary); color: var(--bm-primary-fg); border-color: var(--bm-primary); }}
    .btn-primary.disabled {{ opacity: 0.45; pointer-events: none; }}
    .btn-ghost {{ background: var(--bm-card); color: var(--bm-fg); }}
    .btn-ghost:hover {{ border-color: var(--bm-primary); }}
    .grid-4 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    .card {{ background: var(--bm-card); border: 1px solid var(--bm-border); border-radius: 12px; padding: 14px; }}
    .kpi-label {{ font-size: 12px; color: var(--bm-muted); }}
    .kpi-val {{ font-size: 20px; font-weight: 700; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin: 3px 0; }}
    .toolbar {{
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px;
      padding: 11px 14px; border-bottom: 1px solid var(--bm-border);
    }}
    input[type="search"], select {{
      background: var(--bm-surface); color: var(--bm-fg); border: 1px solid var(--bm-border);
      border-radius: 7px; padding: 6px 10px; font-size: 12px; font-family: inherit;
    }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ padding: 9px 11px; border-bottom: 1px solid var(--bm-border); text-align: left; white-space: nowrap; }}
    th {{ color: var(--bm-muted); font-weight: 600; }}
    td.num, th.num {{ text-align: right; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    tr.data-row:hover {{ background: var(--bm-surface); }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .pos {{ color: var(--bm-success); }}
    .warn {{ color: var(--bm-warning); }}
    .neg {{ color: var(--bm-error); }}
    .muted {{ color: var(--bm-muted); }}
    .chip {{
      display: inline-block; padding: 2px 7px; margin: 1px 3px 1px 0; border-radius: 999px;
      background: var(--bm-surface); border: 1px solid var(--bm-border);
      font-size: 11px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    }}
    .link-btn {{
      display: inline-flex; padding: 4px 9px; border-radius: 6px; text-decoration: none;
      font-size: 11px; font-weight: 600; border: 1px solid var(--bm-border);
      background: var(--bm-surface); color: var(--bm-fg); margin-right: 5px;
    }}
    .link-btn.primary {{ background: var(--bm-primary); color: var(--bm-primary-fg); border-color: var(--bm-primary); }}
    .portal-bar {{
      display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px;
      background: var(--bm-card); border: 1px solid var(--bm-border); border-left: 4px solid var(--bm-primary);
      border-radius: 12px; padding: 9px 14px;
    }}
    .portal-brand {{ font-weight: 800; font-size: 13px; color: var(--bm-fg); text-decoration: none; }}
    .portal-pills {{ display: flex; flex-wrap: wrap; gap: 7px; align-items: center; }}
    .pp {{
      display: inline-flex; align-items: center; padding: 5px 11px; border-radius: 999px;
      font-size: 12px; font-weight: 700; text-decoration: none;
      border: 1px solid var(--bm-border); background: var(--bm-surface); color: var(--bm-fg);
    }}
    .pp:hover {{ border-color: var(--bm-primary); }}
    .pp.b-on {{ background: var(--bm-primary); color: #ffffff; border-color: var(--bm-primary); }}
    .pp.a-go {{ color: #f59e0b; border-color: rgba(245, 158, 11, 0.45); background: rgba(245, 158, 11, 0.12); }}
  </style>
</head>
<body>
  <div class="wrap">
    <nav class="portal-bar" aria-label="Unified Research Portal Navigation">
      <a class="portal-brand" href="../index.html">Alpha_mining · Central Portal</a>
      <div class="portal-pills">
        <a class="pp" href="../index.html">Central Hub (ฐานกลาง)</a>
        <a class="pp a-go" href="../alpha/index.html">ALPHA Track · XAUUSD + ETH</a>
        <a class="pp b-on" href="index.html">BETA Track · ETH Grid</a>
      </div>
    </nav>
    <header class="header">
      <div>
        <h1 class="title">BETA TRACK — Beta Mining Daily Archive Hub</h1>
        <p id="hub-sub" class="subtitle"></p>
      </div>
      <div class="actions">
        <a id="open-latest-btn" class="{latest_btn_cls}" href="{latest_href}">{latest_btn_label}</a>
        <a class="btn-ghost" href="../index.html" style="text-decoration:none">กลับฐานกลาง</a>
        <button id="theme-toggle" type="button" class="btn-ghost">Theme</button>
      </div>
    </header>

    <section class="grid-4">
      <div class="card">
        <div class="kpi-label">Archived Mining Days</div>
        <div id="hub-days" class="kpi-val">-</div>
        <div id="hub-latest" class="kpi-label mono">-</div>
      </div>
      <div class="card">
        <div class="kpi-label">Cumulative Mined Trials</div>
        <div id="hub-trials" class="kpi-val">-</div>
        <div id="hub-qual" class="kpi-label pos">-</div>
      </div>
      <div class="card">
        <div class="kpi-label">#1 All-Time Cashflow Leader</div>
        <div id="hub-top1" class="kpi-val" style="font-size:16px">-</div>
        <div id="hub-top1-sub" class="kpi-label pos mono">-</div>
      </div>
      <div class="card">
        <div class="kpi-label">Hard Safety Gate</div>
        <div class="kpi-val warn" style="font-size:17px">No Liq · DD ≤ {dd_cap:g}%</div>
        <div class="kpi-label">Primary: Cashflow DESC → DD ASC</div>
      </div>
    </section>

    <section class="card" style="padding:0;overflow:hidden;">
      <div class="toolbar">
        <strong>Historical Daily Mining Batches (เลือกดูผล Mine รายวันย้อนหลัง)</strong>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <select id="quick-jump-date" aria-label="Jump to Daily Dashboard" class="mono"></select>
          <input id="archive-search" type="search" placeholder="ค้นหาวันที่ หรือ model_id..." aria-label="Filter historical batches" />
        </div>
      </div>
      <div class="table-wrap">
        <table id="archive-days-table">
          <thead>
            <tr>
              <th>Batch Date</th>
              <th class="num">Models</th>
              <th class="num">Pass Gate</th>
              <th>Mined Models</th>
              <th class="num">Best Batch CF</th>
              <th class="num">Lowest Batch DD</th>
              <th class="num">Window</th>
              <th>Open</th>
            </tr>
          </thead>
          <tbody id="archive-days-body"></tbody>
        </table>
      </div>
    </section>

    <section class="card" style="padding:0;overflow:hidden;">
      <div class="toolbar">
        <strong>Cumulative Top-{top_n} Leaderboard Snapshot</strong>
        <span class="muted">คลิกปุ่ม Open Dashboard ด้านบนเพื่อเข้า Inspector &amp; Live DD Slider</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Model ID</th>
              <th>Signal</th>
              <th>Batch Date</th>
              <th class="num">Realized CF</th>
              <th class="num">AVG Weekly</th>
              <th class="num">Max DD</th>
              <th class="num">CF / DD</th>
              <th class="num">MTM Return</th>
            </tr>
          </thead>
          <tbody id="hub-top-body"></tbody>
        </table>
      </div>
    </section>
  </div>

  <script>
    const PORTAL = {safe_json};

    function escHtml(v) {{
      return String(v ?? "").replace(/[&<>"']/g, ch => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[ch]));
    }}

    function isSafeDate(d) {{
      return /^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(String(d || ""));
    }}

    function fmtUsd(v) {{
      const n = Number(v || 0);
      return (n >= 0 ? "+$" : "-$") + Math.abs(n).toLocaleString("en-US", {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
    }}

    function fmtPct(v) {{
      const n = Number(v || 0);
      return (n >= 0 ? "+" : "-") + Math.abs(n).toFixed(2) + "%";
    }}

    function shortLabel(modelId) {{
      return String(modelId || "").replace(/^beta_\\d+_/, "");
    }}

    function renderPortal() {{
      document.getElementById("hub-sub").textContent =
        `Generated ${{PORTAL.generated_at_utc}} · ${{PORTAL.total_days}} Archived Day(s) · ${{PORTAL.total_models}} Isolated Models · Offline Zero-CDN`;
      document.getElementById("hub-days").textContent = String(PORTAL.total_days);
      document.getElementById("hub-latest").textContent = PORTAL.latest_date ? `Latest: ${{PORTAL.latest_date}}` : "No batches yet";
      document.getElementById("hub-trials").textContent = String(PORTAL.total_trials);
      document.getElementById("hub-qual").textContent = `Qualified: ${{PORTAL.qualified_count}} / ${{PORTAL.total_models}}`;

      const top1 = (PORTAL.top_ranked || [])[0];
      if (top1) {{
        document.getElementById("hub-top1").textContent = top1.model_id;
        document.getElementById("hub-top1-sub").textContent = `CF ${{fmtUsd(top1.cashflow_net_usd)}} · DD ${{Number(top1.max_drawdown_pct).toFixed(2)}}%`;
      }}

      const sel = document.getElementById("quick-jump-date");
      sel.innerHTML = "";
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "เลือกวันเพื่อเปิด Dashboard...";
      sel.appendChild(placeholder);
      (PORTAL.days || []).forEach(d => {{
        if (!isSafeDate(d.batch_date) || d.has_dashboard === false) return;
        const opt = document.createElement("option");
        opt.value = `daily/${{d.batch_date}}/dashboard.html`;
        opt.textContent = d.model_count ? `${{d.batch_date}} (${{d.model_count}} models)` : d.batch_date;
        sel.appendChild(opt);
      }});

      renderArchiveTable("");

      const topBody = document.getElementById("hub-top-body");
      topBody.innerHTML = "";
      const dashDateSet = new Set((PORTAL.days || []).filter(d => isSafeDate(d.batch_date) && d.has_dashboard !== false).map(d => d.batch_date));
      (PORTAL.top_ranked || []).forEach(r => {{
        const tr = document.createElement("tr");
        tr.className = "data-row";
        const safeDate = isSafeDate(r.batch_date) ? r.batch_date : "";
        const dateCell = safeDate && dashDateSet.has(safeDate)
          ? `<a href="daily/${{safeDate}}/dashboard.html" style="color:var(--bm-code-fg);text-decoration:none;">${{safeDate}}</a>`
          : escHtml(r.batch_date || "-");
        tr.innerHTML = `
          <td class="mono" style="font-weight:700;">#${{Number(r.rank || 0)}}</td>
          <td class="mono" style="font-weight:700;">${{escHtml(r.model_id)}}</td>
          <td class="mono muted">${{escHtml(r.signal_name)}}</td>
          <td class="mono">${{dateCell}}</td>
          <td class="num pos" style="font-weight:700;">${{fmtUsd(r.cashflow_net_usd)}}</td>
          <td class="num pos">${{fmtUsd(r.avg_weekly_cf_usd || 0)}}</td>
          <td class="num warn" style="font-weight:700;">${{Number(r.max_drawdown_pct).toFixed(2)}}%</td>
          <td class="num">${{Number(r.cashflow_to_dd_ratio).toFixed(2)}}x</td>
          <td class="num ${{r.mtm_return_pct >= 0 ? 'pos' : 'neg'}}">${{fmtPct(r.mtm_return_pct)}}</td>
        `;
        topBody.appendChild(tr);
      }});
    }}

    function renderArchiveTable(query) {{
      const q = String(query || "").trim().toLowerCase();
      const body = document.getElementById("archive-days-body");
      body.innerHTML = "";
      const rows = (PORTAL.days || []).filter(d => {{
        if (!isSafeDate(d.batch_date)) return false;
        if (!q) return true;
        if (String(d.batch_date || "").toLowerCase().includes(q)) return true;
        return (d.model_ids || []).some(id => String(id).toLowerCase().includes(q));
      }});
      if (!rows.length) {{
        body.innerHTML = `<tr><td colspan="8" class="muted" style="text-align:center;padding:18px;">ไม่พบรายการวันที่ตรงกับคำค้นหา</td></tr>`;
        return;
      }}
      rows.forEach(d => {{
        const tr = document.createElement("tr");
        tr.className = "data-row";
        const chips = (d.model_ids || []).length
          ? (d.model_ids || []).map(id => `<span class="chip">${{escHtml(shortLabel(id))}}</span>`).join("")
          : '<span class="muted">-</span>';
        const dashHref = `daily/${{d.batch_date}}/dashboard.html`;
        const sumHref = `daily/${{d.batch_date}}/daily_summary.md`;
        const spanTxt = d.days_covered ? `${{Math.round(Number(d.days_covered))}}d` : "-";
        const bestCfCell = d.best_cashflow_model_id
          ? `<strong>${{fmtUsd(d.best_cashflow_usd)}}</strong> <span class="muted">(${{escHtml(shortLabel(d.best_cashflow_model_id))}})</span>`
          : '<span class="muted">-</span>';
        const lowDdCell = d.lowest_dd_model_id
          ? `<strong>${{Number(d.lowest_dd_pct || 0).toFixed(2)}}%</strong> <span class="muted">(${{escHtml(shortLabel(d.lowest_dd_model_id))}})</span>`
          : '<span class="muted">-</span>';
        const actionBtns = [
          d.has_dashboard !== false ? `<a class="link-btn primary" href="${{dashHref}}">9-Panel Dashboard</a>` : "",
          d.has_summary !== false ? `<a class="link-btn" href="${{sumHref}}">Summary MD</a>` : ""
        ].filter(Boolean).join("") || '<span class="muted">-</span>';
        tr.innerHTML = `
          <td class="mono" style="font-weight:700;">${{escHtml(d.batch_date)}}</td>
          <td class="num">${{Number(d.model_count || 0)}}</td>
          <td class="num pos">${{Number(d.qualified_count || 0)}} / ${{Number(d.model_count || 0)}}</td>
          <td style="white-space:normal;min-width:260px;">${{chips}}</td>
          <td class="num pos">${{bestCfCell}}</td>
          <td class="num warn">${{lowDdCell}}</td>
          <td class="num muted">${{spanTxt}}</td>
          <td>${{actionBtns}}</td>
        `;
        body.appendChild(tr);
      }});
    }}

    document.getElementById("quick-jump-date").addEventListener("change", ev => {{
      if (/^daily\\/\\d{{4}}-\\d{{2}}-\\d{{2}}\\/dashboard\\.html$/.test(ev.target.value)) {{
        window.location.href = ev.target.value;
      }}
    }});
    document.getElementById("archive-search").addEventListener("input", ev => {{
      renderArchiveTable(ev.target.value);
    }});
    document.getElementById("theme-toggle").addEventListener("click", () => {{
      document.body.classList.toggle("light");
    }});
    if (document.documentElement.classList.contains("light")) {{
      document.body.classList.add("light");
    }}
    renderPortal();
  </script>
</body>
</html>
"""
