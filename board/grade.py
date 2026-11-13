"""Log picks once (the first number we saw is the one we grade), grade finished games from ESPN finals,
record the closing line (CLV), grade parlays, and keep the bankroll from cash tickets (capped cash tickets count as placed)."""
import datetime
from .common import load, save, now_ct, ct_time
from . import espn

KEEP = ("id", "sport", "game", "home", "away", "start", "pick", "decision", "stake", "conf", "components", "gap_a", "gap_b", "gap_min",
        "price", "fair_line", "playable_to", "side", "home_line", "home_ml", "away_ml", "flags", "against", "invalidation", "reason",
        "model_a", "model_b", "model_a_name", "model_b_name", "test_record", "tier", "day", "book", "goalies", "history")


def log_picks(cards, date):
    """Log every call once. A logged paper/watch pick is upgraded to a main if it reaches CASH before the game
    starts. A main is never downgraded here - only a PULL from the pre-game review or your 'skip' takes it out."""
    picks = load("picks.json", [])
    have = {(p["date"], p["id"]): p for p in picks}
    now = now_ct(); hm = now.strftime("%H:%M")
    for c in cards:
        for r in c["games"]:
            if r["decision"] not in ("CASH", "PAPER", "WATCH"):
                continue
            old = have.get((date, r["id"]))
            if old is None:
                p = {k: r.get(k) for k in KEEP}
                p.update(date=date, line_at_pick=r.get("line"), logged_at=hm, result=None, final=None, close=None, clv=None, review="HOLD", review_log=[])
                picks.append(p); have[(date, r["id"])] = p
            elif r["decision"] == "CASH" and old["decision"] != "CASH" and old["result"] is None and ct_time(old["start"]) > now:
                for k in KEEP:
                    old[k] = r.get(k)
                old.update(line_at_pick=r.get("line"), logged_at=hm)
                old["review_log"] = (old.get("review_log") or []) + [f"{hm} upgraded to main ({r['pick']}, conf {r['conf']})"]
    save("picks.json", picks)
    return picks


def lock_mains(cards, date):
    """Mains already logged today stay mains with the same pick and stake (they are on your Capped card)."""
    locked = {p["id"]: p for p in load("picks.json", []) if p["date"] == date and p["decision"] == "CASH" and not p.get("skipped")}
    for c in cards:
        for r in c["games"]:
            p = locked.get(r["id"])
            if not p:
                continue
            if r.get("decision") != "CASH" or r.get("pick") != p["pick"]:
                r["now_says"] = f"{r.get('decision')} {r.get('pick') or ''} {r.get('conf') or ''}".strip()
            for k in ("pick", "stake", "conf", "components", "side", "fair_line", "playable_to", "test_record", "history"):
                if p.get(k) is not None:
                    r[k] = p[k]
            r["decision"] = "CASH"; r["locked"] = True
            r["reason"] = f"Locked as a main at {p.get('logged_at')}. " + (p.get("reason") or "")
    return locked


def _pick_team_line(p):
    txt = p["pick"]
    if " ML " in txt + " ":
        return txt.split(" ML")[0], None
    team, ln = txt.rsplit(" ", 1)
    return team, float(ln)


def payout(price):
    price = price or -110
    return price / 100 if price > 0 else 100 / abs(price)


def grade_all():
    picks = load("picks.json", []); now = now_ct(); changed = 0; boards = {}
    for p in picks:
        if p["result"] is not None:
            continue
        st = ct_time(p["start"])
        if now - st < datetime.timedelta(hours=3, minutes=15):
            continue
        key = (p["sport"], st.strftime("%Y-%m-%d"))
        if key not in boards:
            boards[key] = {g["id"]: g for g in espn.scoreboard(*key)}
        g = boards[key].get(p["id"])
        if not g or not g["completed"]:
            if now - st > datetime.timedelta(days=3):
                p["result"] = "No result"; changed += 1
            continue
        team, ln = _pick_team_line(p)
        is_home = team == p["home"]
        margin = (g["hs"] - g["as"]) if is_home else (g["as"] - g["hs"])
        p["final"] = f"{g['away']} {g['as']}, {g['home']} {g['hs']}"
        if ln is None:
            p["result"] = "Won" if margin > 0 else "Lost"
            p["units"] = round(payout(p.get("price")) if margin > 0 else -1.0, 2)
        else:
            v = margin + ln
            p["result"] = "Won" if v > 0 else "Lost" if v < 0 else "Push"
            p["units"] = round(payout(p.get("price")) if v > 0 else (-1.0 if v < 0 else 0.0), 2)
        p["pl"] = round((p.get("stake") or 0) * p["units"], 2) if p["decision"] == "CASH" and not p.get("skipped") else 0.0
        cl = espn.closing_line(p["sport"], p["id"])
        if cl:
            p["close"] = cl.get("details") or f"ML {cl.get('home_ml')}/{cl.get('away_ml')}"
            if ln is not None:
                chl = espn.home_line(cl.get("details"), g["habbr"], g["aabbr"])
                if chl is not None:
                    p["clv"] = round(ln - (chl if is_home else -chl), 1)  # + = we had a better number than the close
            elif cl.get("home_ml") and cl.get("away_ml") and p.get("price"):
                from .common import american_to_prob
                mine = american_to_prob(p["price"]); close = american_to_prob(cl["home_ml"] if is_home else cl["away_ml"])
                p["clv"] = round((close - mine) * 100, 1)  # + = the close priced our side higher than we paid
        changed += 1
    save("picks.json", picks)
    grade_parlays(picks)
    return picks, changed


def grade_parlays(picks):
    pars = load("parlays.json", [])
    by = {(p["date"], p["id"]): p for p in picks}
    for x in pars:
        if x.get("result"):
            continue
        legs = [by.get((x["date"], lid)) for lid in x["legs"]]
        if any(l is None for l in legs) or any(l["result"] is None for l in legs):
            continue
        res = [l["result"] for l in legs]
        if "Lost" in res:
            x["result"] = "Lost"; x["units"] = -1.0
        elif all(r in ("Won", "Push", "No result") for r in res):
            dec = 1.0
            for l in legs:
                if l["result"] == "Won":
                    dec *= 1 + payout(l.get("price"))
            x["result"] = "Won" if dec > 1 else "Push"; x["units"] = round(dec - 1, 2)
        x["pl"] = round(x["stake"] * x["units"], 2) if x.get("decision") == "CASH" else 0.0
    save("parlays.json", pars)
    return pars


def build_parlays(cards, date, picks):
    """Two parlays max, each using only ONE confident pick (7.0+) plus one 5.5-6.9 leg from a different game.
    $15 when the confident leg is a main, paper otherwise. A $15 parlay is locked once made; paper ones rebuild each run."""
    pars = load("parlays.json", [])
    today = [x for x in pars if x["date"] == date]
    keep = [x for x in today if x["decision"] == "CASH"]
    if len(keep) >= 2:
        return today
    pars = [x for x in pars if not (x["date"] == date and x["decision"] != "CASH")]
    rows = [r for c in cards for r in c["games"] if r["decision"] in ("CASH", "PAPER") and r.get("price") and r.get("pick")]
    now = now_ct()
    rows = [r for r in rows if not r.get("start") or ct_time(r["start"]) > now]
    anchors = sorted([r for r in rows if r["conf"] >= 7.0], key=lambda r: (r["decision"] != "CASH", -r["conf"]))
    legs = sorted([r for r in rows if 5.5 <= r["conf"] < 7.0], key=lambda r: -r["conf"])
    used = {i for x in keep for i in x["legs"]}
    old = [p for p in load("history_old.json", []) if "parlay" in p["b"]]
    ow = sum(1 for p in old if p["r"] == "W")
    hist = f" Our parlay record on the old Board: {ow}-{len(old) - ow} - parlays have been our weakest bet, so they stay $15." if old else ""
    out = list(keep)
    for a in anchors:
        if len(out) == 2:
            break
        if a["id"] in used:
            continue
        leg = next((l for l in legs if l["id"] != a["id"] and l["id"] not in used), None)
        if not leg:
            break
        used |= {a["id"], leg["id"]}
        dec = (1 + payout(a["price"])) * (1 + payout(leg["price"]))
        am = round((dec - 1) * 100)
        out.append({"date": date, "name": f"Parlay {len(out) + 1}", "legs": [a["id"], leg["id"]], "picks": [a["pick"], leg["pick"]],
                    "price": f"+{am}", "decision": "CASH" if a["decision"] == "CASH" else "PAPER", "stake": 15 if a["decision"] == "CASH" else 0,
                    "why": f"Anchor {a['pick']} ({a['conf']}) + leg {leg['pick']} ({leg['conf']}). Only one confident pick per parlay." + hist,
                    "result": None, "made_at": now.strftime("%H:%M")})
    pars.extend(x for x in out if x not in keep); save("parlays.json", pars)
    return out


def summary(picks):
    out = {}
    for p in picks:
        if p["result"] not in ("Won", "Lost", "Push"):
            continue
        for k in (f"{p['sport']} {p['decision']}", f"All {p['decision']}"):
            s = out.setdefault(k, {"w": 0, "l": 0, "p": 0, "units": 0.0, "pl": 0.0, "clv_n": 0, "clv_beat": 0})
            s["w"] += p["result"] == "Won"; s["l"] += p["result"] == "Lost"; s["p"] += p["result"] == "Push"
            s["units"] = round(s["units"] + (p.get("units") or 0), 2); s["pl"] = round(s["pl"] + (p.get("pl") or 0), 2)
            if p.get("clv") is not None:
                s["clv_n"] += 1; s["clv_beat"] += p["clv"] > 0
    return dict(sorted(out.items()))


def tiers(picks):
    """Confidence calibration: how each confidence band has actually done."""
    bands = [("8.0+", 8.0, 99), ("7.0-7.9", 7.0, 8.0), ("5.5-6.9", 5.5, 7.0), ("under 5.5", 0, 5.5)]
    out = []
    for name, lo, hi in bands:
        sel = [p for p in picks if p["result"] in ("Won", "Lost") and p.get("conf") is not None and lo <= p["conf"] < hi]
        w = sum(1 for p in sel if p["result"] == "Won")
        clv = [p["clv"] for p in sel if p.get("clv") is not None]
        out.append({"band": name, "w": w, "l": len(sel) - w, "win": round(w / len(sel), 3) if sel else None,
                    "clv_beat": sum(1 for c in clv if c > 0), "clv_n": len(clv)})
    return out


def bankroll(picks, settings):
    base = settings.get("bankroll_base", 636.23); since = settings.get("base_date", "2026-11-12")
    pl = sum(p.get("pl") or 0 for p in picks if p["date"] >= since and p["decision"] == "CASH" and not p.get("skipped"))
    pl += sum(x.get("pl") or 0 for x in load("parlays.json", []) if x["date"] >= since and x.get("decision") == "CASH")
    return round(base + pl, 2)
