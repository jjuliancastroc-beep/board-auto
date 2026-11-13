"""Player props, built the same way as the main card.

Lines: Underdog's public pick'em board (free, no key) - the line and Underdog's own price for each side.
Stats: ESPN game logs for every player with a line (this season, plus last season when the sample is small).

For each line the Board works out:
  projection   - recent form weighted toward the last 5 and 10 games, per minute where minutes exist,
                 scaled by the team's implied points from the betting line vs its season average
  our chance   - a count model (negative binomial fit to the player's own spread) blended with his real hit rate
  Underdog's   - the chance implied by Underdog's price for that side (vig removed)
  hit rates    - last 5, last 10, this season, last season, vs this opponent
  role         - minutes / time on ice / targets / attempts, recent vs season
  flags        - injury status, teammates out, back-to-back, blowout risk, small sample
Then a 10-point scorecard and a call: PLAY (7.0+ and 5+ points better than Underdog), LEAN (5.5+ and 3+), else PASS.
Props are their own section: tracked and graded, never part of the main card or bankroll unless you say you placed one.
"""
import math, re, unicodedata, datetime, statistics
from concurrent.futures import ThreadPoolExecutor
from .common import get, load, save, now_ct, ct_time, SPORTS, american_to_prob
from . import espn

UD_URL = "https://api.underdogfantasy.com/v1/over_under_lines"
GL_URL = "https://site.web.api.espn.com/apis/common/v3/sports/{path}/athletes/{aid}/gamelog{q}"
ROSTER_URL = "https://site.api.espn.com/apis/site/v2/sports/{path}/teams/{tid}/roster"
SEARCH_URL = "https://site.web.api.espn.com/apis/common/v3/search?query={q}&type=player&limit=8"

GROUP = {"NBA": "B", "CBB": "B", "NFL": "F", "CFB": "F", "NHL": "H"}
# underdog stat -> (label, ESPN game-log fields summed, kind)  kind: score = moves with team scoring, vol = volume, def = defensive/random
STATS = {
    "B": {"points": ("Points", ["points"], "score"), "rebounds": ("Rebounds", ["totalRebounds"], "vol"), "assists": ("Assists", ["assists"], "vol"),
          "three_points_made": ("3-pointers made", ["threePointFieldGoalsMade"], "score"), "pts_rebs_asts": ("Pts+Reb+Ast", ["points", "totalRebounds", "assists"], "score"),
          "pts_rebs": ("Pts+Reb", ["points", "totalRebounds"], "score"), "pts_asts": ("Pts+Ast", ["points", "assists"], "score"),
          "rebs_asts": ("Reb+Ast", ["totalRebounds", "assists"], "vol"), "steals": ("Steals", ["steals"], "def"), "blocks": ("Blocks", ["blocks"], "def"),
          "blks_stls": ("Blocks+Steals", ["blocks", "steals"], "def"), "turnovers": ("Turnovers", ["turnovers"], "def")},
    "F": {"passing_yds": ("Pass yards", ["passingYards"], "score"), "passing_tds": ("Pass TDs", ["passingTouchdowns"], "score"),
          "passing_comps": ("Completions", ["completions"], "vol"), "passing_att": ("Pass attempts", ["passingAttempts"], "vol"),
          "passing_ints": ("Interceptions", ["interceptions"], "def"), "rushing_yds": ("Rush yards", ["rushingYards"], "score"),
          "rushing_att": ("Rush attempts", ["rushingAttempts"], "vol"), "receiving_yds": ("Receiving yards", ["receivingYards"], "score"),
          "receiving_rec": ("Receptions", ["receptions"], "vol"), "receiving_tgts": ("Targets", ["receivingTargets"], "vol"),
          "rush_rec_yds": ("Rush+Rec yards", ["rushingYards", "receivingYards"], "score"), "passing_and_rushing_yds": ("Pass+Rush yards", ["passingYards", "rushingYards"], "score"),
          "rush_rec_tds": ("Rush+Rec TDs", ["rushingTouchdowns", "receivingTouchdowns"], "score")},
    "H": {"goals": ("Goals", ["goals"], "score"), "assists": ("Assists", ["assists"], "score"), "points": ("Points", ["goals", "assists"], "score"),
          "shots": ("Shots on goal", ["shotsTotal"], "vol"), "power_play_points": ("Power-play points", ["powerPlayGoals", "powerPlayAssists"], "score"),
          "saves": ("Saves", ["saves"], "vol"), "goals_against": ("Goals against", ["goalsAgainst"], "def")},
}
# default spread (variance / mean) by stat when the player's own sample is small
DISP = {"points": 1.9, "rebounds": 1.5, "assists": 1.6, "three_points_made": 1.4, "pts_rebs_asts": 2.2, "pts_rebs": 2.0, "pts_asts": 2.0, "rebs_asts": 1.6,
        "steals": 1.1, "blocks": 1.3, "blks_stls": 1.2, "turnovers": 1.2, "passing_yds": 22, "passing_tds": 1.0, "passing_comps": 1.6, "passing_att": 2.0,
        "passing_ints": 1.0, "rushing_yds": 14, "rushing_att": 2.0, "receiving_yds": 16, "receiving_rec": 1.4, "receiving_tgts": 1.5, "rush_rec_yds": 15,
        "passing_and_rushing_yds": 22, "rush_rec_tds": 1.0, "goals": 1.0, "shots": 1.2, "power_play_points": 1.0, "saves": 2.5, "goals_against": 1.2}
ALIASES = [("pts+reb+ast", "pts_rebs_asts"), ("pra", "pts_rebs_asts"), ("pts+reb", "pts_rebs"), ("pr", "pts_rebs"), ("pts+ast", "pts_asts"), ("pa", "pts_asts"),
           ("reb+ast", "rebs_asts"), ("ra", "rebs_asts"), ("blk+stl", "blks_stls"), ("stocks", "blks_stls"), ("3pm", "three_points_made"), ("threes", "three_points_made"),
           ("3s", "three_points_made"), ("3pt", "three_points_made"), ("points", "points"), ("pts", "points"), ("rebounds", "rebounds"), ("rebs", "rebounds"), ("reb", "rebounds"),
           ("assists", "assists"), ("ast", "assists"), ("steals", "steals"), ("stl", "steals"), ("blocks", "blocks"), ("blk", "blocks"), ("turnovers", "turnovers"), ("to", "turnovers"),
           ("pass yds", "passing_yds"), ("passing yards", "passing_yds"), ("pass yards", "passing_yds"), ("pass tds", "passing_tds"), ("passing tds", "passing_tds"),
           ("completions", "passing_comps"), ("attempts", "passing_att"), ("ints", "passing_ints"), ("interceptions", "passing_ints"),
           ("rush+rec yds", "rush_rec_yds"), ("rush+rec yards", "rush_rec_yds"), ("pass+rush yds", "passing_and_rushing_yds"), ("rush yds", "rushing_yds"), ("rushing yards", "rushing_yds"),
           ("rush yards", "rushing_yds"), ("carries", "rushing_att"), ("rush att", "rushing_att"), ("rec yds", "receiving_yds"), ("receiving yards", "receiving_yds"),
           ("rec yards", "receiving_yds"), ("receptions", "receiving_rec"), ("catches", "receiving_rec"), ("rec", "receiving_rec"), ("targets", "receiving_tgts"),
           ("anytime td", "rush_rec_tds"), ("tds", "rush_rec_tds"), ("td", "rush_rec_tds"), ("shots on goal", "shots"), ("sog", "shots"), ("shots", "shots"), ("goals", "goals"),
           ("ppp", "power_play_points"), ("power play points", "power_play_points"), ("saves", "saves")]
PLAY = {"conf": 7.0, "edge": 5.0}; LEAN = {"conf": 5.5, "edge": 3.0}
BREAK_EVEN = 0.55   # an Underdog 3-pick pays 6x -> each pick needs about 55%; a 2-pick (3x) needs about 58%


def norm(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]", " ", s)
    return " ".join(w for w in s.split() if w not in ("jr", "sr", "ii", "iii", "iv", "v"))


# ---------------- data ----------------
def underdog():
    d = get(UD_URL, timeout=90)
    if not d:
        return None
    P = {p["id"]: p for p in d.get("players", [])}; A = {a["id"]: a for a in d.get("appearances", [])}; G = {g["id"]: g for g in d.get("games", [])}
    out, seen = [], set()
    for l in d.get("over_under_lines", []):
        if l.get("status") != "active" or len(l.get("options") or []) != 2:
            continue
        st = (l.get("over_under") or {}).get("appearance_stat") or {}
        ap = A.get(st.get("appearance_id")); 
        if not ap:
            continue
        pl = P.get(ap["player_id"]) or {}; sport = pl.get("sport_id")
        if sport not in GROUP or st.get("stat") not in STATS[GROUP[sport]]:
            continue
        g = G.get(ap.get("match_id")) or {}
        key = (pl["id"], st["stat"])
        if key in seen:
            continue
        seen.add(key)
        opts = {o["choice"]: o for o in l["options"]}
        try:
            ph, pl_ = american_to_prob(int(opts["higher"]["american_price"])), american_to_prob(int(opts["lower"]["american_price"]))
            mh = ph / (ph + pl_)
        except Exception:
            mh = 0.5
        out.append({"sport": sport, "player": f"{pl.get('first_name', '')} {pl.get('last_name', '')}".strip(), "pos": pl.get("position_name"),
                    "stat": st["stat"], "line": float(l["stat_value"]), "mkt_higher": round(mh, 3),
                    "mult": {k: v.get("payout_multiplier") for k, v in opts.items()}, "price": {k: v.get("american_price") for k, v in opts.items()},
                    "game_title": g.get("full_team_names_title") or g.get("title"), "start": g.get("scheduled_at"), "ud_id": l["id"]})
    return out


def _num(v):
    if v in (None, "", "-", "--"):
        return 0.0
    if isinstance(v, str) and ":" in v:
        m, s = v.split(":")[:2]
        return int(m) + int(s) / 60
    try:
        return float(v)
    except Exception:
        return 0.0


def gamelog(path, aid, season=None):
    d = get(GL_URL.format(path=path, aid=aid, q=f"?season={season}" if season else ""))
    if not d or not d.get("names"):
        return [], None
    names = d["names"]; meta = d.get("events") or {}
    prev = None
    for f in d.get("filters", []):
        if f.get("name") == "season":
            opts = [o["value"] for o in f.get("options", [])]
            if f.get("value") in opts and opts.index(f["value"]) + 1 < len(opts):
                prev = opts[opts.index(f["value"]) + 1]
    games = []
    for stype in d.get("seasonTypes", []):
        if "preseason" in stype.get("displayName", "").lower():
            continue
        for cat in stype.get("categories", []):
            for e in cat.get("events", []):
                m = meta.get(e["eventId"]) or {}
                row = {}
                for n, v in zip(names, e.get("stats", [])):
                    if "-" in n and isinstance(v, str) and "-" in v and ":" not in v:
                        a, b = n.split("-"); x, y = (v.split("-") + ["0"])[:2]
                        row[a] = _num(x); row[b] = _num(y)
                    else:
                        row[n] = _num(v)
                games.append({"eid": e["eventId"], "date": (m.get("gameDate") or "")[:10], "opp": (m.get("opponent") or {}).get("abbreviation"),
                              "opp_id": (m.get("opponent") or {}).get("id"), "home": m.get("atVs") != "@", "res": m.get("gameResult"), "s": row})
    uniq = {g["eid"]: g for g in games}
    return sorted(uniq.values(), key=lambda g: g["date"], reverse=True), prev


def role_field(group, stat):
    if group == "B":
        return "minutes", "Minutes"
    if group == "H":
        return ("shotsAgainst", "Shots faced") if stat in ("saves", "goals_against") else ("timeOnIcePerGame", "Ice time")
    if stat.startswith("passing"):
        return "passingAttempts", "Pass attempts"
    if stat.startswith("rushing") or stat == "rush_rec_yds":
        return ("rushingAttempts", "Carries")
    return "receivingTargets", "Targets"


def played(g, group, stat):
    s = g["s"]
    if group == "B":
        return s.get("minutes", 0) > 0
    if group == "H":
        return s.get("timeOnIcePerGame", 0) > 0 or s.get("saves", 0) > 0 or s.get("gameStarted", 0) > 0
    return any(v for v in s.values())


# ---------------- math ----------------
def nb_cdf(k, mu, disp):
    """P(X <= k) for a count with mean mu and variance mu*disp (Poisson when disp ~ 1)."""
    if k < 0:
        return 0.0
    mu = max(mu, 1e-6); tot = 0.0
    if disp <= 1.02:
        lp = -mu
        for i in range(int(k) + 1):
            tot += math.exp(lp); lp += math.log(mu) - math.log(i + 1)
        return min(1.0, tot)
    r = mu / (disp - 1); p = r / (r + mu)
    for i in range(int(k) + 1):
        tot += math.exp(math.lgamma(i + r) - math.lgamma(r) - math.lgamma(i + 1) + r * math.log(p) + i * math.log(1 - p))
    return min(1.0, tot)


def p_over(line, mu, disp):
    if mu > 400:  # big yardage: normal approximation
        sd = math.sqrt(mu * disp)
        return 1 - 0.5 * (1 + math.erf((line + (0.5 if line == int(line) else 0) - mu) / (sd * math.sqrt(2))))
    if line == int(line):
        below = nb_cdf(line - 1, mu, disp); at = nb_cdf(line, mu, disp) - below
        return max(0.0, (1 - below - at) / max(1e-9, 1 - at))
    return 1 - nb_cdf(math.floor(line), mu, disp)


def wavg(parts):
    num = sum(w * v for w, v in parts if v is not None); den = sum(w for w, v in parts if v is not None)
    return num / den if den else None


def avg(xs):
    return sum(xs) / len(xs) if xs else None


# ---------------- evaluate one line ----------------
def evaluate(line_row, ath, games_cur, games_prev, ctx):
    sport = line_row["sport"]; group = GROUP[sport]; stat = line_row["stat"]
    label, fields, kind = STATS[group][stat]
    L = line_row["line"]
    val = lambda g: sum(g["s"].get(f, 0) for f in fields)
    rf, rlabel = role_field(group, stat)
    cur = [g for g in games_cur if played(g, group, stat)]; prv = [g for g in games_prev if played(g, group, stat)]
    out = {**line_row, "espn_id": ath["id"], "team": ath.get("team"), "team_id": ath.get("team_id"), "opp": ctx.get("opp"), "game": ctx.get("game"),
           "event_id": ctx.get("event_id"), "label": label, "flags": [], "for": [], "against": []}
    n_all = len(cur) + len(prv)
    if n_all < 3:
        out.update(call="PASS", conf=0, reason=f"Only {n_all} games of data - not enough to judge.")
        return out
    vc = [val(g) for g in cur]; vp = [val(g) for g in prv]
    l5, l10 = vc[:5], vc[:10]
    use_rate = group in ("B", "H") and rf in ("minutes", "timeOnIcePerGame")
    if use_rate:
        rate = lambda gs: (sum(val(g) for g in gs) / sum(g["s"].get(rf, 0) for g in gs)) if gs and sum(g["s"].get(rf, 0) for g in gs) > 0 else None
        r = wavg([(0.35, rate(cur[:5])), (0.30, rate(cur[:10])), (0.20, rate(cur)), (0.15 if len(cur) < 10 else 0.05, rate(prv))])
        mins = [g["s"].get(rf, 0) for g in cur] or [g["s"].get(rf, 0) for g in prv]
        exp_role = wavg([(0.5, avg(mins[:5])), (0.3, avg(mins[:10])), (0.2, avg(mins))])
        mu = r * exp_role
    else:
        mu = wavg([(0.35, avg(l5)), (0.30, avg(l10)), (0.20, avg(vc)), (0.15 if len(cur) < 6 else 0.05, avg(vp))])
        roles = [g["s"].get(rf, 0) for g in cur]
        exp_role = avg(roles[:5]) if roles else None
    # role trend
    roles_c = [g["s"].get(rf, 0) for g in cur]
    role_l5, role_season = avg(roles_c[:5]), avg(roles_c)
    role_chg = (role_l5 / role_season - 1) if role_l5 and role_season else 0
    # environment: team implied points from the game line vs season scoring
    env = 1.0
    if ctx.get("implied") and ctx.get("team_avg"):
        raw = ctx["implied"] / ctx["team_avg"]
        strength = {"score": 0.6, "vol": 0.3, "def": 0.0}[kind]
        env = max(0.88, min(1.12, 1 + (raw - 1) * strength))
    adj = env
    if ctx.get("b2b") and group == "B":
        adj *= 0.97; out["flags"].append("Back-to-back: minutes usually dip a little")
    if ctx.get("blowout") and group in ("B",):
        adj *= 0.97; out["flags"].append(f"Spread {ctx['spread']:+g}: blowout risk could cut starters' minutes")
    mu *= adj
    # spread of outcomes from his own games (shrunk toward the stat default)
    allv = vc + vp
    m0 = avg(allv)
    sdisp = (statistics.pvariance(allv) / m0) if len(allv) >= 4 and m0 and m0 > 0 else DISP.get(stat, 1.5)
    k = len(allv)
    disp = max(1.0, (k * sdisp + 8 * DISP.get(stat, 1.5)) / (k + 8))
    pm = p_over(L, mu, disp)
    # blend with his real hit rate (this season full weight, last season half)
    hit = lambda vs: (sum(1 for v in vs if v > L), sum(1 for v in vs if v != L))
    hc, nc = hit(vc); hp, np_ = hit(vp)
    K = 8
    p_hi = (hc + 0.5 * hp + K * pm) / (nc + 0.5 * np_ + K)
    mh = line_row["mkt_higher"]
    out["p_raw_higher"] = round(p_hi, 4)
    W = ctx.get("w", 0.35)  # until graded lines prove our numbers, trust Underdog's price this much: p = market + W*(ours - market)
    p_hi = mh + W * (p_hi - mh)
    side = "higher" if p_hi >= mh else "lower"
    p = p_hi if side == "higher" else 1 - p_hi; mk = mh if side == "higher" else 1 - mh; edge = (p - mk) * 100
    good = (lambda v: v > L) if side == "higher" else (lambda v: v < L)
    rate_s = lambda vs: (sum(1 for v in vs if good(v)), sum(1 for v in vs if v != L))
    vs_opp = [val(g) for g in cur + prv if g.get("opp_id") == ctx.get("opp_id")]
    home_v = [val(g) for g in cur if g["home"]]; away_v = [val(g) for g in cur if not g["home"]]
    # playable: worst line where our chance stays at 55%+
    play_to = None
    step = 0.5 if L < 60 else 2.5
    for i in range(0, 41):
        t = L + i * step if side == "higher" else L - i * step
        pp = p_over(t, mu, disp); pp = pp if side == "higher" else 1 - pp
        if pp >= BREAK_EVEN:
            play_to = t
        else:
            break
    out.update(side=side, pick=f"{line_row['player']} {'Higher' if side == 'higher' else 'Lower'} {L:g} {label}", proj=round(mu, 1), p=round(p, 3), mkt=round(mk, 3),
               edge=round(edge, 1), p_model=round(pm if side == "higher" else 1 - pm, 3), disp=round(disp, 2), playable_to=play_to,
               hits={"L5": rate_s(l5), "L10": rate_s(l10), "season": rate_s(vc), "last season": rate_s(vp), "vs opp": rate_s(vs_opp)},
               avgs={"L5": r1(avg(l5)), "L10": r1(avg(l10)), "season": r1(avg(vc)), "last season": r1(avg(vp)), "home": r1(avg(home_v)), "away": r1(avg(away_v)), "vs opp": r1(avg(vs_opp))},
               role={"label": rlabel, "L5": r1(role_l5), "season": r1(role_season), "exp": r1(exp_role), "chg": round(role_chg * 100)},
               env={"implied": ctx.get("implied"), "team_avg": ctx.get("team_avg"), "factor": round(env, 3), "spread": ctx.get("spread"), "total": ctx.get("total")},
               n={"season": len(cur), "last season": len(prv)},
               log=[{"date": g["date"][5:], "opp": ("vs " if g["home"] else "@ ") + str(g["opp"] or ""), "role": r1(g["s"].get(rf, 0)), "v": r1(val(g))} for g in (cur + prv)[:12]])
    # ---- reasons ----
    diff = mu - L
    out["for" if (diff > 0) == (side == "higher") else "against"].append(f"Projection {mu:.1f} vs line {L:g}")
    for k_, (h, n) in out["hits"].items():
        if n >= 4 and k_ in ("L10", "season", "last season"):
            (out["for"] if h / n >= 0.6 else out["against"] if h / n <= 0.4 else []).append(f"{k_}: {h}/{n} {'over' if side == 'higher' else 'under'} {L:g}")
    if abs(role_chg) >= 0.1 and role_l5:
        up = role_chg > 0
        (out["for"] if up == (side == "higher") else out["against"]).append(f"{rlabel} {'up' if up else 'down'} {abs(role_chg) * 100:.0f}% lately ({role_l5:.1f} last 5 vs {role_season:.1f})")
    if abs(env - 1) >= 0.02 and kind != "def":
        up = env > 1
        (out["for"] if up == (side == "higher") else out["against"]).append(f"Team expected to score {ctx['implied']:.1f} vs its {ctx['team_avg']:.1f} average")
    st_ = (ath.get("status") or "").lower()
    if st_ in ("out", "doubtful", "suspension"):
        out.update(call="PASS", conf=0, reason=f"Listed {ath['status']}.", p=p); return out
    if st_ in ("questionable", "day-to-day", "probable"):
        out["flags"].append(f"Listed {ath['status']} - check before the game")
    for t in ctx.get("teammates_out") or []:
        out["flags"].append(f"Teammate out: {t} - more shots/touches to go around")
    if nc < 5:
        out["flags"].append(f"Small sample: {nc} games this season")
    if edge >= 15:
        out["flags"].append("Our chance is 15+ points off Underdog's - re-check warning, not a reason to play")
    # ---- scorecard (max 10) ----
    sd = math.sqrt(mu * disp) if mu > 0 else 1
    margin = abs(diff) / sd if (diff > 0) == (side == "higher") else 0
    comp = {}
    comp["data"] = round(2.0 * min(1.0, margin / 0.6), 2)
    hr = [h / n for k_, (h, n) in out["hits"].items() if n >= 4 and k_ in ("L5", "L10", "season", "last season")]
    comp["hit rates"] = round(1.5 * (sum(1 for x in hr if x >= 0.6) / len(hr)), 2) if hr else 0.3
    comp["vs Underdog"] = 1.5 if edge >= 8 else 1.0 if edge >= 5 else 0.5 if edge >= 3 else 0.0
    comp["role"] = 0.5 if abs(role_chg) < 0.1 else (1.0 if (role_chg > 0) == (side == "higher") else 0.0)
    comp["availability"] = 0.3 if st_ in ("questionable", "day-to-day") else 1.0
    comp["matchup"] = 0.5 if abs(env - 1) < 0.02 or kind == "def" else (1.0 if (env > 1) == (side == "higher") else 0.0)
    comp["sample"] = 1.0 if nc >= 10 else 0.6 if nc >= 5 else 0.2
    tr = ctx.get("test") or {}
    comp["test record"] = 1.0 if tr.get("n", 0) >= 200 and tr.get("win", 0) >= 0.55 else 0.5 if tr.get("n", 0) >= 200 and tr.get("win", 0) >= 0.53 else 0.0
    conf = round(sum(comp.values()) - (0.5 if edge >= 15 else 0) - (0.25 if ctx.get("b2b") and group == "B" else 0) - (0.25 if ctx.get("blowout") else 0), 1)
    if len(cur) < (4 if group == "F" else 5):
        conf = min(conf, 6.4)  # too few games this season to be a PLAY
    out["components"] = comp; out["conf"] = conf
    if mk > 0.62:
        out["call"] = "PASS"; out["reason"] = f"Underdog's price on this side is steep (it already implies {mk * 100:.0f}%) - skip."
    elif conf >= PLAY["conf"] and edge >= PLAY["edge"] and p >= BREAK_EVEN:
        out["call"] = "PLAY"; out["reason"] = f"Our chance {p * 100:.0f}% vs Underdog's {mk * 100:.0f}%, and the numbers line up."
    elif conf >= LEAN["conf"] and edge >= LEAN["edge"] and p >= 0.53:
        out["call"] = "LEAN"; out["reason"] = f"Our chance {p * 100:.0f}% vs Underdog's {mk * 100:.0f}% - leg only, not strong enough alone."
    else:
        out["call"] = "PASS"; out["reason"] = f"Our chance {p * 100:.0f}% vs Underdog's {mk * 100:.0f}% - not enough."
    out["invalidation"] = [f"Line moves past {play_to:g}" if play_to is not None else "Any line move against us",
                           "He's ruled out, questionable, or on a minutes limit" if group == "B" else "He's ruled out or his role changes (injury, benching)"]
    if group == "H" and stat in ("saves", "goals_against"):
        out["invalidation"].append("He's not the confirmed starting goalie")
    return out


def r1(x):
    return None if x is None else round(x, 1)


# ---------------- build the day ----------------
def _match_game(title, start, slate):
    """Underdog game -> ESPN game: start within 3 hours and the team names overlap."""
    if not title or not start:
        return None
    tw = set(norm(title).split()); t0 = ct_time(start); best, bs = None, 0
    for g in slate:
        if abs((ct_time(g["date"]) - t0).total_seconds()) > 3 * 3600:
            continue
        ew = set(norm(f"{g['away']} {g['home']}").split())
        sc = len(tw & ew) / max(1, len(ew))
        if sc > bs:
            best, bs = g, sc
    return best if bs >= 0.5 else None


def team_scoring(sport, date):
    past = espn.season_results(sport, date)
    pf, n = {}, {}
    for g in past:
        for tid, s in ((g["hid"], g["hs"]), (g["aid"], g["as"])):
            pf[tid] = pf.get(tid, 0) + s; n[tid] = n.get(tid, 0) + 1
    return {t: pf[t] / n[t] for t in n if n[t] >= 2}


def build(dates, cards_by_id=None):
    lines = underdog()
    if lines is None:
        return {"ok": False, "note": "Underdog's board didn't load this run.", "props": [], "dates": dates}
    cards_by_id = cards_by_id or {}
    want = [l for l in lines if l["start"] and ct_time(l["start"]).strftime("%Y-%m-%d") in dates]
    slates = {}
    for sport in {l["sport"] for l in want}:
        for d in dates:
            slates.setdefault(sport, []).extend(g for g in espn.scoreboard(sport, d) if g["state"] == "pre")
    # rosters for matched games only
    today = now_ct().strftime("%Y-%m-%d")
    cache = {"date": today, "rosters": {}, "logs": {}}  # fetched fresh each run (fast); not saved
    games_needed = {}
    for l in want:
        g = _match_game(l["game_title"], l["start"], slates.get(l["sport"], []))
        if g:
            l["_g"] = g; games_needed[(l["sport"], g["id"])] = g
    def fetch_roster(key):
        sport, tid = key
        if f"{sport}|{tid}" in cache["rosters"]:
            return
        r = get(ROSTER_URL.format(path=SPORTS[sport]["path"], tid=tid))
        ath = []
        for a in (r or {}).get("athletes", []):
            ath += a.get("items", []) if "items" in a else [a]
        cache["rosters"][f"{sport}|{tid}"] = [{"id": a["id"], "name": a.get("fullName") or a.get("displayName"), "pos": (a.get("position") or {}).get("abbreviation"),
                                              "status": ((a.get("injuries") or [{}])[0].get("status")) if a.get("injuries") else None} for a in ath]
    teams = {(s, tid) for (s, _), g in games_needed.items() for tid in (g["hid"], g["aid"])}
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(fetch_roster, teams))
    index = {}
    for (s, gid), g in games_needed.items():
        for tid, team in ((g["hid"], g["home"]), (g["aid"], g["away"])):
            for a in cache["rosters"].get(f"{s}|{tid}", []):
                index.setdefault((s, gid, norm(a["name"])), {**a, "team": team, "team_id": tid})
    # injuries + scoring context
    inj = {}
    for s in {l["sport"] for l in want}:
        try:
            inj[s] = espn.injuries(s) if s != "CBB" else {}
        except Exception:
            inj[s] = {}
    scoring = {}
    for s in {l["sport"] for l in want}:
        try:
            scoring[s] = team_scoring(s, today)
        except Exception:
            scoring[s] = {}
    jobs = []
    for l in want:
        g = l.get("_g")
        if not g:
            continue
        a = index.get((l["sport"], g["id"], norm(l["player"])))
        if not a:
            continue
        for r in inj.get(l["sport"], {}).get(a["team"], []):
            if norm(r["player"]) == norm(a["name"]) and r.get("status"):
                a = {**a, "status": r["status"]}
        jobs.append((l, a, g))
    def fetch_log(aid_sport):
        aid, sport = aid_sport
        if aid in cache["logs"]:
            return
        cur, prev = gamelog(SPORTS[sport]["path"], aid)
        small = len(cur) < (6 if GROUP[sport] == "F" else 10)
        pv = gamelog(SPORTS[sport]["path"], aid, prev)[0] if (small and prev) else []
        cache["logs"][aid] = {"cur": slim(cur), "prev": slim(pv)}
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(fetch_log, {(a["id"], l["sport"]) for l, a, g in jobs}))
    calib = load("props_calib.json", {}); W = weight(calib); test = calib.get("calls") or {}
    out = []
    for l, a, g in jobs:
        lg = cache["logs"].get(a["id"]) or {"cur": [], "prev": []}
        home = a["team_id"] == g["hid"]
        ctx = {"game": f"{g['away']} @ {g['home']}", "event_id": g["id"], "opp": g["away"] if home else g["home"], "opp_id": g["aid"] if home else g["hid"],
               "spread": None, "total": g.get("total")}
        hl = g.get("home_line")
        if g.get("total") and hl is not None and l["sport"] != "NHL":
            ctx["spread"] = hl if home else -hl
            ctx["implied"] = round((g["total"] - hl) / 2 if home else (g["total"] + hl) / 2, 1)
        elif g.get("total") and l["sport"] == "NHL" and g.get("home_ml") and g.get("away_ml"):
            ph = american_to_prob(g["home_ml"]); pa = american_to_prob(g["away_ml"]); wp = ph / (ph + pa)
            ctx["implied"] = round(g["total"] / 2 + ((wp if home else 1 - wp) - 0.5) * 1.2, 2)
        ctx["team_avg"] = scoring.get(l["sport"], {}).get(a["team_id"])
        ctx["blowout"] = ctx["spread"] is not None and abs(ctx["spread"]) >= {"NBA": 11, "CBB": 15}.get(l["sport"], 99)
        c = cards_by_id.get(g["id"]) or {}
        rest = c.get("rest") or [None, None]
        ctx["b2b"] = (rest[1] if home else rest[0]) == 1 if rest else False
        leaders = set((g.get("hleaders") if home else g.get("aleaders")) or [])
        ctx["w"] = W; ctx["test"] = test
        ctx["teammates_out"] = [r["player"] for r in inj.get(l["sport"], {}).get(a["team"], []) if str(r.get("status", "")).lower() == "out" and r["player"] in leaders and norm(r["player"]) != norm(a["name"])]
        try:
            row = evaluate(l, a, lg["cur"], lg["prev"], ctx)
        except Exception as e:
            row = {**l, "call": "PASS", "conf": 0, "reason": f"Could not evaluate: {e}", "label": l["stat"]}
        row.pop("_g", None); row["date"] = ct_time(l["start"]).strftime("%Y-%m-%d"); row["time"] = ct_time(l["start"]).strftime("%a %-I:%M %p CT")
        row["id"] = f"{row['date']}|{a['id']}|{l['stat']}"
        out.append(row)
    order = {"PLAY": 0, "LEAN": 1, "PASS": 2}
    out.sort(key=lambda r: (r["date"], order.get(r["call"], 3), -(r.get("conf") or 0), -(r.get("edge") or 0)))
    # keep the list usable: max 10 PLAYs and 25 LEANs a day, 1 call per player, 2 per game; the rest drop to PASS with a note
    caps = {"PLAY": 10, "LEAN": 25}; seen = {}
    for r in out:
        if r["call"] not in caps:
            continue
        d = seen.setdefault(r["date"], {"PLAY": 0, "LEAN": 0, "players": set(), "games": {}})
        if r["player"] in d["players"]:
            r["call"] = "PASS"; r["reason"] += " (already have a call on this player)"; continue
        if d["games"].get(r["event_id"], 0) >= 2:
            r["call"] = "PASS"; r["reason"] += " (already 2 calls in this game)"; continue
        if d[r["call"]] >= caps[r["call"]]:
            if r["call"] == "PLAY" and d["LEAN"] < caps["LEAN"]:
                r["call"] = "LEAN"; r["reason"] += " (qualified as a PLAY but outside today's top 10)"
            else:
                r["call"] = "PASS"; r["reason"] += " (outside today's top calls)"; continue
        d[r["call"]] += 1; d["players"].add(r["player"]); d["games"][r["event_id"]] = d["games"].get(r["event_id"], 0) + 1
    out.sort(key=lambda r: (r["date"], order.get(r["call"], 3), -(r.get("conf") or 0), -(r.get("edge") or 0)))
    matched = len(jobs); total = len(want)
    return {"ok": True, "props": out, "dates": dates, "lines": total, "matched": matched,
            "note": f"{total} Underdog lines for these days; {matched} matched to ESPN players and graded."}


def slim(games):
    return [{"eid": g["eid"], "date": g["date"], "opp": g["opp"], "opp_id": g["opp_id"], "home": g["home"],
             "s": {k: v for k, v in g["s"].items() if v}} for g in games[:40]]


# ---------------- calibration: does our number beat Underdog's? ----------------
WGRID = [round(i / 10, 1) for i in range(11)]


def weight(calib):
    """How much to trust our number vs Underdog's. 0.35 until 2,000 graded lines; then whatever weight has scored best."""
    if (calib or {}).get("n", 0) < 2000:
        return 0.35
    ll = calib["ll"]
    return float(min(ll, key=lambda k: ll[k]))


def log_lines(props):
    """Keep every graded line's latest pre-game snapshot so we can test our numbers against Underdog's on all of them."""
    book = load("props_lines.json", {})
    now = now_ct()
    for p in props:
        if "p_raw_higher" not in p or ct_time(p["start"]) <= now:
            continue
        book[p["id"]] = {"sport": p["sport"], "stat": p["stat"], "aid": p["espn_id"], "eid": p["event_id"], "start": p["start"], "line": p["line"],
                         "pr": p["p_raw_higher"], "mh": round(p["mkt_higher"], 4), "call": p["call"], "side": p["side"], "edge": p.get("edge")}
    save("props_lines.json", book)
    return book


def grade_lines():
    """Grade finished lines, fold them into running totals (props_calib.json), and drop them from the snapshot file."""
    book = load("props_lines.json", {}); calib = load("props_calib.json", {})
    calib.setdefault("n", 0); calib.setdefault("ll", {str(w): 0.0 for w in WGRID}); calib.setdefault("bins", {})
    calib.setdefault("brier", {"underdog": 0.0, "ours": 0.0}); calib.setdefault("by_sport", {})
    now = now_ct(); logs = {}; done = []
    due = [(k, b) for k, b in book.items() if (now - ct_time(b["start"])).total_seconds() >= 4 * 3600]
    def fetch(x):
        aid, sport = x
        try:
            logs[aid] = gamelog(SPORTS[sport]["path"], aid)[0]
        except Exception:
            logs[aid] = None
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(fetch, {(b["aid"], b["sport"]) for k, b in due}))
    for k, b in due:
        g = next((x for x in (logs.get(b["aid"]) or []) if x["eid"] == str(b["eid"])), None)
        if not g:
            if (now - ct_time(b["start"])).total_seconds() > 36 * 3600:
                done.append(k)
            continue
        done.append(k)
        v = sum(g["s"].get(f, 0) for f in STATS[GROUP[b["sport"]]][b["stat"]][1])
        if v == b["line"]:
            continue
        y = 1 if v > b["line"] else 0
        calib["n"] += 1
        for w in WGRID:
            q = min(0.99, max(0.01, b["mh"] + w * (b["pr"] - b["mh"])))
            calib["ll"][str(w)] -= math.log(q if y else 1 - q)
        calib["brier"]["underdog"] += (b["mh"] - y) ** 2
        q = b["mh"] + 0.5 * (b["pr"] - b["mh"]); calib["brier"]["ours"] += (q - y) ** 2
        won = y == (1 if b["side"] == "higher" else 0)
        e = b.get("edge") or 0
        bn = "8+" if e >= 8 else "5-8" if e >= 5 else "3-5" if e >= 3 else "0-3"
        r = calib["bins"].setdefault(bn, [0, 0]); r[0 if won else 1] += 1
        r = calib["by_sport"].setdefault(b["sport"], [0, 0]); r[0 if won else 1] += 1
    for k in done:
        book.pop(k, None)
    # the official calls (PLAY/LEAN) record from props.json
    cb = [x for x in load("props.json", []) if x.get("result") in ("Won", "Lost") and x.get("source") == "Underdog board"]
    w_ = sum(1 for x in cb if x["result"] == "Won")
    calib["calls"] = {"n": len(cb), "w": w_, "l": len(cb) - w_, "win": round(w_ / len(cb), 3) if cb else 0}
    calib["weight"] = weight(calib)
    save("props_lines.json", book); save("props_calib.json", calib)
    return calib


# ---------------- entries, logging, grading ----------------
def entries(props, date):
    """Two Underdog 2-pick entries: one PLAY + one LEAN each, different games. Only one confident pick per entry."""
    day = [p for p in props if p.get("date") == date]
    plays = [p for p in day if p["call"] == "PLAY" and p["conf"] >= 7.0]
    leans = [p for p in day if p["call"] == "LEAN" and 5.5 <= p["conf"] < 7.0]
    out, used = [], set()
    for a in plays:
        if len(out) == 2:
            break
        if a["id"] in used:
            continue
        b = next((x for x in leans if x["id"] not in used and x["event_id"] != a["event_id"] and x["player"] != a["player"]), None)
        if not b:
            continue
        used |= {a["id"], b["id"]}
        out.append({"name": f"Entry {len(out) + 1}", "picks": [a["pick"], b["pick"]], "ids": [a["id"], b["id"]],
                    "chance": round(a["p"] * b["p"], 3), "why": f"Anchor {a['pick']} ({a['conf']}) + leg {b['pick']} ({b['conf']}). Different games, one confident pick."})
    return out


KEEP = ("id", "date", "sport", "player", "team", "opp", "game", "event_id", "espn_id", "stat", "label", "side", "line", "pick", "proj", "p", "mkt", "edge", "conf",
        "call", "start", "time", "playable_to")


def log(props):
    book = load("props.json", [])
    have = {p["id"]: p for p in book}
    now = now_ct()
    cur = {p["id"]: p for p in props}
    for p in props:
        if p["call"] in ("PLAY", "LEAN") and p["id"] not in have:
            row = {k: p.get(k) for k in KEEP}
            row.update(logged_at=now.strftime("%m/%d %I:%M %p"), close_line=p["line"], result=None, actual=None, placed=False, source="Underdog board")
            book.append(row); have[row["id"]] = row
    for b in book:  # keep the latest pre-game line as the close
        if b["result"] is None and b["id"] in cur and ct_time(b["start"]) > now:
            b["close_line"] = cur[b["id"]]["line"]
    save("props.json", book)
    return book


def grade(book=None):
    book = book if book is not None else load("props.json", [])
    now = now_ct(); logs = {}
    for b in book:
        if b["result"] is not None or not b.get("start") or (now - ct_time(b["start"])).total_seconds() < 4 * 3600:
            continue
        sport = b["sport"]; group = GROUP[sport]
        if b["espn_id"] not in logs:
            logs[b["espn_id"]] = gamelog(SPORTS[sport]["path"], b["espn_id"])[0]
        g = next((x for x in logs[b["espn_id"]] if x["eid"] == str(b["event_id"])), None)
        if not g:
            if (now - ct_time(b["start"])).total_seconds() > 36 * 3600:
                b["result"] = "Void"; b["actual"] = "did not play"
            continue
        v = sum(g["s"].get(f, 0) for f in STATS[group][b["stat"]][1])
        b["actual"] = v
        if v == b["line"]:
            b["result"] = "Push"
        else:
            b["result"] = "Won" if (v > b["line"]) == (b["side"] == "higher") else "Lost"
        cl = b.get("close_line")
        if cl is not None:
            b["clv"] = round((cl - b["line"]) if b["side"] == "higher" else (b["line"] - cl), 1)
    save("props.json", book)
    return book


def record(book):
    out = {}
    def add(k, b):
        r = out.setdefault(k, {"w": 0, "l": 0, "p": 0, "clv_beat": 0, "clv_n": 0})
        if b["result"] == "Won": r["w"] += 1
        elif b["result"] == "Lost": r["l"] += 1
        elif b["result"] == "Push": r["p"] += 1
        if b.get("clv") is not None and b["result"] in ("Won", "Lost"):
            r["clv_n"] += 1; r["clv_beat"] += 1 if b["clv"] > 0 else 0
    for b in book:
        if b["result"] in ("Won", "Lost", "Push"):
            if b.get("source") == "your request":
                add("Your requests", b); continue
            add("All props", b); add(f"{b['call']}s", b); add(b["sport"], b); add(b["label"], b)
            if b.get("placed"):
                add("Placed", b)
    return out


# ---------------- ask about any line (from a GitHub comment) ----------------
def parse_request(text):
    """'prop Jokic over 25.5 points'  ->  (name, side, line, stat)"""
    t = text.strip()
    m = re.match(r"^prop\s+(.+?)\s+(over|under|higher|lower|o|u)\s+(\d+(?:\.\d+)?)\s+(.+)$", t, re.I)
    if not m:
        return None
    name, side, line, stat_words = m.groups()
    sw = stat_words.lower().strip()
    stat = next((s for a, s in ALIASES if sw == a or sw.startswith(a + " ") or sw.replace(" ", "") == a.replace(" ", "")), None)
    if not stat:
        stat = next((s for a, s in ALIASES if a in sw), None)
    side = "higher" if side.lower() in ("over", "higher", "o") else "lower"
    return name.strip(), side, float(line), stat


LEAGUE = {"nba": "NBA", "mens-college-basketball": "CBB", "nfl": "NFL", "college-football": "CFB", "nhl": "NHL"}


def ask(text, cards_by_id=None):
    req = parse_request(text)
    if not req:
        return None
    name, side, line, stat = req
    if not stat:
        return [f"Couldn't tell which stat '{text}' means. Try points, rebounds, assists, pra, threes, pass yds, rush yds, rec yds, receptions, shots, saves."]
    d = get(SEARCH_URL.format(q=urllib_quote(name))) or {}
    hit = next((i for i in d.get("items", []) if i.get("league") in LEAGUE and stat in STATS[GROUP[LEAGUE[i["league"]]]]), None)
    if not hit:
        return [f"Couldn't find {name} in NBA/NFL/NHL/college with a {stat} stat."]
    sport = LEAGUE[hit["league"]]; tid = ((hit.get("teamRelationships") or [{}])[0].get("core") or {}).get("id")
    today = now_ct().strftime("%Y-%m-%d"); tmr = (now_ct() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    g = next((x for d_ in (today, tmr) for x in espn.scoreboard(sport, d_) if tid in (x["hid"], x["aid"]) and x["state"] == "pre"), None)
    if not g:
        return [f"{hit['displayName']} has no game today or tomorrow."]
    cur, prev = gamelog(SPORTS[sport]["path"], hit["id"])
    pv = gamelog(SPORTS[sport]["path"], hit["id"], prev)[0] if prev and len(cur) < 10 else []
    home = tid == g["hid"]
    ctx = {"game": f"{g['away']} @ {g['home']}", "event_id": g["id"], "opp": g["away"] if home else g["home"], "opp_id": g["aid"] if home else g["hid"], "total": g.get("total"), "spread": None}
    if g.get("total") and g.get("home_line") is not None and sport != "NHL":
        hl = g["home_line"]; ctx["spread"] = hl if home else -hl; ctx["implied"] = (g["total"] - hl) / 2 if home else (g["total"] + hl) / 2
        ctx["team_avg"] = team_scoring(sport, today).get(tid)
    ctx["blowout"] = ctx["spread"] is not None and abs(ctx["spread"]) >= {"NBA": 11, "CBB": 15}.get(sport, 99)
    mh, src = 0.5, None
    try:  # use Underdog's own price if it has this exact line
        u = next((x for x in (underdog() or []) if x["sport"] == sport and x["stat"] == stat and norm(x["player"]) == norm(hit["displayName"])), None)
        if u and u["line"] == line:
            mh, src = u["mkt_higher"], "Underdog"
        elif u:
            src = f"Underdog has this at {u['line']:g}, not {line:g}"
    except Exception:
        pass
    row = {"sport": sport, "player": hit["displayName"], "stat": stat, "line": line, "mkt_higher": mh, "start": g["date"], "game_title": ctx["game"]}
    ath = {"id": hit["id"], "team": (hit.get("teamRelationships") or [{}])[0].get("displayName"), "team_id": tid}
    r = evaluate(row, ath, slim(cur), slim(pv), ctx)
    if "side" in r and r["side"] != side:  # report the side you asked about
        r["note"] = f"The numbers lean the other way ({'Higher' if r['side'] == 'higher' else 'Lower'})."
    r["date"] = ct_time(g["date"]).strftime("%Y-%m-%d"); r["time"] = ct_time(g["date"]).strftime("%a %-I:%M %p CT"); r["id"] = f"{r['date']}|{hit['id']}|{stat}|ask"
    r["source"] = "your request"
    if src and src != "Underdog":
        r["note"] = ((r.get("note") or "") + f" {src}.").strip()
    book = load("props.json", [])
    if r.get("call") in ("PLAY", "LEAN", "PASS") and "side" in r and not any(b["id"] == r["id"] for b in book):
        b = {k: r.get(k) for k in KEEP}; b.update(logged_at=now_ct().strftime("%m/%d %I:%M %p"), close_line=line, result=None, actual=None, placed=False, source="your request", asked_side=side)
        book.append(b); save("props.json", book)
    return summary_lines(r)


def summary_lines(r):
    if "side" not in r:
        return [f"{r.get('player')} {r.get('label', '')}: {r.get('reason')}"]
    h = r["hits"]; a = r["avgs"]
    fmt = lambda x: f"{x[0]}/{x[1]}" if x[1] else "-"
    out = [f"{r['pick']} - {r['call']} (confidence {r['conf']})",
           f"{r['game']}, {r['time']}",
           f"Projection {r['proj']} | our chance {r['p'] * 100:.0f}%" + ("" if r["mkt"] == 0.5 else f" vs Underdog {r['mkt'] * 100:.0f}%"),
           f"Hit rate: last 5 {fmt(h['L5'])}, last 10 {fmt(h['L10'])}, season {fmt(h['season'])}, last season {fmt(h['last season'])}, vs {r['opp']} {fmt(h['vs opp'])}",
           f"Averages: last 5 {a['L5']}, last 10 {a['L10']}, season {a['season']}",
           f"{r['role']['label']}: last 5 {r['role']['L5']} vs season {r['role']['season']}",
           f"Playable to {r['playable_to']:g}" if r.get("playable_to") is not None else "Playable: not at 55%+ at any nearby line"]
    out += [f"For: {x}" for x in r["for"]] + [f"Against: {x}" for x in r["against"]] + [f"Flag: {x}" for x in r["flags"]]
    if r.get("note"):
        out.append(r["note"])
    return out


def urllib_quote(s):
    import urllib.parse
    return urllib.parse.quote(s)
