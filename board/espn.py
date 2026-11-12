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
    v = c.get("venue") or {}
    ad = v.get("address") or {}
    g["venue"] = v.get("fullName"); g["city"] = ad.get("city"); g["state_abbr"] = ad.get("state"); g["indoor"] = v.get("indoor")
    w = ev.get("weather") or {}
    if w:
        g["weather"] = {"text": w.get("displayValue"), "temp": w.get("temperature")}
    g["tv"] = ", ".join(n for b in c.get("broadcasts") or [] for n in b.get("names", []))[:60]
    for side, comp in (("h", h), ("a", a)):
        pr = comp.get("probables") or []
        g[side + "goalie"] = next((x.get("athlete", {}).get("displayName") for x in pr if "Goalie" in (x.get("displayName") or "")), None)
        g[side + "leaders"] = sorted({l["athlete"]["displayName"] for cat in comp.get("leaders") or [] for l in cat.get("leaders", [])[:1] if l.get("athlete")})
        rec = next((r.get("summary") for r in comp.get("records") or [] if r.get("type") in ("total", "ytd")), None)
        g[side + "record"] = rec
    o = (c.get("odds") or [None])[0]
    if o:
        g["book"] = (o.get("provider") or {}).get("name")
        g["details"] = o.get("details")
        g["total"] = o.get("overUnder")
        g["home_line"] = home_line(o.get("details"), g["habbr"], g["aabbr"], o.get("spread"), (o.get("homeTeamOdds") or {}).get("favorite"))
        g["home_ml"] = (o.get("homeTeamOdds") or {}).get("moneyLine")
        g["away_ml"] = (o.get("awayTeamOdds") or {}).get("moneyLine")
        try:
            ps = o["pointSpread"]["home"]
            g["home_line_open"] = float(ps["open"]["line"]); g["home_spread_odds"] = int(str(ps["close"]["odds"]).replace("+", ""))
            g["away_spread_odds"] = int(str(o["pointSpread"]["away"]["close"]["odds"]).replace("+", ""))
        except Exception:
            pass
        try:
            g["total_open"] = float(str(o["total"]["over"]["open"]["line"]).lstrip("ou"))
        except Exception:
            pass
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
        ho = it.get("homeTeamOdds") or {}
        out = {"details": it.get("details"), "total": it.get("overUnder"), "book": (it.get("provider") or {}).get("name"),
               "home_ml": ho.get("moneyLine"), "away_ml": (it.get("awayTeamOdds") or {}).get("moneyLine")}
        try:
            out["home_open"] = float(str(ho["open"]["pointSpread"]["american"]).replace("+", "").replace("PK", "0").replace("EVEN", "0"))
        except Exception:
            pass
        try:
            out["home_ml_open"] = int(str(ho["open"]["moneyLine"]["american"]).replace("+", ""))
            out["away_ml_open"] = int(str(it["awayTeamOdds"]["open"]["moneyLine"]["american"]).replace("+", ""))
        except Exception:
            pass
        try:
            out["total_open"] = float(str(it["open"]["total"]["american"]).lstrip("ou"))
        except Exception:
            pass
        return out
    return None


def _geocode(city, state):
    geo = load("geo.json", {}); key = f"{city}|{state}"
    if key in geo:
        return geo[key]
    import urllib.parse
    loc = None
    r = get("https://geocoding-api.open-meteo.com/v1/search?count=10&country=US&name=" + urllib.parse.quote(city), tries=1) or {}
    for x in r.get("results") or []:
        if not state or (x.get("admin1") or "").lower().startswith(STATES.get(state, "~").lower()):
            loc = [x["latitude"], x["longitude"]]; break
    if not loc:
        q = urllib.parse.quote(f"{city}, {STATES.get(state, state or '')}, USA")
        r = get(f"https://nominatim.openstreetmap.org/search?format=json&limit=1&q={q}", tries=1) or []
        if r:
            loc = [float(r[0]["lat"]), float(r[0]["lon"])]
    if loc:
        geo[key] = loc; save("geo.json", geo)
    return loc


def wind_at(city, state, iso):
    """Forecast wind (mph), gusts, rain chance and temperature at kickoff. Open-Meteo first, National Weather Service as backup (both free)."""
    import datetime as dt
    if not city:
        return None
    loc = _geocode(city, state)
    if not loc:
        return None
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).replace(minute=0, second=0)
    f = get(f"https://api.open-meteo.com/v1/forecast?latitude={loc[0]}&longitude={loc[1]}&hourly=wind_speed_10m,wind_gusts_10m,precipitation_probability,temperature_2m&wind_speed_unit=mph&temperature_unit=fahrenheit&timezone=UTC&forecast_days=7", tries=1)
    if f and "hourly" in f:
        hrs = f["hourly"]["time"]; k = t.strftime("%Y-%m-%dT%H:00")
        if k in hrs:
            i = hrs.index(k)
            return {"wind": f["hourly"]["wind_speed_10m"][i], "gust": f["hourly"]["wind_gusts_10m"][i], "rain": f["hourly"]["precipitation_probability"][i], "temp": f["hourly"]["temperature_2m"][i], "src": "Open-Meteo"}
    pt = get(f"https://api.weather.gov/points/{loc[0]:.4f},{loc[1]:.4f}", tries=2)
    url = ((pt or {}).get("properties") or {}).get("forecastHourly")
    fh = get(url, tries=2) if url else None
    for p in ((fh or {}).get("properties") or {}).get("periods", []):
        st = dt.datetime.fromisoformat(p["startTime"]); en = dt.datetime.fromisoformat(p["endTime"])
        if st <= t < en:
            try:
                w = float(str(p.get("windSpeed", "0")).split()[0])
            except Exception:
                w = 0.0
            return {"wind": w, "gust": w, "rain": (p.get("probabilityOfPrecipitation") or {}).get("value") or 0, "temp": p.get("temperature"), "src": "NWS"}
    return None


STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
          "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
          "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
          "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
          "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "DC": "District"}
