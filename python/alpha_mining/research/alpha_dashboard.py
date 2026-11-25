"""Alpha Mining Markdown summary, self-contained 9-panel HTML dashboard and archive hub.

100% offline (zero CDN, zero external requests). Panels (Daily Batch tab, all models of the day
across XAUUSD + ETHUSDT and every timeframe, Round 1 + Round 2 accumulated):
    01 Equity Return %            02 Drawdown %               03 Net Return vs Buy & Hold %
    04 In-Sample vs OOS Sharpe    05 Risk / Return scatter    06 Exposure % & Win Rate %
    07 Trades & Profit Factor     08 Beta & Corr vs Underlying 09 Daily-Return Correlation Matrix
plus symbol/round filters, clickable legend pills, a sortable performance table, the cumulative
Top-9 board (overall + per symbol, with Deflated-Sharpe haircut) and the full model catalog.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any, Sequence

from .portal_hub import humanize_alpha_model
from .stability import stability_from_alpha_series

_SAFE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DEFAULT_CENTRAL_HUB_HREF = "../../../index.html"
DEFAULT_BETA_HUB_HREF = "../../../beta/index.html"  # GitHub Pages: /alpha/daily/<date>/ -> /beta/index.html


def _safe_inline_json(payload: Any) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _model_short(m: dict[str, Any]) -> str:
    return f"{m.get('symbol', '?')} {m.get('timeframe', '?')} {m.get('family', '?')}"


def render_daily_summary_markdown(
    *,
    batch_date: str,
    batch_metrics: Sequence[dict[str, Any]],
    ranking_board: dict[str, Any],
) -> str:
    rule = ranking_board.get("ranking_rule", {})
    gates = rule.get("hard_gates", {})
    mt = rule.get("multiple_testing", {})
    top_n = rule.get("top_n", 9)
    by_sym: dict[str, int] = {}
    for m in batch_metrics:
        by_sym[str(m.get("symbol"))] = by_sym.get(str(m.get("symbol")), 0) + 1
    rounds = sorted({int(m["round_no"]) for m in batch_metrics if m.get("round_no") is not None})
    lines = [
        f"# Alpha_mining — Alpha Mining Daily Summary ({batch_date})",
        "",
        f"- **Generated (UTC):** `{ranking_board.get('generated_at_utc', '')}`",
        f"- **Models Tested Today:** `{len(batch_metrics)}` ("
        + ", ".join(f"`{k}`: {v}" for k, v in sorted(by_sym.items()))
        + f") | **Rounds:** `{rounds or [1]}` | **Cumulative Trials (`N_trials`):** `{ranking_board.get('total_trials', 0)}`",
        f"- **Top-{top_n} Rule:** `OOS Sharpe DESC -> Max DD ASC` | **Hard Gates:** `no liquidation`, "
        f"`trades >= {gates.get('min_trades', 30)}`, `OOS profit > 0`, `Max DD <= {gates.get('max_drawdown_pct_limit', 50):g}%`",
        f"- **Multiple-testing:** expected max daily Sharpe under H0 for `N={mt.get('n_trials', '?')}` trials = `{mt.get('expected_max_daily_sharpe_h0', '?')}`; `DSR≈` is the probability a model beats that haircut.",
        "- **XAUUSD data:** public feed is `PAXGUSDT` (gold-backed, 24/7) as a PROXY for broker XAUUSD; costs 2 bps/side. ETHUSDT = Binance USD-M perp, 5 bps/side.",
        "",
        f"## 1. โมเดลที่ Mine วันนี้ ({batch_date} — {len(batch_metrics)} โมเดล)",
        "",
        "| Model ID | Sym | TF | Dir | Return | CAGR | Max DD | Sharpe | IS Sh | OOS Sh | OOS Ret | Trades | Win% | PF | B&H |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in batch_metrics:
        lines.append(
            f"| `{m['model_id']}` | {m.get('symbol')} | {m.get('timeframe')} | {m.get('direction')} "
            f"| {float(m.get('total_return_pct', 0)):+.1f}% | {float(m.get('cagr_pct', 0)):+.1f}% "
            f"| {float(m.get('max_drawdown_pct', 0)):.1f}% | {float(m.get('sharpe_daily_ann', 0)):.2f} "
            f"| {float(m.get('is_sharpe_ann', 0)):.2f} | {float(m.get('oos_sharpe_ann', 0)):.2f} "
            f"| {float(m.get('oos_return_pct', 0)):+.1f}% | {int(m.get('trades', 0)):,} "
            f"| {float(m.get('win_rate_pct', 0)):.1f}% | {float(m.get('profit_factor', 0)):.2f} "
            f"| {float(m.get('buy_hold_return_pct', 0)):+.1f}% |"
        )
    lines.extend(
        [
            "",
            f"## 2. Cumulative Top-{top_n} Ranking Board (OOS Sharpe สูงสุด → DD ต่ำสุด)",
            "",
            "| Rank | Model ID | Sym | TF | OOS Sharpe | OOS Ret | Max DD | Trades | DSR≈ | Batch |",
            "|---:|---|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    top_rows = ranking_board.get("top_ranked", [])
    if not top_rows:
        lines.append("| - | ยังไม่มีโมเดลที่ผ่าน Hard Gate | - | - | - | - | - | - | - | - |")
    for r in top_rows:
        lines.append(
            f"| **#{r['rank']}** | `{r['model_id']}` | {r.get('symbol')} | {r.get('timeframe')} "
            f"| {float(r.get('oos_sharpe_ann', 0)):.2f} | {float(r.get('oos_return_pct', 0)):+.1f}% "
            f"| {float(r.get('max_drawdown_pct', 0)):.1f}% | {int(r.get('trades', 0)):,} "
            f"| {float(r.get('dsr_approx', 0)):.2f} | `{r.get('batch_date', '')}` |"
        )
    disq_today = [d for d in ranking_board.get("disqualified", []) if d.get("model_id") in {m["model_id"] for m in batch_metrics}]
    if disq_today:
        lines.extend(["", "### โมเดลวันนี้ที่ไม่ผ่าน Hard Gate", ""])
        for d in disq_today:
            lines.append(f"- `{d['model_id']}`: เหตุผล `{', '.join(d.get('disqualify_reasons', []))}`")
    lines.append("")
    return "\n".join(lines)


_DASHBOARD_TEMPLATE = r"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>__TITLE__</title>
<style>
:root{--bg:#0b1017;--card:#121923;--surf:#192331;--bd:#263244;--fg:#e6edf6;--mut:#8ea0b8;--pri:#3b82f6;--ok:#22c55e;--warn:#f59e0b;--err:#ef4444;--grid:rgba(148,163,184,.14);--axis:#94a3b8}
*{box-sizing:border-box}body{margin:0;padding:18px 20px 36px;background:var(--bg);color:var(--fg);font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1460px;margin:0 auto;display:flex;flex-direction:column;gap:14px}
.header{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px;padding-bottom:12px;border-bottom:1px solid var(--bd)}
h1{margin:0;font-size:19px}.sub{color:var(--mut);font-size:12px;margin-top:3px}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
button,a.nav{cursor:pointer;border:1px solid var(--bd);border-radius:8px;padding:7px 12px;font-size:12px;font-weight:600;background:var(--card);color:var(--fg);text-decoration:none}
button:hover,a.nav:hover{border-color:var(--pri)}button.active{background:var(--pri);border-color:var(--pri);color:#fff}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:12px 14px;min-width:0;overflow:hidden}
.kl{color:var(--mut);font-size:12px}.kv{font-size:20px;font-weight:700;font-family:ui-monospace,Menlo,monospace;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:10px 14px}
.gate-bar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:12px 14px;margin-bottom:14px}
.gate-grp{display:flex;flex-wrap:wrap;gap:12px;align-items:center}
.gate-lbl{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--fg)}
.gate-lbl input[type="number"]{width:66px;padding:4px 6px;border-radius:6px;border:1px solid var(--bd);background:var(--surf);color:var(--fg);font:600 12px ui-monospace,Menlo,monospace}
.gate-lbl input[type="range"]{width:120px;accent-color:var(--pri)}
.gate-lbl select{padding:5px 8px;border-radius:6px;border:1px solid var(--bd);background:var(--surf);color:var(--fg);font:600 12px -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
select.dnav{cursor:pointer;border:1px solid var(--bd);border-radius:8px;padding:6px 10px;font:600 12px ui-monospace,Menlo,monospace;background:var(--surf);color:var(--fg)}
select.dnav:hover{border-color:var(--pri)}
.pill{display:inline-flex;align-items:center;gap:7px;padding:5px 10px;border-radius:999px;border:1px solid var(--bd);background:var(--surf);font:600 12px ui-monospace,Menlo,monospace;cursor:pointer;user-select:none}
.pill.off{opacity:.35}.dot{width:9px;height:9px;border-radius:50%}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.wide{grid-column:1/-1}
@media(max-width:980px){.grid{grid-template-columns:1fr}}
.panel{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:12px 14px 10px;min-width:0}
.ph{display:flex;justify-content:space-between;gap:6px;border-bottom:1px solid var(--bd);padding-bottom:7px;margin-bottom:6px}
.pt{font-weight:700;font-size:13px}.ps{color:var(--mut);font:11px ui-monospace,Menlo,monospace}
.cv{position:relative;width:100%;height:300px}.cv canvas{width:100%;height:100%;display:block}
table{border-collapse:collapse;width:100%;font-size:12px}th,td{padding:6px 8px;border-bottom:1px solid var(--bd);text-align:right;white-space:nowrap}
th{cursor:pointer;color:var(--mut);position:sticky;top:0;background:var(--card)}th:first-child,td:first-child,td.l,th.l{text-align:left}
.tw{overflow-x:auto;max-height:560px}.pos{color:var(--ok)}.neg{color:var(--err)}.mut{color:var(--mut)}
.badge{display:inline-block;padding:1px 7px;border-radius:6px;font-size:11px;font-weight:700;background:var(--surf);border:1px solid var(--bd)}
.badge.xau{color:#fbbf24;border-color:#fbbf24}.badge.eth{color:#93c5fd;border-color:#93c5fd}
#tip{position:fixed;pointer-events:none;background:rgba(11,16,23,.96);border:1px solid var(--bd);border-radius:8px;padding:6px 9px;font:11px ui-monospace,Menlo,monospace;z-index:9;display:none;max-width:420px;white-space:pre-line}
.hidden{display:none!important}.note{color:var(--mut);font-size:12px}
.portal-bar{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;background:#0f1722;border:1px solid var(--bd);border-radius:12px;padding:10px 14px}
.portal-pills{display:flex;flex-wrap:wrap;gap:7px;align-items:center}
.pp{display:inline-flex;align-items:center;padding:6px 12px;border-radius:999px;font-size:12px;font-weight:700;text-decoration:none;border:1px solid var(--bd);background:var(--surf);color:var(--fg);cursor:pointer}
.pp:hover{border-color:var(--fg)}.pp.xau-on{background:#f59e0b;color:#0b1017;border-color:#f59e0b}.pp.eth-on{background:#06b6d4;color:#061318;border-color:#06b6d4}.pp.all-on{background:var(--fg);color:var(--bg);border-color:var(--fg)}.pp.b-go{color:#60a5fa;border-color:rgba(59,130,246,.45);background:rgba(59,130,246,.12)}
</style>
</head>
<body>
<div class="wrap">
  <nav class="portal-bar" aria-label="Unified Research Portal Navigation">
    <div class="portal-pills" id="top-cats">
      <a class="pp" href="../../../index.html">หน้าหลัก</a>
      <a class="pp" href="../../../library.html">ห้องสมุดโมเดล</a>
      <a class="pp" data-sym="XAUUSD" href="#sym=XAUUSD">ALPHA · ทองคำ (XAUUSD)</a>
      <a class="pp" data-sym="ETHUSDT" href="#sym=ETHUSDT">ALPHA · ETH</a>
      <a class="pp" data-sym="ALL" href="#sym=ALL">ALPHA · ทั้งหมด</a>
      <a class="pp b-go" href="../../../beta/index.html">BETA · ETH Grid</a>
    </div>
    <div class="row" id="nav"></div>
  </nav>
  <div class="header">
    <div><h1 id="title"></h1><div class="sub" id="sub"></div></div>
    <div class="row" id="tabs">
      <button data-tab="daily" class="active">กราฟเปรียบเทียบวันนี้</button>
      <button data-tab="ranking">อันดับ Top 9</button>
      <button data-tab="all">ตารางโมเดลทั้งหมด</button>
    </div>
  </div>
  <div class="kpis" id="kpis"></div>
  <div id="tab-daily">
    <div class="bar" id="legend" style="margin-bottom:14px"></div>
    <div class="grid" id="panels"></div>
    <div class="card" style="margin-top:14px"><div class="pt" style="margin-bottom:8px">ตารางสรุปผลทุกโมเดลในหมวดนี้</div><div class="tw" id="tbl-daily"></div></div>
  </div>
  <div id="tab-ranking" class="hidden">
    <div class="gate-bar" id="alpha-gate-bar">
      <div class="gate-grp">
        <label class="gate-lbl"><span class="mut">จัดเรียง:</span>
          <select id="g-mode">
            <option value="oos_sharpe" selected>OOS Sharpe → Max DD (ค่าเริ่มต้น)</option>
            <option value="stable_sharpe">ความนิ่ง (OOS Sharpe × R²)</option>
            <option value="oos_return">กำไร OOS % สูงสุด</option>
            <option value="total_return">กำไรรวม % สูงสุด</option>
            <option value="calmar">CAGR / Max DD สูงสุด</option>
          </select>
        </label>
        <label class="gate-lbl"><span class="mut">Max DD ≤</span>
          <input id="g-dd" type="range" min="10" max="100" step="1" value="50" />
          <b id="g-dd-val" style="font-family:ui-monospace,Menlo,monospace;min-width:40px">50%</b>
        </label>
        <label class="gate-lbl"><span class="mut">ความแกว่ง Vol ≤</span>
          <input id="g-vol" type="range" min="5" max="100" step="1" value="60" />
          <b id="g-vol-val" style="font-family:ui-monospace,Menlo,monospace;min-width:40px">60%</b>
        </label>
        <label class="gate-lbl"><span class="mut">ความนิ่ง R² ≥</span>
          <input id="g-r2" type="range" min="0" max="0.95" step="0.05" value="0.25" />
          <b id="g-r2-val" style="font-family:ui-monospace,Menlo,monospace;min-width:38px">0.25</b>
        </label>
        <label class="gate-lbl"><span class="mut">เทรด ≥</span>
          <input id="g-trades" type="number" min="0" max="500" step="5" value="30" />
        </label>
        <label class="gate-lbl"><span class="mut">OOS Sharpe ≥</span>
          <input id="g-sharpe" type="number" min="-5" max="10" step="0.1" value="0" />
        </label>
        <label class="gate-lbl">
          <input id="g-oos-pos" type="checkbox" checked />
          <span>บังคับกำไร OOS &gt; 0%</span>
        </label>
        <label class="gate-lbl"><span class="mut">Top</span>
          <input id="g-topn" type="number" min="3" max="20" step="1" value="9" style="width:52px" />
        </label>
      </div>
      <div class="gate-grp">
        <span class="note" id="g-summary"></span>
        <button id="g-reset" type="button">รีเซ็ต Gate</button>
      </div>
    </div>
    <div class="card" style="margin-bottom:14px">
      <div class="ph" style="margin-bottom:10px">
        <span class="pt" id="rank-panels-title">กราฟ 9-Panel — อันดับ Top 9 สะสม</span>
        <span class="ps" id="rank-panels-sub">เปรียบเทียบโมเดลอันดับสูงสุดทุกวันพร้อมกัน (คลิกชื่อเพื่อเปิด/ปิดเส้น)</span>
      </div>
      <div class="bar" id="rank-legend" style="margin-bottom:12px"></div>
      <div class="grid" id="rank-panels"></div>
    </div>
    <div id="rank-tables"></div>
  </div>
  <div id="tab-all" class="hidden"><div class="card"><div class="tw" id="tbl-all"></div></div></div>
  <div class="note" id="foot"></div>
</div>
<div id="tip"></div>
<script>
const P = __PAYLOAD__;
const COLORS=["#3b82f6","#f59e0b","#22c55e","#ef4444","#a855f7","#14b8a6","#f472b6","#eab308","#60a5fa","#fb923c","#4ade80","#f87171","#c084fc","#2dd4bf","#f9a8d4","#facc15","#93c5fd","#fdba74","#86efac","#fca5a5"];
const DEFAULT_GATES={
  dd:Number((P.ranking&&P.ranking.ranking_rule&&P.ranking.ranking_rule.hard_gates&&P.ranking.ranking_rule.hard_gates.max_drawdown_pct_limit)||50),
  maxVol:60,
  minR2:0.25,
  trades:Number((P.ranking&&P.ranking.ranking_rule&&P.ranking.ranking_rule.hard_gates&&P.ranking.ranking_rule.hard_gates.min_trades)||30),
  minSharpe:0,
  requireOosPos:true,
  mode:"oos_sharpe",
  topN:Number(P.top_n||9)
};
const S={tab:P.default_tab||"daily",sym:"ALL",round:"ALL",off:new Set(),rankOff:new Set(),gates:Object.assign({},DEFAULT_GATES),sort:{daily:["oos_sharpe_ann",-1],all:["oos_sharpe_ann",-1]}};
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?"":s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num=(v,d=2)=>(v===null||v===undefined||Number.isNaN(Number(v)))?"–":Number(v).toFixed(d);
const sgn=(v,d=1,suf="%")=>{const n=Number(v);if(Number.isNaN(n))return "–";return `<span class="${n>=0?"pos":"neg"}">${n>=0?"+":""}${n.toFixed(d)}${suf}</span>`};
const pd=s=>{const[a,b,c]=s.split("-").map(Number);return Math.floor(Date.UTC(a,b-1,c)/864e5)};
const ds=n=>new Date(n*864e5).toISOString().slice(0,10);
const symBadge=s=>`<span class="badge ${s==="XAUUSD"?"xau":"eth"}">${esc(s)}</span>`;
const MODEL_BY_ID={};(P.models||[]).forEach(m=>{MODEL_BY_ID[m.model_id]=m});(P.batch_models||[]).forEach(m=>{if(!MODEL_BY_ID[m.model_id])MODEL_BY_ID[m.model_id]=m});
const colorOf={};P.batch_models.forEach((m,i)=>{colorOf[m.model_id]=COLORS[i%COLORS.length]});
const idxOf={};P.batch_models.forEach((m,i)=>{idxOf[m.model_id]=String(i+1).padStart(2,"0")});
const visible=m=>(S.sym==="ALL"||m.symbol===S.sym)&&(S.round==="ALL"||String(m.round_no||1)===S.round);
const shown=()=>P.batch_models.filter(m=>visible(m)&&!S.off.has(m.model_id));
function evalAlphaRanking(){
  const g=S.gates;
  const pool=(P.models&&P.models.length)?P.models:(P.batch_models||[]);
  const qual=[],disq=[];
  pool.forEach(m=>{
    const reasons=[];
    const dd=Number(m.max_drawdown_pct||0),tr=Number(m.trades||0),osh=Number(m.oos_sharpe_ann||0),oret=Number(m.oos_return_pct||0);
    const vol=Number(m.ann_vol_pct||0),r2=Number(m.equity_r2||0);
    if(tr<g.trades)reasons.push(`TRADES<${g.trades}`);
    if(g.requireOosPos&&oret<=0)reasons.push("OOS_RET<=0%");
    if(g.minSharpe===0?(osh<=0):(osh<g.minSharpe))reasons.push(`OOS_SHARPE<${g.minSharpe}`);
    if(dd>g.dd)reasons.push(`MAX_DD>${g.dd}%`);
    if(g.maxVol<100&&vol>g.maxVol)reasons.push(`VOL>${g.maxVol}%`);
    if(g.minR2>0&&r2<g.minR2)reasons.push(`R2<${g.minR2.toFixed(2)}`);
    if(reasons.length)disq.push(Object.assign({},m,{disqualify_reasons:reasons}));
    else qual.push(Object.assign({},m));
  });
  const score=(m)=>{
    if(g.mode==="stable_sharpe")return Number(m.oos_sharpe_ann||0)*Math.max(0.05,Number(m.equity_r2||0));
    if(g.mode==="oos_return")return Number(m.oos_return_pct||0);
    if(g.mode==="total_return")return Number(m.total_return_pct||0);
    if(g.mode==="calmar"){const dd=Math.max(0.5,Number(m.max_drawdown_pct||0));return Number(m.cagr_pct||0)/dd}
    return Number(m.oos_sharpe_ann||0);
  };
  const cmp=(a,b)=>{
    const d=score(b)-score(a);
    if(Math.abs(d)>1e-9)return d;
    return Number(a.max_drawdown_pct||0)-Number(b.max_drawdown_pct||0);
  };
  qual.sort(cmp);
  disq.sort(cmp);
  const topN=Math.max(1,Number(g.topN||9));
  const topAll=qual.slice(0,topN).map((m,i)=>Object.assign({},m,{rank:i+1}));
  const bySym={};
  const syms=[...new Set(pool.map(m=>m.symbol).filter(Boolean))].sort();
  syms.forEach(sym=>{
    bySym[sym]=qual.filter(m=>m.symbol===sym).slice(0,topN).map((m,i)=>Object.assign({},m,{rank:i+1}));
  });
  return {qualified_count:qual.length,qualified_by_symbol:Object.fromEntries(syms.map(s=>[s,qual.filter(m=>m.symbol===s).length])),top_ranked:topAll,top_ranked_by_symbol:bySym,disqualified:disq};
}
function topRankModels(){
  const rr=evalAlphaRanking();
  const rows=S.sym==="ALL"?(rr.top_ranked||[]):((rr.top_ranked_by_symbol||{})[S.sym]||[]);
  return rows.map((r,i)=>{
    const full=MODEL_BY_ID[r.model_id]||{};
    return Object.assign({},full,r,{_rkTag:"#"+(r.rank||(i+1)),_rkColor:COLORS[i%COLORS.length]});
  });
}
const tip=$("tip");
function showTip(e,t){tip.style.display="block";tip.textContent=t;const x=Math.min(e.clientX+14,innerWidth-tip.offsetWidth-8);tip.style.left=x+"px";tip.style.top=(e.clientY+14)+"px"}
function hideTip(){tip.style.display="none"}
const curveCache={};
function curves(mid){
  if(curveCache[mid])return curveCache[mid];const s=P.series[mid];if(!s)return null;
  const x0=pd(s.start_date);let e=1,pk=1;const xs=[],eq=[],dd=[];
  s.strategy_bp.forEach((b,i)=>{e*=1+b/1e4;pk=Math.max(pk,e);xs.push(x0+i);eq.push((e-1)*100);dd.push(-(1-e/pk)*100)});
  const step=Math.max(1,Math.ceil(xs.length/700));const pick=a=>a.filter((_,i)=>i%step===0||i===a.length-1);
  return curveCache[mid]={xs:pick(xs),eq:pick(eq),dd:pick(dd)};
}
function setup(cv){const r=cv.getBoundingClientRect(),d=devicePixelRatio||1;cv.width=Math.max(10,r.width*d);cv.height=Math.max(10,r.height*d);const c=cv.getContext("2d");c.setTransform(d,0,0,d,0,0);return{c,w:r.width,h:r.height}}
const ML=58,MR=10,MT=8,MB=26;
function axes(c,w,h,x0,x1,y0,y1,xf,yf){
  c.font="10px ui-monospace,Menlo,monospace";c.fillStyle="#94a3b8";c.strokeStyle="rgba(148,163,184,.14)";c.lineWidth=1;
  for(let i=0;i<=5;i++){const v=y0+(y1-y0)*i/5,y=h-MB-(h-MB-MT)*i/5;c.beginPath();c.moveTo(ML,y);c.lineTo(w-MR,y);c.stroke();c.textAlign="right";c.fillText(yf(v),ML-5,y+3)}
  if(xf)for(let i=0;i<=5;i++){const v=x0+(x1-x0)*i/5,x=ML+(w-ML-MR)*i/5;c.textAlign="center";c.fillText(xf(v),x,h-8)}
}
function lineChart(cv,list,yf){
  const{c,w,h}=setup(cv);c.clearRect(0,0,w,h);
  if(!list.length){c.fillStyle="#8ea0b8";c.fillText("no data",ML,h/2);cv.onmousemove=null;return}
  let x0=1e18,x1=-1e18,y0=1e18,y1=-1e18;list.forEach(s=>{x0=Math.min(x0,s.xs[0]);x1=Math.max(x1,s.xs[s.xs.length-1]);s.ys.forEach(v=>{y0=Math.min(y0,v);y1=Math.max(y1,v)})});
  if(y0===y1){y0-=1;y1+=1}const pad=(y1-y0)*.05;y0-=pad;y1+=pad;if(x0===x1)x1=x0+1;
  axes(c,w,h,x0,x1,y0,y1,v=>ds(Math.round(v)).slice(0,7),yf);
  const X=v=>ML+(v-x0)/(x1-x0)*(w-ML-MR),Y=v=>h-MB-(v-y0)/(y1-y0)*(h-MB-MT);
  if(y0<0&&y1>0){c.strokeStyle="rgba(148,163,184,.45)";c.setLineDash([4,4]);c.beginPath();c.moveTo(ML,Y(0));c.lineTo(w-MR,Y(0));c.stroke();c.setLineDash([])}
  list.forEach(s=>{c.strokeStyle=s.color;c.lineWidth=1.6;c.beginPath();s.xs.forEach((x,i)=>{const px=X(x),py=Y(s.ys[i]);i?c.lineTo(px,py):c.moveTo(px,py)});c.stroke()});
  cv.onmousemove=e=>{const r=cv.getBoundingClientRect(),dx=x0+(e.clientX-r.left-ML)/(w-ML-MR)*(x1-x0);
    const rows=list.map(s=>{let lo=0,hi=s.xs.length-1;while(lo<hi){const m=(lo+hi)>>1;s.xs[m]<dx?lo=m+1:hi=m}return[s.name,s.ys[lo],s.xs[lo]]}).filter(r=>Math.abs(r[2]-dx)<40).sort((a,b)=>b[1]-a[1]);
    if(!rows.length){hideTip();return}showTip(e,ds(Math.round(dx))+"\n"+rows.map(r=>r[0]+": "+yf(r[1])).join("\n"))};
  cv.onmouseleave=hideTip;
}
function barChart(cv,labels,groups,yf,names){
  const{c,w,h}=setup(cv);c.clearRect(0,0,w,h);const hits=[];
  if(!labels.length){c.fillStyle="#8ea0b8";c.fillText("no data",ML,h/2);cv.onmousemove=null;return}
  let y0=0,y1=0;groups.forEach(g=>g.vals.forEach(v=>{if(v!=null){y0=Math.min(y0,v);y1=Math.max(y1,v)}}));if(y0===y1)y1=y0+1;const pad=(y1-y0)*.08;if(y0<0)y0-=pad;y1+=pad;
  axes(c,w,h,0,1,y0,y1,null,yf);const Y=v=>h-MB-(v-y0)/(y1-y0)*(h-MB-MT),slot=(w-ML-MR)/labels.length,bw=Math.max(2,slot*.8/groups.length);
  c.strokeStyle="rgba(148,163,184,.5)";c.beginPath();c.moveTo(ML,Y(0));c.lineTo(w-MR,Y(0));c.stroke();
  labels.forEach((lb,i)=>{const bx=ML+slot*i+slot*.1;groups.forEach((g,k)=>{const v=g.vals[i];if(v==null)return;const x=bx+k*bw,ya=Y(Math.max(v,0)),yb=Y(Math.min(v,0));c.fillStyle=g.color;c.fillRect(x,ya,bw-1,Math.max(1,yb-ya));hits.push([x,ya,bw,Math.max(1,yb-ya),`${names[i]}\n${g.name}: ${yf(v)}`])});
    c.fillStyle="#94a3b8";c.textAlign="center";c.font="10px ui-monospace,Menlo,monospace";if(slot>16||i%2===0)c.fillText(lb,ML+slot*i+slot/2,h-8)});
  groups.forEach((g,k)=>{c.fillStyle=g.color;c.fillRect(ML+k*110,2,8,8);c.fillStyle="#94a3b8";c.textAlign="left";c.fillText(g.name,ML+k*110+11,10)});
  cv.onmousemove=e=>{const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;const hit=hits.find(q=>mx>=q[0]&&mx<=q[0]+q[2]&&my>=q[1]-4&&my<=q[1]+q[3]+4);hit?showTip(e,hit[4]):hideTip()};cv.onmouseleave=hideTip;
}
function ddBarChart(cv,labels,ms,colorFn,names,gatePct){
  const{c,w,h}=setup(cv);c.clearRect(0,0,w,h);const hits=[];
  if(!labels.length){c.fillStyle="#8ea0b8";c.fillText("no data",ML,h/2);cv.onmousemove=null;return}
  const vals=ms.map(m=>Math.max(0,Number(m.max_drawdown_pct||0)));
  const maxV=Math.max(gatePct*1.05,...vals,10);
  const y0=0,y1=maxV*1.12;
  axes(c,w,h,0,1,y0,y1,null,v=>v.toFixed(0)+"%");
  const Y=v=>h-MB-(v-y0)/(y1-y0)*(h-MB-MT),slot=(w-ML-MR)/labels.length,bw=Math.max(6,Math.min(48,slot*0.68));
  const yBase=Y(0);
  c.strokeStyle="rgba(148,163,184,.5)";c.beginPath();c.moveTo(ML,yBase);c.lineTo(w-MR,yBase);c.stroke();
  if(gatePct>0&&gatePct<=y1){
    const yg=Y(gatePct);
    c.save();c.strokeStyle="rgba(239,68,68,.75)";c.setLineDash([5,4]);c.lineWidth=1.4;c.beginPath();c.moveTo(ML,yg);c.lineTo(w-MR,yg);c.stroke();
    c.setLineDash([]);c.fillStyle="#f87171";c.font="10px ui-monospace,Menlo,monospace";c.textAlign="right";c.fillText("Gate ≤ "+gatePct+"%",w-MR-2,yg-4);c.restore();
  }
  labels.forEach((lb,i)=>{
    const v=vals[i],m=ms[i],x=ML+slot*i+(slot-bw)/2,yt=Y(v),bh=Math.max(1,yBase-yt);
    const over=gatePct>0&&v>gatePct;
    c.fillStyle=over?"#ef4444":colorFn(m);c.fillRect(x,yt,bw,bh);
    if(slot>=24){c.fillStyle=over?"#fca5a5":"#cbd5e1";c.font="10px ui-monospace,Menlo,monospace";c.textAlign="center";c.fillText(v.toFixed(1)+"%",x+bw/2,Math.max(MT+9,yt-4))}
    c.fillStyle="#94a3b8";c.textAlign="center";c.font="10px ui-monospace,Menlo,monospace";if(slot>16||i%2===0)c.fillText(lb,ML+slot*i+slot/2,h-8);
    const oosDd=m.oos_max_drawdown_pct!=null?`\nOOS Max DD: ${Number(m.oos_max_drawdown_pct).toFixed(1)}%`:"";
    hits.push([x-2,yt-4,bw+4,bh+8,`${names[i]}\nMax DD: ${v.toFixed(1)}%${oosDd}\nGate (≤ ${gatePct}%): ${over?"เกินเกณฑ์":"ผ่าน"}`]);
  });
  cv.onmousemove=e=>{const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;const hit=hits.find(q=>mx>=q[0]&&mx<=q[0]+q[2]&&my>=q[1]&&my<=q[1]+q[3]);hit?showTip(e,hit[4]):hideTip()};cv.onmouseleave=hideTip;
}
function scatter(cv,pts){
  const{c,w,h}=setup(cv);c.clearRect(0,0,w,h);
  if(!pts.length){c.fillStyle="#8ea0b8";c.fillText("no data",ML,h/2);cv.onmousemove=null;return}
  let x0=0,x1=Math.max(...pts.map(p=>p.x))*1.1||1,y0=Math.min(0,...pts.map(p=>p.y)),y1=Math.max(...pts.map(p=>p.y))*1.1||1;if(y0===y1)y1=y0+1;
  axes(c,w,h,x0,x1,y0,y1,v=>v.toFixed(0)+"%",v=>v.toFixed(0)+"%");const X=v=>ML+(v-x0)/(x1-x0)*(w-ML-MR),Y=v=>h-MB-(v-y0)/(y1-y0)*(h-MB-MT);
  c.font="10px ui-monospace,Menlo,monospace";pts.forEach(p=>{c.fillStyle=p.color;c.beginPath();c.arc(X(p.x),Y(p.y),5,0,6.3);c.fill();c.fillStyle="#cbd5e1";c.textAlign="left";c.fillText(p.tag,X(p.x)+7,Y(p.y)+3)});
  cv.onmousemove=e=>{const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;const hit=pts.find(p=>Math.hypot(X(p.x)-mx,Y(p.y)-my)<9);hit?showTip(e,hit.text):hideTip()};cv.onmouseleave=hideTip;
}
function heat(cv,labels,mat,names){
  const{c,w,h}=setup(cv);c.clearRect(0,0,w,h);const n=labels.length;
  if(n<2){c.fillStyle="#8ea0b8";c.fillText("need >= 2 models",ML,h/2);cv.onmousemove=null;return}
  const L=34,T=18,cw=(w-L-6)/n,ch=(h-T-6)/n;
  mat.forEach((row,i)=>row.forEach((v,j)=>{const t=Math.max(-1,Math.min(1,v));const r=t>0?255:Math.round(255*(1+t)),b=t<0?255:Math.round(255*(1-t)),g=Math.round(255*(1-Math.abs(t)*.85));c.fillStyle=`rgb(${r},${g},${b})`;c.fillRect(L+j*cw,T+i*ch,cw-1,ch-1);if(n<=12){c.fillStyle="#0b1017";c.font="10px ui-monospace,Menlo,monospace";c.textAlign="center";c.fillText(v.toFixed(2),L+j*cw+cw/2,T+i*ch+ch/2+3)}}));
  c.fillStyle="#94a3b8";c.font="10px ui-monospace,Menlo,monospace";labels.forEach((lb,i)=>{c.textAlign="center";c.fillText(lb,L+i*cw+cw/2,12);c.textAlign="right";c.fillText(lb,L-4,T+i*ch+ch/2+3)});
  cv.onmousemove=e=>{const r=cv.getBoundingClientRect(),j=Math.floor((e.clientX-r.left-L)/cw),i=Math.floor((e.clientY-r.top-T)/ch);if(i>=0&&j>=0&&i<n&&j<n)showTip(e,`${names[i]}\n× ${names[j]}\nρ=${mat[i][j].toFixed(3)}`);else hideTip()};cv.onmouseleave=hideTip;
}
function corrMatrix(models){
  const maps=models.map(m=>{const s=P.series[m.model_id];const mp=new Map();if(s){const x0=pd(s.start_date);s.strategy_bp.forEach((b,i)=>mp.set(x0+i,b/1e4))}return mp});
  return maps.map(a=>maps.map(b=>{if(a===b)return 1;const xs=[],ys=[];a.forEach((v,k)=>{if(b.has(k)){xs.push(v);ys.push(b.get(k))}});const n=xs.length;if(n<10)return 0;const mx=xs.reduce((s,v)=>s+v,0)/n,my=ys.reduce((s,v)=>s+v,0)/n;let sxy=0,sxx=0,syy=0;for(let i=0;i<n;i++){sxy+=(xs[i]-mx)*(ys[i]-my);sxx+=(xs[i]-mx)**2;syy+=(ys[i]-my)**2}return sxx>0&&syy>0?sxy/Math.sqrt(sxx*syy):0}))
}
const PANELS=[
 ["01 / Equity Return","% · daily compounded, 1x notional","eq"],["02 / Max Drawdown %","% · Bar Chart (Hard Gate ≤ "+((P.ranking&&P.ranking.ranking_rule&&P.ranking.ranking_rule.hard_gates&&P.ranking.ranking_rule.hard_gates.max_drawdown_pct_limit)||50)+"%)","dd"],
 ["03 / Net Return vs Buy & Hold","% · full window","ret"],["04 / In-Sample vs OOS Sharpe","annualised · OOS = last "+Math.round((P.oos_fraction||.3)*100)+"%","sh"],
 ["05 / Risk vs Return","x = Max DD %, y = CAGR %","rr"],["06 / Exposure & Win Rate","% of bars in market · % winning trades","ex"],
 ["07 / Trades & Profit Factor","count · gross win / gross loss","tr"],["08 / Beta & Correlation vs Underlying","daily returns","bc"],
 ["09 / Daily-Return Correlation Matrix","Pearson, overlapping days","cm","wide"]
];
function buildPanelsInto(hostId,prefix){const el=$(hostId);el.innerHTML=PANELS.map(p=>`<div class="panel ${p[3]||""}"><div class="ph"><span class="pt">${p[0]}</span><span class="ps">${p[1]}</span></div><div class="cv" style="${p[3]?"height:380px":""}"><canvas id="${prefix}${p[2]}"></canvas></div></div>`).join("")}
function buildPanels(){buildPanelsInto("panels","cv-");buildPanelsInto("rank-panels","rcv-")}
function drawPanelsInto(prefix,ms,tagFn,colorFn,ddGateOverride){
  const labels=ms.map(tagFn),names=ms.map(m=>m.model_id+" ["+m.symbol+" "+m.timeframe+"]");
  const L=(key)=>ms.map(m=>{const c=curves(m.model_id);return c?{name:tagFn(m)+" "+m.symbol+" "+m.timeframe+" "+m.family,color:colorFn(m),xs:c.xs,ys:c[key]}:null}).filter(Boolean);
  const ddGate=ddGateOverride!=null?Number(ddGateOverride):Number(S.gates.dd||50);
  const subEl=$(prefix+"dd")&&$(prefix+"dd").closest(".panel")&&$(prefix+"dd").closest(".panel").querySelector(".ps");
  if(subEl)subEl.textContent=`% · Bar Chart (Hard Gate ≤ ${ddGate}%)`;
  lineChart($(prefix+"eq"),L("eq"),v=>v.toFixed(0)+"%");ddBarChart($(prefix+"dd"),labels,ms,colorFn,names,ddGate);
  barChart($(prefix+"ret"),labels,[{name:"Strategy",color:"#3b82f6",vals:ms.map(m=>m.total_return_pct)},{name:"Buy&Hold",color:"#64748b",vals:ms.map(m=>m.buy_hold_return_pct)}],v=>v.toFixed(0)+"%",names);
  barChart($(prefix+"sh"),labels,[{name:"IS Sharpe",color:"#f59e0b",vals:ms.map(m=>m.is_sharpe_ann)},{name:"OOS Sharpe",color:"#22c55e",vals:ms.map(m=>m.oos_sharpe_ann)}],v=>v.toFixed(2),names);
  scatter($(prefix+"rr"),ms.map(m=>({x:m.max_drawdown_pct,y:m.cagr_pct,color:colorFn(m),tag:tagFn(m),text:m.model_id+"\nMaxDD "+num(m.max_drawdown_pct)+"%  CAGR "+num(m.cagr_pct)+"%\nOOS Sharpe "+num(m.oos_sharpe_ann)})));
  barChart($(prefix+"ex"),labels,[{name:"Exposure %",color:"#14b8a6",vals:ms.map(m=>m.exposure_pct)},{name:"Win rate %",color:"#a855f7",vals:ms.map(m=>m.win_rate_pct)}],v=>v.toFixed(0)+"%",names);
  barChart($(prefix+"tr"),labels,[{name:"Trades/10",color:"#eab308",vals:ms.map(m=>m.trades/10)},{name:"Profit factor",color:"#f472b6",vals:ms.map(m=>Math.min(m.profit_factor,10))}],v=>v.toFixed(1),names);
  barChart($(prefix+"bc"),labels,[{name:"Beta",color:"#60a5fa",vals:ms.map(m=>m.beta_to_underlying)},{name:"Corr",color:"#fb923c",vals:ms.map(m=>m.corr_to_underlying)}],v=>v.toFixed(2),names);
  heat($(prefix+"cm"),labels,corrMatrix(ms),names);
}
function drawPanels(){drawPanelsInto("cv-",shown(),m=>idxOf[m.model_id],m=>colorOf[m.model_id],S.gates.dd)}
function drawRankPanels(){
  const allTop=topRankModels();
  const catTxt=S.sym==="ALL"?"รวมทุกสินทรัพย์":S.sym;
  $("rank-panels-title").textContent=`กราฟ 9-Panel — อันดับ Top-${S.gates.topN} สะสม (${catTxt})`;
  const active=allTop.filter(m=>!S.rankOff.has(m.model_id));
  $("rank-legend").innerHTML=allTop.length
    ? allTop.map(m=>`<span class="pill ${S.rankOff.has(m.model_id)?"off":""}" data-rm="${esc(m.model_id)}" title="${esc(m.model_id+" — "+(m.hypothesis||""))}"><span class="dot" style="background:${m._rkColor}"></span>${esc(m._rkTag)} ${esc(m.label||m.family)}</span>`).join("")+`<button id="rank-allon">เปิดทั้งหมด</button><button id="rank-alloff">ซ่อนทั้งหมด</button>`
    : `<span class="note">ยังไม่มีโมเดลในหมวดนี้ที่ผ่าน Gate ปัจจุบัน — ลองปรับแถบ Gate ด้านบนเพื่อสำรวจเพิ่ม</span>`;
  $("rank-legend").querySelectorAll("[data-rm]").forEach(p=>p.onclick=()=>{const id=p.dataset.rm;S.rankOff.has(id)?S.rankOff.delete(id):S.rankOff.add(id);drawRankPanels()});
  const onBtn=$("rank-allon"),offBtn=$("rank-alloff");
  if(onBtn)onBtn.onclick=()=>{S.rankOff.clear();drawRankPanels()};
  if(offBtn)offBtn.onclick=()=>{allTop.forEach(m=>S.rankOff.add(m.model_id));drawRankPanels()};
  drawPanelsInto("rcv-",active,m=>m._rkTag,m=>m._rkColor,S.gates.dd);
}
const COLS=[["label","โมเดล","l"],["symbol","สินทรัพย์"],["timeframe","TF"],["direction","ฝั่ง"],["oos_return_pct","กำไร OOS"],["oos_sharpe_ann","OOS Sharpe"],["total_return_pct","กำไรรวม"],["max_drawdown_pct","Max DD"],["ann_vol_pct","Vol/ปี"],["equity_r2","R² นิ่ง"],["trades","จำนวนเทรด"],["win_rate_pct","Win%"],["profit_factor","PF"],["rank","อันดับ"]];
let RK={};const DSR={};[...(P.ranking.top_ranked||[]),...(P.ranking.disqualified||[])].forEach(r=>DSR[r.model_id]=r.dsr_approx);
function cell(m,k){
  const v=m[k];
  if(k==="label")return `<td class="l" title="${esc(m.model_id+" — "+(m.hypothesis||""))}"><b>${esc(v||m.model_id)}</b></td>`;
  if(k==="symbol")return `<td>${symBadge(v)}</td>`;
  if(k==="rank")return `<td>${RK[m.model_id]?"#"+RK[m.model_id]:"–"}</td>`;
  if(k==="dsr_approx")return `<td>${num(DSR[m.model_id],2)}</td>`;
  if(["total_return_pct","cagr_pct","oos_return_pct","buy_hold_return_pct"].includes(k))return `<td>${sgn(v)}</td>`;
  if(["max_drawdown_pct","win_rate_pct","exposure_pct","ann_vol_pct","ulcer_index_pct"].includes(k))return `<td>${num(v,1)}%</td>`;
  if(k==="equity_r2")return `<td>${num(v,2)}</td>`;
  if(typeof v==="number")return `<td>${num(v,k==="trades"?0:2)}</td>`;
  return `<td>${esc(v)}</td>`;
}
function table(el,rows,key){
  const[sk,sd]=S.sort[key];const val=m=>sk==="rank"?(RK[m.model_id]||1e9):sk==="dsr_approx"?(DSR[m.model_id]??-1):(m[sk]??"");
  const sorted=[...rows].sort((a,b)=>{const x=val(a),y=val(b);return (typeof x==="string"?x.localeCompare(y):(x-y))*sd});
  el.innerHTML=`<table><thead><tr>${COLS.map(c=>`<th class="${c[2]||""}" data-k="${c[0]}">${c[1]}${sk===c[0]?(sd>0?" ▲":" ▼"):""}</th>`).join("")}</tr></thead><tbody>${sorted.map(m=>`<tr>${COLS.map(c=>cell(m,c[0])).join("")}</tr>`).join("")}</tbody></table>`;
  el.querySelectorAll("th").forEach(th=>th.onclick=()=>{const k=th.dataset.k;S.sort[key]=[k,S.sort[key][0]===k?-S.sort[key][1]:-1];render()});
}
function rankTable(rows){return `<table><thead><tr><th>อันดับ</th><th class="l">โมเดล</th><th>สินทรัพย์</th><th>TF</th><th>OOS Sharpe</th><th>กำไร OOS</th><th>Max DD</th><th>Vol/ปี</th><th>R² นิ่ง</th><th>เทรด</th><th>วันที่ทดสอบ</th></tr></thead><tbody>${rows.map(r=>`<tr><td>#${r.rank}</td><td class="l" title="${esc(r.model_id+" — "+(r.hypothesis||""))}"><b>${esc(r.label||r.model_id)}</b></td><td>${symBadge(r.symbol)}</td><td>${esc(r.timeframe)}</td><td>${num(r.oos_sharpe_ann)}</td><td>${sgn(r.oos_return_pct)}</td><td>${num(r.max_drawdown_pct,1)}%</td><td>${num(r.ann_vol_pct,1)}%</td><td>${num(r.equity_r2,2)}</td><td>${r.trades}</td><td>${esc(r.batch_date)}</td></tr>`).join("")||'<tr><td colspan="11" class="mut">ยังไม่มีโมเดลในหมวดนี้ที่ผ่านเกณฑ์ทั้งหมด</td></tr>'}</tbody></table>`}
function syncGateUi(){
  const g=S.gates;
  if($("g-dd"))$("g-dd").value=String(g.dd);
  if($("g-dd-val"))$("g-dd-val").textContent=g.dd+"%";
  if($("g-vol"))$("g-vol").value=String(g.maxVol);
  if($("g-vol-val"))$("g-vol-val").textContent=g.maxVol>=100?"ไม่จำกัด":(g.maxVol+"%");
  if($("g-r2"))$("g-r2").value=String(g.minR2);
  if($("g-r2-val"))$("g-r2-val").textContent=Number(g.minR2).toFixed(2);
  if($("g-trades"))$("g-trades").value=String(g.trades);
  if($("g-sharpe"))$("g-sharpe").value=String(g.minSharpe);
  if($("g-oos-pos"))$("g-oos-pos").checked=Boolean(g.requireOosPos);
  if($("g-mode"))$("g-mode").value=g.mode;
  if($("g-topn"))$("g-topn").value=String(g.topN);
}
function renderRanking(){
  const rr=evalAlphaRanking();
  RK={};(rr.top_ranked||[]).forEach(r=>{RK[r.model_id]=r.rank});
  const g=S.gates;
  const qualSym=S.sym==="ALL"?rr.qualified_count:((rr.qualified_by_symbol||{})[S.sym]||0);
  const totSym=((P.models&&P.models.length)?P.models:P.batch_models).filter(m=>S.sym==="ALL"||m.symbol===S.sym).length;
  if($("g-summary"))$("g-summary").textContent=`ผ่านเกณฑ์ ${qualSym}/${totSym} โมเดล`;
  const volTxt=g.maxVol>=100?"ไม่จำกัด":`≤ ${g.maxVol}%`;
  const gateDesc=`เกณฑ์ปัจจุบัน: ${g.requireOosPos?"OOS > 0%, ":""}OOS Sharpe ${g.minSharpe===0?"> 0":"≥ "+g.minSharpe}, เทรด ≥ ${g.trades}, Max DD ≤ ${g.dd}%, Vol ${volTxt}, R² ≥ ${Number(g.minR2).toFixed(2)}`;
  let h="";
  if(S.sym==="ALL"){
    h+=`<div class="card"><div class="pt" style="margin-bottom:6px">อันดับ Top-${g.topN} สะสมรวม</div><div class="note" style="margin-bottom:8px">${esc(gateDesc)}</div><div class="tw">${rankTable(rr.top_ranked||[])}</div></div>`;
  }
  Object.entries(rr.top_ranked_by_symbol||{}).filter(([s])=>S.sym==="ALL"||S.sym===s).forEach(([s,rows])=>{h+=`<div class="card" style="margin-top:14px"><div class="pt" style="margin-bottom:8px">${symBadge(s)} อันดับ Top-${g.topN} เฉพาะสินทรัพย์นี้</div><div class="note" style="margin-bottom:8px">${esc(gateDesc)}</div><div class="tw">${rankTable(rows)}</div></div>`});
  const dq=(rr.disqualified||[]).filter(d=>S.sym==="ALL"||d.symbol===S.sym);
  h+=`<div class="card" style="margin-top:14px"><div class="pt" style="margin-bottom:8px">โมเดลที่ยังไม่ผ่านเกณฑ์ (${dq.length})</div><div class="tw"><table><thead><tr><th class="l">โมเดล</th><th>สินทรัพย์</th><th>TF</th><th>OOS Sharpe</th><th>กำไร OOS</th><th>Max DD</th><th>Vol/ปี</th><th>R²</th><th class="l">สาเหตุ</th></tr></thead><tbody>${dq.map(d=>`<tr><td class="l" title="${esc(d.model_id)}">${esc(d.label||d.model_id)}</td><td>${symBadge(d.symbol)}</td><td>${esc(d.timeframe)}</td><td>${num(d.oos_sharpe_ann)}</td><td>${sgn(d.oos_return_pct)}</td><td>${num(d.max_drawdown_pct,1)}%</td><td>${num(d.ann_vol_pct,1)}%</td><td>${num(d.equity_r2,2)}</td><td class="l mut">${esc((d.disqualify_reasons||[]).join(", "))}</td></tr>`).join("")}</tbody></table></div></div>`;
  $("rank-tables").innerHTML=h;
}
function renderKpis(){
  const ms=P.batch_models.filter(visible),oos=ms.filter(m=>m.oos_return_pct>0).length,best=ms.reduce((a,m)=>(!a||m.oos_sharpe_ann>a.oos_sharpe_ann)?m:a,null);
  const rr=evalAlphaRanking();
  const qualSym=S.sym==="ALL"?rr.qualified_count:((rr.qualified_by_symbol||{})[S.sym]||0);
  const k=[["โมเดลในหน้านี้",ms.length+" โมเดล"],["กำไร OOS เป็นบวก",oos+" / "+ms.length],["OOS Sharpe สูงสุด",best?num(best.oos_sharpe_ann)+" ("+(best.label||best.family)+")":"–"],["ผ่านเกณฑ์ขึ้นบอร์ด",qualSym+" โมเดล"]];
  $("kpis").innerHTML=k.map(x=>`<div class="card"><div class="kl">${x[0]}</div><div class="kv" style="font-size:17px">${esc(x[1])}</div></div>`).join("");
}
function syncHash(){
  const rawHash=location.hash||"";
  const m=rawHash.match(/sym=(XAUUSD|ETHUSDT|ALL)/i);
  if(m)S.sym=m[1].toUpperCase();
  const tm=rawHash.match(/tab=(daily|ranking|all)/i);
  if(tm)S.tab=tm[1].toLowerCase();
  document.querySelectorAll("#top-cats [data-sym]").forEach(a=>{
    const s=a.dataset.sym;
    a.className="pp"+(S.sym===s?(s==="XAUUSD"?" xau-on":s==="ETHUSDT"?" eth-on":" all-on"):"");
  });
  const catLabel=S.sym==="XAUUSD"?"ALPHA · ทองคำ (XAUUSD)":S.sym==="ETHUSDT"?"ALPHA · คริปโต (ETHUSDT)":"ALPHA · ทั้งหมด (XAUUSD + ETHUSDT)";
  $("title").textContent=catLabel+" — "+P.batch_date;
}
function renderLegend(){
  const ms=P.batch_models.filter(visible);
  const rounds=["ALL",...new Set(P.batch_models.map(m=>String(m.round_no||1)))];
  const rBtns=rounds.length>2?`<span class="note">รอบ:</span>`+rounds.map(r=>`<button data-r="${r}" class="${S.round===r?"active":""}">${r==="ALL"?"ทั้งหมด":"รอบ "+r}</button>`).join("")+`<span style="width:8px"></span>`:"";
  $("legend").innerHTML=rBtns+ms.map(m=>`<span class="pill ${S.off.has(m.model_id)?"off":""}" data-m="${esc(m.model_id)}" title="${esc(m.model_id+" — "+(m.hypothesis||""))}"><span class="dot" style="background:${colorOf[m.model_id]}"></span>${idxOf[m.model_id]} ${esc(m.label||m.family)}</span>`).join("")+`<button id="allon">เปิดทั้งหมด</button><button id="alloff">ซ่อนทั้งหมด</button>`;
  $("legend").querySelectorAll(".pill").forEach(p=>p.onclick=()=>{const id=p.dataset.m;S.off.has(id)?S.off.delete(id):S.off.add(id);render()});
  $("legend").querySelectorAll("[data-r]").forEach(b=>b.onclick=()=>{S.round=b.dataset.r;render()});
  $("allon").onclick=()=>{S.off.clear();render()};$("alloff").onclick=()=>{ms.forEach(m=>S.off.add(m.model_id));render()};
}
let LIVE_DATES=(P.available_dates||[]).slice();
function navHash(){
  const parts=[];
  if(S.sym!=="ALL")parts.push("sym="+S.sym);
  if(S.tab==="ranking")parts.push("tab=ranking");
  return parts.length?"#"+parts.join("&"):"";
}
function renderNav(){
  const h=navHash();
  const byDate=new Map();
  LIVE_DATES.forEach(d=>{if(d&&/^\d{4}-\d{2}-\d{2}$/.test(String(d.batch_date||"")))byDate.set(d.batch_date,d)});
  if(!byDate.has(P.batch_date))byDate.set(P.batch_date,{batch_date:P.batch_date,model_count:(P.batch_models||[]).length});
  const ds_=[...byDate.values()].sort((a,b)=>String(b.batch_date).localeCompare(String(a.batch_date)));
  const i=ds_.findIndex(d=>d.batch_date===P.batch_date),older=ds_[i+1],newer=ds_[i-1];
  const opts=ds_.map(d=>`<option value="${esc(d.batch_date)}" ${d.batch_date===P.batch_date?"selected":""}>${esc(d.batch_date)}${d.model_count?" ("+d.model_count+")":""}</option>`).join("");
  $("nav").innerHTML=(older?`<a class="nav" href="../${esc(older.batch_date)}/dashboard.html${h}">◀ ${esc(older.batch_date)}</a>`:"")+`<select id="date-sel" class="dnav" aria-label="เลือกวันที่">${opts}</select>`+(newer?`<a class="nav" href="../${esc(newer.batch_date)}/dashboard.html${h}">${esc(newer.batch_date)} ▶</a>`:"");
  const sel=$("date-sel");
  if(sel)sel.onchange=()=>{if(sel.value&&sel.value!==P.batch_date&&/^\d{4}-\d{2}-\d{2}$/.test(sel.value))location.href="../"+sel.value+"/dashboard.html"+navHash()};
}
if(typeof fetch==="function"&&location.protocol!=="file:"){
  fetch("../index.json",{cache:"no-store"}).then(r=>r.ok?r.json():null).then(idx=>{
    if(idx&&Array.isArray(idx.days)&&idx.days.length){LIVE_DATES=idx.days;renderNav()}
  }).catch(()=>{});
}
function render(){
  syncHash();
  document.querySelectorAll("#tabs button").forEach(b=>b.classList.toggle("active",b.dataset.tab===S.tab));
  ["daily","ranking","all"].forEach(t=>$("tab-"+t).classList.toggle("hidden",t!==S.tab));
  renderNav();renderKpis();renderRanking();
  if(S.tab==="daily"){renderLegend();drawPanels();table($("tbl-daily"),P.batch_models.filter(visible),"daily")}
  if(S.tab==="ranking"){drawRankPanels()}
  if(S.tab==="all")table($("tbl-all"),P.models.filter(m=>S.sym==="ALL"||m.symbol===S.sym),"all");
}
$("sub").textContent="คลิกชื่อโมเดลด้านล่างเพื่อเปิด/ปิดเส้นกราฟ · OOS = ช่วงทดสอบนอกกลุ่มตัวอย่าง 30% ล่าสุด";
$("foot").textContent="ข้อมูลวิจัยเชิงทดลองแบบ Causal (ตัดสินใจเมื่อปิดแท่ง → เข้าที่ราคาเปิดแท่งถัดไป หักค่าธรรมเนียมต่อขาแล้ว)";
function onGateChange(){
  S.gates.dd=Math.max(1,Math.min(100,Number($("g-dd").value||50)));
  S.gates.maxVol=Math.max(5,Math.min(100,Number($("g-vol").value||60)));
  S.gates.minR2=Math.max(0,Math.min(0.95,Number($("g-r2").value||0)));
  S.gates.trades=Math.max(0,Number($("g-trades").value||0));
  S.gates.minSharpe=Number($("g-sharpe").value||0);
  S.gates.requireOosPos=Boolean($("g-oos-pos").checked);
  S.gates.mode=$("g-mode").value||"oos_sharpe";
  S.gates.topN=Math.max(1,Math.min(20,Number($("g-topn").value||9)));
  $("g-dd-val").textContent=S.gates.dd+"%";
  $("g-vol-val").textContent=S.gates.maxVol>=100?"ไม่จำกัด":(S.gates.maxVol+"%");
  $("g-r2-val").textContent=Number(S.gates.minR2).toFixed(2);
  render();
}
["g-dd","g-vol","g-r2","g-trades","g-sharpe","g-oos-pos","g-mode","g-topn"].forEach(id=>{
  const el=$(id);
  if(el){el.addEventListener("input",onGateChange);el.addEventListener("change",onGateChange)}
});
if($("g-reset"))$("g-reset").onclick=()=>{S.gates=Object.assign({},DEFAULT_GATES);S.rankOff.clear();syncGateUi();render()};
document.querySelectorAll("#tabs button").forEach(b=>b.onclick=()=>{S.tab=b.dataset.tab;if(location.hash.includes("tab=")){history.replaceState(null,"",location.hash.replace(/&?tab=(daily|ranking|all)/i,"")||"#");}render()});
addEventListener("hashchange",()=>render());
buildPanels();syncGateUi();render();
addEventListener("resize",()=>{if(S.tab==="daily")drawPanels();else if(S.tab==="ranking")drawRankPanels()});
</script>
</body>
</html>
"""


def render_dashboard_html(
    *,
    batch_date: str,
    batch_metrics: Sequence[dict[str, Any]],
    all_models_metrics: Sequence[dict[str, Any]],
    ranking_board: dict[str, Any],
    batch_series: dict[str, dict[str, Any]],
    available_dates: Sequence[dict[str, Any]] = (),
    beta_hub_href: str = DEFAULT_BETA_HUB_HREF,
    default_tab: str = "daily",
) -> str:
    rule = ranking_board.get("ranking_rule", {})
    ranking_slim = {
        "ranking_rule": rule,
        "qualified_count": int(ranking_board.get("qualified_count", 0)),
        "top_ranked": [_slim(r) for r in ranking_board.get("top_ranked", [])],
        "top_ranked_by_symbol": {
            s: [_slim(r) for r in rows] for s, rows in (ranking_board.get("top_ranked_by_symbol") or {}).items()
        },
        "disqualified": [_slim(r) for r in ranking_board.get("disqualified", [])],
    }
    dates = [
        {"batch_date": str(d["batch_date"]), "model_count": int(d.get("model_count", 0))}
        for d in available_dates
        if isinstance(d, dict) and _SAFE_DATE_RE.fullmatch(str(d.get("batch_date", "")))
    ]
    if _SAFE_DATE_RE.fullmatch(batch_date) and batch_date not in {d["batch_date"] for d in dates}:
        dates.append({"batch_date": batch_date, "model_count": len(batch_metrics)})
    dates.sort(key=lambda d: d["batch_date"], reverse=True)
    rounds = sorted({int(m["round_no"]) for m in batch_metrics if m.get("round_no") is not None}) or [1]
    batch_ids = [m["model_id"] for m in batch_metrics]
    top_ids = [r["model_id"] for r in ranking_board.get("top_ranked", []) if r.get("model_id")]
    for rows in (ranking_board.get("top_ranked_by_symbol") or {}).values():
        top_ids.extend(r["model_id"] for r in rows if r.get("model_id"))
    # Include top candidates per symbol across all_models_metrics so interactive Gate loosening still plots curves.
    by_sym_all: dict[str, list[dict[str, Any]]] = {}
    for m in all_models_metrics:
        by_sym_all.setdefault(str(m.get("symbol", "")), []).append(m)
    extra_ids: list[str] = []
    for sym_rows in by_sym_all.values():
        ranked_sym = sorted(
            sym_rows,
            key=lambda x: (-float(x.get("oos_sharpe_ann", -999.0)), float(x.get("max_drawdown_pct", 999.0))),
        )
        extra_ids.extend(str(m["model_id"]) for m in ranked_sym[:30] if m.get("model_id"))
    series_ids = list(dict.fromkeys([*batch_ids, *top_ids, *extra_ids]))
    stab_by_id = {mid: stability_from_alpha_series(ser) for mid, ser in batch_series.items()}

    def _with_stab(m: dict[str, Any]) -> dict[str, Any]:
        rec = _slim(m, keep_hyp=True)
        mid = str(rec.get("model_id", ""))
        if mid in stab_by_id:
            rec.update(stab_by_id[mid])
        else:
            rec.setdefault("ann_vol_pct", 0.0)
            rec.setdefault("ulcer_index_pct", 0.0)
            rec.setdefault("equity_r2", 0.0)
        return rec

    payload = {
        "batch_date": batch_date,
        "generated_at_utc": ranking_board.get("generated_at_utc", ""),
        "total_trials": int(ranking_board.get("total_trials", 0)),
        "top_n": int(rule.get("top_n", 9)),
        "oos_fraction": next((m.get("oos_fraction") for m in batch_metrics if m.get("oos_fraction")), 0.3),
        "default_tab": default_tab if default_tab in {"daily", "ranking", "all"} else "daily",
        "rounds": rounds,
        "beta_hub_href": beta_hub_href,
        "batch_models": [_with_stab(m) for m in batch_metrics],
        "models": [_with_stab(m) for m in all_models_metrics],
        "series": {mid: batch_series[mid] for mid in series_ids if mid in batch_series},
        "ranking": ranking_slim,
        "available_dates": dates,
    }
    title = f"Alpha_mining — Alpha Mining 9-Panel Dashboard ({html.escape(batch_date)})"
    return _DASHBOARD_TEMPLATE.replace("__TITLE__", title).replace("__PAYLOAD__", _safe_inline_json(payload))


_SLIM_KEYS = (
    "model_id", "symbol", "timeframe", "direction", "family", "round_no", "batch_date", "trial_number",
    "total_return_pct", "cagr_pct", "max_drawdown_pct", "sharpe_daily_ann", "is_sharpe_ann", "oos_sharpe_ann",
    "oos_return_pct", "oos_max_drawdown_pct", "trades", "win_rate_pct", "profit_factor", "exposure_pct",
    "buy_hold_return_pct", "beta_to_underlying", "corr_to_underlying", "dsr_approx", "oos_fraction",
    "disqualify_reasons", "rank", "days_covered", "data_is_proxy",
    "ann_vol_pct", "ulcer_index_pct", "equity_r2",
)


def _slim(m: dict[str, Any], keep_hyp: bool = False) -> dict[str, Any]:
    out = {k: m[k] for k in _SLIM_KEYS if k in m}
    out["label"] = humanize_alpha_model(m)
    if keep_hyp and m.get("hypothesis"):
        out["hypothesis"] = str(m["hypothesis"])[:300]
    return out


def render_portal_index_html(
    *,
    daily_days: Sequence[dict[str, Any]],
    ranking_board: dict[str, Any],
    latest_date: str | None = None,
    central_hub_href: str = "../index.html",
    beta_hub_href: str = "../beta/index.html",
) -> str:
    """Static zero-JS archive hub listing every Alpha day + cumulative Top-9, with a link to the Beta hub."""
    days = sorted(
        (d for d in daily_days if isinstance(d, dict) and _SAFE_DATE_RE.fullmatch(str(d.get("batch_date", "")))),
        key=lambda d: d["batch_date"],
        reverse=True,
    )
    rule = ranking_board.get("ranking_rule", {})
    top_n = int(rule.get("top_n", 9))
    latest = latest_date if latest_date and _SAFE_DATE_RE.fullmatch(latest_date) else (days[0]["batch_date"] if days else "")
    e = html.escape

    def _day_row(d: dict[str, Any]) -> str:
        sym = ", ".join(f"{e(k)}: {v}" for k, v in sorted((d.get("by_symbol") or {}).items()))
        link = (
            f'<a href="{e(d["dashboard_rel_path"])}">dashboard</a>' if d.get("has_dashboard", True) else "–"
        ) + (f' · <a href="{e(d["summary_rel_path"])}">summary</a>' if d.get("has_summary") else "")
        return (
            f"<tr><td>{e(d['batch_date'])}</td><td>{int(d.get('model_count', 0))}</td>"
            f"<td>{e(','.join(str(r) for r in d.get('rounds', [])) or '1')}</td><td>{sym}</td>"
            f"<td>{int(d.get('profitable_oos_count', 0))}</td>"
            f"<td>{e(str(d.get('best_oos_sharpe_model_id', '')))} ({float(d.get('best_oos_sharpe', 0)):.2f})</td><td>{link}</td></tr>"
        )

    top_rows = "".join(
        f"<tr><td>#{int(r['rank'])}</td><td>{e(str(r['model_id']))}</td><td>{e(str(r.get('symbol')))}</td>"
        f"<td>{e(str(r.get('timeframe')))}</td><td>{float(r.get('oos_sharpe_ann', 0)):.2f}</td>"
        f"<td>{float(r.get('oos_return_pct', 0)):+.1f}%</td><td>{float(r.get('max_drawdown_pct', 0)):.1f}%</td>"
        f"<td>{float(r.get('dsr_approx', 0)):.2f}</td></tr>"
        for r in ranking_board.get("top_ranked", [])
    ) or '<tr><td colspan="8">No model passes the hard gates yet.</td></tr>'
    latest_link = f'<a class="btn" href="daily/{e(latest)}/dashboard.html">Open latest ({e(latest)})</a>' if latest else ""
    return f"""<!DOCTYPE html>
<html lang="th"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Alpha_mining — Alpha Mining Hub</title>
<style>
body{{margin:0;padding:22px;background:#0b1017;color:#e6edf6;font:13px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}}
.w{{max-width:1200px;margin:0 auto}}h1{{font-size:20px;margin:0 0 4px}}.m{{color:#8ea0b8}}
.card{{background:#121923;border:1px solid #263244;border-radius:12px;padding:14px;margin-top:14px;overflow-x:auto}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:6px 8px;border-bottom:1px solid #263244;text-align:left;white-space:nowrap}}th{{color:#8ea0b8}}
a{{color:#93c5fd}}a.btn{{display:inline-block;padding:7px 12px;border:1px solid #263244;border-radius:8px;background:#192331;text-decoration:none;margin-right:8px;font-weight:700}}
a.btn.alpha-cta{{background:#f59e0b;color:#0b1017;border-color:#f59e0b}}
.pbar{{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;background:#0f1722;border:1px solid #263244;border-left:4px solid #f59e0b;border-radius:12px;padding:10px 14px;margin-bottom:14px}}
.pp{{display:inline-flex;padding:5px 11px;border-radius:999px;font-size:12px;font-weight:700;text-decoration:none;border:1px solid #263244;background:#192331;color:#e6edf6;margin-left:6px}}
.pp.a-on{{background:#f59e0b;color:#0b1017;border-color:#f59e0b}}.pp.b-go{{color:#60a5fa;border-color:rgba(59,130,246,.45);background:rgba(59,130,246,.12)}}
</style></head><body><div class="w">
<nav class="pbar"><b style="font-size:14px">Alpha_mining · Central Portal</b><div><a class="pp" href="{e(central_hub_href)}">Central Hub (ฐานกลาง)</a><a class="pp a-on" href="index.html">ALPHA Track · XAUUSD + ETH</a><a class="pp b-go" href="{e(beta_hub_href)}">BETA Track · ETH Grid</a></div></nav>
<h1>ALPHA TRACK — Alpha Mining Hub (XAUUSD + ETHUSDT)</h1>
<div class="m">Generated {e(str(ranking_board.get('generated_at_utc', '')))} · {len(days)} day(s) · {int(ranking_board.get('total_models', 0))} models · N_trials={int(ranking_board.get('total_trials', 0))} · 20 models/day (10 XAUUSD + 10 ETHUSDT) in 2 rounds</div>
<div style="margin-top:12px">{latest_link.replace('class="btn"', 'class="btn alpha-cta"')}<a class="btn" href="{e(central_hub_href)}">กลับฐานกลาง (Central Hub)</a><a class="btn" href="{e(beta_hub_href)}">สลับไป BETA Hub</a></div>
<div class="card"><b>Cumulative Top-{top_n}</b> <span class="m">(OOS Sharpe DESC, Max DD ASC; DSR≈ = multiple-testing haircut)</span>
<table><thead><tr><th>Rank</th><th>Model</th><th>Sym</th><th>TF</th><th>OOS Sharpe</th><th>OOS Ret</th><th>Max DD</th><th>DSR≈</th></tr></thead><tbody>{top_rows}</tbody></table></div>
<div class="card"><b>Daily batches</b>
<table><thead><tr><th>Date</th><th>Models</th><th>Rounds</th><th>By symbol</th><th>OOS profitable</th><th>Best OOS Sharpe</th><th>Links</th></tr></thead><tbody>{"".join(_day_row(d) for d in days)}</tbody></table></div>
<div class="m" style="margin-top:14px">Exploratory research only. XAUUSD uses the PAXGUSDT gold-backed proxy feed on GitHub Actions.</div>
</div></body></html>
"""
