"""ESPN free endpoints: scoreboards (games, scores, DraftKings lines), injuries, power indexes, closing odds."""
import datetime, re
from .common import SPORTS, SEASON_START, get, load, save, ct_time

SB = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={d}{params}"


def parse_event(ev, sport):
    c = ev["competitions"][0]
    h = next(x for x in c["competitors"] if x["homeAway"] == "home")
    a = next(x for x in c["competitors"] if x["homeAway"] == "away")
    st = c["status"]["type"]
    g = {"id": ev["id"], "sport": sport, "date": ev["date"], "neutral": bool(c.get("neutralSite")),
         "home": h["team"].get("displayName"), "away": a["team"].get("displayName"),
         "habbr": h["team"].get("abbreviation"), "aabbr": a["team"].get("abbreviation"),
         "hid": h["team"].get("id"), "aid": a["team"].get("id"),
         "hconf": str(h["team"].get("conferenceId", "")), "aconf": str(a["team"].get("conferenceId", "")),
         "completed": bool(st.get("completed")), "state": st.get("state"),
         "hs": int(h["score"]) if h.get("score") not in (None, "") and st.get("state") != "pre" else None,
         "as": int(a["score"]) if a.get("score") not in (None, "") and st.get("state") != "pre" else None}
    o = (c.get("odds") or [None])[0]
    if o:
        g["book"] = (o.get("provider") or {}).get("name")
        g["details"] = o.get("details")
        g["total"] = o.get("overUnder")
        g["home_line"] = home_line(o.get("details"), g["habbr"], g["aabbr"], o.get("spread"), (o.get("homeTeamOdds") or {}).get("favorite"))
        g["home_ml"] = (o.get("homeTeamOdds") or {}).get("moneyLine")
        g["away_ml"] = (o.get("awayTeamOdds") or {}).get("moneyLine")
        if g["home_ml"] is None:
            ml = o.get("moneyline") or {}
            try:
                g["home_ml"] = int(str(ml["home"]["close"]["odds"]).replace("+", ""))
                g["away_ml"] = int(str(ml["away"]["close"]["odds"]).replace("+", ""))
            except Exception:
                pass
    return g


def home_line(details, habbr, aabbr, spread=None, home_fav=None):
    """Home team's spread (negative = home favored)."""
    if not details:
        return None
    d = details.strip()
    if d.upper().startswith("EVEN") or d.upper() == "PK":
        return 0.0
    m = re.match(r"^(\S+)\s+(-?\d+(?:\.\d+)?)$", d)
    if not m:
        return None
    ab, ln = m.group(1), float(m.group(2))
    if ab == habbr:
        return ln
    if ab == aabbr:
        return -ln
    return None


def scoreboard(sport, date):
    cfg = SPORTS[sport]
    d = get(SB.format(path=cfg["path"], d=date.replace("-", ""), params=cfg["params"]))
    return [parse_event(ev, sport) for ev in (d or {}).get("events", [])]


def season_results(sport, upto):
    """Completed games from season start to the day before `upto`, cached per date (finished days never change)."""
    start = datetime.date.fromisoformat(SEASON_START[sport]); end = datetime.date.fromisoformat(upto)
    out = []; day = start
    while day < end:
        ds = day.isoformat(); key = f"cache/{sport}_{ds}.json"
        rows = load(key, None)
        if rows is None:
            rows = [g for g in scoreboard(sport, ds) if g["completed"] and g["hs"] is not None]
            if (end - day).days > 1:
                save(key, rows)  # only cache days that are surely final
        out.extend(rows)
        day += datetime.timedelta(days=1)
    seen = set(); uniq = []
    for g in out:
        if g["id"] not in seen:
            seen.add(g["id"]); uniq.append(g)
    return uniq


def power_index(sport):
    cfg = SPORTS[sport]
    if not cfg["power"]:
        return {}
    out = {}; page = 1
    while True:
        d = get(f"https://site.web.api.espn.com/apis/fitt/v3/sports/{cfg['power']}/powerindex?region=us&lang=en&limit=200&page={page}")
        if not d:
            break
        for t in d.get("teams", []):
            try:
                out[t["team"]["id"]] = float(t["categories"][0]["values"][0])
            except Exception:
                pass
        pg = d.get("pagination", {})
        if page >= pg.get("pages", 1):
            break
        page += 1
    return out


def injuries(sport):
    d = get(f"https://site.api.espn.com/apis/site/v2/sports/{SPORTS[sport]['path']}/injuries")
    out = {}
    for t in (d or {}).get("injuries", []):
        name = t.get("displayName")
        rows = []
        for i in t.get("injuries", []):
            ath = i.get("athlete", {})
            rows.append({"player": ath.get("displayName"), "pos": (ath.get("position") or {}).get("abbreviation"), "status": i.get("status")})
        out[name] = rows
    return out


def closing_line(sport, event_id):
    """Pregame line ESPN shows after the game (its last pregame number) - used as the closing line."""
    lg = SPORTS[sport]["path"].split("/")
    d = get(f"https://sports.core.api.espn.com/v2/sports/{lg[0]}/leagues/{lg[1]}/events/{event_id}/competitions/{event_id}/odds")
    for it in (d or {}).get("items", []):
        if "Live" in ((it.get("provider") or {}).get("name") or ""):
            continue
        return {"details": it.get("details"), "total": it.get("overUnder"), "book": (it.get("provider") or {}).get("name"),
                "home_ml": (it.get("homeTeamOdds") or {}).get("moneyLine"), "away_ml": (it.get("awayTeamOdds") or {}).get("moneyLine")}
    return None
