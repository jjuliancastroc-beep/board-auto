"""Render docs/index.html - one self-contained page (data inlined) that the automation rebuilds every run."""
import json, os, html
from .common import ROOT, load, now_ct

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Board - Auto</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--line:#262b36;--text:#e8eaef;--mute:#9aa3b2;--good:#3ecf8e;--bad:#ef6b6b;--warn:#e7b44c;--acc:#6ea8fe}
@media (prefers-color-scheme: light){:root{--bg:#f6f7f9;--card:#fff;--line:#e3e6eb;--text:#151821;--mute:#5d6676;--good:#14804a;--bad:#c23b3b;--warn:#9a6700;--acc:#2457c5}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
header{padding:18px 16px 8px;max-width:1000px;margin:auto}h1{font-size:20px;margin:0}.sub{color:var(--mute);font-size:13px}
nav{display:flex;gap:6px;overflow-x:auto;padding:8px 16px;max-width:1000px;margin:auto;position:sticky;top:0;background:var(--bg);z-index:2}
nav button{background:var(--card);color:var(--text);border:1px solid var(--line);border-radius:999px;padding:7px 14px;font-size:14px;white-space:nowrap;cursor:pointer}
nav button.on{background:var(--acc);border-color:var(--acc);color:#fff}
main{max-width:1000px;margin:auto;padding:8px 16px 40px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:10px 0}
.row{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}.tag{font-size:12px;font-weight:600;border-radius:6px;padding:2px 8px;border:1px solid var(--line)}
.CASH{color:#fff;background:var(--good);border-color:var(--good)}.PAPER{color:var(--acc);border-color:var(--acc)}.WATCH{color:var(--warn);border-color:var(--warn)}.PASS{color:var(--mute)}
.big{font-size:17px;font-weight:600}.mute{color:var(--mute);font-size:13px}.flag{color:var(--warn);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:14px}td:first-child{white-space:nowrap}td,th{padding:7px 6px;border-bottom:1px solid var(--line);text-align:left;font-variant-numeric:tabular-nums}th{color:var(--mute);font-weight:500;font-size:12px}
.W{color:var(--good)}.L{color:var(--bad)}.hide{display:none}.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}.kpi div{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}.kpi b{display:block;font-size:20px}
details summary{cursor:pointer;color:var(--acc);font-size:14px}
</style></head><body>
<header><h1>The Board - Auto</h1><div class="sub" id="upd"></div></header>
<nav id="nav"></nav><main id="main"></main>
<script>
const D = __DATA__;
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
document.getElementById("upd").textContent = `Updated ${D.updated} - rebuilt automatically twice a day. Lines: ${D.lines_source}.`;
const tabs = {Today: today, Results: results, "Past-games test": test, Rules: rules};
const nav = document.getElementById("nav"); let cur = "Today";
Object.keys(tabs).forEach(t => { const b = document.createElement("button"); b.textContent = t; b.onclick = () => { cur = t; draw(); }; nav.appendChild(b); });
function draw(){ [...nav.children].forEach(b => b.classList.toggle("on", b.textContent === cur)); document.getElementById("main").innerHTML = tabs[cur](); window.scrollTo(0,0); }
function plain(r){
  if (r.decision === "PASS") return r.reason || "No edge.";
  const a = r.model_a, b = r.model_b, hl = r.home_line;
  if (r.sport === "NHL") return `${r.model_a_name} and ${r.model_b_name} give ${r.gap_a > 0 ? r.home : r.away} more win chance than the price does (${r.gap_a}/${r.gap_b} points). ${r.reason}`;
  const fav = m => m == null ? "?" : (m >= 0 ? `${r.home} by ${m.toFixed(1)}` : `${r.away} by ${(-m).toFixed(1)}`);
  return `Market: ${esc(r.line)}. ${r.model_a_name} says ${fav(a)}; ${r.model_b_name} says ${fav(b)}. Gap ${r.gap_a} / ${r.gap_b} points. ${r.reason}`;
}
function today(){
  let h = `<div class="card"><div class="big">${esc(D.headline)}</div><div class="mute">${esc(D.bankroll_note)}</div></div>`;
  for (const c of D.cards){
    if (!c.games.length) continue;
    const live = c.games.filter(r => r.decision !== "PASS");
    h += `<h3>${c.sport} <span class="mute">${c.games.length} games - ${live.length} with a model call</span></h3>`;
    for (const r of live){
      const inj = [...(r.inj_away||[]).map(x => `${esc(x.player)} (${esc(r.away.split(" ").pop())}) ${esc(x.status)}`), ...(r.inj_home||[]).map(x => `${esc(x.player)} (${esc(r.home.split(" ").pop())}) ${esc(x.status)}`)];
      const tr = r.test_record ? `Past-games test for this kind of pick: ${r.test_record.w}-${r.test_record.l} (${(r.test_record.win*100).toFixed(1)}%)` : (r.decision !== "PASS" ? "No past-games test for this sport yet" : "");
      h += `<div class="card ${r.decision === "PASS" ? "pass" : ""}"><div class="row"><div><div class="big">${esc(r.decision === "PASS" ? r.game : r.pick)}</div><div class="mute">${esc(r.game)} - ${esc(r.time)}${r.tier ? " - " + r.tier + " " + r.day : ""}</div></div>
      <div><span class="tag ${r.decision}">${r.decision}${r.stake ? " $" + r.stake : ""}</span>${r.conf ? ` <span class="tag">${r.conf}</span>` : ""}</div></div>
      <p>${esc(plain(r))}</p>${tr ? `<div class="mute">${esc(tr)}</div>` : ""}${(r.flags||[]).map(f => `<div class="flag">${esc(f)}</div>`).join("")}
      ${inj.length ? `<details><summary>Injuries (${inj.length})</summary><div class="mute">${inj.join("; ")}</div></details>` : ""}</div>`;
    }
    const passed = c.games.filter(r => r.decision === "PASS");
    if (passed.length) h += `<details class="card"><summary>Passed games (${passed.length})</summary><table>${passed.map(r => `<tr><td>${esc(r.game)}<div class="mute">${esc(r.time)} - ${esc(r.line || "no line")}</div></td><td class="mute">${esc(r.reason)}</td></tr>`).join("")}</table></details>`;
  }
  return h;
}
function results(){
  const S = D.summary; let h = Object.keys(S).length ? "" : `<div class="card mute">Nothing graded yet. Picks grade themselves from ESPN finals on the next run after each game ends.</div>`; h += `<div class="kpi">`;
  for (const [k, s] of Object.entries(S)) h += `<div><span class="mute">${esc(k)}</span><b>${s.w}-${s.l}${s.p ? "-" + s.p : ""}</b><span class="mute">${s.units >= 0 ? "+" : ""}${s.units}u${s.pl ? ` / $${s.pl}` : ""}${s.clv_n ? ` - beat close ${s.clv_beat}/${s.clv_n}` : ""}</span></div>`;
  h += `</div><div class="card"><table><tr><th>Date</th><th>Pick</th><th>Type</th><th>Result</th><th>Close</th></tr>`;
  for (const p of D.picks.slice().reverse().slice(0, 300)) h += `<tr><td>${esc(p.date.slice(5))}</td><td>${esc(p.pick)}<div class="mute">${esc(p.game)}</div></td><td>${esc(p.decision)}${p.stake ? " $" + p.stake : ""}</td><td class="${(p.result||"")[0]}">${esc(p.result || "Pending")}<div class="mute">${esc(p.final || "")}</div></td><td>${esc(p.close || "")}${p.clv != null ? `<div class="mute">${p.clv > 0 ? "+" : ""}${p.clv} pts vs close</div>` : ""}</td></tr>`;
  return h + `</table></div>`;
}
function rec(o){ return o ? `${o.w}-${o.l} (${(o.win*100).toFixed(1)}%)` : "-"; }
function test(){
  const B = D.backtest; let h = `<div class="card"><div class="big">What the past games say</div><p>We replayed ${B.n.CFB} college and ${B.n.NFL} NFL games, using only what was known before each game. A pick needs to win 52.4% just to break even at -110. The card only puts cash on a kind of pick that won 53.5%+ over 200+ games.</p></div>`;
  h += `<div class="card"><b>College football - both models agree, gap 3+</b><table><tr><th>Kind of game</th><th>Record</th></tr>${Object.entries(B.CFB).map(([k,v]) => `<tr><td>${esc(k)}</td><td>${rec(v)}</td></tr>`).join("")}</table></div>`;
  h += `<div class="card"><b>NFL - both models agree, gap 3+</b><table><tr><th>Day</th><th>Record</th></tr>${Object.entries(B.NFL).map(([k,v]) => `<tr><td>${esc(k)}</td><td>${rec(v)}</td></tr>`).join("")}</table></div>`;
  for (const s of ["CFB","NFL"]) h += `<div class="card"><b>${s} - does a bigger gap win more?</b><table><tr><th>Gap (points)</th><th>Record</th></tr>${Object.entries(B.by_gap[s]).map(([k,v]) => `<tr><td>${esc(k)}</td><td>${rec(v)}</td></tr>`).join("")}</table></div>`;
  h += `<div class="card mute">${B.notes.map(esc).join("<br>")}</div>`;
  return h;
}
function rules(){ return `<div class="card">${D.rules.map(r => `<p>${esc(r)}</p>`).join("")}</div>`; }
draw();
</script></body></html>"""


def render(cards, picks, summary, backtest, headline, bankroll_note):
    data = {"updated": now_ct().strftime("%a %b %-d, %-I:%M %p CT"), "cards": cards, "picks": picks, "summary": summary, "backtest": backtest,
            "headline": headline, "bankroll_note": bankroll_note, "lines_source": "DraftKings via ESPN (free feed)",
            "rules": load("rules.json", [])}
    out = PAGE.replace("__DATA__", json.dumps(data, default=float).replace("</", "<\\/"))
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    with open(os.path.join(ROOT, "docs", "index.html"), "w") as f:
        f.write(out)
    with open(os.path.join(ROOT, "docs", ".nojekyll"), "w") as f:
        f.write("")
