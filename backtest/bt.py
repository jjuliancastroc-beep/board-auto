import json, csv, re, datetime, random, math, collections
import numpy as np
rng = np.random.default_rng(7)
POWER = {"8", "5", "4", "1"}; P12 = "9"
def ct_wd(iso): return (datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")) - datetime.timedelta(hours=6)).strftime("%a")
def ratings_fit(past, teams_prior, hfa=2.5, lam=3.0, cap=28):
    # ridge least squares margin model, shrink toward prior
    idx = {t: i for i, t in enumerate(teams_prior)}; n = len(idx)
    A = np.zeros((len(past) + n, n)); b = np.zeros(len(past) + n)
    for k, g in enumerate(past):
        A[k, idx[g["h"]]] = 1; A[k, idx[g["a"]]] = -1
        b[k] = max(-cap, min(cap, g["m"])) - (0 if g["neu"] else hfa)
    for t, i in idx.items(): A[len(past) + i, i] = math.sqrt(lam); b[len(past) + i] = math.sqrt(lam) * teams_prior[t]
    r, *_ = np.linalg.lstsq(A, b, rcond=None); return {t: r[i] for t, i in idx.items()}
def run(games, hfa, sd, label, tier_fn, wd_fn, min_week=4, lam=3.0, fcs_prior=-18):
    by_season = collections.defaultdict(list)
    for g in games: by_season[g["season"]].append(g)
    prior_final = {}; out = []
    for season in sorted(by_season):
        G = sorted(by_season[season], key=lambda g: g["date"]); weeks = sorted({g["week"] for g in G})
        teams = {g["h"] for g in G} | {g["a"] for g in G}
        cnt = collections.Counter([g["h"] for g in G] + [g["a"] for g in G])
        prior = {t: (0.5 * prior_final[t] if t in prior_final else (fcs_prior if cnt[t] <= 2 else 0.0)) for t in teams}
        hist = collections.defaultdict(list); past = []
        for wk in weeks:
            wg = [g for g in G if g["week"] == wk]
            R = ratings_fit(past, prior, hfa, lam) if past else prior
            for g in wg:
                if wk >= min_week and g.get("hs") is not None:
                    A_ = R[g["h"]] - R[g["a"]] + (0 if g["neu"] else hfa)
                    lh = hist[g["h"]][-8:]; la = hist[g["a"]][-8:]
                    B_ = (np.mean(lh) if lh else 0) - (np.mean(la) if la else 0) + (0 if g["neu"] else hfa)
                    bl = 0.5 * A_ + 0.5 * B_
                    mkt = -g["hs"]   # market home margin
                    sims = rng.normal(bl, sd, 10000); p_home_cover = float(np.mean(sims + g["hs"] > 0))
                    out.append({"season": season, "week": wk, "tier": tier_fn(g), "wd": wd_fn(g), "A": A_, "B": B_, "bl": bl, "mkt": mkt, "gap": bl - mkt, "gapA": A_ - mkt, "gapB": B_ - mkt, "m": g["m"], "hs": g["hs"], "p": p_home_cover})
            for g in wg:
                past.append(g); hist[g["h"]].append(max(-35, min(35, g["m"]))); hist[g["a"]].append(max(-35, min(35, -g["m"])))
        prior_final = ratings_fit(past, prior, hfa, lam)
    return out
def ats(rows, key="gap", lo=3, hi=99, both=False):
    w = l = p = 0
    for r in rows:
        g = r[key]
        if not (lo <= abs(g) < hi): continue
        if both and not (np.sign(r["gapA"]) == np.sign(r["gapB"]) == np.sign(g) and min(abs(r["gapA"]), abs(r["gapB"])) >= lo): continue
        cover = r["m"] + r["hs"]
        if cover == 0: p += 1; continue
        if (cover > 0) == (g > 0): w += 1
        else: l += 1
    n = w + l; return w, l, p, (w / n if n else float("nan"))
def fmt(t): w, l, p, pct = t; roi = (w * 0.909 - l) / (w + l) * 100 if w + l else 0; return f"{w}-{l}" + (f"-{p}" if p else "") + f" ({pct*100:.1f}%, ROI {roi:+.1f}% at -110)"
res = {}
# ---------------- CFB ----------------
C = json.load(open("cfb_games.json")); cg = []
for g in C:
    if g.get("details") in (None, ""): continue
    det = g["details"]; hs = None
    if det.upper().startswith("EVEN"): hs = 0.0
    else:
        m = re.match(r"^(\S+)\s+(-?\d+(?:\.\d+)?)$", det.strip())
        if not m: continue
        ab, ln = m.group(1), float(m.group(2))
        if ab == g["habbr"]: hs = ln
        elif ab == g["aabbr"]: hs = -ln
        else: continue
    cg.append({"season": g["season"], "week": g["week"], "date": g["date"], "h": g["hid"], "a": g["aid"], "neu": g["neutral"], "m": g["hs"] - g["as"], "hs": hs, "hconf": str(g["hconf"]), "aconf": str(g["aconf"]), "hid": g["hid"], "aid": g["aid"]})
def cfb_tier(g):
    pw = POWER | ({P12} if g["season"] == 2023 else set())
    hp = g["hconf"] in pw or g["hid"] == "87"; ap = g["aconf"] in pw or g["aid"] == "87"
    return "P4vP4" if hp and ap else "G5/mixed"
def cfb_wd(g): return "Sat" if ct_wd(g["date"]) in ("Sat",) else "Midweek" if ct_wd(g["date"]) in ("Tue", "Wed", "Thu", "Fri") else ct_wd(g["date"])
rows = run(cg, 2.5, 16.0, "CFB", cfb_tier, cfb_wd)
lines = [f"CFB games tested (week 4+, 2023-2025, ESPN BET line): {len(rows)}"]
res_sd = float(np.std([r["m"] - r["bl"] for r in rows])); lines.append(f"Model miss size (SD of actual minus blend): {res_sd:.1f} pts; market miss SD {float(np.std([r['m'] - r['mkt'] for r in rows])):.1f}")
for lo, hi in ((0, 3), (3, 5), (5, 7), (7, 99)): lines.append(f"  blend gap {lo}-{hi}: {fmt(ats(rows, lo=lo, hi=hi))}")
lines.append(f"  gap 3+ both models agree: {fmt(ats(rows, lo=3, both=True))}")
for tier in ("P4vP4", "G5/mixed"):
    for wd in ("Sat", "Midweek"):
        sub = [r for r in rows if r["tier"] == tier and r["wd"] == wd]
        lines.append(f"  {tier} {wd} ({len(sub)} games): gap 3+ {fmt(ats(sub, lo=3))}; both agree {fmt(ats(sub, lo=3, both=True))}; gap 7+ {fmt(ats(sub, lo=7))}")
# monte carlo calibration: predicted cover prob buckets
cal = collections.defaultdict(lambda: [0, 0])
for r in rows:
    pc = r["p"] if r["gap"] > 0 else 1 - r["p"]; cover = r["m"] + r["hs"]
    if cover == 0: continue
    won = (cover > 0) == (r["gap"] > 0); b = min(int(pc * 20) / 20, 0.7); cal[b][0] += won; cal[b][1] += 1
lines.append("  Monte Carlo cover-probability check (sim says -> actually won):")
for b in sorted(cal): w_, n_ = cal[b]; lines.append(f"    sim {b*100:.0f}-{b*100+5:.0f}%: won {w_}/{n_} = {w_/n_*100:.1f}%")
res["CFB"] = lines
# ---------------- NFL ----------------
N = [x for x in csv.DictReader(open("nfl_games.csv")) if x["season"] in ("2022", "2023", "2024", "2025", "2026") and x["result"] not in ("", "NA") and x["spread_line"] not in ("", "NA") and x["game_type"] == "REG"]
ng = [{"season": int(x["season"]), "week": int(x["week"]), "date": x["gameday"] + "T18:00Z", "h": x["home_team"], "a": x["away_team"], "neu": x["location"] == "Neutral", "m": int(x["result"]), "hs": -float(x["spread_line"]), "wd": x["weekday"], "tot": float(x["total_line"]), "pts": int(x["total"])} for x in N]
nrows = run(ng, 1.8, 13.0, "NFL", lambda g: "NFL", lambda g: "Sun" if g["wd"] == "Sunday" else "Prime/other", min_week=4, lam=4.0)
nrows = [r for r in nrows if r["season"] >= 2023]
L2 = [f"NFL games tested (week 4+, 2023-2026 to date, closing line): {len(nrows)}"]
for lo, hi in ((0, 3), (3, 5), (5, 99)): L2.append(f"  blend gap {lo}-{hi}: {fmt(ats(nrows, lo=lo, hi=hi))}")
L2.append(f"  gap 3+ both models agree: {fmt(ats(nrows, lo=3, both=True))}")
for wd in ("Sun", "Prime/other"):
    sub = [r for r in nrows if r["wd"] == wd]; L2.append(f"  {wd} ({len(sub)}): gap 3+ {fmt(ats(sub, lo=3))}")
res["NFL"] = L2
json.dump({"cfb_rows": rows, "nfl_rows": nrows}, open("bt_rows.json", "w"), default=float)
print("\n".join(res["CFB"] + [""] + res["NFL"]))
