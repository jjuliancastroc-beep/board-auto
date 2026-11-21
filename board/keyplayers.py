"""Each NBA team's top scorers this season, from ESPN box scores (11/21).
ESPN's own 'leaders' list leaves out injured players, so a star who is ruled out never showed up as 'teammate out'.
This keeps a running season total per player (data/key_players.json) and adds each finished day once."""
import datetime, statistics
from concurrent.futures import ThreadPoolExecutor
from .common import load, save, today_ct
from .espn import get

SEASON_START = "2026-10-20"
BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"


def _day(d):
    s = get(f"{BASE}/scoreboard?dates={d.replace('-', '')}") or {}
    ids = [e["id"] for e in s.get("events", []) if e.get("status", {}).get("type", {}).get("completed")]
    def summ(i):
        return get(f"{BASE}/summary?event={i}")
    with ThreadPoolExecutor(8) as ex:
        return list(ex.map(summ, ids)), len(ids)


def update(max_days=40):
    kp = load("key_players.json", {"days": [], "players": {}, "team_games": {}})
    done = set(kp["days"]); d = datetime.date.fromisoformat(SEASON_START); end = datetime.date.fromisoformat(today_ct())
    n = 0
    while d < end and n < max_days:
        ds = d.isoformat(); d += datetime.timedelta(days=1)
        if ds in done:
            continue
        summs, nids = _day(ds)
        if any(s is None for s in summs):
            continue  # a feed failed - try this day again next run
        for s in summs:
            for t in s.get("boxscore", {}).get("players", []):
                team = t["team"]["displayName"]; kp["team_games"][team] = kp["team_games"].get(team, 0) + 1
                st = (t.get("statistics") or [{}])[0]; names = st.get("names", [])
                for a in st.get("athletes", []):
                    if a.get("didNotPlay") or not a.get("stats"):
                        continue
                    try:
                        pts = float(dict(zip(names, a["stats"]))["PTS"])
                    except Exception:
                        continue
                    p = kp["players"].setdefault(a["athlete"]["id"], {"name": a["athlete"]["displayName"], "team": team, "n": 0, "pts": 0.0})
                    p["team"] = team; p["n"] += 1; p["pts"] += pts
        kp["days"].append(ds); n += 1
    save("key_players.json", kp)
    return kp


def stars(kp=None, top=2, min_ppg=18):
    """{team display name: [top scorers]} - top 2 by points per game, 18+ ppg, played 60%+ of the team's games."""
    kp = kp or load("key_players.json", {"players": {}, "team_games": {}})
    by = {}
    for p in kp["players"].values():
        tg = kp["team_games"].get(p["team"], 0)
        if p["n"] >= 5 and p["n"] >= 0.6 * tg and p["pts"] / p["n"] >= min_ppg:
            by.setdefault(p["team"], []).append((p["pts"] / p["n"], p["name"]))
    return {t: [n for _, n in sorted(v, reverse=True)[:top]] for t, v in by.items()}
