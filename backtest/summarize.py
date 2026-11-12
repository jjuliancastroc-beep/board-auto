"""Turn backtest rows into bucket records used on the card (gap over the bar AND both models agree)."""
import json, os, sys
import numpy as np
here = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(here, "bt_rows.json")))
def rec(rows, lo=3.0):
    w = l = 0
    for r in rows:
        g = r["gap"]
        if abs(g) < lo or not (np.sign(r["gapA"]) == np.sign(r["gapB"]) == np.sign(g) and min(abs(r["gapA"]), abs(r["gapB"])) >= lo): continue
        c = r["m"] + r["hs"]
        if c == 0: continue
        w += (c > 0) == (g > 0); l += (c > 0) != (g > 0)
    return {"w": w, "l": l, "n": w + l, "win": round(w / (w + l), 3) if w + l else 0}
def rec_any(rows, lo, hi):
    w = l = 0
    for r in rows:
        if not (lo <= abs(r["gap"]) < hi): continue
        c = r["m"] + r["hs"]
        if c == 0: continue
        w += (c > 0) == (r["gap"] > 0); l += (c > 0) != (r["gap"] > 0)
    return {"w": w, "l": l, "n": w + l, "win": round(w / (w + l), 3) if w + l else 0}
cfb, nfl = R["cfb_rows"], R["nfl_rows"]
out = {"CFB": {f"{t} {d}": rec([r for r in cfb if r["tier"] == t and r["wd"] == d]) for t in ("P4vP4", "G5/mixed") for d in ("Sat", "Midweek")},
       "NFL": {d: rec([r for r in nfl if r["wd"] == d]) for d in ("Sun", "Prime/other")},
       "by_gap": {"CFB": {f"{lo}-{hi if hi < 99 else '+'}": rec_any(cfb, lo, hi) for lo, hi in ((0, 3), (3, 5), (5, 7), (7, 99))},
                  "NFL": {f"{lo}-{hi if hi < 99 else '+'}": rec_any(nfl, lo, hi) for lo, hi in ((0, 3), (3, 5), (5, 99))}},
       "overall": {"CFB": rec(cfb), "NFL": rec(nfl)},
       "n": {"CFB": len(cfb), "NFL": len(nfl)},
       "calibration_cfb": None,
       "notes": ["CFB: 2023-2025 regular seasons, weeks 4+, ESPN BET line. Point-in-time models only (ratings from games already played + last-8 margins).",
                 "NFL: 2023 to 2026 week 9, weeks 4+, closing line (nflverse).",
                 "Break-even against a -110 price is 52.4%. A kind of pick needs 53.5%+ over 200+ games before the card will put cash on it."]}
json.dump(out, open(os.path.join(os.path.dirname(here), "data", "backtest.json"), "w"), indent=1)
print(json.dumps(out["CFB"]), json.dumps(out["NFL"]))
