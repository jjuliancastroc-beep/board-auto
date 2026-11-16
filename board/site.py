"""Render docs/index.html - one self-contained page (data inlined), rebuilt on every run.
Tabs match the original Board: Today, Board, Card, Confidence, Record, Lab, Rules, Reviews, Requests, Props."""
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
const money = v => v == null ? "-" : (v < 0 ? "-$" : "+$") + Math.abs(v).toFixed(2);
const cmdUrl = t => `https://github.com/${D.repo}/issues/new?title=${encodeURIComponent(t)}`;
const cmd = (t, label, cls) => `<a class="pill ${cls||""}" style="text-decoration:none;display:inline-block;margin:6px 6px 0 0" target="_blank" rel="noopener" onclick="event.stopPropagation()" href="${cmdUrl(t)}">${label}</a>`;
(function(){
  const age = Math.round((Date.now()/1000 - D.ts) / 60), hr = new Date().getHours();
  const late = age > 75 && hr >= 7;
  document.getElementById("upd").innerHTML = `Updated ${esc(D.updated)}. Rebuilds by itself about every 30 minutes, 7 AM to 3 AM CT.` +
    (late ? `<div class="flag" style="margin-top:6px">This page is ${age >= 120 ? Math.round(age/60) + " hours" : age + " minutes"} old - the Board's clock stalled. A refresh restarts it. ${cmd("refresh", "Refresh now")}<span class="mute">(opens GitHub - just hit Submit)</span></div>` : "");
})();
const root = document.documentElement; if (localStorage.theme === "light") root.classList.add("light");
document.getElementById("theme").onclick = () => { root.classList.toggle("light"); localStorage.theme = root.classList.contains("light") ? "light" : "dark"; };
const ALL = D.cards.flatMap(c => c.games);
const TABS = {Today: today, Board: board, Card: cardTab, Confidence: confTab, Record: record, Lab: lab, Rules: rules, Reviews: reviews, Requests: requests, Props: propsTab};
let cur = location.hash.slice(1) || "Today", sport = (D.cards.slice().sort((a,b) => b.games.filter(r=>r.decision!=="PASS").length - a.games.filter(r=>r.decision!=="PASS").length)[0] || {}).sport || "NFL", gameId = null, recFilter = "cash";
const nav = document.getElementById("nav");
Object.keys(TABS).forEach(t => { const b = document.createElement("button"); b.textContent = t; b.onclick = () => { cur = t; gameId = null; location.hash = t; draw(); }; nav.appendChild(b); });
function draw(){ [...nav.children].forEach(b => b.classList.toggle("on", b.textContent === cur)); document.getElementById("main").innerHTML = (TABS[cur] || today)(); bind(); }
function bind(){
  document.querySelectorAll("[data-game]").forEach(e => e.onclick = () => { const r = ALL.find(x => x.id === e.dataset.game); sport = r.sport; gameId = r.id; cur = "Card"; location.hash = "Card"; draw(); window.scrollTo(0,0); });
  document.querySelectorAll("[data-sport]").forEach(e => e.onclick = () => { sport = e.dataset.sport; gameId = null; draw(); });
  document.querySelectorAll("[data-rf]").forEach(e => e.onclick = () => { recFilter = e.dataset.rf; draw(); });
  const bk = document.getElementById("bk"); if (bk) bk.onclick = () => { gameId = null; draw(); };
  const gp = document.getElementById("goprops"); if (gp) gp.onclick = () => { cur = "Props"; location.hash = "Props"; draw(); };
  document.querySelectorAll("[data-prop]").forEach(e => e.onclick = () => { propId = e.dataset.prop; draw(); window.scrollTo(0,0); });
  document.querySelectorAll("[data-pday]").forEach(e => e.onclick = () => { pday = e.dataset.pday; draw(); });
  document.querySelectorAll("[data-psport]").forEach(e => e.onclick = () => { psport = e.dataset.psport; draw(); });
  const pb = document.getElementById("pbk"); if (pb) pb.onclick = () => { propId = null; draw(); };
  const q = document.getElementById("pq"); if (q) q.oninput = () => { pq = q.value; document.getElementById("plines").innerHTML = lineRows(); };
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
  <p style="margin:8px 0">${esc(plain(r))} ${esc(r.reason)}</p>${(r.flags||[]).slice(0,3).map(f => `<div class="flag">${esc(f)}</div>`).join("")}${r.decision === "CASH" ? `<div class="mute" style="margin-top:6px">${(D.skipped||{})[r.id] ? "You skipped this one - not counted." : "Counted as placed at $" + r.stake + "."} ${(D.skipped||{})[r.id] ? cmd("placed " + r.pick, "I did place it") : cmd("skip " + r.pick, "I didn't place it")}</div>` : ""}<div class="mute" style="margin-top:6px">Tap for the full workup</div></div>`;
}
function today(){
  const cash = ALL.filter(r => r.decision === "CASH"), paper = ALL.filter(r => r.decision === "PAPER");
  const B = D.bank; let h = `<div class="kpi"><div><span class="mute">Bankroll</span><b>$${B.now.toFixed(2)}</b><span class="mute">goal $${B.goal.toLocaleString()}</span></div>
  <div><span class="mute">Today's mains</span><b>${cash.length ? "$" + cash.reduce((a,r)=>a+r.stake,0) : "Pass"}</b><span class="mute">${cash.length} single(s), ${D.parlays.filter(p=>p.decision==="CASH").length} parlay(s)</span></div>
  <div><span class="mute">Paper picks today</span><b>${paper.length}</b><span class="mute">tracked, $0</span></div>
  <div><span class="mute">System check</span><b class="${D.health.ok ? "W" : "L"}">${D.health.ok ? "All good" : "Needs a look"}</b><span class="mute">${esc(D.health.time)}</span></div></div>`;
  const goal = Math.min(1, B.now / B.goal); h += `<div class="bar"><i style="width:${(goal*100).toFixed(1)}%"></i></div><div class="mute">${pct(goal)} of the way to $${B.goal.toLocaleString()}</div>`;
  h += `<div class="card"><div class="big">${cash.length ? "Mains (" + cash.length + " of 3)" : "No mains today - pass"}</div><div class="mute">${cash.length ? "Counted as placed (Capped card) unless you comment 'skip' on one. $50 at 8.0+, $25 at 7.0-7.9." : esc(D.why_pass)}</div></div>`;
  cash.forEach(r => h += pickCard(r));
  (D.moved||[]).forEach(p => h += `<div class="card"><div class="row"><div class="big">${esc(p.pick)}</div><span class="tag CASH">CASH $${p.stake}</span></div><div class="mute">${esc(p.sport)} - ${esc(p.game)}</div><div class="flag">${esc(p.moved)}</div><p style="margin:8px 0">Still counted as placed at $${p.stake} and will be graded when it is played. ${p.book_ok ? "Your book kept the ticket open (you confirmed)." : "Check the ticket in your book - some books cancel bets when a game changes days."}</p>${p.book_ok ? "" : cmd("skip " + p.pick, "My book cancelled it")}</div>`);
  const pl = Object.keys(D.pulls||{}); if (pl.length) h += `<h3>Pull alerts</h3>` + pl.map(id => `<div class="card"><span class="tag PULL">PULL</span> ${esc(D.pulls[id])}</div>`).join("");
  if (D.parlays.length) h += `<h3>Parlays</h3>` + D.parlays.map(p => `<div class="card"><div class="row"><div class="big">${esc(p.name)}: ${p.picks.map(esc).join(" + ")}</div><span class="tag ${p.decision}">${p.decision}${p.stake ? " $"+p.stake : ""} ${esc(p.price)}</span></div><div class="mute">${esc(p.why)}</div></div>`).join("");
  const P = D.props || {}; const pt = (P.calls||[]).filter(x => x.date === P.today);
  const PCt = P.card || {singles: [], parlays: []};
  h += `<div class="card click" id="goprops"><div class="row"><b>Props card</b><span class="tag">separate</span></div>${PCt.singles.map(x => `<div>${x.status==="PULL" ? '<span class="tag PULL">PULL</span> ' : ""}${esc(x.pick)} <span class="mute">$15</span></div>`).join("")}${PCt.parlays.map(e => `<div>${e.status==="PULL" ? '<span class="tag PULL">PULL</span> ' : ""}${e.legs.map(x=>esc(x.pick)).join(" + ")} <span class="mute">parlay $15</span></div>`).join("")}<div class="mute">${PCt.singles.length} singles, ${PCt.parlays.length} parlays. ${pt.filter(x=>x.call==="PLAY").length} plays, ${pt.filter(x=>x.call==="LEAN").length} leans from ${P.n_lines||0} Underdog lines - tap for the Props tab.</div></div>`;
  const top = ALL.filter(r => r.pick && r.decision !== "PASS").sort((a,b) => ({CASH:0,PAPER:1,WATCH:2}[a.decision] - {CASH:0,PAPER:1,WATCH:2}[b.decision]) || (b.conf||0) - (a.conf||0)).slice(0,10);
  h += `<h3>Top 10</h3><div class="card"><div class="mute">Best calls across every sport. Mains are marked; the rest are paper (tracked, $0) or watch.</div><table><tr><th>#</th><th>Pick</th><th>Call</th></tr>${top.map((r,i) => `<tr class="click" data-game="${r.id}"><td>${i+1}</td><td>${esc(r.pick)}${r.decision==="CASH" ? ' <span class="tag CASH">MAIN</span>' : ""}<div class="mute">${r.sport} - ${esc(r.time)}${r.history && r.history.adj ? " - our record " + (r.history.adj>0?"+":"") + r.history.adj : ""}</div></td><td class="n">${tag(r)}</td></tr>`).join("") || '<tr><td colspan="3" class="mute">Nothing today.</td></tr>'}</table></div>`;
  h += `<h3>By sport</h3><div class="card"><table><tr><th>Sport</th><th>Games</th><th>Mains</th><th>Paper</th><th>Watch</th></tr>${D.cards.map(c => `<tr class="click" data-sport="${c.sport}"><td>${c.sport}</td><td>${c.games.length}</td><td>${c.games.filter(r=>r.decision==="CASH").length}</td><td>${c.games.filter(r=>r.decision==="PAPER").length}</td><td>${c.games.filter(r=>r.decision==="WATCH").length}</td></tr>`).join("")}</table></div>`;
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
  const comp = r.components || {}; const W = {efficiency:2,veto:1.5,models:1.5,starters:1.5,coaching:1,against:1,price:1,situational:0.5,"our history":0.5};
  const inj = (list, team) => (list||[]).map(x => `${esc(x.player)}${x.pos ? " ("+esc(x.pos)+")" : ""} - ${esc(x.status)}`).join("<br>") || "Nothing listed";
  let h = `<button class="pill" id="bk">Back to ${r.sport} card</button><div class="card"><div class="row"><div><div class="big">${esc(r.pick || r.game)}</div><div class="mute">${esc(r.game)} - ${esc(r.time)}${r.tv ? " - " + esc(r.tv) : ""}${r.venue ? " - " + esc(r.venue) : ""}</div></div><div>${tag(r)}</div></div>
  <p><b>In plain words:</b> ${esc(plain(r))} ${esc(r.reason)}</p>
  ${r.pick && r.decision !== "CASH" && r.decision !== "PASS" ? `<div class="mute">Not a main, so the Board counts it at $0.${(D.user_placed||{})[r.id] ? " You told the Board you placed it at $" + D.user_placed[r.id] + ". " + cmd("skip " + r.pick, "Undo") : " If you bet it anyway, tell the Board so the bankroll stays right: " + cmd("placed " + r.pick + " $25", "I placed this")}</div>` : ""}
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
  <div class="box"><b>Confidence ${r.conf ?? "-"}</b>${Object.keys(W).map(k => `<div class="row mute" style="margin-top:4px"><span>${k}</span><span>${comp[k] ?? "-"} / ${W[k]}</span></div><div class="bar"><i style="width:${Math.max(0,Math.min(100,(comp[k]||0)/W[k]*100)).toFixed(0)}%"></i></div>`).join("")}${r.history ? `<div class="mute" style="margin-top:6px">${esc(r.history.text)}</div>` : ""}</div></div>
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
  const W = [["efficiency",2,"How far both models are past the bar"],["veto",1.5,"No veto (QB/star doubt, models 10+ apart); 7+ from market costs 0.5"],["models",1.5,"Both models agree (1.5) or only one (0.5)"],["starters",1.5,"Drops for each QB / star / goalie flag"],["coaching",1,"Not measured automatically - held near neutral"],["against",1,"Drops for each factor against the pick (line move, key number, rest)"],["price",1,"Past-games test record for this kind of pick"],["situational",0.5,"Back-to-backs and schedule spots"],["our history","+/-0.5","Our own record on this kind of pick (old Board + this one), last 60 days, recent counts more, pulled toward break-even so a streak can't take over"]];
  let h = `<div class="card"><b>The scorecard (max 10)</b><table><tr><th>Part</th><th>Max</th><th>What fills it</th></tr>${W.map(w => `<tr><td>${w[0]}</td><td>${w[1]}</td><td class="mute">${w[2]}</td></tr>`).join("")}</table><p class="mute">8.0+ = $50 single. 7.0-7.9 = $25 single. 5.5-6.9 = parlay leg or paper. Under 5.5 = pass. A main needs both models agreeing, 7.0+, no veto, and an approved sport (football and NBA now; CBB/NHL paper until you approve them). Midweek or small-conference CFB needs 8.0+.</p></div>`;
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
  h += `<div class="card"><b>Parlays</b><table>${D.all_parlays.slice().reverse().map(p => `<tr><td class="n">${esc(p.date.slice(5))}</td><td>${p.picks.map(esc).join(" + ")}<div class="mute">${p.decision} ${esc(p.placed_price || p.price)}${p.skipped ? " - not placed, not counted" : p.user_placed ? " - you placed it at $" + p.stake : p.decision === "CASH" ? " - $" + p.stake : ""}${p.pl ? " - " + money(p.pl) : ""}</div>${p.note ? `<div class="mute">${esc(p.note)}</div>` : ""}</td><td class="${esc(p.result||"")}">${esc(p.result || "Pending")}</td></tr>`).join("") || '<tr><td class="mute">None yet</td></tr>'}</table></div>`;
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
let propId = null, pday = null, psport = "All", pq = "";
const hr = x => x && x[1] ? `${x[0]}/${x[1]}` : "-";
const hrc = x => x && x[1] ? (x[0]/x[1] >= 0.6 ? "W" : x[0]/x[1] < 0.45 ? "L" : "") : "";
function onCard(x){
  const P = D.props || {}, PC = (x.date === P.today ? P.card : null) || {singles: [], parlays: []};
  if (PC.singles.some(s => s.id === x.id)) return "single";
  if (PC.parlays.some(e => e.legs.some(l => l.id === x.id))) return "parlay";
  return null;
}
function pTag(x){
  const oc = onCard(x), today = x.date === (D.props||{}).today;
  const amt = oc ? `<div class="mute" style="text-align:right;margin-top:4px">On the card: $15 ${oc}</div>` : (x.call === "PLAY" && today ? `<div class="mute" style="text-align:right;margin-top:4px">Extra - no amount</div>` : "");
  return `<span class="tag ${x.call==="PLAY"?"CASH":x.call==="LEAN"?"PAPER":"PASS"}">${x.call}</span> <span class="tag">${x.conf ?? "-"}</span>${amt}`;
}
function propCard(x){
  return `<div class="card click" data-prop="${esc(x.id)}"><div class="row"><div><div class="big">${esc(x.pick)}</div><div class="mute">${esc(x.sport)} - ${esc(x.game)} - ${esc(x.time)}</div></div><div>${pTag(x)}</div></div>
  <div style="margin-top:6px">Projection <b>${x.proj}</b> vs line ${x.line}. Our chance <b>${pct(x.p)}</b>, Underdog ${pct(x.mkt)}${x.bk != null ? `, ${esc((x.bk_books||[]).join(" + "))} ${pct(x.bk)}` : ""}.</div>
  ${bookLine(x)}<div class="mute">Last 5 ${hr(x.hits.L5)} | last 10 ${hr(x.hits.L10)} | season ${hr(x.hits.season)} | last season ${hr(x.hits["last season"])} | vs opp ${hr(x.hits["vs opp"])}</div>
  ${x.flags.slice(0,2).map(f => `<div class="flag">${esc(f)}</div>`).join("")}</div>`;
}
function bookTxt(b){
  return b.over_x != null || b.under_x != null ? `${b.line} (Higher pays ${b.over_x ?? "-"}x, Lower ${b.under_x ?? "-"}x)` : `${b.line} (Over ${b.over > 0 ? "+" : ""}${b.over}, Under ${b.under > 0 ? "+" : ""}${b.under})`;
}
function bookLine(x){
  const b = x.books || [];
  return b.length ? `<div class="mute">Other books: ${b.map(v => esc(v.book) + " " + v.line + (v.line !== x.line ? " (different line)" : "")).join(" | ")}</div>` : "";
}
function lineRows(){
  const P = D.props; const q = pq.trim().toLowerCase();
  const rows = P.lines.filter(r => r[0] === pday && (psport === "All" || r[1] === psport) && (!q || (r[2] + " " + r[3]).toLowerCase().includes(q))).slice(0, 300);
  return rows.map(r => `<tr><td>${esc(r[2])}<div class="mute">${esc(r[3])} ${r[4]} - ${esc(r[10])}</div></td><td class="n">${r[5] ? esc(r[5]) : "-"}</td><td class="n">${pct(r[6])}<div class="mute">UD ${pct(r[7])}${r[11] != null ? " | books " + pct(r[11]) : ""}</div></td><td class="n">${r[8] ?? "-"}<div class="mute">${esc(r[9])}</div></td></tr>`).join("") || `<tr><td class="mute">No lines match.</td></tr>`;
}
function propDetail(x){
  const L = x.line, up = x.side === "higher";
  const comp = Object.entries(x.components || {}), MAX = {"data":2,"hit rates":1.5,"vs Underdog":1.5,"role":1,"availability":1,"matchup":1,"sample":1,"test record":1,"our history":0.5};
  let h = `<button class="pill" id="pbk">Back to props</button>
  <div class="card"><div class="row"><div><div class="big">${esc(x.pick)}</div><div class="mute">${esc(x.sport)} - ${esc(x.team)} - ${esc(x.game)} - ${esc(x.time)}</div></div><div>${pTag(x)}</div></div>
  <p>${esc(x.reason)}</p>
  ${onCard(x) ? `<div class="mute">On today's props card as a $15 ${onCard(x)}${onCard(x) === "parlay" ? " leg" : ""}. Mark it placed from the Props tab.</div>` : (x.call === "PLAY" || x.call === "LEAN" ? `<div class="mute">${x.call === "PLAY" ? "Extra play: it cleared the bar but the card was already full or it is from a game already on the card, so it has no amount." : "Lean: a parlay leg only, no amount."} ${(D.props.placed_ids||[]).includes(x.id) ? "You told the Board you placed it. " + cmd("skip " + x.pick, "Undo") : "If you put it in anyway: " + cmd("placed " + x.pick, "I placed this")}</div>` : "")}
  <div class="mute">Underdog price: Higher ${esc(x.price?.higher ?? "-")} (pays ${esc(x.mult?.higher ?? "1")}x), Lower ${esc(x.price?.lower ?? "-")} (pays ${esc(x.mult?.lower ?? "1")}x).</div></div>
  <div class="card"><b>The numbers</b><table>
  <tr><td>Our projection</td><td class="n">${x.proj} (line ${L})</td></tr>
  <tr><td>Our chance ${esc(x.side)}</td><td class="n">${pct(x.p)}</td></tr><tr><td>Underdog's chance (no-vig)</td><td class="n">${pct(x.mkt)}</td></tr>
  ${x.bk != null ? `<tr><td>${esc((x.bk_books||[]).join(" + "))} chance (no-vig, at Underdog's line)</td><td class="n">${pct(x.bk)}</td></tr>` : ""}<tr><td>Gap</td><td class="n">${sgn(x.edge)} pts</td></tr><tr><td>Playable to</td><td class="n">${x.playable_to ?? "-"}</td></tr>
  <tr><td>Model alone (before leaning on Underdog)</td><td class="n">${pct(up ? x.p_raw_higher : 1 - x.p_raw_higher)}</td></tr></table></div>
  <div class="card"><b>Other books on this prop</b>${(x.books||[]).length ? `<table><tr><td>Underdog</td><td class="n">${L} (Higher ${esc(x.price?.higher ?? "-")}, Lower ${esc(x.price?.lower ?? "-")})</td></tr>${x.books.map(b => `<tr><td>${esc(b.book)}</td><td class="n">${esc(bookTxt(b))}</td></tr>`).join("")}</table>
  <div class="mute" style="margin-top:6px">${x.bk != null ? "DraftKings and Pinnacle are sportsbooks, so their prices count in our chance. " : "No sportsbook price on this one. "}Sleeper is shown because that is where you play - check its line before you put it in. A different line there changes the bet.</div>` : `<div class="mute">No other book has this prop right now, so there is nothing to check Underdog's number against.</div>`}</div>
  <div class="card"><b>Hit rates (${esc(x.side)} ${L})</b><table><tr><th></th><th>Hit</th><th>Average</th></tr>
  ${["L5","L10","season","last season","vs opp"].map(k => `<tr><td>${k === "L5" ? "Last 5" : k === "L10" ? "Last 10" : k === "vs opp" ? "vs " + esc(x.opp) : k[0].toUpperCase()+k.slice(1)}</td><td class="n ${hrc(x.hits[k])}">${hr(x.hits[k])}</td><td class="n">${x.avgs[k] ?? "-"}</td></tr>`).join("")}
  <tr><td>Home / away</td><td></td><td class="n">${x.avgs.home ?? "-"} / ${x.avgs.away ?? "-"}</td></tr></table></div>
  <div class="card"><b>Role and game</b><table><tr><td>${esc(x.role.label)}</td><td class="n">last 5 ${x.role.L5 ?? "-"} vs season ${x.role.season ?? "-"} (${sgn(x.role.chg)}%)</td></tr>
  <tr><td>Expected ${esc(x.role.label.toLowerCase())}</td><td class="n">${x.role.exp ?? "-"}</td></tr>
  <tr><td>Opponent on this stat</td><td class="n">${x.opp_f && x.opp_f[0] ? sgn(x.opp_f[0]) + "% (" + x.opp_f[1] + " games)" : "About average"}</td></tr>
  ${x.cv ? `<tr><td>Swing (boom-or-bust)</td><td class="n">${Math.round(x.cv*100)}%${x.cv > 0.6 ? " - high" : ""}</td></tr>` : ""}
  ${x.env ? `<tr><td>Team expected to score</td><td class="n">${x.env.implied ?? "-"} (season avg ${x.env.team_avg ? x.env.team_avg.toFixed(1) : "-"})</td></tr><tr><td>Game total / spread</td><td class="n">${x.env.total ?? "-"} / ${x.env.spread != null ? sgn(x.env.spread) : "-"}</td></tr>` : ""}</table></div>
  <div class="card"><b>Confidence ${x.conf} / 10</b>${comp.map(([k,v]) => `<div class="row" style="margin-top:6px"><span>${esc(k)}</span><span class="mute">${v} / ${MAX[k]}</span></div><div class="bar"><i style="width:${Math.max(0, Math.min(100, v/MAX[k]*100))}%"></i></div>`).join("")}${x.history ? `<div class="mute" style="margin-top:6px">${esc(x.history.text)}</div>` : ""}
  <div class="mute" style="margin-top:6px">"Test record" stays 0 until 200 graded prop calls hit 53%+. That keeps every prop below 9.0 until there is proof.</div></div>
  <div class="card"><b>Why</b>${x.for.map(f => `<div class="pro">For: ${esc(f)}</div>`).join("")}${x.against.map(f => `<div class="ag">Against: ${esc(f)}</div>`).join("")}${x.flags.map(f => `<div class="flag">Flag: ${esc(f)}</div>`).join("")}
  <div style="margin-top:6px"><b>Pull if:</b> ${(x.invalidation||[]).map(esc).join("; ")}</div></div>
  <div class="card"><b>Game log</b><table><tr><th>Date</th><th>Opp</th><th>${esc(x.role.label)}</th><th>${esc(x.label)}</th></tr>
  ${(x.log||[]).map(g => `<tr><td>${esc(g.date)}</td><td>${esc(g.opp)}</td><td class="n">${g.role ?? "-"}</td><td class="n ${(g.v > L) === up ? "W" : "L"}">${g.v}</td></tr>`).join("")}</table>
  <div class="mute">Green = would have hit ${esc(x.side)} ${L}.</div></div>`;
  return h;
}
function myEntries(P, day){
  const M = P.my || {list: [], record: {}}, r = M.record || {};
  const top = []; day.filter(c => c.call === "PLAY").sort((a, b) => b.conf - a.conf).forEach(c => { if (top.length < 4 && !top.some(t => t.player === c.player)) top.push(c); });
  const tag = e => e.result === "Won" || e.result === "Part" ? `<span class="tag CASH">${e.result === "Part" ? "Part win" : "Won"}${e.pl != null ? " " + money(e.pl) : ""}</span>` : e.result === "Lost" ? `<span class="tag PULL">Lost ${money(e.pl)}</span>` : e.result === "Check" ? `<span class="tag PAPER">Needs payout</span>` : `<span class="tag PAPER">Open</span>`;
  const kind = e => e.flex ? `flex ${e.mult}x / ${e.flex}x` : (e.kind === "flex" ? "flex" : (e.mult ? e.mult + "x" : "payout not given")) + (e.est ? " (est.)" : "");
  let h = `<div class="card"><b>My entries</b><div class="mute">The prop tickets you actually put in, built your way - singles, 2-picks, flexes. Real stakes and payouts. Separate from the main bankroll and from the Board's paper card.</div>
  <div class="kpi"><div><span class="mute">Record</span><b>${r.w||0}-${r.l||0}</b></div><div><span class="mute">Put in</span><b>$${(r.staked||0).toFixed(2)}</b></div><div><span class="mute">Came back</span><b>$${(r.back||0).toFixed(2)}</b></div><div><span class="mute">Net</span><b class="${(r.pl||0) >= 0 ? "W" : "L"}">${money(r.pl||0)}</b></div></div>
  ${r.open ? `<div class="mute">${r.open} still open.</div>` : ""}${r.need ? `<div class="flag">${r.need} settled but the Board needs the payout - say "entry N won $X".</div>` : ""}
  <div>${cmd("entry $15 2.00x Player + Player", "Log a ticket")}${top.length === 4 ? cmd("entry $15 flex " + top.map(c => c.player).join(" + "), "I flexed today's top 4") : ""}</div>
  <div class="mute" style="margin-top:6px">Tap, fix the amount, the multiplier and the names, then Submit. Flex: "flex 4.38/1.07" = pays 4.38x if all hit, 1.07x with one miss. The Board grades the legs itself.</div>
  ${M.list.length ? `<table style="margin-top:8px">${M.list.map(e => `<tr><td><b>#${e.n}</b> <span class="mute">${esc(e.date.slice(5))}${e.app ? " - " + esc(e.app) : ""} - $${e.stake} ${kind(e)}</span><div>${e.legs.map(l => esc(l.pick) + (l.result ? ` <span class="${l.result === "Won" ? "W" : l.result === "Lost" ? "L" : "mute"}">(${l.actual != null ? l.actual + ", " : ""}${esc(l.result.toLowerCase())})</span>` : "")).join("<br>")}</div>${e.note ? `<div class="mute">${esc(e.note)}</div>` : ""}</td><td class="n">${tag(e)}</td></tr>`).join("")}</table>` : `<div class="mute" style="margin-top:8px">Nothing logged yet.</div>`}</div>`;
  return h;
}
function propsTab(){
  const P = D.props || {calls: [], lines: [], entries: {}, dates: []};
  if (!pday) pday = P.today;
  if (propId) { const x = P.calls.find(c => c.id === propId); if (x) return propDetail(x); }
  const C = P.calib || {}, R = P.record || {};
  let h = `<div class="card"><b>Player props</b><p>About every 30 minutes the Board pulls Underdog's board and checks each line two ways. First against the player's ESPN game log: last 5, last 10, season, last season, vs this opponent, minutes or snaps trend, injuries, and what the game line says his team will score. Second against what DraftKings and Pinnacle charge for the same prop. Sleeper's line is shown too, since that is where you play.</p>
  <p class="mute">Payouts: a 2-pick pays 3x, so each pick needs about 58%. A 3-pick pays 6x, so each needs about 55%. Steep sides (Underdog already above 62%) are skipped. Deep checks too: what each opponent gives up on that stat, boom-or-bust players, and our own record on that kind of prop (a small nudge, max 0.5). Props are kept apart from the main card. Up to 10 plays a day; the card is 3 singles + 2 parlays at $15. Tell the Board if you put one in ("placed Bey").</p>
  ${(C.weight ?? 0.35) > 0 ? `<p class="flag">Not proven yet. Underdog's lines are sharp and our numbers often disagree with them, so for now we only trust our number ${Math.round((C.weight ?? 0.35)*100)}% and Underdog's ${Math.round((1-(C.weight ?? 0.35))*100)}%. After 2,000 graded lines the Board sets that split from results (${C.n || 0} graded so far).</p>` : `<p class="flag">Our own number is switched off: over ${C.n || 0} graded lines, Underdog's number beat ours. A call now needs two things - DraftKings or Pinnacle pricing the prop differently from Underdog, and his game log agreeing. That check is new and not proven. The Board grades it on every line (${C.nb || 0} so far) and drops it by itself if it does not win. College football and college basketball props have no sportsbook price in the free feeds, so those stay pass.</p>`}
  <div class="mute">${esc(P.note || "")}</div></div>`;
  h += `<div class="sel">${(P.dates||[]).map(d => `<button class="pill ${d===pday?"on":""}" data-pday="${d}">${d === P.today ? "Today" : "Tomorrow"}</button>`).join("")}</div>`;
  const sp = ["All", ...new Set(P.calls.concat([]).map(c => c.sport))];
  h += `<div class="sel">${sp.map(s => `<button class="pill ${s===psport?"on":""}" data-psport="${s}">${s}</button>`).join("")}</div>`;
  const day = P.calls.filter(c => c.date === pday && (psport === "All" || c.sport === psport));
  const PC = P.card || {singles: [], parlays: []}, CR = P.card_record || {};
  const wl = r => r ? `${r.w}-${r.l}` : "0-0";
  const st = x => x.status === "PULL" ? `<span class="tag PULL">PULL</span>` : (x.result ? `<span class="tag ${x.result==="Won"?"CASH":x.result==="Lost"?"PULL":""}">${esc(x.result)}</span>` : (x.placed ? `<span class="tag CASH">PLACED $${x.stake||15}</span>` : `<span class="tag PAPER">$${x.stake||15} paper</span>`));
  const pb = (x, name) => x.status === "PULL" && !x.placed ? "" : `<div>${x.placed ? `<span class="mute">You placed this at $${x.stake||15}.</span> ${cmd("skip " + name, "Undo")}` : cmd("placed " + name, "I placed this")}</div>`;
  const single = x => `<div class="card click" data-prop="${x.id}"><div class="row"><div><div class="big">${esc(x.pick)}</div><div class="mute">${esc(x.sport)} - ${esc(x.game)} - ${esc(x.time)} - ours ${pct(x.p)} vs Underdog ${pct(x.mkt)} - conf ${x.conf}</div></div>${st(x)}</div>${x.status==="PULL" ? `<div class="ag">Pull: ${esc(x.pull_why)}</div>` : ""}${x.line_now != null && x.line_now !== x.line ? `<div class="flag">Line now ${x.line_now}</div>` : ""}${pb(x, x.pick)}</div>`;
  const parlay = e => `<div class="card"><div class="row"><div class="big">${esc(e.name)}: ${e.legs.map(x => esc(x.pick) + (x.result ? ` <span class="${x.result==="Won"?"W":x.result==="Lost"?"L":"mute"}">(${esc(x.result.toLowerCase())})</span>` : "")).join(" + ")}</div>${st(e)}</div><div class="mute">Both hit about ${pct(e.chance)} of the time (needs 33.3% at 3x). ${esc(e.why)}</div>${e.status==="PULL" ? `<div class="ag">Pull: ${esc(e.pull_why)}</div>` : ""}${pb(e, "prop " + e.name.toLowerCase().replace("prop ", ""))}</div>`;
  if (pday === P.today) {
    h += `<div class="card"><b>Today's props card</b><div class="mute">3 singles + 2 parlays, $15 each. These are the only props with an amount. ${P.auto ? "Mode: counted as placed unless you tap Undo." : "Mode: paper until you tap \"I placed this\"."}</div>${PC.singles.length || PC.parlays.length ? cmd("placed card", "I placed the whole card") : ""}
    <table style="margin-top:8px"><tr><th></th><th>Record</th><th>$ (est.)</th></tr><tr><td>Card singles (all, paper)</td><td class="n">${wl(CR.singles)}</td><td class="n">${money(CR.singles?.pl)}</td></tr><tr><td>Card parlays (all, paper)</td><td class="n">${wl(CR.parlays)}</td><td class="n">${money(CR.parlays?.pl)}</td></tr></table><div class="mute" style="margin-top:6px">What you actually put in is under "My entries" below.</div></div>`;
    h += myEntries(P, day);
    h += `<h3>Prop singles (${PC.singles.length} of 3)</h3>` + (PC.singles.map(single).join("") || `<div class="card mute">No prop single yet - nothing has cleared PLAY. Slots fill as lines post.</div>`);
    h += `<h3>Prop parlays (${PC.parlays.length} of 2)</h3><div class="mute" style="margin:-4px 0 8px">2-pick at 3x: one PLAY plus one LEAN from a different game.</div>` + (PC.parlays.map(parlay).join("") || `<div class="card mute">No prop parlay yet - needs a PLAY and a LEAN from different games.</div>`);
    const PV = P.card_prev;
    if (PV && (PV.singles.length || PV.parlays.length)) h += `<details class="card"><summary>Last card (${esc(PV.date)}) - results</summary><div class="mute" style="margin:6px 0">Forgot to tell the Board? You can still tap "I placed this".</div>${PV.singles.map(single).join("")}${PV.parlays.map(parlay).join("")}</details>`;
  } else {
    const en = (P.entries||{})[pday] || [];
    h += `<h3>Early look - parlays</h3>` + (en.length ? en.map(e => `<div class="card"><div class="big">${esc(e.name)}: ${e.picks.map(esc).join(" + ")}</div><div class="mute">Both hit about ${pct(e.chance)}. ${esc(e.why)} The card for this day locks on the day.</div></div>`).join("") : `<div class="card mute">Nothing yet.</div>`);
  }
  const plays = day.filter(c => c.call === "PLAY"), leans = day.filter(c => c.call === "LEAN");
  h += `<h3>All plays (${plays.length})</h3><div class="mute" style="margin:-4px 0 8px">Every prop that cleared the bar, up to 10 a day. Only the card above has an amount. The card takes the first plays that clear the bar and then locks, so a play that shows up later is an "extra" - tracked, no amount.</div>` + (plays.map(propCard).join("") || `<div class="card mute">Pass - no prop cleared the bar.</div>`);
  h += `<h3>Leans - legs only (${leans.length})</h3>` + (leans.map(propCard).join("") || `<div class="card mute">None.</div>`);
  h += `<details class="card"><summary>All lines (${P.lines.filter(r => r[0] === pday).length})</summary><input id="pq" placeholder="Search player or stat" value="${esc(pq)}" style="width:100%;margin:8px 0;padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--card2);color:var(--text)">
  <table><thead><tr><th>Player / line</th><th>Lean</th><th>Ours / UD</th><th>Conf</th></tr></thead><tbody id="plines">${lineRows()}</tbody></table></details>`;
  const RR = Object.entries(R);
  h += `<div class="card"><b>Props record</b>${RR.length ? `<table><tr><th></th><th>W-L-P</th><th>Win %</th><th>Beat close</th></tr>${RR.map(([k,v]) => `<tr><td>${esc(k)}</td><td class="n">${v.w}-${v.l}-${v.p}</td><td class="n">${v.w+v.l ? pct(v.w/(v.w+v.l)) : "-"}</td><td class="n">${v.clv_n ? v.clv_beat + "/" + v.clv_n : "-"}</td></tr>`).join("")}</table>` : `<div class="mute">Nothing graded yet. Calls grade about 4 hours after the game.</div>`}</div>`;
  const bins = C.bins || {};
  h += `<div class="card"><b>Is our number better than Underdog's?</b><div class="mute">Every line on the board gets graded, not just our calls - ${C.n || 0} so far.</div>
  ${C.n ? `<table><tr><td>Underdog's error (lower is better)</td><td class="n">${(C.brier.underdog/C.n).toFixed(4)}</td></tr><tr><td>Our blended error</td><td class="n">${(C.brier.ours/C.n).toFixed(4)}</td></tr>
  ${["0-3","3-5","5-8","8+"].filter(k => bins[k]).map(k => `<tr><td>Our side, gap ${k} pts</td><td class="n">${bins[k][0]}-${bins[k][1]} (${pct(bins[k][0]/(bins[k][0]+bins[k][1]))})</td></tr>`).join("")}
  ${Object.entries(C.by_sport||{}).map(([k,v]) => `<tr><td>${esc(k)} our side</td><td class="n">${v[0]}-${v[1]} (${pct(v[0]/(v[0]+v[1]))})</td></tr>`).join("")}</table>` : `<div class="mute">First grades land tomorrow morning.</div>`}</div>`;
  const bb = C.bins_b || {};
  h += `<div class="card"><b>Are the sportsbooks better than Underdog?</b><div class="mute">Same test for the DraftKings / Pinnacle number, on every line that had one - ${C.nb || 0} graded so far. The Board believes the full gap until 1,000 are graded, then whatever share has scored best.</div>
  ${C.nb ? `<table><tr><td>Underdog's error (lower is better)</td><td class="n">${(C.brier_b.underdog/C.nb).toFixed(4)}</td></tr><tr><td>Sportsbooks' error</td><td class="n">${(C.brier_b.books/C.nb).toFixed(4)}</td></tr>
  ${["3-5","5-8","8+"].filter(k => bb[k]).map(k => `<tr><td>Sportsbooks' side, gap ${k} pts</td><td class="n">${bb[k][0]}-${bb[k][1]} (${pct(bb[k][0]/(bb[k][0]+bb[k][1]))})</td></tr>`).join("")}</table>` : `<div class="mute">First grades land after tonight's games.</div>`}</div>`;
  const BD = P.bands || [];
  h += `<div class="card"><b>Is prop confidence telling the truth?</b><div class="mute">Graded calls by the confidence they were logged at. Higher bands should win more. It takes about 100 results in a band before this means anything.</div><table><tr><th>Band</th><th>Record</th><th>Win %</th></tr>${BD.map(t => `<tr><td>${t.band}</td><td class="n">${t.w}-${t.l}</td><td class="n">${t.w+t.l ? pct(t.w/(t.w+t.l)) : "-"}${t.w+t.l && t.w+t.l < 100 ? ' <span class="mute">(too few)</span>' : ""}</td></tr>`).join("")}</table></div>`;
  const recent = (P.recent || []);
  if (recent.length) h += `<div class="card"><b>Recent graded calls</b><table>${recent.map(b => `<tr><td>${esc(b.pick)}<div class="mute">${esc(b.date)} ${b.placed ? "- placed" : ""}</div></td><td class="n ${b.result}">${esc(b.result)}</td><td class="n">${b.actual ?? "-"}</td></tr>`).join("")}</table></div>`;
  return h;
}
draw();
</script></body></html>"""

COMMANDS = [["placed Mitchell", "You put that pick in. Works for props, paper picks and parlays. Add an amount if it wasn't the usual: placed Mitchell $20."],
            ["placed card", "You put in today's whole props card (3 singles + 2 parlays)."],
            ["entry $15 2.75x Vilardi + Traore", "Your own prop ticket, built your way. It goes in My entries on the Props tab and the Board grades it. Flex: entry $15 flex 4.38/1.07 A + B + C + D."],
            ["entry 7 won $48", "Fix an entry: 'entry 7 won $48', 'entry 7 lost' or 'entry 7 remove'."],
            ["placed prop parlay 1", "You put in that prop parlay. 'placed parlay 1' is the main-card parlay."],
            ["skip Raptors", "You did NOT place that ticket - it stops counting. Works for mains, parlays and props."],
            ["props auto", "Count the props card as placed every day unless you skip one. 'props manual' turns that off."],
            ["bankroll 650", "Set the bankroll. Placed tickets add to it from today."],
            ["approve CBB", "Let a sport have mains. Your graduation call."], ["unapprove NBA", "Back to paper."],
            ["goal 10000", "Change the goal."], ["prop Brunson over 25.5 points", "Full workup on any player line today or tomorrow."],
            ["refresh", "Rebuild the Board right now."], ["help", "List commands."]]

LAB_NOTES = [
    "Against the closing line, none of the simple team models beat the market in any sport. The market's average miss is smaller than ours everywhere.",
    "Against the OPENING line it looks different: when both models agreed with the open, the line usually moved our way by game time (NBA 41-28, NHL 203-105, college basketball 156-149). College basketball covered 54.6% against the open over 399 games. That is one season - promising, not proven.",
    "What that means: the models may be early, not wrong. The money is in getting the number before the market moves. The Board grades every pick on the first number it logs and tracks the close, so in a few weeks we'll know if it gets the good numbers live.",
    "Next to add: an evening run that grabs next-day college basketball openers, a totals model test, and NHL goalie quality.",
]


def props_data(pr, date):
    from . import props as P, entries as E
    pr = pr or {"props": []}
    calls = [x for x in pr["props"] if x.get("call") in ("PLAY", "LEAN")]
    lines = [[x.get("date"), x.get("sport"), x.get("player"), x.get("label") or x.get("stat"), x.get("line"), (x.get("side") or "").title() or None,
              x.get("p"), x.get("mkt"), x.get("conf"), x.get("call"), x.get("game") or x.get("game_title"), x.get("bk")] for x in pr["props"]]
    book = load("props.json", [])
    dates = pr.get("dates") or [date]
    prev = max([d for d in (load("props_card.json", {}) or {}) if d < date], default=None)
    return {"today": date, "dates": dates, "calls": calls, "lines": lines, "n_lines": len([l for l in lines if l[0] == date]), "note": pr.get("note"),
            "entries": {d: P.entries(pr["props"], d) for d in dates}, "record": P.record(book), "calib": load("props_calib.json", {}),
            "recent": [b for b in book if b.get("result") in ("Won", "Lost", "Push", "Void")][-30:][::-1],
            "card": prop_card(date, book), "card_prev": prop_card(prev, book) if prev else None, "card_record": P.card_record(book),
            "bands": P.bands(book), "auto": bool(load("settings.json", {}).get("props_auto")),
            "placed_ids": [b["id"] for b in book if b.get("placed")],
            "my": {"list": load("my_entries.json", [])[-40:][::-1], "record": E.record()}}


def prop_card(date, book):
    pc = (load("props_card.json", {}) or {}).get(date) or {"singles": [], "parlays": []}
    res = {b["id"]: b.get("result") for b in book}
    for it in pc["singles"] + [x for e in pc["parlays"] for x in e["legs"]]:
        it["result"] = res.get(it["id"])
    for e in pc["parlays"]:
        rs = [x.get("result") for x in e["legs"]]
        e["result"] = "Lost" if "Lost" in rs else "Won" if all(r == "Won" for r in rs) else None
    pc["date"] = date
    return pc


def render(cards, picks, pars, bt, btl, st, hl, pr=None):
    now = now_ct(); date = now.strftime("%Y-%m-%d")
    pulls = {p["id"]: f"{p['pick']}: {p['review_log'][-1]}" for p in picks if p.get("review") == "PULL" and p["result"] is None}
    cash = [r for c in cards for r in c["games"] if r["decision"] == "CASH"]
    why = ("Mains below." if cash else
           "No pick passed every gate for a main: both models agree, confidence 7.0+ (8.0+ for midweek or small-conference CFB), no veto, and a sport you've approved (football and NBA). Paper picks are still graded so the record builds.")
    data = {"updated": now.strftime("%a %b %-d, %-I:%M %p CT"), "cards": cards, "picks": picks[-1500:], "parlays": [x for x in pars if x["date"] == date], "all_parlays": pars[-200:],
            "summary": grade.summary(picks), "tiers": grade.tiers(picks), "bt": bt, "btl": btl, "grad": review.graduation(picks, bt, btl, st),
            "bank": {"now": grade.bankroll(picks, st), "goal": st.get("goal", 10000)}, "health": hl, "pulls": pulls, "why_pass": why,
            "review_log": {p["id"]: p.get("review_log", []) for p in picks if p["result"] is None},
            "reviews": load("reviews.json", []), "requests": load("requests_log.json", []), "commands": COMMANDS, "lab_notes": LAB_NOTES,
            "bars": {k: v["bar"] for k, v in SPORTS.items()}, "rules": load("rules.json", []), "props": props_data(pr, date),
            "repo": os.environ.get("GITHUB_REPOSITORY") or "jjuliancastroc-beep/board-auto", "ts": int(now.timestamp()), "today": date,
            "moved": [{k: p.get(k) for k in ("id", "pick", "stake", "sport", "game", "moved", "start", "book_ok")} for p in picks
                      if p.get("moved") and p["result"] is None and grade.counts(p) and p["id"] not in {r["id"] for c in cards for r in c["games"]}],
            "skipped": {p["id"]: True for p in picks if p["date"] == date and p.get("skipped")},
            "user_placed": {p["id"]: p.get("stake") for p in picks if p["date"] == date and p.get("user_placed")}}
    out = PAGE.replace("__DATA__", json.dumps(data, default=float).replace("</", "<\\/"))
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    with open(os.path.join(ROOT, "docs", "index.html"), "w") as f:
        f.write(out)
    open(os.path.join(ROOT, "docs", ".nojekyll"), "w").close()
