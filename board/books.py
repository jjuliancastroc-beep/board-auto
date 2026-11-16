"""Other books' numbers on the same player props, so Underdog's line is not the only one the Board looks at.

  DraftKings - through ESPN's odds feed (NBA): the line and both prices
  Pinnacle   - its public guest feed (NBA, NFL, NHL): the line and both prices
  Sleeper    - its pick'em board (every sport): the line and both payout multipliers

All free, no key. A source that fails is skipped for that run and the system check says which ones loaded.
Only the two sportsbooks (real prices on both sides) go into the "books' chance". Sleeper is shown for comparison.
"""
import json, re, time, urllib.request, unicodedata
from concurrent.futures import ThreadPoolExecutor
from .common import load, save, today_ct, ct_time, SPORTS, american_to_prob

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
DK_URL = "https://sports.core.api.espn.com/v2/sports/{kind}/leagues/{league}/events/{eid}/competitions/{eid}/odds/100/propBets?lang=en&region=us&limit=1000&page={page}"
PIN_URL = "https://guest.api.arcadia.pinnacle.com/0.1/leagues/{lid}/{what}"
PIN_KEY = "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"  # the public guest key pinnacle.com's own page uses; not a secret
PIN_LEAGUE = {"NBA": 487, "NFL": 889, "NHL": 1456}
SLP_URL = "https://api.sleeper.app/lines/available?dynamic=true&include_preseason=true&eg=15.control"
SLP_PLAYERS = "https://api.sleeper.app/v1/players/{sport}"
SLP_SPORT = {"nba": "NBA", "nfl": "NFL", "nhl": "NHL", "cfb": "CFB", "cbb": "CBB"}
PRICED = ("DraftKings", "Pinnacle")  # books whose two-sided prices feed the books' chance

# each book's name for a stat -> ours (Underdog's stat key)
DK_STAT = {"points": "points", "rebounds": "rebounds", "assists": "assists", "3-point field goals": "three_points_made", "steals": "steals", "blocks": "blocks",
           "points, rebounds, and assists": "pts_rebs_asts", "points and rebounds": "pts_rebs", "points and assists": "pts_asts", "assists and rebounds": "rebs_asts",
           "passing yards": "passing_yds", "passing touchdowns": "passing_tds", "pass completions": "passing_comps", "pass attempts": "passing_att",
           "rushing yards": "rushing_yds", "rushing attempts": "rushing_att", "receiving yards": "receiving_yds", "receptions": "receiving_rec",
           "rushing + receiving yards": "rush_rec_yds", "shots on goal": "shots", "saves": "saves", "goals": "goals"}
PIN_STAT = {"B": {"points": "points", "rebounds": "rebounds", "assists": "assists", "threes made": "three_points_made", "pts & rebs & asts": "pts_rebs_asts",
                  "steals": "steals", "blocks": "blocks"},
            "F": {"receptions": "receiving_rec", "receiving yards": "receiving_yds", "rushing yards": "rushing_yds", "rush attempts": "rushing_att",
                  "pass attempts": "passing_att", "pass completions": "passing_comps", "touchdown passes": "passing_tds", "interceptions": "passing_ints",
                  "passing yards": "passing_yds"},
            "H": {"points": "points", "assists": "assists", "shots on goal": "shots", "goals": "goals", "saves": "saves"}}
SLP_STAT = {"B": {"points": "points", "rebounds": "rebounds", "assists": "assists", "threes_made": "three_points_made", "pts_reb_ast": "pts_rebs_asts",
                  "points_and_rebounds": "pts_rebs", "points_and_assists": "pts_asts", "rebounds_and_assists": "rebs_asts", "steals": "steals", "blocks": "blocks",
                  "blocks_and_steals": "blks_stls", "turnovers": "turnovers"},
            "F": {"passing_yards": "passing_yds", "passing_touchdowns": "passing_tds", "pass_completions": "passing_comps", "passing_attempts": "passing_att",
                  "interceptions": "passing_ints", "rushing_yards": "rushing_yds", "rushing_attempts": "rushing_att", "receiving_yards": "receiving_yds",
                  "receptions": "receiving_rec", "rushing_and_receiving_yards": "rush_rec_yds", "passing_and_rushing_yards": "passing_and_rushing_yds"},
            "H": {"goals": "goals", "assists": "assists", "points": "points", "shots": "shots", "powerplay_points": "power_play_points", "saves": "saves",
                  "goals_against": "goals_against"}}
GROUP = {"NBA": "B", "CBB": "B", "NFL": "F", "CFB": "F", "NHL": "H"}


def norm(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z ]", " ", s)
    return " ".join(w for w in s.split() if w not in ("jr", "sr", "ii", "iii", "iv", "v"))


def _get(url, headers=None, timeout=25, tries=2):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})})
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
        except Exception:
            pass
        time.sleep(1.0)
    return None


def _am(v):
    s = str(v).strip().upper()
    return 100 if s in ("EVEN", "EV") else int(float(s))


def novig(over, under):
    a, b = american_to_prob(over), american_to_prob(under)
    return a / (a + b)


# ---------------- DraftKings (through ESPN) ----------------
def parse_dk(items):
    """ESPN lists each player line twice: the Higher price first, then the Lower price."""
    rows = {}
    for x in items or []:
        ref = (x.get("athlete") or {}).get("$ref") or ""
        m = re.search(r"athletes/(\d+)", ref)
        name = ((x.get("type") or {}).get("name") or "").lower()
        if not m or not name.startswith("total "):
            continue
        stat = DK_STAT.get(name[6:].strip())
        try:
            line = float(x["current"]["target"]["value"]); price = _am(x["odds"]["american"]["value"])
        except Exception:
            continue
        if stat:
            rows.setdefault((m.group(1), stat), []).append((line, price))
    out = {}
    for k, v in rows.items():
        if len(v) == 2 and v[0][0] == v[1][0]:
            out[k] = {"book": "DraftKings", "line": v[0][0], "over": v[0][1], "under": v[1][1]}
    return out


def draftkings(games):
    """games: [(sport, espn event id)] -> {(sport, espn athlete id, stat): row}"""
    out = {}
    def one(g):
        sport, eid = g
        items = []
        for page in (1, 2, 3):
            kind, league = SPORTS[sport]["path"].split("/")
            d = _get(DK_URL.format(kind=kind, league=league, eid=eid, page=page), tries=1)
            if not d:
                break
            items += d.get("items") or []
            if page >= (d.get("pageCount") or 1):
                break
        for (aid, stat), row in parse_dk(items).items():
            out[(sport, aid, stat)] = row
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(one, [g for g in games if g[0] in ("NBA", "NFL", "NHL")]))
    return out


# ---------------- Pinnacle ----------------
def parse_pinnacle(sport, matchups, markets):
    mk = {m["matchupId"]: m for m in markets or [] if m.get("type") == "total" and m.get("period") == 0}
    out, twice = {}, set()
    for x in matchups or []:
        sp = x.get("special") or {}
        if x.get("type") != "special" or sp.get("category") != "Player Props" or x.get("isLive") or x["id"] not in mk:
            continue
        m = re.match(r"^(.*?)\s*(?:\([^)]*\))?\s+Total\s+(.+)$", sp.get("description") or "")
        if not m:
            continue
        stat = PIN_STAT[GROUP[sport]].get(m.group(2).strip().lower())
        ids = {p["name"]: p["id"] for p in x.get("participants") or []}
        pr = {p.get("participantId"): p for p in mk[x["id"]].get("prices") or []}
        o, u = pr.get(ids.get("Over")), pr.get(ids.get("Under"))
        if not stat or not o or not u or o.get("points") is None:
            continue
        home = next((p["name"] for p in (x.get("parent") or {}).get("participants") or [] if p.get("alignment") == "home"), "")
        k = (sport, norm(m.group(1)), stat)
        if k in out:
            twice.add(k)
        out[k] = {"book": "Pinnacle", "line": float(o["points"]), "over": int(o["price"]), "under": int(u["price"]), "home": home, "start": x.get("startTime")}
    for k in twice:  # two players with the same name on the slate - can't tell them apart, drop both
        out.pop(k, None)
    return out


def pinnacle(sports):
    out = {}
    for sport in sports:
        lid = PIN_LEAGUE.get(sport)
        if not lid:
            continue
        h = {"X-API-Key": PIN_KEY, "Referer": "https://www.pinnacle.com/"}
        mu = _get(PIN_URL.format(lid=lid, what="matchups"), h)
        mk = _get(PIN_URL.format(lid=lid, what="markets/straight"), h) if mu else None
        if mu and mk:
            out.update(parse_pinnacle(sport, mu, mk))
    return out


# ---------------- Sleeper ----------------
def sleeper_names(need):
    """need: {sleeper sport: set(ids)} -> {(sleeper sport, id): name}. Names are kept in a small cache file;
    a sport's full player list (large) is downloaded at most once a day, and only when a new id shows up."""
    cache = load("cache/sleeper_names.json", {}); today = today_ct(); changed = False
    for sp, ids in need.items():
        have = cache.setdefault(sp, {})
        miss = [i for i in ids if i not in have]
        if miss and cache.setdefault("_fetched", {}).get(sp) != today:
            d = _get(SLP_PLAYERS.format(sport=sp), timeout=90, tries=1) or {}
            for i in miss:
                p = d.get(i) or {}
                nm = p.get("full_name") or " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
                if nm:
                    have[i] = nm
            cache["_fetched"][sp] = today; changed = True
    if changed:
        save("cache/sleeper_names.json", cache)
    return {(sp, i): n for sp, m in cache.items() if sp != "_fetched" for i, n in m.items()}


def parse_sleeper(lines, names):
    out, twice = {}, set()
    for x in lines or []:
        sport = SLP_SPORT.get(x.get("sport"))
        if not sport or x.get("status") != "active" or x.get("game_status") != "pre_game" or x.get("outcome_type") != "over_under" or x.get("line_type") != "normal":
            continue
        stat = SLP_STAT[GROUP[sport]].get(x.get("wager_type"))
        name = names.get((x.get("sport"), str(x.get("subject_id"))))
        op = {o.get("outcome"): o for o in x.get("options") or []}
        o, u = op.get("over"), op.get("under")
        if not stat or not name or not o or not u:
            continue
        try:
            row = {"book": "Sleeper", "line": float(o["outcome_value"]), "over_x": float(o["payout_multiplier"]), "under_x": float(u["payout_multiplier"])}
        except Exception:
            continue
        k = (sport, norm(name), stat)
        if k in out:
            twice.add(k)
        out[k] = row
    for k in twice:
        out.pop(k, None)
    return out


def sleeper():
    lines = _get(SLP_URL, timeout=60)
    if not lines:
        return {}
    need = {}
    for x in lines:
        if x.get("sport") in SLP_SPORT and x.get("subject_type") == "player":
            need.setdefault(x["sport"], set()).add(str(x.get("subject_id")))
    return parse_sleeper(lines, sleeper_names(need))


# ---------------- put them on the Underdog lines ----------------
def _same_game(row, g):
    """Pinnacle row belongs to this ESPN game: same home team (last word) and within a day of the start."""
    a, b = norm(row.get("home")).split(), norm(g.get("home")).split()
    if a and b and a[-1] != b[-1]:
        return False
    try:
        return abs((ct_time(row["start"]) - ct_time(g["date"])).total_seconds()) < 24 * 3600
    except Exception:
        return True


def collect(jobs):
    """jobs: [(underdog line, espn athlete, espn game)]. Adds line['books'] = the other books' numbers on that same prop.
    Returns how many lines each book covered."""
    sports = {l["sport"] for l, a, g in jobs}
    src = {}
    for name, fn in (("DraftKings", lambda: draftkings({(l["sport"], g["id"]) for l, a, g in jobs})), ("Pinnacle", lambda: pinnacle(sports)), ("Sleeper", sleeper)):
        try:
            src[name] = fn()
        except Exception as e:
            print(f"books: {name} failed: {e}"); src[name] = {}
    hits = {k: 0 for k in src}
    for l, a, g in jobs:
        rows = []
        r = src["DraftKings"].get((l["sport"], str(a["id"]), l["stat"]))
        if r:
            rows.append(dict(r))
        r = src["Pinnacle"].get((l["sport"], norm(l["player"]), l["stat"]))
        if r and _same_game(r, g):
            rows.append({k: v for k, v in r.items() if k not in ("home", "start")})
        r = src["Sleeper"].get((l["sport"], norm(l["player"]), l["stat"]))
        if r:
            rows.append(dict(r))
        for r in rows:
            hits[r["book"]] += 1
            r["p"] = round(novig(r["over"], r["under"]) if "over" in r else (1 / r["over_x"]) / (1 / r["over_x"] + 1 / r["under_x"]), 4)
        l["books"] = rows
    return hits


def at_line(p, line, target, disp, p_over):
    """A book says 'Higher than `line`' happens p of the time. What does that say about Underdog's `target` line?
    Find the average that gives the book's chance at the book's line, then read the chance at Underdog's line."""
    if line == target:
        return p
    lo, hi = 0.01, max(10.0, line * 4 + 20)
    for _ in range(50):
        mid = (lo + hi) / 2
        if p_over(line, mid, disp) < p:
            lo = mid
        else:
            hi = mid
    return p_over(target, (lo + hi) / 2, disp)


def consensus(rows, target, disp, p_over):
    """The sportsbooks' chance of Higher at Underdog's line: the average of DraftKings and Pinnacle, prices with the vig taken out.
    A book whose line is not close to Underdog's is left out (shown, not counted) - it may be an old number. Returns (chance or None, books used)."""
    qs, used = [], []
    for r in rows or []:
        if r.get("book") not in PRICED or "over" not in r:
            continue
        if abs(r["line"] - target) > max(0.5, 0.06 * target):  # 2.5 vs 3.5 is a different bet; 21.5 vs 22.5 is close enough to translate
            continue
        qs.append(at_line(novig(r["over"], r["under"]), r["line"], target, disp, p_over)); used.append(r["book"])
    return (sum(qs) / len(qs), used) if qs else (None, [])
