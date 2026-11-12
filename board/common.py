"""Shared helpers: HTTP with retry, Central-time dates, sport config, file IO."""
import json, os, time, datetime, urllib.request, math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CT = datetime.timezone(datetime.timedelta(hours=-6))  # Central (standard time; Nov-Mar)

SPORTS = {
    # key: (espn path, scoreboard extra params, home edge in points, gap bar, ESPN power index path or None)
    "NFL": {"path": "football/nfl", "params": "", "hfa": 1.8, "bar": 3.0, "power": "football/nfl", "cap": 28, "sd": 13.0, "lam": 4.0},
    "CFB": {"path": "football/college-football", "params": "&groups=80&limit=400", "hfa": 2.5, "bar": 3.0, "power": "football/college-football", "cap": 28, "sd": 16.0, "lam": 3.0},
    "NBA": {"path": "basketball/nba", "params": "", "hfa": 2.5, "bar": 4.5, "power": None, "cap": 30, "sd": 12.5, "lam": 6.0},
    "CBB": {"path": "basketball/mens-college-basketball", "params": "&groups=50&limit=400", "hfa": 3.4, "bar": 4.5, "power": "basketball/mens-college-basketball", "cap": 30, "sd": 11.0, "lam": 4.0},
    "NHL": {"path": "hockey/nhl", "params": "", "hfa": 0.25, "bar": 5.0, "power": None, "cap": 5, "sd": 2.3, "lam": 8.0},
}
SEASON_START = {"NFL": "2026-09-10", "CFB": "2026-08-29", "NBA": "2026-10-20", "CBB": "2026-11-02", "NHL": "2026-10-06"}
POWER_CONF = {"8", "5", "4", "1"}  # SEC, Big Ten, Big 12, ACC (ESPN conference ids); Notre Dame id 87


def now_ct():
    return datetime.datetime.now(CT)


def today_ct():
    return now_ct().strftime("%Y-%m-%d")


def get(url, tries=3, timeout=30):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (board-auto)"})
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def load(name, default):
    p = os.path.join(DATA, name)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return default


def save(name, obj):
    p = os.path.join(DATA, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump(obj, f, indent=1, default=float)


def ct_time(iso):
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(CT)


def american_to_prob(a):
    a = float(a)
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))
