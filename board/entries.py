"""My entries: the prop tickets you actually put in (Sleeper, Underdog...), exactly as you built them -
singles, 2-picks, flexes made from several Board picks. Real stakes and real payouts.
Kept apart from the main bankroll and from the Board's own (paper) props card record.

  entry $15 2.75x Vilardi + Traore                         a 2-pick, all must hit
  entry $15 1.83x Wolf points 6.5                          a single; add stat/line if your app's line differs
  entry $15 flex 4.38/1.07 Vilardi + Traore + Pionk + Gauthier   flex: 4.38x if all hit, 1.07x with one miss
  entry 7 won $48        entry 7 lost        entry 7 remove       fix or delete entry number 7
The Board grades each leg itself from the box score. A tap on "I placed this" also lands here (payout estimated until you give the real one).
"""
import re, datetime
from .common import load, save, today_ct

FILE = "my_entries.json"
SIDES = {"over": "Higher", "higher": "Higher", "more": "Higher", "under": "Lower", "lower": "Lower", "less": "Lower"}


def _f(x):
    return float(x)


def _near(d, days):
    t = datetime.datetime.strptime(today_ct(), "%Y-%m-%d")
    return abs((datetime.datetime.strptime(d, "%Y-%m-%d") - t).days) <= days


def match_leg(text, book, oncard=()):
    """Find the Board prop a leg means. All name/stat words must be in the Board's pick text. Best match: on the card, PLAY, highest confidence, newest."""
    words = text.lower().replace(",", " ").split()
    line = next((float(w) for w in words if re.fullmatch(r"\d+(\.\d+)?", w)), None)
    side = next((SIDES[w] for w in words if w in SIDES), None)
    name = [w for w in words if w not in SIDES and not re.fullmatch(r"\d+(\.\d+)?", w)]
    cand = [b for b in book if b.get("pick") and _near(b["date"], 1) and all(w in b["pick"].lower() for w in name)] if name else []
    if not cand:
        return {"pick": text.strip(), "id": None, "result": None, "actual": None}
    cand.sort(key=lambda b: (b["id"] in oncard, b.get("call") == "PLAY", b.get("call") == "LEAN", b.get("conf") or 0, b["date"]))
    b = cand[-1]
    s = side or (b.get("side") or "").title() or "Higher"; ln = line if line is not None else b.get("line")
    return {"pick": f"{b['player']} {s} {ln:g} {b.get('label') or b.get('stat')}", "id": b["id"], "line": ln, "side": s, "board_line": b.get("line"),
            "conf": b.get("conf"), "result": None, "actual": None}


def settle(e):
    """Work out an entry from its legs. A manual result (fixed) is never touched."""
    if e.get("fixed"):
        return e
    rs = [l.get("result") for l in e["legs"]]
    if any(r is None for r in rs):
        if "Lost" in rs and not e.get("flex"):
            e.update(result="Lost", payout=0.0, pl=-e["stake"])
        return e
    miss = rs.count("Lost"); live = [r for r in rs if r in ("Won", "Lost")]
    if len(live) < len(rs):  # a push or a scratch changes the payout in the app - needs your number
        e["result"] = "Lost" if miss and not e.get("flex") else "Check"
        if e["result"] == "Lost":
            e.update(payout=0.0, pl=-e["stake"])
        return e
    if miss == 1 and e.get("kind") == "flex" and not e.get("flex"):  # a flex still pays with one miss, but the Board wasn't told how much
        e.update(result="Check", payout=None, pl=None); return e
    mult = e.get("mult") if miss == 0 else (e.get("flex") if miss == 1 and e.get("flex") else 0.0)
    e["result"] = "Won" if miss == 0 else ("Part" if mult else "Lost")
    if mult is None:
        e["payout"] = None; e["pl"] = None  # won, but the Board was never told the payout
    else:
        e["payout"] = round(e["stake"] * mult, 2); e["pl"] = round(e["payout"] - e["stake"], 2)
    return e


def grade(book=None, ents=None):
    """Fill in leg results from the graded props book, then settle each entry."""
    keep = ents is None
    ents = ents if ents is not None else load(FILE, []); book = book if book is not None else load("props.json", [])
    by = {b["id"]: b for b in book}
    for e in ents:
        if e.get("fixed"):
            continue
        for l in e["legs"]:
            b = by.get(l.get("id"))
            if l.get("result") or not b or b.get("result") is None:
                continue
            a = b.get("actual")
            if b["result"] in ("Void", "No result") or a is None:
                l["result"] = "Void"; continue
            l["actual"] = a
            l["result"] = "Push" if a == l["line"] else ("Won" if (a > l["line"]) == (l["side"] == "Higher") else "Lost")
        settle(e)
    if keep:
        save(FILE, ents)
    return ents


def sync(book=None, allc=None, ents=None):
    """A tap on 'I placed this' (or props auto) becomes an entry here, so there is one place for what you put in.
    Undo removes it. Entries you logged yourself or sent as screenshots are never touched."""
    keep = ents is None
    ents = ents if ents is not None else load(FILE, []); book = book if book is not None else load("props.json", [])
    allc = allc if allc is not None else load("props_card.json", {})
    from .props import PROP_STAKE, _payout
    want = {}  # (date, leg ids) -> (stake, estimated multiplier, picks)
    by = {b["id"]: b for b in book}
    for d, pc in allc.items():
        for it in pc.get("singles", []):
            if it.get("placed"):
                want[(d, (it["id"],))] = (it.get("stake") or PROP_STAKE, round(1 + _payout(it.get("odds")), 2))
        for e in pc.get("parlays", []):
            if e.get("placed"):
                want[(d, tuple(sorted(x["id"] for x in e["legs"])))] = (e.get("stake") or PROP_STAKE, 3.0)
    for b in book:
        if b.get("placed") and (b["date"], (b["id"],)) not in want:
            want[(b["date"], (b["id"],))] = (b.get("placed_stake") or PROP_STAKE, round(1 + _payout(b.get("odds")), 2))
    key = lambda e: (e["date"], tuple(sorted(l.get("id") or "" for l in e["legs"])))
    have = {key(e) for e in ents}
    ents[:] = [e for e in ents if e.get("source") != "tap" or key(e) in want]
    for (d, ids), (stake, mult) in sorted(want.items()):
        if (d, ids) in have or any(i not in by for i in ids):
            continue
        legs = [{"pick": by[i]["pick"], "id": i, "line": by[i].get("line"), "side": (by[i].get("side") or "Higher").title(), "board_line": by[i].get("line"),
                 "conf": by[i].get("conf"), "result": None, "actual": None} for i in ids]
        ents.append({"n": next_n(ents), "date": d, "app": "", "stake": stake, "mult": mult, "flex": None, "kind": "single" if len(ids) == 1 else "all", "est": True, "legs": legs,
                     "result": None, "payout": None, "pl": None, "source": "tap"})
    if keep:
        save(FILE, ents)
    return ents


def next_n(ents):
    return max([e.get("n", 0) for e in ents], default=0) + 1


def record(ents=None):
    ents = ents if ents is not None else load(FILE, [])
    out = {"w": 0, "l": 0, "open": 0, "staked": 0.0, "back": 0.0, "pl": 0.0, "need": 0}
    for e in ents:
        r = e.get("result")
        if r in ("Won", "Part", "Lost") and e.get("pl") is not None:
            out["w" if e["pl"] > 0 else "l"] += 1
            out["staked"] += e["stake"]; out["back"] += e["payout"]; out["pl"] += e["pl"]
        elif r in ("Won", "Check"):
            out["need"] += 1
        else:
            out["open"] += 1
    for k in ("staked", "back", "pl"):
        out[k] = round(out[k], 2)
    return out


def command(arg):
    ents = load(FILE, []); book = load("props.json", [])
    m = re.fullmatch(r"#?(\d+)\s+(won|lost|remove|delete)(?:\s+\$?(\d+(?:\.\d+)?))?", arg.strip().lower())
    if m:
        e = next((e for e in ents if e.get("n") == int(m.group(1))), None)
        if not e:
            return [f"No entry number {m.group(1)}."]
        if m.group(2) in ("remove", "delete"):
            ents.remove(e); save(FILE, ents); return [f"Removed entry {e['n']}."]
        if m.group(2) == "won":
            pay = float(m.group(3)) if m.group(3) else (round(e["stake"] * e["mult"], 2) if e.get("mult") else None)
            if pay is None:
                return [f"What did entry {e['n']} pay? Say: entry {e['n']} won $48"]
            e.update(result="Won", payout=pay, pl=round(pay - e["stake"], 2), fixed=True, est=False)
        else:
            e.update(result="Lost", payout=0.0, pl=-e["stake"], fixed=True)
        save(FILE, ents)
        return [f"Entry {e['n']} set to {e['result']}" + (f", paid ${e['payout']:.2f} ({e['pl']:+.2f})." if e["result"] == "Won" else f" (-${e['stake']:g}).")]
    stake = 15.0; mult = None; flex = None; rest = arg
    m = re.search(r"\$(\d+(?:\.\d+)?)", rest)
    if m:
        stake = float(m.group(1)); rest = rest[:m.start()] + rest[m.end():]
    m = re.search(r"\bflex\s+(\d+(?:\.\d+)?)x?\s*[/|]\s*(\d+(?:\.\d+)?)x?", rest, re.I)
    if m:
        mult, flex = float(m.group(1)), float(m.group(2)); rest = rest[:m.start()] + rest[m.end():]
    else:
        m = re.search(r"\b(\d+(?:\.\d+)?)x\b", rest, re.I)
        if m:
            mult = float(m.group(1)); rest = rest[:m.start()] + rest[m.end():]
    kind = "flex" if flex or re.search(r"\bflex\b", rest, re.I) else None
    legs = [t.strip() for t in re.split(r"\s*(?:\+|,|&| and )\s*", re.sub(r"\bflex\b", " ", rest, flags=re.I)) if t.strip()]
    if not legs:
        return ["Format: entry $15 2.75x Vilardi + Traore   (flex: entry $15 flex 4.38/1.07 A + B + C + D)"]
    oncard = {it["id"] for pc in load("props_card.json", {}).values() for it in pc.get("singles", [])}
    e = {"n": next_n(ents), "date": today_ct(), "app": "", "stake": stake, "mult": mult, "flex": flex, "kind": kind or ("single" if len(legs) == 1 else "all"), "est": False,
         "legs": [match_leg(t, book, oncard) for t in legs], "result": None, "payout": None, "pl": None, "source": "you"}
    ds = [l["id"][:10] for l in e["legs"] if l.get("id")]
    if ds:
        e["date"] = min(ds)
    ents.append(e); grade(book, ents); save(FILE, ents)
    out = [f"Entry {e['n']} logged: ${stake:g}" + (f" flex {mult:g}x / {flex:g}x" if flex else f" at {mult:g}x" if mult else " (no payout given - add it when it settles)") + ": " +
           " + ".join(l["pick"] for l in e["legs"]) + "."]
    miss = [l["pick"] for l in e["legs"] if not l.get("id")]
    if miss:
        out.append("Not on the Board, so I can't grade these myself: " + ", ".join(miss) + f". When it settles say: entry {e['n']} won $X  or  entry {e['n']} lost")
    return out
