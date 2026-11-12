"""Log picks once (the first number we saw is the one we grade) and grade finished games from ESPN finals and closing lines."""
import datetime
from .common import load, save, now_ct, ct_time
from . import espn


def log_picks(cards, date):
    picks = load("picks.json", [])
    have = {(p["date"], p["id"]) for p in picks}
    for c in cards:
        for r in c["games"]:
            if r["decision"] in ("CASH", "PAPER", "WATCH") and (date, r["id"]) not in have:
                picks.append({"date": date, "id": r["id"], "sport": r["sport"], "game": r["game"], "home": r["home"], "away": r["away"], "start": r["start"],
                              "pick": r["pick"], "decision": r["decision"], "stake": r.get("stake", 0), "conf": r.get("conf"), "gap_a": r.get("gap_a"), "gap_b": r.get("gap_b"),
                              "line_at_pick": r.get("line"), "book": r.get("book"), "home_line": r.get("home_line"), "home_ml": r.get("home_ml"), "away_ml": r.get("away_ml"),
                              "flags": r.get("flags", []), "result": None, "final": None, "close": None, "clv": None})
    save("picks.json", picks)
    return picks


def _pick_team_line(p):
    txt = p["pick"]
    if " ML " in txt + " ":
        team = txt.split(" ML")[0]; return team, None
    team, ln = txt.rsplit(" ", 1)
    return team, float(ln)


def grade_all():
    picks = load("picks.json", []); now = now_ct(); changed = 0
    by_date = {}
    for p in picks:
        if p["result"] is not None:
            continue
        st = ct_time(p["start"])
        if now - st < datetime.timedelta(hours=3, minutes=30):
            continue
        key = (p["sport"], st.strftime("%Y-%m-%d"))
        if key not in by_date:
            by_date[key] = {g["id"]: g for g in espn.scoreboard(*key)}
        g = by_date[key].get(p["id"])
        if not g or not g["completed"]:
            if now - st > datetime.timedelta(days=3):
                p["result"] = "No result (postponed or not found)"; changed += 1
            continue
        team, ln = _pick_team_line(p)
        is_home = team == p["home"]
        margin = (g["hs"] - g["as"]) if is_home else (g["as"] - g["hs"])
        p["final"] = f"{g['away']} {g['as']}, {g['home']} {g['hs']}"
        if ln is None:
            p["result"] = "Won" if margin > 0 else "Lost"
            price = p["home_ml"] if is_home else p["away_ml"]
            p["units"] = round((price / 100 if price > 0 else 100 / abs(price)) if margin > 0 else -1.0, 2) if price else None
        else:
            v = margin + ln
            p["result"] = "Won" if v > 0 else "Lost" if v < 0 else "Push"
            p["units"] = 0.91 if v > 0 else (-1.0 if v < 0 else 0.0)
        if p.get("stake"):
            p["pl"] = round(p["stake"] * p["units"], 2) if p.get("units") is not None else 0
        cl = espn.closing_line(p["sport"], p["id"])
        if cl:
            p["close"] = cl.get("details") or (f"ML {cl.get('home_ml')}/{cl.get('away_ml')}")
            if ln is not None:
                chl = espn.home_line(cl.get("details"), g["habbr"], g["aabbr"])
                if chl is not None:
                    close_side = chl if is_home else -chl
                    p["clv"] = round(ln - close_side, 1)  # + means we had the better number
        changed += 1
    save("picks.json", picks)
    return picks, changed


def summary(picks):
    out = {}
    for p in picks:
        if p["result"] not in ("Won", "Lost", "Push"):
            continue
        k = f"{p['sport']} {p['decision']}"
        s = out.setdefault(k, {"w": 0, "l": 0, "p": 0, "units": 0.0, "pl": 0.0, "clv_n": 0, "clv_beat": 0})
        s["w"] += p["result"] == "Won"; s["l"] += p["result"] == "Lost"; s["p"] += p["result"] == "Push"
        s["units"] = round(s["units"] + (p.get("units") or 0), 2); s["pl"] = round(s["pl"] + (p.get("pl") or 0), 2)
        if p.get("clv") is not None:
            s["clv_n"] += 1; s["clv_beat"] += p["clv"] > 0
    return out
