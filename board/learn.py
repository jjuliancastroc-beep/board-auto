"""The Board's memory and the decisions it makes from it (owner's call, 11/20: "let it make the learning decision but it needs to learn").

What it remembers (data/memory.json, kept in the repo so nothing is lost between runs):
  - every kind of main pick (sport + bet type, sport + confidence band) and how it has done: every graded pick counts,
    cash, paper and watch, bet or not
  - every graded prop line Underdog posted (data/memory_lines.jsonl), so it can find prop types Underdog misprices
  - a lessons log: each time the Board changes its mind about a kind of pick, with the date and the record behind it
  - its own learned plays and how they did, so it can tell when its learning is wrong

What it decides, without asking:
  1. Learned single. A pick the scorecard graded under 7.0 (or in a paper sport) becomes a real single at a smaller
     stake ($10) when its kind of pick has proven itself: 30+ graded results, still above break-even after the record is
     pulled 50 games toward 50/50, and up in units. Most 2 a day, and only when both models agree.
  2. Learned caution. A cash pick whose kind of pick has proven to lose (30+ results, under break-even by 3+ points
     after the pull) drops to the $10 stake. The scorecard grade itself is never changed.
  3. Learned prop leg. A prop on a kind of line where Underdog has been wrong by 4+ points over 400+ graded lines
     becomes a parlay leg (never a single - your 11/16 rule).
  4. Self-check. If its learned plays lose 4+ units over 20+ results, it stops making them for 7 days and writes down why.

The pull toward 50/50 is what keeps a hot streak from fooling it: 23-9 counts as about 58%, not 72%.
"""
import datetime, json, math, os, re
from .common import load, save, today_ct, now_ct, ROOT

MIN_N = 30            # results before a kind of pick can prove anything
PRIOR = 25            # phantom wins and losses (50 games at 50%) mixed into every record
WIN_CUSHION = 0.015   # a proven winner must beat break-even by this much after the pull
LOSE_CUSHION = 0.03   # a proven loser is this far under break-even after the pull
LEARN_STAKE = 10
MAX_LEARNED = 2
PAUSE_N, PAUSE_UNITS, PAUSE_DAYS = 20, -4.0, 7
PROP_MIN_N, PROP_PRIOR, PROP_EDGE = 400, 100, 0.04
LINES = "memory_lines.jsonl"


def _payout(price):
    try:
        o = float(str(price).replace("+", ""))
    except (TypeError, ValueError):
        o = -110.0
    return o / 100 if o > 0 else 100 / abs(o)


def kind(p):
    """Bet type: fav, dog under 10, dog 10-20, dog 20+, ML fav, ML dog."""
    pick = p.get("pick") or ""
    if " ML" in pick:
        return "ML dog" if _payout(p.get("price")) >= 1 else "ML fav"
    m = re.search(r"([+-]\d+(?:\.\d+)?)$", pick.strip())
    if not m:
        return None
    v = float(m.group(1))
    return "fav" if v < 0 else "dog under 10" if v < 10 else "dog 10-20" if v < 20 else "dog 20+"


def band(c):
    c = c or 0
    return "8+" if c >= 8 else "7-7.9" if c >= 7 else "6-6.9" if c >= 6 else "5.5-5.9" if c >= 5.5 else "under 5.5"


def keys(p):
    k = kind(p)
    return ([f"{p['sport']} {k}"] if k else []) + [f"{p['sport']} conf {band(p.get('conf'))}"]


def judge(w, l, units, be):
    n = w + l
    s = (w + PRIOR) / (n + 2 * PRIOR)
    if n >= MIN_N and s >= be + WIN_CUSHION and units > 0:
        st = "proven winner"
    elif n >= MIN_N and s <= be - LOSE_CUSHION:
        st = "proven loser"
    else:
        st = "learning"
    return round(s, 4), st


def buckets(picks):
    out = {}
    for p in picks:
        if p.get("result") not in ("Won", "Lost") or not p.get("pick"):
            continue
        won = p["result"] == "Won"; pay = _payout(p.get("price"))
        for k in keys(p):
            b = out.setdefault(k, {"w": 0, "l": 0, "units": 0.0, "be_sum": 0.0})
            b["w" if won else "l"] += 1; b["units"] += pay if won else -1.0; b["be_sum"] += 1 / (1 + pay)
    for k, b in out.items():
        n = b["w"] + b["l"]; be = b.pop("be_sum") / n
        b["units"] = round(b["units"], 2); b["be"] = round(be, 4)
        b["shrunk"], b["status"] = judge(b["w"], b["l"], b["units"], be)
    return out


def learned_record(picks):
    r = [p for p in picks if p.get("learned") and p.get("result") in ("Won", "Lost") and not p.get("skipped")]
    w = sum(1 for p in r if p["result"] == "Won")
    u = round(sum(_payout(p.get("price")) if p["result"] == "Won" else -1.0 for p in r), 2)
    return {"w": w, "l": len(r) - w, "units": u}


def update(picks=None):
    """Refresh the memory from every graded pick and line. Writes a lesson whenever a kind of pick changes status."""
    picks = picks if picks is not None else load("picks.json", [])
    mem = load("memory.json", {}); today = today_ct()
    old = mem.get("buckets", {}); new = buckets(picks)
    lessons = mem.get("lessons", [])
    for k, b in new.items():
        was = (old.get(k) or {}).get("status", "learning")
        if b["status"] != was:
            n = b["w"] + b["l"]
            lessons.append({"date": today, "what": k, "from": was, "to": b["status"],
                            "text": f"{k}: {b['w']}-{b['l']} ({b['w'] / n * 100:.0f}%, {b['units']:+.1f} units). Counted as {b['shrunk'] * 100:.1f}% after the pull toward 50/50; "
                                    f"break-even {b['be'] * 100:.1f}%. Now {b['status']}" + (" - lower-graded picks of this kind can be played at $10." if b["status"] == "proven winner"
                                    else " - cash picks of this kind drop to $10." if b["status"] == "proven loser" else " - back to watching.")})
    rec = learned_record(picks)
    pause = mem.get("paused_until")
    if pause and pause < today:
        lessons.append({"date": today, "what": "learned plays", "from": "paused", "to": "on", "text": "Pause over - learned plays are back on."}); pause = None
    if not pause and rec["w"] + rec["l"] >= PAUSE_N and rec["units"] <= PAUSE_UNITS and not mem.get("pause_seen") == (rec["w"], rec["l"]):
        pause = (datetime.datetime.strptime(today, "%Y-%m-%d") + datetime.timedelta(days=PAUSE_DAYS)).strftime("%Y-%m-%d")
        mem["pause_seen"] = (rec["w"], rec["l"])
        lessons.append({"date": today, "what": "learned plays", "from": "on", "to": "paused",
                        "text": f"Learned plays are {rec['w']}-{rec['l']} ({rec['units']:+.1f} units). The learning was wrong, so it stops making them until {pause}."})
    mem.update(buckets=new, lessons=lessons[-300:], learned=rec, paused_until=pause, props=prop_buckets(), updated=now_ct().strftime("%m/%d %I:%M %p"))
    save("memory.json", mem)
    return mem


def apply(cards, mem, date, picks):
    """Make today's learned decisions on the card rows (before the day caps are applied)."""
    B = mem.get("buckets", {}); paused = bool(mem.get("paused_until"))
    already = sum(1 for p in picks if p["date"] == date and p.get("learned") and p["decision"] == "CASH")
    rows = [r for c in cards for r in c["games"] if r.get("pick")]
    for r in rows:   # 2. caution on proven losers
        if r["decision"] == "CASH" and not r.get("locked") and not r.get("learned"):
            bad = [k for k in keys(r) if (B.get(k) or {}).get("status") == "proven loser"]
            if bad and r.get("stake", 0) > LEARN_STAKE:
                b = B[bad[0]]
                r["stake"] = LEARN_STAKE; r["learned_caution"] = True
                r["reason"] += f" Learned caution: {bad[0]} is {b['w']}-{b['l']} on the Board, so the stake drops to ${LEARN_STAKE}."
    if paused:
        return
    cand = []
    for r in rows:   # 1. learned singles
        if r["decision"] != "PAPER" or (r.get("conf") or 0) < 5.5 or r.get("veto") or not r.get("models_agree", True):
            continue
        ks = keys(r); st = [(B.get(k) or {}).get("status") for k in ks]
        if "proven loser" in st or "proven winner" not in st:
            continue
        best = max((B[k] for k in ks if B[k]["status"] == "proven winner"), key=lambda b: b["shrunk"])
        kname = next(k for k in ks if B[k] is best)
        cand.append((best["shrunk"], r.get("conf") or 0, r, kname, best))
    games = {r["id"] for r in rows if r["decision"] == "CASH"}
    for _, _, r, kname, b in sorted(cand, key=lambda x: (-x[0], -x[1])):
        if already >= MAX_LEARNED or r["id"] in games:
            continue
        r.update(decision="CASH", stake=LEARN_STAKE, learned=True)
        r["reason"] = (f"Learned play: graded {r['conf']} " + ("(under the usual bar)" if (r.get("conf") or 0) < 7 else "(in a paper sport)") + f", but {kname} is {b['w']}-{b['l']} ({b['units']:+.1f} units) on the Board - "
                       f"{b['shrunk'] * 100:.1f}% after the pull toward 50/50 vs {b['be'] * 100:.1f}% break-even. Smaller stake (${LEARN_STAKE}) because the grade is lower. ") + r["reason"]
        already += 1; games.add(r["id"])


# ---------- props: remember every graded line, look for kinds of lines Underdog gets wrong ----------

def remember_line(b, y, date):
    """One graded Underdog line -> memory_lines.jsonl (sport, stat, line, Underdog's chance of Higher, books' chance, what happened)."""
    path = os.path.join(ROOT, "data", LINES)
    row = {"d": date, "s": b["sport"], "t": b["stat"], "ln": b["line"], "mh": b["mh"], "bk": b.get("bk"), "y": y, "c": b.get("conf"), "sd": b.get("side")}
    with open(path, "a") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


def _lines():
    path = os.path.join(ROOT, "data", LINES)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(x) for x in f if x.strip()]


def prop_buckets(rows=None):
    """For each sport + stat + side: how often that side hit vs how often Underdog's price said it would."""
    rows = rows if rows is not None else _lines()
    agg = {}
    for r in rows:
        for side in ("higher", "lower"):
            a = agg.setdefault(f"{r['s']} {r['t']} {side}", {"n": 0, "hit": 0, "said": 0.0})
            a["n"] += 1; a["hit"] += r["y"] if side == "higher" else 1 - r["y"]; a["said"] += r["mh"] if side == "higher" else 1 - r["mh"]
    for r in rows:   # 11/21 owner's question: does a high prop confidence win by itself, even with no gap to Underdog?
        if r.get("c") is None or r.get("sd") not in ("higher", "lower"):
            continue
        a = agg.setdefault(f"{r['s']} conf {band(r['c'])} leaned side", {"n": 0, "hit": 0, "said": 0.0})
        hi = r["sd"] == "higher"
        a["n"] += 1; a["hit"] += r["y"] if hi else 1 - r["y"]; a["said"] += r["mh"] if hi else 1 - r["mh"]
    out = {}
    for k, a in agg.items():
        said = a["said"] / a["n"]
        s = (a["hit"] + PROP_PRIOR * said) / (a["n"] + PROP_PRIOR)   # pulled toward Underdog's own number
        gap = s - said
        out[k] = {"n": a["n"], "hit": round(a["hit"] / a["n"], 4), "said": round(said, 4), "gap": round(gap, 4),
                  "status": "proven winner" if a["n"] >= PROP_MIN_N and gap >= PROP_EDGE else "learning"}
    return out


def apply_props(props, mem, cap=6):
    """A prop on a proven kind of line becomes a parlay leg (LEAN). Never a single. Most 6 a day."""
    P = mem.get("props") or {}; n = 0
    for p in sorted(props, key=lambda p: -(p.get("conf") or 0)):
        if n >= cap or p.get("call") != "PASS" or p.get("mkt") is None or p.get("line") is None:
            continue
        mh = p["mkt"] if p.get("side") == "higher" else 1 - p["mkt"]
        tries = [(side, P.get(f"{p['sport']} {p['stat']} {side}"), f"{side} on {p['sport']} {p['stat']}") for side in ("higher", "lower")]
        if p.get("side") in ("higher", "lower") and p.get("conf") is not None:
            tries.insert(0, (p["side"], P.get(f"{p['sport']} conf {band(p['conf'])} leaned side"), f"{p['sport']} props graded {band(p['conf'])} (the side it leaned)"))
        for side, b, what in tries:
            mk = mh if side == "higher" else 1 - mh
            if not b or b["status"] != "proven winner" or mk > 0.62:
                continue
            ch = min(0.99, mk + b["gap"])
            p.update(call="LEAN", learned=True, side=side, conf=max(p.get("conf") or 0, 5.5), p=round(ch, 3), mkt=round(mk, 3), edge=round(b["gap"] * 100, 1),
                     pick=f"{p['player']} {side.title()} {p['line']:g} {p.get('label') or p['stat']}",
                     reason=f"Learned leg: {what} has hit {b['hit'] * 100:.0f}% over {b['n']} graded Underdog lines when Underdog's price said {b['said'] * 100:.0f}%. Parlay leg only.")
            n += 1
            break
    return props
