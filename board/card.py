"""Build today's card for every sport.

Each game: two models vs the DraftKings line ESPN shows, plus the factors the Board always checked -
injuries (QB / star players), rest and back-to-backs, weather and wind (outdoor football), NHL starting goalies,
line movement since open, key numbers, totals. Then the Board's rules decide CASH / PAPER / WATCH / PASS.

MAIN (cash, Capped card) needs ALL of: both models agree past the bar, confidence 7.0+ (8.0+ for midweek/G5 CFB,
rule L-1112-1), no veto, and the sport is on your cash list (data/settings.json "cash_approved"; football and NBA by
default, CBB/NHL stay paper until you graduate them). Up to 3 mains a day, $50 at 8.0+, $25 at 7.0-7.9.
The past-games test still feeds confidence (a failing test halves the efficiency points and zeroes price),
and our own recent record nudges it by at most +/-0.5 (board/history.py).
"""
import datetime
from .common import SPORTS, POWER_CONF, ct_time, american_to_prob, norm_cdf, load
from . import espn, model, history

UNITS = {"8": 50, "7": 25}
CASH_GATE = {"min_games": 200, "min_win": 0.535}  # break-even at -110 is 52.4%; we want a cushion
TOTAL_BAR = {"NFL": 4.0, "CFB": 5.0, "NBA": 6.0, "CBB": 6.0, "NHL": 0.6}
KEY_NUMBERS = {"NFL": (3, 7, 10, 6, 4), "CFB": (3, 7, 10, 14)}


def cfb_tier(g):
    hp = g["hconf"] in POWER_CONF or g["hid"] == "87"; ap = g["aconf"] in POWER_CONF or g["aid"] == "87"
    return "P4vP4" if hp and ap else "G5/mixed"


def cfb_day(g):
    d = ct_time(g["date"]).strftime("%a")
    return "Sat" if d == "Sat" else ("Midweek" if d in ("Tue", "Wed", "Thu", "Fri") else d)


def bucket_record(sport, g, bt, btl):
    """Past-games test record for this kind of pick (both models agree past the bar)."""
    if sport == "CFB":
        return bt.get("CFB", {}).get(f"{cfb_tier(g)} {cfb_day(g)}")
    if sport == "NFL":
        return bt.get("NFL", {}).get("Sun" if ct_time(g["date"]).strftime("%a") == "Sun" else "Prime/other")
    s = btl.get(sport) or {}
    return s.get("both_agree")


def key_injuries(inj, team):
    rows = inj.get(team, [])
    return [r for r in rows if str(r.get("status", "")).lower() in ("out", "questionable", "doubtful", "day-to-day")][:10]


def rest_days(past, team_id, start_iso):
    st = ct_time(start_iso).date(); last = None
    for g in past:
        if team_id in (g["hid"], g["aid"]):
            d = ct_time(g["date"]).date()
            if d < st and (last is None or d > last):
                last = d
    return (st - last).days if last else None


def team_totals(past, cap_n=None):
    """Points for / against per game for each team (season)."""
    pf, pa, n = {}, {}, {}
    for g in past:
        for t, f, a in ((g["hid"], g["hs"], g["as"]), (g["aid"], g["as"], g["hs"])):
            pf[t] = pf.get(t, 0) + f; pa[t] = pa.get(t, 0) + a; n[t] = n.get(t, 0) + 1
    return {t: (pf[t] / n[t], pa[t] / n[t], n[t]) for t in n}


def build(sport, date, bt, btl, settings):
    cfg = SPORTS[sport]
    slate = [g for g in espn.scoreboard(sport, date) if g["state"] == "pre"]
    if not slate:
        return {"sport": sport, "games": [], "note": "No games today."}
    past = espn.season_results(sport, date)
    R = model.ridge_ratings(past, cfg["hfa"], cfg["cap"], cfg["lam"])
    L = model.last_n(past, cfg["cap"], 10 if sport in ("NBA", "NHL") else 8)
    F5 = model.last_n(past, cfg["cap"], 5)
    P = espn.power_index(sport) if cfg["power"] else {}
    gp = model.games_played(past)
    TT = team_totals(past)
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
        if sport in ("CFB", "NFL", "CBB"):
            mA, mB, nA, nB = p_m, r_m, ("FPI" if sport != "CBB" else "BPI"), "Ratings"
        else:
            mA, mB, nA, nB = r_m, l_m, "Ratings", "Last 10"
        row = {"id": g["id"], "sport": sport, "game": f"{g['away']} @ {g['home']}", "home": g["home"], "away": g["away"],
               "time": ct_time(g["date"]).strftime("%a %-I:%M %p CT"), "start": g["date"], "book": g.get("book"), "line": g.get("details"),
               "home_line": g.get("home_line"), "home_line_open": g.get("home_line_open"), "spread_odds": [g.get("away_spread_odds"), g.get("home_spread_odds")],
               "total": g.get("total"), "total_open": g.get("total_open"), "home_ml": g.get("home_ml"), "away_ml": g.get("away_ml"),
               "model_a_name": nA, "model_b_name": nB, "model_a": None if mA is None else round(mA, 1), "model_b": None if mB is None else round(mB, 1),
               "games_played": [gp.get(g["aid"], 0), gp.get(g["hid"], 0)], "neutral": g["neutral"], "records": [g.get("arecord"), g.get("hrecord")],
               "venue": g.get("venue"), "tv": g.get("tv"), "indoor": g.get("indoor"),
               "inj_home": key_injuries(inj, g["home"]), "inj_away": key_injuries(inj, g["away"]),
               "stars": [g.get("aleaders") or [], g.get("hleaders") or []], "goalies": [g.get("agoalie"), g.get("hgoalie")],
               "rest": [rest_days(past, g["aid"], g["date"]), rest_days(past, g["hid"], g["date"])],
               "form5": [round(F5[g["aid"]][0], 1) if F5.get(g["aid"], (0, 0))[1] >= 4 else None, round(F5[g["hid"]][0], 1) if F5.get(g["hid"], (0, 0))[1] >= 4 else None],
               "decision": "PASS", "reason": "", "flags": [], "factors": [], "against": [], "invalidation": []}
        if sport == "CFB":
            row["tier"] = cfb_tier(g); row["day"] = cfb_day(g)
        if sport in ("NFL", "CFB") and g.get("indoor") is False:
            try:
                row["wind"] = espn.wind_at(g.get("city"), g.get("state_abbr"), g["date"])
            except Exception:
                row["wind"] = None
            row["weather"] = g.get("weather")
        # totals projection: season points for/against, and a recent-form version
        if g["hid"] in TT and g["aid"] in TT:
            h, a = TT[g["hid"]], TT[g["aid"]]
            row["total_model"] = round((h[0] + a[1]) / 2 + (a[0] + h[1]) / 2, 1)
        add_factors(row, sport, cfg)
        if sport == "NHL":
            screen_nhl(row, g, mA, mB, cfg, btl)
        else:
            screen_spread(row, g, mA, mB, cfg, sport, bt, btl)
        screen_total(row, sport)
        finalize(row, sport, settings)
        rows.append(row)
    order = {"CASH": 0, "PAPER": 1, "WATCH": 2, "PASS": 3}
    rows.sort(key=lambda r: (order[r["decision"]], -(r.get("conf") or 0)))
    return {"sport": sport, "games": rows, "n_past": len(past), "model_note": MODEL_NOTE[sport]}


MODEL_NOTE = {
    "NFL": "FPI (ESPN's season power rating) and an opponent-adjusted ratings model from every game played this season. Checks QB status, weather and wind, rest (short weeks), key numbers 3 and 7.",
    "CFB": "FPI and an opponent-adjusted ratings model from every FBS game this season. Checks QB status, weather and wind, conference tier and weekday (L-1112-1), key numbers.",
    "NBA": "Opponent-adjusted ratings model and last-10-games form. Checks star players (team leaders) on the injury report, back-to-backs and rest, line movement.",
    "CBB": "BPI and an opponent-adjusted ratings model. Early season leans on preseason priors. Sides only.",
    "NHL": "Ratings model (goal margin) and last-10 form turned into win chances vs the moneyline. Checks probable starting goalies and back-to-backs. Tracking only.",
}


def add_factors(row, sport, cfg):
    f, fl = row["factors"], row["flags"]
    ra, rh = row["rest"]
    if ra is not None and rh is not None:
        f.append(f"Rest: {row['away'].split(' ')[-1]} {ra} day(s), {row['home'].split(' ')[-1]} {rh} day(s)")
        if sport in ("NBA", "NHL"):
            if ra == 1: fl.append(f"{row['away']} on a back-to-back")
            if rh == 1: fl.append(f"{row['home']} on a back-to-back")
    hl, ho = row.get("home_line"), row.get("home_line_open")
    if hl is not None and ho is not None and hl != ho:
        fav = row["home"] if hl < ho else row["away"]
        f.append(f"Line moved {abs(hl - ho):g} pts toward {fav} since open ({ho:+g} to {hl:+g} home)")
    if row.get("wind"):
        w = row["wind"]; f.append(f"Kickoff forecast: wind {w['wind']:.0f} mph (gusts {w['gust']:.0f}), {w['temp']:.0f}F, rain chance {w['rain']}%")
        if w["wind"] >= 15: fl.append("Wind 15+ mph - passing and kicking take a hit (lean under, not a bet by itself)")
    if row.get("indoor"):
        f.append("Indoors - weather does not matter")
    if sport == "NHL":
        ga, gh = row["goalies"]
        f.append(f"Probable goalies: {ga or 'not posted'} ({row['away'].split(' ')[-1]}), {gh or 'not posted'} ({row['home'].split(' ')[-1]})")
        if not ga or not gh: fl.append("Starting goalie not posted yet")
    # QB / star checks
    for side, team, inj, stars in (("away", row["away"], row["inj_away"], row["stars"][0]), ("home", row["home"], row["inj_home"], row["stars"][1])):
        for x in inj:
            st = str(x.get("status", "")).lower()
            if sport in ("NFL", "CFB") and x.get("pos") == "QB" and st in ("out", "questionable", "doubtful"):
                fl.append(f"QB {x['player']} ({team}) {x['status']} - QB rule: no bet on this game until settled")
                row.setdefault("veto_sides", []).append("game")
            if sport == "NBA" and x.get("player") in stars and st in ("out", "questionable", "doubtful", "day-to-day"):
                fl.append(f"Star {x['player']} ({team}) {x['status']}")
                if st != "out":
                    row.setdefault("veto_sides", []).append("game")


def playable(line, gap_min, bar):
    """Worst number still worth it: the line can move against us by (gap - bar) before the edge is gone."""
    room = max(0.0, gap_min - bar)
    return round(line - room, 1)


def screen_spread(row, g, mA, mB, cfg, sport, bt, btl):
    hl = g.get("home_line")
    if hl is None or mA is None or mB is None:
        row["reason"] = "Missing line or a model number - no call."; return
    mkt = -hl
    gA, gB = mA - mkt, mB - mkt
    row["gap_a"], row["gap_b"] = round(gA, 1), round(gB, 1)
    bar = cfg["bar"]
    both = (gA >= bar and gB >= bar) or (gA <= -bar and gB <= -bar)
    one = max(abs(gA), abs(gB)) >= bar
    side_home = (gA + gB) > 0
    gap_min = min(abs(gA), abs(gB)) if both else max(abs(gA), abs(gB))
    row["gap_min"] = round(gap_min, 1)
    team = g["home"] if side_home else g["away"]; line = hl if side_home else -hl
    odds = row["spread_odds"][1 if side_home else 0] or -110
    row["pick"] = f"{team} {line:+g}"; row["price"] = odds; row["side"] = "home" if side_home else "away"
    avg = (mA + mB) / 2
    fair = -avg if side_home else avg
    row["fair_line"] = round(fair, 1)
    row["playable_to"] = playable(line, gap_min, bar) if both else None
    p = norm_cdf((avg - mkt) / cfg["sd"]); row["sim_cover"] = round(p if side_home else 1 - p, 3)
    fl, ag = row["flags"], row["against"]
    if sport == "CFB" and (row.get("tier") == "G5/mixed" or row.get("day") == "Midweek"):
        fl.append("L-1112-1: midweek or small-conference game - no $25 single (8.0+ only)")
    if max(abs(gA), abs(gB)) >= 7:
        fl.append("A model is 7+ points from the market - re-check warning, not a reason to bet")
    if sport == "CBB" and min(row["games_played"]) < 5:
        fl.append("Early season: under 5 games for a team - prior-heavy")
    veto = abs(gA - gB) >= 10
    if veto:
        fl.append("Models 10+ points apart - automatic pass")
    # against-the-pick factors
    ho = row.get("home_line_open")
    if ho is not None and ho != hl:
        moved_toward_us = (hl > ho) if side_home else (hl < ho)
        (ag if not moved_toward_us else row["factors"]).append(("Market moved away from this side since open" if not moved_toward_us else "Market moved toward this side since open (we get a worse number than early bettors)"))
    if sport in KEY_NUMBERS and line < 0 and any(abs(line) - 0.5 == k for k in KEY_NUMBERS[sport][:2]):
        ag.append(f"Laying {line:g} - just past a key number ({abs(line) - 0.5:g})")
    ra, rh = row["rest"]
    if ra is not None and rh is not None:
        mine, theirs = (rh, ra) if side_home else (ra, rh)
        if mine < theirs and (sport in ("NBA", "NHL") and mine == 1 or sport in ("NFL",) and mine < 6):
            ag.append("Our side has less rest")
    if both and abs(gA) < abs(gB) * 0.5:
        ag.append("One model is only barely past the bar")
    fa, fh = row.get("form5") or [None, None]
    if fa is not None and fh is not None:
        mine, theirs = (fh, fa) if side_home else (fa, fh)
        gap5 = mine - theirs
        if gap5 <= -bar:
            ag.append(f"Last 5 games point the other way (our side {mine:+.1f} a game, theirs {theirs:+.1f})")
        elif gap5 >= bar:
            row["factors"].append(f"Last 5 games agree (our side {mine:+.1f} a game, theirs {theirs:+.1f})")
    row["history"] = history.record(history.main_buckets(sport, row["pick"]))
    rec = bucket_record(sport, g, bt, btl)
    row["test_record"] = rec
    row["models_agree"] = both
    row["one_model"] = one and not both
    row["veto"] = veto or bool(row.get("veto_sides"))
    row["conf"], row["components"] = confidence(row, gap_min, bar, both)
    row["invalidation"] = inval(row, sport)


def screen_nhl(row, g, mA, mB, cfg, btl):
    hm, am = g.get("home_ml"), g.get("away_ml")
    if hm is None or am is None or mA is None or mB is None:
        row["reason"] = "Missing price or model - no call."; return
    ph, pa = american_to_prob(hm), american_to_prob(am); mkt_h = ph / (ph + pa)
    pA = norm_cdf(mA / cfg["sd"]); pB = norm_cdf(mB / cfg["sd"])
    eA, eB = (pA - mkt_h) * 100, (pB - mkt_h) * 100
    row["gap_a"], row["gap_b"] = round(eA, 1), round(eB, 1)
    row["win_prob"] = [round(1 - (pA + pB) / 2, 3), round((pA + pB) / 2, 3)]; row["market_prob"] = [round(1 - mkt_h, 3), round(mkt_h, 3)]
    bar = cfg["bar"]
    both = (eA >= bar and eB >= bar) or (eA <= -bar and eB <= -bar)
    side_home = (eA + eB) > 0
    price = hm if side_home else am
    row["pick"] = f"{g['home'] if side_home else g['away']} ML ({price:+d})"; row["price"] = price; row["side"] = "home" if side_home else "away"
    gap_min = min(abs(eA), abs(eB)) if both else max(abs(eA), abs(eB))
    row["gap_min"] = round(gap_min, 1)
    pfair = (pA + pB) / 2 if side_home else 1 - (pA + pB) / 2
    row["fair_line"] = int(round(-100 * pfair / (1 - pfair))) if pfair >= 0.5 else int(round(100 * (1 - pfair) / pfair))
    if max(abs(eA), abs(eB)) >= 12:
        row["flags"].append("A model is 12+ win-chance points from the market - re-check warning, not a reason to bet")
    row["models_agree"] = both; row["one_model"] = (max(abs(eA), abs(eB)) >= bar) and not both; row["veto"] = False
    row["test_record"] = (btl.get("NHL") or {}).get("both_agree")
    row["history"] = history.record(history.main_buckets("NHL", row["pick"]))
    row["conf"], row["components"] = confidence(row, gap_min / 2, bar / 2, both)
    row["invalidation"] = ["A different goalie starts for either team", f"Price moves past {row['fair_line']:+d} (our fair price)"]


def screen_total(row, sport):
    t, tm = row.get("total"), row.get("total_model")
    if t is None or tm is None or sport == "NHL":
        return
    diff = tm - float(t)
    row["total_gap"] = round(diff, 1)
    if abs(diff) >= TOTAL_BAR[sport]:
        row["total_lean"] = f"{'Over' if diff > 0 else 'Under'} {t} (season scoring says {tm}) - WATCH only, totals have no past-games test yet"


def confidence(row, gap_min, bar, both):
    """The Board's 8-part scorecard, filled from data (max 10)."""
    fl = row["flags"]; ag = row["against"]
    eff = 2.0 * min(1.0, gap_min / (2 * bar))
    veto = 0.0 if row.get("veto") else (1.0 if any("re-check warning" in x for x in fl) else 1.5)
    models = 1.5 if both else (0.5 if row.get("one_model") else 0.0)
    inj_flags = sum(1 for x in fl if x.startswith(("QB", "Star", "Starting goalie")))
    starters = max(0.0, 1.5 - 0.75 * inj_flags)
    against = max(0.0, 1.0 - 0.35 * len(ag))
    tr = row.get("test_record") or {}
    tw = tr.get("win") if tr.get("win") is not None else (tr["w"] / (tr["w"] + tr["l"]) if tr.get("w", 0) + tr.get("l", 0) else 0)
    # data first: a gap only counts fully if past games show this kind of gap actually wins
    if tw < 0.524:
        eff *= 0.5
    price = 1.0 if tr.get("n", 0) >= 200 and tw >= 0.535 else (0.5 if tw >= 0.524 else 0.0)
    coaching = 0.5  # not measured automatically - held at neutral
    situational = 0.5 if not any("back-to-back" in x for x in fl) else 0.2
    comps = {"efficiency": round(eff, 2), "veto": veto, "models": models, "starters": round(starters, 2), "coaching": coaching,
             "against": round(against, 2), "price": price, "situational": situational,
             "our history": (row.get("history") or {}).get("adj", 0.0)}
    total = round(max(0.0, min(10.0, sum(comps.values()))), 1)
    if not both:
        total = min(total, 6.9)  # one model alone is never a single
    return total, comps


def inval(row, sport):
    out = []
    if row.get("playable_to") is not None:
        out.append(f"Line moves past {row['playable_to']:+g}")
    if sport in ("NFL", "CFB"):
        out.append("Either starting QB is ruled out or downgraded")
    if sport == "NBA":
        out.append("A star on either team changes status (questionable to out or back in)")
    if sport == "CBB":
        out.append("Key starter news (CBB injury reports are thin - check before tip)")
    return out


def finalize(row, sport, settings):
    if "pick" not in row:
        return
    conf = row["conf"]; rec = row.get("test_record")
    approved = sport in (settings.get("cash_approved") or [])
    l1112 = any(f.startswith("L-1112-1") for f in row["flags"]) and conf < 8.0
    if row.get("veto"):
        row["decision"] = "PASS"; row["reason"] = "Veto: " + "; ".join(x for x in row["flags"] if x.startswith(("QB", "Star", "Models 10+")))
        return
    if not row["models_agree"]:
        row["decision"] = "WATCH" if row["one_model"] else "PASS"
        row["reason"] = "Only one model clears the bar - never a bet by itself." if row["one_model"] else "Neither model clears the bar."
        return
    test = f" Past-games test for this kind of pick: {rec['win'] * 100:.1f}% over {rec['n']}." if rec and rec.get("n") else " No past-games test for this kind of pick."
    if approved and conf >= 7.0 and not l1112:
        row["decision"] = "CASH"; row["stake"] = UNITS["8"] if conf >= 8.0 else UNITS["7"]
        row["reason"] = f"Both models clear the bar, confidence {conf}." + test
        return
    row["decision"] = "PAPER" if conf >= 5.5 else "WATCH"; row["stake"] = 0
    why = []
    if not approved:
        why.append(f"{sport} is a paper sport until you graduate it ('approve {sport}')")
    if conf < 7.0:
        why.append(f"confidence {conf} is under 7.0")
    if l1112:
        why.append("L-1112-1 (midweek or small-conference CFB needs 8.0+)")
    row["reason"] = "Both models agree, but " + "; ".join(why) + "." + test
