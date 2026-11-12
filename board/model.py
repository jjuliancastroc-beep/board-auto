"""Team-strength models built only from games already played (no look-ahead).

Model R ("ratings"): ridge least-squares on capped margins with home edge - an opponent-adjusted margin rating.
Model L ("last games"): average capped margin over each team's last N games (the Board's old Model B).
Model P ("power index"): ESPN FPI / BPI where ESPN publishes one (CFB, NFL, CBB).
"""
import collections
import numpy as np


def ridge_ratings(games, hfa, cap, lam, prior=None):
    teams = sorted({g["hid"] for g in games} | {g["aid"] for g in games})
    if not teams:
        return {}
    idx = {t: i for i, t in enumerate(teams)}; n = len(teams)
    A = np.zeros((len(games) + n, n)); b = np.zeros(len(games) + n)
    for k, g in enumerate(games):
        A[k, idx[g["hid"]]] = 1; A[k, idx[g["aid"]]] = -1
        m = max(-cap, min(cap, g["hs"] - g["as"]))
        b[k] = m - (0 if g.get("neutral") else hfa)
    s = np.sqrt(lam)
    for t, i in idx.items():
        A[len(games) + i, i] = s; b[len(games) + i] = s * ((prior or {}).get(t, 0.0))
    r, *_ = np.linalg.lstsq(A, b, rcond=None)
    return {t: float(r[i]) for t, i in idx.items()}


def last_n(games, cap, n=8):
    hist = collections.defaultdict(list)
    for g in sorted(games, key=lambda x: x["date"]):
        m = max(-cap, min(cap, g["hs"] - g["as"]))
        hist[g["hid"]].append(m); hist[g["aid"]].append(-m)
    return {t: (sum(v[-n:]) / len(v[-n:]), len(v)) for t, v in hist.items()}


def games_played(games):
    c = collections.Counter()
    for g in games:
        c[g["hid"]] += 1; c[g["aid"]] += 1
    return c
