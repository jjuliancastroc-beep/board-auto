"""Past-games test for NBA, NHL and college basketball (2025-26 season) using the same two models the live card uses.
Walk forward day by day: models only see games already played. Lines = ESPN's last pregame line (closing line).
Writes data/backtest_live.json.   Run: python -m backtest.bt_live [NBA NHL CBB]
"""
import sys, json, os, datetime, collections, concurrent.futures as cf
from board.common import SPORTS, get, load, save, american_to_prob, norm_cdf
from board import espn, model

SEASONS = {"NBA": ("2025-10-21", "2026-04-12"), "NHL": ("2025-10-07", "2026-04-16"), "CBB": ("2025-11-03", "2026-03-15")}


def day_games(sport, ds):
    key = f"hist/{sport}_{ds}.json"
    rows = load(key, None)
    if rows is None:
        rows = [g for g in espn.scoreboard(sport, ds) if g["completed"] and g["hs"] is not None]
        save(key, rows)
    return rows


def odds(sport, gid):
    key = f"hist/odds_{sport}.json"
    return None


def fetch_season(sport):
    a, b = SEASONS[sport]; d0 = datetime.date.fromisoformat(a); d1 = datetime.date.fromisoformat(b)
    days = [(d0 + datetime.timedelta(n)).isoformat() for n in range((d1 - d0).days + 1)]
    with cf.ThreadPoolExecutor(12) as ex:
        res = list(ex.map(lambda d: (d, day_games(sport, d)), days))
    games = []
    seen = set()
    for d, rows in res:
        for g in rows:
            if g["id"] not in seen:
                seen.add(g["id"]); g["day"] = d; games.append(g)
    oc = load(f"hist/odds_{sport}.json", {})
    need = [g["id"] for g in games if g["id"] not in oc or (oc[g["id"]] and "home_open" not in oc[g["id"]] and "home_ml_open" not in oc[g["id"]])]
    def one(gid):
        try:
            return gid, espn.closing_line(sport, gid)
        except Exception:
            return gid, None
    with cf.ThreadPoolExecutor(16) as ex:
        for gid, cl in ex.map(one, need):
            oc[gid] = cl
    save(f"hist/odds_{sport}.json", oc)
    return games, oc


def run(sport):
    cfg = SPORTS[sport]
    games, oc = fetch_season(sport)
    games.sort(key=lambda g: g["date"])
    by_day = collections.defaultdict(list)
    for g in games:
        by_day[g["day"]].append(g)
    past = []; rows = []
    for d in sorted(by_day):
        if len(past) > (150 if sport != "CBB" else 1500):
            R = model.ridge_ratings(past, cfg["hfa"], cfg["cap"], cfg["lam"])
            L = model.last_n(past, cfg["cap"], 10 if sport in ("NBA", "NHL") else 8)
            gp = model.games_played(past)
            for g in by_day[d]:
                cl = oc.get(g["id"])
                if not cl or g["hid"] not in R or g["aid"] not in R or g["hid"] not in L or g["aid"] not in L:
                    continue
                hfa = 0 if g["neutral"] else cfg["hfa"]
                mA = R[g["hid"]] - R[g["aid"]] + hfa; mB = L[g["hid"]][0] - L[g["aid"]][0] + hfa
                margin = g["hs"] - g["as"]
                r = {"day": d, "id": g["id"], "mA": round(mA, 2), "mB": round(mB, 2), "margin": margin, "gp": min(gp[g["hid"]], gp[g["aid"]]),
                     "b2b": None}
                if sport == "NHL":
                    hm, am = cl.get("home_ml"), cl.get("away_ml")
                    if hm is None or am is None:
                        continue
                    ph, pa = american_to_prob(hm), american_to_prob(am); mh = ph / (ph + pa)
                    r.update(hmo=cl.get("home_ml_open"), amo=cl.get("away_ml_open"), hm=hm, am=am, mkt=round(mh, 4), eA=round((norm_cdf(mA / cfg["sd"]) - mh) * 100, 2), eB=round((norm_cdf(mB / cfg["sd"]) - mh) * 100, 2))
                else:
                    hl = espn.home_line(cl.get("details"), g["habbr"], g["aabbr"])
                    if hl is None:
                        continue
                    r.update(hl=hl, gA=round(mA + hl, 2), gB=round(mB + hl, 2), total=cl.get("total"), pts=g["hs"] + g["as"], ho=cl.get("home_open"), to=cl.get("total_open"))
                rows.append(r)
        past.extend(by_day[d])
    return rows


def rec(sel):
    w = sum(1 for s in sel if s > 0); l = sum(1 for s in sel if s < 0)
    return {"w": w, "l": l, "n": w + l, "win": round(w / (w + l), 3) if w + l else 0}


def summarize(sport, rows):
    bar = SPORTS[sport]["bar"]; out = {"games": len(rows)}
    if sport == "NHL":
        def res(r, home):
            won = (r["margin"] > 0) == home
            price = r["hm"] if home else r["am"]
            u = (price / 100 if price > 0 else 100 / -price) if won else -1.0
            return won, u
        both = []
        for r in rows:
            if (r["eA"] >= bar and r["eB"] >= bar) or (r["eA"] <= -bar and r["eB"] <= -bar):
                both.append(res(r, r["eA"] > 0))
        w = sum(1 for x in both if x[0]); u = round(sum(x[1] for x in both), 2)
        out["both_agree"] = {"w": w, "l": len(both) - w, "n": len(both), "win": round(w / len(both), 3) if both else 0, "units": u, "roi": round(u / len(both), 3) if both else 0}
        for lo, hi in ((5, 8), (8, 12), (12, 99)):
            sel = [res(r, r["eA"] > 0) for r in rows if ((r["eA"] >= bar and r["eB"] >= bar) or (r["eA"] <= -bar and r["eB"] <= -bar)) and lo <= min(abs(r["eA"]), abs(r["eB"])) < hi]
            uu = round(sum(x[1] for x in sel), 2)
            out[f"edge {lo}-{hi if hi < 99 else '+'}"] = {"w": sum(1 for x in sel if x[0]), "l": sum(1 for x in sel if not x[0]), "n": len(sel), "units": uu, "roi": round(uu / len(sel), 3) if sel else 0}
        op = [r for r in rows if r.get("hmo") and r.get("amo")]
        beat = lost = 0; ws = 0; us = 0.0; n = 0
        for r in op:
            a, b = american_to_prob(r["hmo"]), american_to_prob(r["amo"]); mo = a / (a + b)
            eA = (norm_cdf(r["mA"] / SPORTS["NHL"]["sd"]) - mo) * 100; eB = (norm_cdf(r["mB"] / SPORTS["NHL"]["sd"]) - mo) * 100
            if not ((eA >= bar and eB >= bar) or (eA <= -bar and eB <= -bar)):
                continue
            home = eA > 0; n += 1
            clv = (r["mkt"] - mo) * (1 if home else -1)
            beat += clv > 0.005; lost += clv < -0.005
            won = (r["margin"] > 0) == home; price = r["hmo"] if home else r["amo"]
            ws += won; us += (price / 100 if price > 0 else 100 / -price) if won else -1.0
        out["vs opening line"] = {"n": n, "w": ws, "l": n - ws, "units": round(us, 2), "beat_close": beat, "lost_close": lost}
        fav = [res(r, r["mkt"] > 0.5) for r in rows]
        out["always favorite"] = {"n": len(fav), "units": round(sum(x[1] for x in fav), 2)}
        return out
    def cover(r, home):
        v = r["margin"] + r["hl"]
        return (v if home else -v)
    both = [cover(r, r["gA"] > 0) for r in rows if (r["gA"] >= bar and r["gB"] >= bar) or (r["gA"] <= -bar and r["gB"] <= -bar)]
    out["both_agree"] = rec(both)
    for lo, hi in ((0, 3), (3, bar), (bar, 7), (7, 10), (10, 99)):
        sel = [cover(r, r["gA"] > 0) for r in rows if lo <= abs(r["gA"]) < hi]
        out[f"ratings gap {lo}-{hi if hi < 99 else '+'}"] = rec(sel)
    out["early (<10 games)"] = rec([cover(r, r["gA"] > 0) for r in rows if r["gp"] < 10 and ((r["gA"] >= bar and r["gB"] >= bar) or (r["gA"] <= -bar and r["gB"] <= -bar))])
    out["later (10+ games)"] = rec([cover(r, r["gA"] > 0) for r in rows if r["gp"] >= 10 and ((r["gA"] >= bar and r["gB"] >= bar) or (r["gA"] <= -bar and r["gB"] <= -bar))])
    out["home dogs"] = rec([cover(r, True) for r in rows if r["hl"] > 0])
    out["fade both models"] = rec([cover(r, r["gA"] < 0) for r in rows if (r["gA"] >= bar and r["gB"] >= bar) or (r["gA"] <= -bar and r["gB"] <= -bar)])
    # opening-line test: models vs the OPEN number (what an early bettor gets) - cover vs open and line move toward us
    op = [r for r in rows if r.get("ho") is not None]
    sel = [r for r in op if ((r["mA"] + r["ho"]) >= bar and (r["mB"] + r["ho"]) >= bar) or ((r["mA"] + r["ho"]) <= -bar and (r["mB"] + r["ho"]) <= -bar)]
    def mv(r):
        home = (r["mA"] + r["ho"]) > 0
        return (r["ho"] - r["hl"]) * (1 if home else -1)  # + = we got a better number than the close
    cov = [((r["margin"] + r["ho"]) if (r["mA"] + r["ho"]) > 0 else -(r["margin"] + r["ho"])) for r in sel]
    moves = [mv(r) for r in sel]
    out["vs opening line"] = dict(rec(cov), beat_close=sum(1 for m in moves if m > 0), lost_close=sum(1 for m in moves if m < 0), avg_clv=round(sum(moves) / len(moves), 2) if moves else 0)
    miss_m = [abs(r["margin"] - (r["mA"])) for r in rows]; miss_k = [abs(r["margin"] + r["hl"]) for r in rows]
    out["avg miss: model vs market"] = [round(sum(miss_m) / len(miss_m), 2), round(sum(miss_k) / len(miss_k), 2)]
    return out


if __name__ == "__main__":
    sports = sys.argv[1:] or ["NBA", "NHL", "CBB"]
    res = load("backtest_live.json", {})
    for s in sports:
        rows = run(s)
        save(f"hist/rows_{s}.json", rows)
        res[s] = summarize(s, rows)
        print(s, json.dumps(res[s]))
        save("backtest_live.json", res)
