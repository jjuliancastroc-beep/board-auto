"""Render docs/index.html - one self-contained page (data inlined), rebuilt on every run.
Tabs match the original Board: Today, Board, Card, Confidence, Record, Lab, Rules, Reviews, Requests, Streaks."""
import json, os
from .common import ROOT, load, now_ct, SPORTS
from . import grade, review
from .card import MODEL_NOTE

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Board</title>
<style>
:root{--bg:#0e1014;--card:#161920;--card2:#1c2029;--line:#272c37;--text:#e7e9ee;--mute:#99a2b1;--good:#3ecf8e;--bad:#ef6b6b;--warn:#e7b44c;--acc:#6ea8fe}
:root.light{--bg:#f5f6f8;--card:#fff;--card2:#f3f5f8;--line:#e2e5ea;--text:#151821;--mute:#5d6676;--good:#13804a;--bad:#c23b3b;--warn:#946300;--acc:#2457c5}
*{box-sizing:border-box}html{background:var(--bg)}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
header{padding:16px 16px 6px;max-width:1000px;margin:auto;display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
h1{font-size:20px;margin:0}.sub{color:var(--mute);font-size:13px}h3{margin:18px 0 6px;font-size:16px}
.theme{background:var(--card);border:1px solid var(--line);color:var(--text);border-radius:8px;padding:6px 10px;cursor:pointer}
nav{display:flex;gap:6px;overflow-x:auto;padding:8px 16px;max-width:1000px;margin:auto;position:sticky;top:0;background:var(--bg);z-index:3;scrollbar-width:none}
nav button,.pill{background:var(--card);color:var(--text);border:1px solid var(--line);border-radius:999px;padding:7px 13px;font-size:14px;white-space:nowrap;cursor:pointer}
nav button.on,.pill.on{background:var(--acc);border-color:var(--acc);color:#fff}
main{max-width:1000px;margin:auto;padding:6px 16px 48px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:10px 0}
.click{cursor:pointer}.click:hover{border-color:var(--acc)}
.row{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:flex-start}.tag{font-size:12px;font-weight:600;border-radius:6px;padding:2px 8px;border:1px solid var(--line);white-space:nowrap}
.CASH{color:#fff;background:var(--good);border-color:var(--good)}.PAPER{color:var(--acc);border-color:var(--acc)}.WATCH{color:var(--warn);border-color:var(--warn)}.PASS{color:var(--mute)}.PULL{color:#fff;background:var(--bad);border-color:var(--bad)}
.big{font-size:17px;font-weight:600}.mute{color:var(--mute);font-size:13px}.flag{color:var(--warn);font-size:13px}.ag{color:var(--bad);font-size:13px}.pro{color:var(--good);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:7px 6px;border-bottom:1px solid var(--line);text-align:left;font-variant-numeric:tabular-nums;vertical-align:top}th{color:var(--mute);font-weight:500;font-size:12px}td.n{white-space:nowrap}
.W,.Won{color:var(--good)}.L,.Lost{color:var(--bad)}.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:10px 0}.kpi div{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}.kpi b{display:block;font-size:20px;font-variant-numeric:tabular-nums}
details summary{cursor:pointer;color:var(--acc);font-size:14px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px}@media(max-width:600px){.grid2{grid-template-columns:1fr}}
.bar{height:8px;background:var(--card2);border-radius:4px;overflow:hidden}.bar i{display:block;height:100%;background:var(--acc)}
.sel{display:flex;gap:6px;overflow-x:auto;margin:8px 0}.box{background:var(--card2);border-radius:8px;padding:10px}
</style></head><body>
<header><div><h1>The Board</h1><div class="sub" id="upd"></div></div><button class="theme" id="theme" aria-label="Toggle light and dark">Light/Dark</button></header>
<nav id="nav"></nav><main id="main"></main>
<script>
const D = __DATA__;
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const pct = x => x == null ? "-" : (x*100).toFixed(1) + "%";
const rec = o => o && o.n ? `${o.w}-${o.l} (${pct(o.win ?? o.w/(o.w+o.l))})` : "-";
const sgn = x => x == null ? "-" : (x > 0 ? "+" : "") + x;
const short = t => String(t||"").split(" ").slice(-1)[0];
document.getElementById("upd").textContent = `Updated ${D.updated}. Runs by itself every hour, 7 AM to midnight CT.`;
const root = document.documentElement; if (localStorage.theme === "light") root.classList.add("light");
document.getElementById("theme").onclick = () => { root.classList.toggle("light"); localStorage.theme = root.classList.contains("light") ? "light" : "dark"; };
const ALL = D.cards.flatMap(c => c.games);
const TABS = {Today: today, Board: board, Card: cardTab, Confidence: confTab, Record: record, Lab: lab, Rules: rules, Reviews: reviews, Requests: requests, Streaks: streaks};
let cur = location.hash.slice(1) || "Today", sport = (D.cards.slice().sort((a,b) => b.games.filter(r=>r.decision!=="PASS").length - a.games.filter(r=>r.decision!=="PASS").length)[0] || {}).sport || "NFL", gameId = null, recFilter = "cash";
const nav = document.getElementById("nav");
Object.keys(TABS).forEach(t => { const b = document.createElement("button"); b.textContent = t; b.onclick = () => { cur = t; gameId = null; location.hash = t; draw(); }; nav.appendChild(b); });
function draw(){ [...nav.children].forEach(b => b.classList.toggle("on", b.textContent === cur)); document.getElementById("main").innerHTML = (TABS[cur] || today)(); bind(); }
function bind(){
  document.querySelectorAll("[data-game]").forEach(e => e.onclick = () => { const r = ALL.find(x => x.id === e.dataset.game); sport = r.sport; gameId = r.id; cur = "Card"; location.hash = "Card"; draw(); window.scrollTo(0,0); });
  document.querySelectorAll("[data-sport]").forEach(e => e.onclick = () => { sport = e.dataset.sport; gameId = null; draw(); });
  document.querySelectorAll("[data-rf]").forEach(e => e.onclick = () => { recFilter = e.dataset.rf; draw(); });
  const bk = document.getElementById("bk"); if (bk) bk.onclick = () => { gameId = null; draw(); };
}
function tag(r){ const pulled = (D.pulls||{})[r.id]; return `<span class="tag ${pulled ? "PULL" : r.decision}">${pulled ? "PULL" : r.decision}${r.stake ? " $" + r.stake : ""}</span>${r.conf ? ` <span class="tag">${r.conf}</span>` : ""}`; }
function plain(r){
  if (!r.pick) return r.reason || "No call.";
  if (r.sport === "NHL") return `Both models give ${esc(r.side === "home" ? r.home : r.away)} a better win chance (${pct(r.side==="home"?r.win_prob?.[1]:r.win_prob?.[0])}) than the price says (${pct(r.side==="home"?r.market_prob?.[1]:r.market_prob?.[0])}).`;
  const fav = m => m == null ? "?" : (m >= 0 ? `${short(r.home)} by ${m.toFixed(1)}` : `${short(r.away)} by ${(-m).toFixed(1)}`);
  return `Line ${esc(r.line)}. ${r.model_a_name} has ${fav(r.model_a)}, ${r.model_b_name} has ${fav(r.model_b)}.`;
}
function pickCard(r){
  return `<div class="card click" data-game="${r.id}"><div class="row"><div><div class="big">${esc(r.pick || r.game)}</div><div class="mute">${r.sport} - ${esc(r.game)} - ${esc(r.time)}</div></div><div>${tag(r)}</div></div>
  <p style="margin:8px 0">${esc(plain(r))} ${esc(r.reason)}</p>${(r.flags||[]).slice(0,3).map(f => `<div class="flag">${esc(f)}</div>`).join("")}<div class="mute" style="margin-top:6px">Tap for the full workup</div></div>`;
}
function today(){
  const cash = ALL.filter(r => r.decision === "CASH"), paper = ALL.filter(r => r.decision === "PAPER");
  const B = D.bank; let h = `<div class="kpi"><div><span class="mute">Bankroll</span><b>$${B.now.toFixed(2)}</b><span class="mute">goal $${B.goal.toLocaleString()}</span></div>
  <div><span class="mute">Today's cash</span><b>${cash.length ? "$" + cash.reduce((a,r)=>a+r.stake,0) : "Pass"}</b><span class="mute">${cash.length} single(s), ${D.parlays.filter(p=>p.decision==="CASH").length} parlay(s)</span></div>
  <div><span class="mute">Paper picks today</span><b>${paper.length}</b><span class="mute">tracked, $0</span></div>
  <div><span class="mute">System check</span><b class="${D.health.ok ? "W" : "L"}">${D.health.ok ? "All good" : "Needs a look"}</b><span class="mute">${esc(D.health.time)}</span></div></div>`;
  const goal = Math.min(1, B.now / B.goal); h += `<div class="bar"><i style="width:${(goal*100).toFixed(1)}%"></i></div><div class="mute">${pct(goal)} of the way to $${B.goal.toLocaleString()}</div>`;
  h += `<div class="card"><div class="big">${cash.length ? "Cash card" : "Pass on cash today"}</div><div class="mute">${esc(D.why_pass)}</div></div>`;
  cash.forEach(r => h += pickCard(r));
  const pl = Object.keys(D.pulls||{}); if (pl.length) h += `<h3>Pull alerts</h3>` + pl.map(id => `<div class="card"><span class="tag PULL">PULL</span> ${esc(D.pulls[id])}</div>`).join("");
  if (D.parlays.length) h += `<h3>Parlays</h3>` + D.parlays.map(p => `<div class="card"><div class="row"><div class="big">${esc(p.name)}: ${p.picks.map(esc).join(" + ")}</div><span class="tag ${p.decision}">${p.decision}${p.stake ? " $"+p.stake : ""} ${esc(p.price)}</span></div><div class="mute">${esc(p.why)}</div></div>`).join("");
  h += `<h3>Top paper picks</h3>`; paper.sort((a,b)=>b.conf-a.conf).slice(0,5).forEach(r => h += pickCard(r));
  h += `<h3>By sport</h3><div class="card"><table><tr><th>Sport</th><th>Games</th><th>Cash</th><th>Paper</th><th>Watch</th></tr>${D.cards.map(c => `<tr class="click" data-sport="${c.sport}"><td>${c.sport}</td><td>${c.games.length}</td><td>${c.games.filter(r=>r.decision==="CASH").length}</td><td>${c.games.filter(r=>r.decision==="PAPER").length}</td><td>${c.games.filter(r=>r.decision==="WATCH").length}</td></tr>`).join("")}</table></div>`;
  return h;
}
function board(){
  const rows = ALL.filter(r => r.decision !== "PASS").sort((a,b) => ({CASH:0,PAPER:1,WATCH:2}[a.decision] - {CASH:0,PAPER:1,WATCH:2}[b.decision]) || b.conf - a.conf);
  return `<div class="card mute">Every call across all sports, best first. Fair line = where the two models put it. Playable = worst number still worth taking.</div><div class="card"><table><tr><th>Pick</th><th>Call</th><th>Fair / play to</th></tr>${rows.map(r => `<tr class="click" data-game="${r.id}"><td>${esc(r.pick)}<div class="mute">${r.sport} - ${esc(r.time)} - test ${r.test_record ? pct(r.test_record.win ?? r.test_record.w/(r.test_record.w+r.test_record.l)) : "-"}</div></td><td class="n">${tag(r)}</td><td class="n">${r.fair_line != null ? sgn(r.fair_line) : "-"}<div class="mute">${r.playable_to != null ? sgn(r.playable_to) : "-"}</div></td></tr>`).join("")}</table></div>`;
}
function cardTab(){
  let h = `<div class="sel">${D.cards.map(c => `<button class="pill ${c.sport===sport?"on":""}" data-sport="${c.sport}">${c.sport} (${c.games.length})</button>`).join("")}</div>`;
  const c = D.cards.find(x => x.sport === sport) || {games: []};
  if (gameId){ const r = ALL.find(x => x.id === gameId); if (r) return h + detail(r); }
  h += `<div class="card mute">${esc(c.model_note || c.note || "")}</div>`;
  if (!c.games.length) return h + `<div class="card">${esc(c.note || "No games today.")}</div>`;
  const live = c.games.filter(r => r.decision !== "PASS"), pass = c.games.filter(r => r.decision === "PASS");
  live.forEach(r => h += pickCard(r));
  if (pass.length) h += `<div class="card"><b>Passed (${pass.length})</b><table>${pass.map(r => `<tr class="click" data-game="${r.id}"><td>${esc(r.game)}<div class="mute">${esc(r.time)} - ${esc(r.line || "no line")}</div></td><td class="mute">${esc(r.reason)}</td></tr>`).join("")}</table></div>`;
  return h;
}
function detail(r){
  const comp = r.components || {}; const W = {efficiency:2,veto:1.5,models:1.5,starters:1.5,coaching:1,against:1,price:1,situational:0.5};
  const inj = (list, team) => (list||[]).map(x => `${esc(x.player)}${x.pos ? " ("+esc(x.pos)+")" : ""} - ${esc(x.status)}`).join("<br>") || "Nothing listed";
  let h = `<button class="pill" id="bk">Back to ${r.sport} card</button><div class="card"><div class="row"><div><div class="big">${esc(r.pick || r.game)}</div><div class="mute">${esc(r.game)} - ${esc(r.time)}${r.tv ? " - " + esc(r.tv) : ""}${r.venue ? " - " + esc(r.venue) : ""}</div></div><div>${tag(r)}</div></div>
  <p><b>In plain words:</b> ${esc(plain(r))} ${esc(r.reason)}</p>
  <div class="grid2"><div class="box"><b>The numbers</b><table>
  <tr><td>Line now (${esc(r.book || "DK")})</td><td class="n">${esc(r.line || "-")}${r.price ? " (" + sgn(r.price) + ")" : ""}</td></tr>
  <tr><td>Opened</td><td class="n">${r.home_line_open != null ? short(r.home) + " " + sgn(r.home_line_open) : "-"}</td></tr>
  <tr><td>${esc(r.model_a_name)}</td><td class="n">${r.model_a != null ? short(r.home) + " " + sgn(-r.model_a) : "-"}${r.gap_a != null ? " (gap " + sgn(r.gap_a) + ")" : ""}</td></tr>
  <tr><td>${esc(r.model_b_name)}</td><td class="n">${r.model_b != null ? short(r.home) + " " + sgn(-r.model_b) : "-"}${r.gap_b != null ? " (gap " + sgn(r.gap_b) + ")" : ""}</td></tr>
  <tr><td>Fair line</td><td class="n">${r.fair_line != null ? sgn(r.fair_line) : "-"}</td></tr>
  <tr><td>Playable to</td><td class="n">${r.playable_to != null ? sgn(r.playable_to) : "-"}</td></tr>
  <tr><td>Sim cover chance</td><td class="n">${r.sim_cover != null ? pct(r.sim_cover) : (r.win_prob ? pct(r.side==="home"?r.win_prob[1]:r.win_prob[0]) + " win" : "-")}</td></tr>
  <tr><td>Total</td><td class="n">${r.total ?? "-"}${r.total_model ? " (season scoring " + r.total_model + ")" : ""}</td></tr>
  <tr><td>Records</td><td class="n">${esc(short(r.away))} ${esc(r.records?.[0] || "-")}, ${esc(short(r.home))} ${esc(r.records?.[1] || "-")}</td></tr>
  <tr><td>Past-games test</td><td class="n">${rec(r.test_record)}</td></tr></table>
  <div class="mute">Gap = how far a model is from the line. The bar is ${D.bars[r.sport]} ${r.sport==="NHL"?"win-chance points":"points"}. Sim cover chance comes from the models, and the past-games test showed those run hot - trust the test record more.</div></div>
  <div class="box"><b>Confidence ${r.conf ?? "-"}</b>${Object.keys(W).map(k => `<div class="row mute" style="margin-top:4px"><span>${k}</span><span>${comp[k] ?? "-"} / ${W[k]}</span></div><div class="bar"><i style="width:${((comp[k]||0)/W[k]*100).toFixed(0)}%"></i></div>`).join("")}</div></div>
  ${r.total_lean ? `<p class="flag">${esc(r.total_lean)}</p>` : ""}
  <h3>Why it could work</h3>${(r.factors||[]).map(f => `<div class="pro">${esc(f)}</div>`).join("") || '<div class="mute">-</div>'}
  <h3>What's against it</h3>${(r.against||[]).map(f => `<div class="ag">${esc(f)}</div>`).join("") || '<div class="mute">Nothing flagged</div>'}
  <h3>Flags</h3>${(r.flags||[]).map(f => `<div class="flag">${esc(f)}</div>`).join("") || '<div class="mute">None</div>'}
  <h3>Pull it if</h3>${(r.invalidation||[]).map(f => `<div>${esc(f)}</div>`).join("") || '<div class="mute">-</div>'}
  ${r.sport==="NHL" ? `<h3>Goalies</h3><div>${esc(short(r.away))}: ${esc(r.goalies?.[0] || "not posted")}<br>${esc(short(r.home))}: ${esc(r.goalies?.[1] || "not posted")}</div>` : ""}
  ${r.wind ? `<h3>Weather at kickoff</h3><div>Wind ${r.wind.wind} mph (gusts ${r.wind.gust}), ${r.wind.temp}F, rain ${r.wind.rain}% <span class="mute">(${esc(r.wind.src)})</span></div>` : ""}
  <h3>Injuries</h3><div class="grid2"><div class="box"><b>${esc(r.away)}</b><div class="mute">${inj(r.inj_away)}</div></div><div class="box"><b>${esc(r.home)}</b><div class="mute">${inj(r.inj_home)}</div></div></div>
  <h3>Rest</h3><div class="mute">${esc(short(r.away))}: ${r.rest?.[0] ?? "-"} day(s), ${esc(short(r.home))}: ${r.rest?.[1] ?? "-"} day(s)</div>
  ${(D.review_log[r.id]||[]).length ? `<h3>Review log</h3>${D.review_log[r.id].map(x => `<div class="mute">${esc(x)}</div>`).join("")}` : ""}</div>`;
  return h;
}
function confTab(){
  const W = [["efficiency",2,"How far both models are past the bar"],["veto",1.5,"No veto (QB/star doubt, models 10+ apart); 7+ from market costs 0.5"],["models",1.5,"Both models agree (1.5) or only one (0.5)"],["starters",1.5,"Drops for each QB / star / goalie flag"],["coaching",1,"Not measured automatically - held near neutral"],["against",1,"Drops for each factor against the pick (line move, key number, rest)"],["price",1,"Past-games test record for this kind of pick"],["situational",0.5,"Back-to-backs and schedule spots"]];
  let h = `<div class="card"><b>The scorecard (max 10)</b><table><tr><th>Part</th><th>Max</th><th>What fills it</th></tr>${W.map(w => `<tr><td>${w[0]}</td><td>${w[1]}</td><td class="mute">${w[2]}</td></tr>`).join("")}</table><p class="mute">8.0+ = $50 single. 7.0-7.9 = $25 single. 5.5-6.9 = parlay leg or paper. Under 5.5 = pass. Confidence alone never makes a pick cash - the past-games test and your approval do.</p></div>`;
  h += `<div class="card"><b>Is confidence telling the truth?</b><div class="mute">Every graded pick, by confidence band. Higher bands should win more. If they don't, the scorecard needs fixing.</div><table><tr><th>Band</th><th>Record</th><th>Win %</th><th>Beat close</th></tr>${D.tiers.map(t => `<tr><td>${t.band}</td><td>${t.w}-${t.l}</td><td>${t.win == null ? "-" : pct(t.win)}</td><td>${t.clv_n ? t.clv_beat + "/" + t.clv_n : "-"}</td></tr>`).join("")}</table></div>`;
  return h;
}
function record(){
  const S = D.summary; let h = `<div class="kpi">`;
  const keys = Object.keys(S).filter(k => k.startsWith("All")).concat(Object.keys(S).filter(k => !k.startsWith("All")));
  if (!keys.length) h += `<div><span class="mute">Nothing graded yet</span><b>0-0</b><span class="mute">picks grade themselves after each game</span></div>`;
  for (const k of keys){ const s = S[k]; h += `<div><span class="mute">${esc(k)}</span><b>${s.w}-${s.l}${s.p ? "-" + s.p : ""}</b><span class="mute">${sgn(s.units)}u${s.pl ? ` / $${s.pl}` : ""}${s.clv_n ? ` - beat close ${s.clv_beat}/${s.clv_n}` : ""}</span></div>`; }
  h += `</div><div class="sel">${[["cash","Placed (cash)"],["paper","Paper"],["all","All tracked"]].map(([k,l]) => `<button class="pill ${recFilter===k?"on":""}" data-rf="${k}">${l}</button>`).join("")}</div>`;
  const list = D.picks.filter(p => recFilter === "all" || (recFilter === "cash" ? p.decision === "CASH" : p.decision === "PAPER")).slice().reverse().slice(0, 400);
  h += `<div class="card"><table><tr><th>Date</th><th>Pick</th><th>Result</th><th>vs close</th></tr>${list.map(p => `<tr><td class="n">${esc(p.date.slice(5))}</td><td>${esc(p.pick)}<div class="mute">${p.sport} ${esc(p.decision)}${p.stake ? " $" + p.stake : ""}${p.conf ? " - " + p.conf : ""}${p.review === "PULL" ? " - PULLED" : ""}${p.skipped ? " - not placed" : ""}</div></td><td class="${esc(p.result||"")}">${esc(p.result || "Pending")}<div class="mute">${esc(p.final || "")}</div></td><td class="n">${p.clv != null ? sgn(p.clv) : "-"}<div class="mute">${esc(p.close || "")}</div></td></tr>`).join("") || '<tr><td colspan="4" class="mute">None yet</td></tr>'}</table></div>`;
  h += `<div class="card"><b>Parlays</b><table>${D.all_parlays.slice().reverse().map(p => `<tr><td class="n">${esc(p.date.slice(5))}</td><td>${p.picks.map(esc).join(" + ")}<div class="mute">${p.decision} ${esc(p.price)}</div></td><td class="${esc(p.result||"")}">${esc(p.result || "Pending")}</td></tr>`).join("") || '<tr><td class="mute">None yet</td></tr>'}</table></div>`;
  return h;
}
function lab(){
  let h = `<div class="card"><b>Path to cash</b><div class="mute">A sport only gets cash picks when its kind of pick passes a test AND you approve it. You approve by commenting "approve NBA" (etc.) on any issue in the GitHub repo.</div><table><tr><th>Sport</th><th>Status</th><th>Evidence</th></tr>${D.grad.map(g => `<tr><td>${g.sport}</td><td><span class="tag ${g.status==="Paper"?"PAPER":g.status.startsWith("Ready")?"WATCH":"CASH"}">${esc(g.status)}</span></td><td class="mute">${esc(g.evidence)}</td></tr>`).join("")}</table><div class="mute">Needs: ${esc(D.grad[0]?.need || "")}</div></div>`;
  const B = D.bt, L = D.btl;
  h += `<div class="card"><b>Past-games test: what we found</b><p>Break-even at -110 is 52.4%. Replayed using only what was known before each game.</p><table><tr><th>Test</th><th>Record</th></tr>
  ${Object.entries(B.CFB||{}).map(([k,v]) => `<tr><td>College football, both models agree - ${esc(k)}</td><td class="n">${rec(v)}</td></tr>`).join("")}
  ${Object.entries(B.NFL||{}).map(([k,v]) => `<tr><td>NFL, both models agree - ${esc(k)}</td><td class="n">${rec(v)}</td></tr>`).join("")}
  ${["NBA","CBB"].map(s => L[s] ? `<tr><td>${s} last season, both agree vs closing line</td><td class="n">${rec(L[s].both_agree)}</td></tr><tr><td>${s} both agree vs OPENING line</td><td class="n">${rec(L[s]["vs opening line"])} - beat close ${L[s]["vs opening line"].beat_close}-${L[s]["vs opening line"].lost_close}</td></tr>` : "").join("")}
  ${L.NHL ? `<tr><td>NHL last season, both agree (moneyline)</td><td class="n">${rec(L.NHL.both_agree)}, ${sgn(L.NHL.both_agree.units)}u</td></tr><tr><td>NHL both agree vs OPENING price</td><td class="n">${L.NHL["vs opening line"].w}-${L.NHL["vs opening line"].l}, ${sgn(L.NHL["vs opening line"].units)}u - beat close ${L.NHL["vs opening line"].beat_close}-${L.NHL["vs opening line"].lost_close}</td></tr>` : ""}
  </table></div>`;
  for (const s of ["NBA","CBB"]) if (L[s]) h += `<div class="card"><b>${s} - does a bigger gap win more?</b><table>${Object.entries(L[s]).filter(([k]) => k.startsWith("ratings gap")).map(([k,v]) => `<tr><td>${esc(k.replace("ratings gap","gap"))}</td><td class="n">${rec(v)}</td></tr>`).join("")}<tr><td>Home underdogs</td><td class="n">${rec(L[s]["home dogs"])}</td></tr><tr><td>Fade both models</td><td class="n">${rec(L[s]["fade both models"])}</td></tr></table></div>`;
  h += `<div class="card"><b>What it means</b>${D.lab_notes.map(n => `<p>${esc(n)}</p>`).join("")}</div>`;
  return h;
}
function rules(){ return `<div class="card">${D.rules.map(r => `<p>${esc(r)}</p>`).join("")}</div><div class="card"><b>Bars by sport</b><table>${Object.entries(D.bars).map(([k,v]) => `<tr><td>${k}</td><td>${v} ${k==="NHL"?"win-chance points":"points"}</td></tr>`).join("")}</table></div>`; }
function reviews(){
  let h = `<div class="card"><div class="row"><b>System check</b><span class="tag ${D.health.ok?"CASH":"PULL"}">${D.health.ok?"All good":"Problem"}</span></div><div class="mute">${esc(D.health.time)}</div>${D.health.problems.map(p => `<div class="ag">${esc(p)}</div>`).join("")}${D.health.notes.map(p => `<div class="mute">${esc(p)}</div>`).join("")}</div>`;
  h += `<div class="card"><b>Pre-game checks</b><div class="mute">Every run re-checks each open pick's line and injury report. It can only say PULL or hold - never add a bet.</div>${Object.entries(D.review_log).filter(([,v]) => v.length).slice(-30).map(([id,v]) => { const p = D.picks.find(x => x.id === id); return `<div style="margin-top:6px"><b>${esc(p?.pick)}</b>${v.slice(-3).map(x => `<div class="mute">${esc(x)}</div>`).join("")}</div>`; }).join("") || '<div class="mute">No open picks.</div>'}</div>`;
  h += D.reviews.slice().reverse().map(r => `<div class="card"><b>${esc(r.title)}</b>${r.lines.map(l => `<div>${esc(l)}</div>`).join("")}</div>`).join("") || `<div class="card mute">The weekly report posts every Tuesday morning and emails you.</div>`;
  return h;
}
function requests(){
  return `<div class="card"><b>Change things from your phone</b><p>Open the <a href="https://github.com/jjuliancastroc-beep/board-auto/issues" style="color:var(--acc)">Issues page</a> on GitHub and comment on any issue (or open a new one). Only your account's comments count. The Board answers in a minute.</p>
  <table>${D.commands.map(c => `<tr><td class="n"><b>${esc(c[0])}</b></td><td class="mute">${esc(c[1])}</td></tr>`).join("")}</table></div>
  <div class="card"><b>Recent requests</b>${D.requests.slice().reverse().map(r => `<div style="margin-top:6px"><span class="mute">${esc(r.date)}</span> ${esc(r.text)}<div class="pro">${r.result.map(esc).join(" ")}</div></div>`).join("") || '<div class="mute">None yet.</div>'}</div>`;
}
function streaks(){ return `<div class="card"><b>Props and streaks</b><p>Not automated yet. ESPN's free feed has no player-prop lines, so props stay a separate section you ask me about. To automate them, the Board needs a prop odds feed (The Odds API has a free key, but props cost extra per game).</p></div>`; }
draw();
</script></body></html>"""

COMMANDS = [["bankroll 650", "Set the bankroll. Cash tickets add to it from today."], ["skip Raptors", "You didn't place that cash ticket - stops counting it."],
            ["approve NBA", "Let a sport have cash picks (only once its test passes). Your graduation call."], ["unapprove NBA", "Back to paper."],
            ["goal 10000", "Change the goal."], ["help", "List commands."]]

LAB_NOTES = [
    "Against the closing line, none of the simple team models beat the market in any sport. The market's average miss is smaller than ours everywhere.",
    "Against the OPENING line it looks different: when both models agreed with the open, the line usually moved our way by game time (NBA 41-28, NHL 203-105, college basketball 156-149). College basketball covered 54.6% against the open over 399 games. That is one season - promising, not proven.",
    "What that means: the models may be early, not wrong. The money is in getting the number before the market moves. The Board grades every pick on the first number it logs and tracks the close, so in a few weeks we'll know if it gets the good numbers live.",
    "Next to add: an evening run that grabs next-day college basketball openers, a totals model test, and NHL goalie quality.",
]


def render(cards, picks, pars, bt, btl, st, hl):
    now = now_ct(); date = now.strftime("%Y-%m-%d")
    pulls = {p["id"]: f"{p['pick']}: {p['review_log'][-1]}" for p in picks if p.get("review") == "PULL" and p["result"] is None}
    cash = [r for c in cards for r in c["games"] if r["decision"] == "CASH"]
    why = ("Cash picks below." if cash else
           "No pick passed every gate: both models agree, confidence 7.0+, the past-games test, and your approval for that sport. Paper picks are still graded so the record builds.")
    data = {"updated": now.strftime("%a %b %-d, %-I:%M %p CT"), "cards": cards, "picks": picks[-1500:], "parlays": [x for x in pars if x["date"] == date], "all_parlays": pars[-200:],
            "summary": grade.summary(picks), "tiers": grade.tiers(picks), "bt": bt, "btl": btl, "grad": review.graduation(picks, bt, btl, st),
            "bank": {"now": grade.bankroll(picks, st), "goal": st.get("goal", 10000)}, "health": hl, "pulls": pulls, "why_pass": why,
            "review_log": {p["id"]: p.get("review_log", []) for p in picks if p["result"] is None},
            "reviews": load("reviews.json", []), "requests": load("requests_log.json", []), "commands": COMMANDS, "lab_notes": LAB_NOTES,
            "bars": {k: v["bar"] for k, v in SPORTS.items()}, "rules": load("rules.json", [])}
    out = PAGE.replace("__DATA__", json.dumps(data, default=float).replace("</", "<\\/"))
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    with open(os.path.join(ROOT, "docs", "index.html"), "w") as f:
        f.write(out)
    open(os.path.join(ROOT, "docs", ".nojekyll"), "w").close()
