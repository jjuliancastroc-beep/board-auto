"""Our own track record, used LIGHTLY.

Sources: the old Board site's graded tickets (data/history_old.json - bucket, date, result only) plus this Board's
graded picks (data/picks.json) and graded props (data/props.json).

Why light: our own record is a small, noisy sample. Leaning on it hard would let a hot or cold streak swing the
confidence score. So:
  - only the last 60 days count, and recent results count more (a result loses half its weight every 21 days)
  - the record is pulled toward break-even by 40 phantom games before it says anything
  - the most it can move a confidence score is +/-0.5
"""
import datetime, re
from .common import load, today_ct

HALF_LIFE = 21
MAX_AGE = 60
K = 40
CAP = 0.5
_cache = {}


def _rows():
    if "rows" in _cache:
        return _cache["rows"]
    rows = []
    for o in load("history_old.json", []):
        rows.append((o["d"], o["b"], o["r"] == "W", "old Board"))
    for p in load("picks.json", []):
        if p.get("result") not in ("Won", "Lost") or not p.get("pick"):
            continue
        rows.append((p["date"], main_buckets(p.get("sport"), p["pick"], p.get("price")), p["result"] == "Won", "this Board"))
    for p in load("props.json", []):
        if p.get("result") not in ("Won", "Lost") or not p.get("side"):
            continue
        rows.append((p["date"], prop_buckets(p.get("sport"), p["stat"], p["side"]), p["result"] == "Won", "this Board"))
    _cache["rows"] = rows
    return rows


def reset():
    _cache.clear()


def main_buckets(sport, pick, price=None):
    """'Lakers -4.5' -> ['spread fav', 'NBA spread fav'];  'Stars ML (+120)' -> ['ml', 'NHL ml']."""
    if " ML" in pick:
        b = "ml"
    else:
        m = re.findall(r"([+-]\d+(?:\.\d+)?)$", pick.strip())
        if not m:
            return []
        b = "spread fav" if float(m[-1]) < 0 else "spread dog"
    return [b] + ([f"{sport} {b}"] if sport else [])


def prop_buckets(sport, stat, side):
    s = "over" if side == "higher" else "under"
    return [f"prop {s}", f"prop {stat} {s}"] + ([f"{sport} prop {stat} {s}"] if sport else [])


def record(keys, center=0.524):
    """Best-matching bucket (most specific with 15+ results, else the general one) -> adjustment and plain summary."""
    today = datetime.date.fromisoformat(today_ct())
    best = None
    for key in reversed(keys):  # most specific first
        w = l = we = le = 0.0
        for d, bks, won, _src in _rows():
            if key not in bks:
                continue
            age = (today - datetime.date.fromisoformat(d)).days
            if age < 0 or age > MAX_AGE:
                continue
            wt = 0.5 ** (age / HALF_LIFE)
            if won:
                w += 1; we += wt
            else:
                l += 1; le += wt
        if w + l >= 15 or (key == keys[0] and w + l > 0):
            best = (key, int(w), int(l), we, le)
            break
    if not best:
        return {"adj": 0.0, "text": "No track record yet for this kind of pick.", "key": None}
    key, w, l, we, le = best
    shrunk = (we + K * center) / (we + le + K)
    adj = round(max(-CAP, min(CAP, (shrunk - center) * 5)), 2)
    return {"adj": adj, "key": key, "w": w, "l": l,
            "text": f"Our record on {key}: {w}-{l} (last 60 days, recent counts more) -> {adj:+.2f} to confidence"}
