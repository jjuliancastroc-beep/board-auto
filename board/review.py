"""Automatic review - the part that replaces a person checking the card.

1. Pre-game check (every run): for each logged pick that hasn't started, compare the CURRENT line and injury
   report with what we logged. If the line moved past the playable number, or a QB / star / goalie changed,
   the pick is marked PULL with the reason. It never adds bets and never says "keep it in" - only pull or hold.
2. Health check (every run): did every feed load, do lines exist, are the models sane, is grading caught up.
   Problems show on the Reviews tab and trigger an email.
3. Weekly report (Tuesday morning): record by sport and confidence band, closing-line results, which kinds of
   picks are ready for you to approve for cash, and which rules are hurting.
"""
import datetime
from .common import load, save, now_ct, ct_time, SPORTS
from . import espn
from .card import key_injuries


def prelock(picks, cards):
    now = now_ct(); alerts = []
    live = {r["id"]: r for c in cards for r in c["games"]}
    for p in picks:
        if p["result"] is not None or ct_time(p["start"]) <= now or p.get("review") == "PULL":
            continue
        r = live.get(p["id"])
        if not r:
            continue
        why = []
        p.setdefault("review_log", []); team, _, ln = p["pick"].rpartition(" ")
        if " ML " not in p["pick"] + " " and r.get("home_line") is not None and p.get("playable_to") is not None:
            cur = r["home_line"] if p.get("side") == "home" else -r["home_line"]
            if cur < p["playable_to"]:
                why.append(f"line is now {cur:+g}, past the playable number {p['playable_to']:+g}")
        new_flags = [f for f in r["flags"] if f.startswith(("QB", "Star", "Starting goalie")) and f not in (p.get("flags") or [])]
        why += new_flags
        if p["sport"] == "NHL" and r.get("goalies") and p.get("goalies") and r["goalies"] != p.get("goalies"):
            why.append(f"goalie change: {r['goalies']}")
        if why:
            p["review"] = "PULL"; p["review_log"].append(f"{now.strftime('%m/%d %I:%M %p')}: PULL - " + "; ".join(why))
            alerts.append(p)
        else:
            stamp = now.strftime("%m/%d %I:%M %p")
            if not p["review_log"] or not p["review_log"][-1].endswith("no change"):
                p["review_log"].append(f"{stamp}: checked line and injuries - no change")
    save("picks.json", picks)
    return alerts


def health(cards, picks):
    probs = []; notes = []
    for c in cards:
        n = len(c["games"])
        if c.get("note", "").startswith("Build failed"):
            probs.append(f"{c['sport']}: {c['note']}")
            continue
        if n == 0:
            notes.append(f"{c['sport']}: no games today")
            continue
        with_line = sum(1 for r in c["games"] if r.get("home_line") is not None or r.get("home_ml") is not None)
        with_model = sum(1 for r in c["games"] if r.get("model_a") is not None and r.get("model_b") is not None)
        notes.append(f"{c['sport']}: {n} games, {with_line} with a line, {with_model} with both models")
        if with_line < 0.5 * n and c["sport"] != "CBB":
            probs.append(f"{c['sport']}: only {with_line} of {n} games have a line - DraftKings feed may be down")
        if with_model < 0.5 * n:
            probs.append(f"{c['sport']}: only {with_model} of {n} games have both models - check data feed")
        big = [r for r in c["games"] if r.get("model_a") is not None and abs(r["model_a"]) > (60 if c["sport"] in ("CFB", "CBB") else 30)]
        if c["sport"] != "NHL" and big:
            probs.append(f"{c['sport']}: model margin over sanity limit in {len(big)} game(s)")
    stale = [p for p in picks if p["result"] is None and now_ct() - ct_time(p["start"]) > datetime.timedelta(days=1)]
    if stale:
        probs.append(f"{len(stale)} pick(s) more than a day old still ungraded")
    return {"time": now_ct().strftime("%a %b %-d %-I:%M %p CT"), "ok": not probs, "problems": probs, "notes": notes}


def weekly(picks, pars, bt, btl, settings, force=False):
    now = now_ct(); reviews = load("reviews.json", [])
    wk = now.strftime("%G-W%V")
    if not force and (now.strftime("%a") != "Tue" or any(r.get("week") == wk for r in reviews)):
        return None
    start = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    week = [p for p in picks if p["date"] >= start and p["result"] in ("Won", "Lost", "Push")]
    lines = []
    by = {}
    for p in week:
        k = f"{p['sport']} {p['decision']}"; s = by.setdefault(k, [0, 0, 0.0, 0, 0])
        s[0] += p["result"] == "Won"; s[1] += p["result"] == "Lost"; s[2] += p.get("units") or 0
        if p.get("clv") is not None:
            s[3] += 1; s[4] += p["clv"] > 0
    for k, s in sorted(by.items()):
        lines.append(f"{k}: {s[0]}-{s[1]}, {s[2]:+.2f}u, beat the close {s[4]}/{s[3]}")
    if not lines:
        lines.append("No graded picks this week.")
    pulled = [p for p in week if p.get("review") == "PULL"]
    if pulled:
        pw = sum(1 for p in pulled if p["result"] == "Won")
        lines.append(f"Pulled picks: {pw}-{len(pulled) - pw} (if pulls keep winning, the pull rules are too strict)")
    ready = graduation(picks, bt, btl, settings)
    for g in ready:
        if g["status"] == "Ready for your approval":
            lines.append(f"READY: {g['what']} - {g['evidence']}. Comment 'approve {g['sport']}' on a Board issue to allow cash.")
    entry = {"week": wk, "date": now.strftime("%Y-%m-%d"), "title": f"Weekly report {now.strftime('%b %-d')}", "lines": lines}
    reviews.append(entry); save("reviews.json", reviews)
    return entry


def graduation(picks, bt, btl, settings):
    """Where each sport stands on the path from paper to cash."""
    out = []
    approved = settings.get("cash_approved") or []
    for sport in SPORTS:
        if sport == "CFB":
            hist = max((v for v in bt.get("CFB", {}).values()), key=lambda v: v.get("n", 0), default=None)
            hist_note = "best bucket " + (f"{hist['w']}-{hist['l']}" if hist else "-")
        elif sport == "NFL":
            hist = bt.get("NFL", {}).get("Sun"); hist_note = "Sunday " + (f"{hist['w']}-{hist['l']}" if hist else "-")
        else:
            hist = (btl.get(sport) or {}).get("both_agree"); hist_note = "last season " + (f"{hist['w']}-{hist['l']}" if hist else "-")
        live = [p for p in picks if p["sport"] == sport and p["decision"] in ("PAPER", "CASH") and p["result"] in ("Won", "Lost")]
        lw = sum(1 for p in live if p["result"] == "Won")
        clv = [p["clv"] for p in live if p.get("clv") is not None]
        beat = sum(1 for c in clv if c > 0)
        hist_ok = bool(hist) and hist.get("n", 0) >= 200 and hist.get("win", 0) >= 0.535
        live_ok = len(live) >= 100 and lw / len(live) >= 0.535 and (not clv or beat / len(clv) >= 0.5)
        if sport in approved:
            status = "Approved for cash"
        elif hist_ok or live_ok:
            status = "Ready for your approval"
        else:
            status = "Paper"
        out.append({"sport": sport, "status": status, "what": f"{sport} both-models picks",
                    "evidence": f"past games {hist_note}{' (' + str(round(hist['win'] * 100, 1)) + '%)' if hist else ''}; live paper {lw}-{len(live) - lw}; beat close {beat}/{len(clv)}",
                    "need": "53.5%+ over 200+ past games, or 53.5%+ over 100+ live paper picks while beating the close half the time"})
    return out
