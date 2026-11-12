import json, urllib.request, concurrent.futures as cf, time
def get(u, tries=3):
    for i in range(tries):
        try: return json.load(urllib.request.urlopen(u, timeout=30))
        except Exception as e: time.sleep(1+i)
    return None
games = []
for season in (2023, 2024, 2025):
    for wk in range(1, 17):
        d = get(f"https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?dates={season}&seasontype=2&week={wk}&groups=80&limit=400")
        for ev in (d or {}).get("events", []):
            c = ev["competitions"][0]
            if not c["status"]["type"].get("completed"): continue
            h = next(x for x in c["competitors"] if x["homeAway"] == "home"); a = next(x for x in c["competitors"] if x["homeAway"] == "away")
            games.append({"season": season, "week": wk, "id": ev["id"], "date": ev["date"], "neutral": c.get("neutralSite", False), "conf_game": c.get("conferenceCompetition", False),
              "home": h["team"]["displayName"], "away": a["team"]["displayName"], "hid": h["team"]["id"], "aid": a["team"]["id"], "habbr": h["team"].get("abbreviation"), "aabbr": a["team"].get("abbreviation"),
              "hconf": h["team"].get("conferenceId"), "aconf": a["team"].get("conferenceId"), "hs": int(h["score"]), "as": int(a["score"])})
    print(season, len(games), flush=True)
def odds(g):
    d = get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/events/{g['id']}/competitions/{g['id']}/odds")
    for it in (d or {}).get("items", []):
        if "Live" in (it.get("provider", {}).get("name") or ""): continue
        g["details"] = it.get("details"); g["spread"] = it.get("spread"); g["ou"] = it.get("overUnder"); g["provider"] = it.get("provider", {}).get("name")
        hto = it.get("homeTeamOdds") or {}; g["home_fav"] = hto.get("favorite"); break
    return g
with cf.ThreadPoolExecutor(16) as ex: games = list(ex.map(odds, games))
json.dump(games, open("cfb_games.json", "w"))
print("with odds", sum(1 for g in games if g.get("spread") is not None), "of", len(games))
