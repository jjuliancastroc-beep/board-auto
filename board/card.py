"""Build today's card for every sport: screen each game with two models against the DraftKings line ESPN shows,
apply the Board's rules, attach the past-games test record for that kind of pick, and decide paper vs cash."""
from .common import SPORTS, POWER_CONF, ct_time, american_to_prob, norm_cdf, load
from . import espn, model

UNITS = {"8": 50, "7": 25}
CASH_GATE = {"min_games": 200, "min_win": 0.535}  # break-even at -110 is 52.4%; we want a cushion


def cfb_tier(g):
    hp = g["hconf"] in POWER_CONF or g["hid"] == "87"; ap = g["aconf"] in POWER_CONF or g["aid"] == "87"
    return "P4vP4" if hp and ap else "G5/mixed"


def cfb_day(g):
    return "Sat" if ct_time(g["date"]).strftime("%a") == "Sat" else ("Midweek" if ct_time(g["date"]).strftime("%a") in ("Tue", "Wed", "Thu", "Fri") else ct_time(g["date"]).strftime("%a"))


def bucket_record(sport, g, bt):
    """Past-games test record for this kind of pick (gap over the bar, both models agree)."""
    if sport == "CFB":
        return bt.get("CFB", {}).get(f"{cfb_tier(g)} {cfb_day(g)}")
    if sport == "NFL":
        return bt.get("NFL", {}).get("Sun" if ct_time(g["date"]).strftime("%a") == "Sun" else "Prime/other")
    return None


def confidence(gap_min, bar, both, flags, veto):
    eff = 2.0 * min(1.0, gap_min / (2 * bar))
    comps = {"efficiency": round(eff, 2), "veto": 0.0 if veto else 1.5, "models": 1.5 if both else 0.5,
             "starters": 0.8 if flags else 1.3, "coaching": 0.5, "against": 0.5, "price": 0.6, "situational": 0.25}
    return round(sum(comps.values()), 1), comps


def key_injuries(inj, team):
    rows = inj.get(team, [])
    out = [r for r in rows if str(r.get("status", "")).lower() in ("out", "questionable", "doubtful", "day-to-day")]
    return out[:8]


def build(sport, date, bt):
    cfg = SPORTS[sport]
    slate = [g for g in espn.scoreboard(sport, date) if g["state"] == "pre"]
    if not slate:
        return {"sport": sport, "games": [], "note": "No games today."}
    past = espn.season_results(sport, date)
    R = model.ridge_ratings(past, cfg["hfa"], cfg["cap"], cfg["lam"])
    L = model.last_n(past, cfg["cap"], 10 if sport in ("NBA", "NHL") else 8)
    P = espn.power_index(sport) if cfg["power"] else {}
    gp = model.games_played(past)
    try:
        inj = espn.injuries(sport) if sport in ("NFL", "NBA", "NHL", "CFB") else {}
    except Exception:
        inj = {}
    rows = []
    for g in slate:
        hfa = 0 if g["neutral"] else cfg["hfa"]
        r_m = (R.get(g["hid"], 0) - R.get(g["aid"], 0) + hfa) if (g["hid"] in R and g["aid"] in R) else None
        l_m = (L[g["hid"]][0] - L[g["aid"]][0] + hfa) if (g["hid"] in L and g["aid"] in L) else None
        p_m = (P[g["hid"]] - P[g["aid"]] + hfa) if (g["hid"] in P and g["aid"] in P) else None
        # model pair per sport: power index + ratings where ESPN has one, else ratings + last games
        if sport in ("CFB", "NFL", "CBB"):
            mA, mB, nA, nB = p_m, r_m, ("FPI" if sport != "CBB" else "BPI"), "Ratings"
        else:
            mA, mB, nA, nB = r_m, l_m, "Ratings", "Last 10"
        row = {"id": g["id"], "sport": sport, "game": f"{g['away']} @ {g['home']}", "home": g["home"], "away": g["away"],
               "time": ct_time(g["date"]).strftime("%a %-I:%M %p CT"), "start": g["date"], "book": g.get("book"), "line": g.get("details"),
               "home_line": g.get("home_line"), "total": g.get("total"), "home_ml": g.get("home_ml"), "away_ml": g.get("away_ml"),
               "model_a_name": nA, "model_b_name": nB, "model_a": None if mA is None else round(mA, 1), "model_b": None if mB is None else round(mB, 1),
               "games_played": [gp.get(g["aid"], 0), gp.get(g["hid"], 0)], "neutral": g["neutral"],
               "inj_home": key_injuries(inj, g["home"]), "inj_away": key_injuries(inj, g["away"]), "decision": "PASS", "reason": "", "flags": []}
        if sport == "CFB":
            row["tier"] = cfb_tier(g); row["day"] = cfb_day(g)
        if sport == "NHL":
            screen_nhl(row, g, mA, mB, cfg)
        else:
            screen_spread(row, g, mA, mB, cfg, sport, bt)
        rows.append(row)
    rows.sort(key=lambda r: (0 if r["decision"] != "PASS" else 1, -(r.get("gap_min") or 0)))
    return {"sport": sport, "games": rows, "n_past": len(past)}


def screen_spread(row, g, mA, mB, cfg, sport, bt):
    hl = g.get("home_line")
    if hl is None or mA is None or mB is None:
        row["reason"] = "Missing line or a model number - no call."; return
    mkt = -hl  # market's home margin
    gA, gB = mA - mkt, mB - mkt
    row["gap_a"], row["gap_b"] = round(gA, 1), round(gB, 1)
    both = (gA >= cfg["bar"] and gB >= cfg["bar"]) or (gA <= -cfg["bar"] and gB <= -cfg["bar"])
    side_home = gA > 0
    gap_min = min(abs(gA), abs(gB)) if both else max(abs(gA), abs(gB))
    row["gap_min"] = round(gap_min, 1)
    team = g["home"] if side_home else g["away"]; line = hl if side_home else -hl
    row["pick"] = f"{team} {line:+g}"
    sim_p = norm_cdf(((mA + mB) / 2 - mkt) / cfg["sd"]) if side_home else 1 - norm_cdf(((mA + mB) / 2 - mkt) / cfg["sd"])
    row["sim_cover"] = round(sim_p, 3)
    flags = []
    if sport == "CFB" and (row.get("tier") == "G5/mixed" or row.get("day") == "Midweek"):
        flags.append("L-1112-1: midweek or small-conference game - no $25 single (8.0+ only)")
    if sport in ("NBA",) and (row["inj_home"] or row["inj_away"]) and any(str(x["status"]).lower() in ("questionable", "doubtful", "day-to-day") for x in row["inj_home"] + row["inj_away"]):
        flags.append("Questionable players listed - star veto check before tip")
    if max(abs(gA), abs(gB)) >= 7:
        flags.append("A model is 7+ points from the market - re-check warning, not a reason to bet")
    if sport == "CBB" and min(row["games_played"]) < 5:
        flags.append("Early season: under 5 games for a team - prior-heavy")
    veto = abs(gA - gB) >= 10
    if veto:
        flags.append("Models 10+ points apart - automatic pass")
    conf, comps = confidence(gap_min, cfg["bar"], both, flags, veto)
    row["conf"], row["components"], row["flags"] = conf, comps, flags
    rec = bucket_record(sport, g, bt)
    row["test_record"] = rec
    if not both or veto:
        row["decision"] = "WATCH" if (not veto and max(abs(gA), abs(gB)) >= cfg["bar"]) else "PASS"
        row["reason"] = "Only one model clears the bar." if row["decision"] == "WATCH" else ("Models disagree by 10+." if veto else "Neither model clears the bar.")
        return
    tested = rec and rec.get("n", 0) >= CASH_GATE["min_games"] and rec.get("win", 0) >= CASH_GATE["min_win"]
    l1112_block = any(f.startswith("L-1112-1") for f in flags) and conf < 8.0
    if tested and conf >= 7.0 and not l1112_block:
        row["decision"] = "CASH"; row["stake"] = UNITS["8"] if conf >= 8.0 else UNITS["7"]
        row["reason"] = f"Both models clear the bar and this kind of pick has won {rec['win']*100:.1f}% over {rec['n']} past games."
    else:
        row["decision"] = "PAPER"; row["stake"] = 0
        why = []
        if not rec:
            why.append("no past-games test for this sport yet")
        elif not tested:
            why.append(f"this kind of pick won {rec['win']*100:.1f}% over {rec['n']} past games - not enough to beat the -110 price")
        if conf < 7.0:
            why.append(f"confidence {conf} is under 7.0")
        if l1112_block:
            why.append("L-1112-1")
        row["reason"] = "Both models clear the bar, but " + "; ".join(why) + "."


def screen_nhl(row, g, mA, mB, cfg):
    hm, am = g.get("home_ml"), g.get("away_ml")
    if hm is None or am is None or mA is None or mB is None:
        row["reason"] = "Missing price or model - no call."; return
    ph, pa = american_to_prob(hm), american_to_prob(am); mkt_h = ph / (ph + pa)
    pA = norm_cdf(mA / cfg["sd"]); pB = norm_cdf(mB / cfg["sd"])
    eA, eB = (pA - mkt_h) * 100, (pB - mkt_h) * 100
    row["gap_a"], row["gap_b"] = round(eA, 1), round(eB, 1)
    both = (eA >= cfg["bar"] and eB >= cfg["bar"]) or (eA <= -cfg["bar"] and eB <= -cfg["bar"])
    side_home = eA > 0
    row["pick"] = f"{g['home'] if side_home else g['away']} ML ({(hm if side_home else am):+d})"
    row["gap_min"] = round(min(abs(eA), abs(eB)) if both else max(abs(eA), abs(eB)), 1)
    row["conf"], row["components"] = confidence(row["gap_min"] / 2, cfg["bar"] / 2, both, [], False)
    row["test_record"] = None
    if both:
        row["decision"] = "PAPER"; row["stake"] = 0; row["reason"] = f"Both models see {row['gap_min']} win-probability points of value; NHL is tracking only (no past-games test yet)."
    else:
        row["reason"] = "Edge under 5 points on at least one model."
