import json, csv, collections
C = json.load(open("bt_rows.json")); cr, nr = C["cfb_rows"], C["nfl_rows"]
def rec(rows, pick):  # pick(r) -> +1 home, -1 away, 0 none
    w = l = 0
    for r in rows:
        s = pick(r)
        if not s: continue
        c = r["m"] + r["hs"]
        if c == 0: continue
        w += (c > 0) == (s > 0); l += (c > 0) != (s > 0)
    return f"{w}-{l} ({w/(w+l)*100:.1f}%)" if w + l else "none"
for name, rows in (("CFB", cr), ("NFL", nr)):
    print(name)
    print("  home underdogs:", rec(rows, lambda r: 1 if r["hs"] > 0 else 0))
    print("  home dogs +3 to +7:", rec(rows, lambda r: 1 if 3 <= r["hs"] <= 7 else 0))
    print("  big dogs +14 or more:", rec(rows, lambda r: (1 if r["hs"] >= 14 else -1 if r["hs"] <= -14 else 0)))
    print("  fade model (bet against gap 7+):", rec(rows, lambda r: (-1 if r["gap"] >= 7 else 1 if r["gap"] <= -7 else 0)))
    print("  model A only gap 5+:", rec(rows, lambda r: (1 if r["gapA"] >= 5 else -1 if r["gapA"] <= -5 else 0)), " model B only gap 5+:", rec(rows, lambda r: (1 if r["gapB"] >= 5 else -1 if r["gapB"] <= -5 else 0)))
# NFL totals: unders overall, and by total size
N = [x for x in csv.DictReader(open("nfl_games.csv")) if x["season"] in ("2023", "2024", "2025", "2026") and x["result"] not in ("", "NA") and x["total_line"] not in ("", "NA") and x["game_type"] == "REG"]
def tot(rows, f):
    u = o = 0
    for x in rows:
        if not f(x): continue
        t, L = int(x["total"]), float(x["total_line"])
        if t == L: continue
        u += t < L; o += t > L
    return f"under {u}-{o} ({u/(u+o)*100:.1f}%)"
print("NFL totals all:", tot(N, lambda x: True), "| prime-time:", tot(N, lambda x: x["weekday"] != "Sunday"), "| wind 15+:", tot(N, lambda x: x["wind"] not in ("", "NA") and float(x["wind"]) >= 15), "| total 47+:", tot(N, lambda x: float(x["total_line"]) >= 47), "| divisional:", tot(N, lambda x: x["div_game"] == "1"))
