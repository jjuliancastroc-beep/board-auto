"""Change settings from your phone: tap a button on the Board (it opens a filled-in GitHub issue - just hit Submit),
or comment on any issue in the repo. Only the repo owner's comments count.

  bankroll 650          set the bankroll to $650 (from today on, placed tickets add to it)
  approve NBA           allow mains for that sport (your graduation call)
  unapprove NBA         back to paper
  skip Raptors          you did NOT place that ticket - it stops counting (mains, parlays, props)
  placed Mitchell       you put that pick in. Works for props, prop parlays ("placed prop parlay 1"), paper picks
                        ("placed Lindenwood $25") and main parlays ("placed parlay 1"). Add "$20" to set the amount.
  placed card           you put in today's whole props card (3 singles + 2 parlays)
  props auto            count the props card as placed every day unless you skip one;  props manual  = back to telling it
  goal 10000            change the goal
  prop Brunson over 25.5 points   full workup on any player line (today or tomorrow)
  refresh               rebuild the Board right now
  help                  list commands
"""
import os, json, sys, re
from .common import load, save, today_ct, SPORTS
from .notify import _api, OWNER
from . import props


def _amount(arg):
    m = re.search(r"\s\$(\d+(?:\.\d+)?)\s*$", arg)
    return (arg[:m.start()].strip(), float(m.group(1))) if m else (arg.strip(), None)


def _recent_cards():
    allc = load("props_card.json", {})
    return allc, sorted(allc, reverse=True)[:3]


def placed(arg):
    """Record what you actually put in. Order: props card -> today's main card -> any logged prop."""
    name, amt = _amount(arg); low = name.lower(); out = []
    allc, days = _recent_cards(); book = load("props.json", []); byid = {b["id"]: b for b in book}
    def mark(it, what):
        it["placed"] = True
        if amt is not None:
            it["stake"] = amt
        it.setdefault("stake", props.PROP_STAKE)
        out.append(f"Marked placed: {what} (${it['stake']:g}).")
    if low in ("card", "props card", "the card", "all props", "prop card"):
        d = today_ct(); pc = allc.get(d) or {"singles": [], "parlays": []}
        for it in pc["singles"]:
            if it.get("status") != "PULL":
                mark(it, it["pick"])
                if it["id"] in byid:
                    byid[it["id"]]["placed"] = True
        for e in pc["parlays"]:
            if e.get("status") != "PULL":
                mark(e, e["name"] + ": " + " + ".join(x["pick"] for x in e["legs"]))
        save("props_card.json", allc); save("props.json", book)
        return out or ["Nothing on today's props card yet."]
    m = re.fullmatch(r"prop parlay (\d)", low)
    if m:
        for d in days:
            e = next((e for e in allc[d]["parlays"] if e["name"].endswith(m.group(1))), None)
            if e:
                mark(e, f"{e['name']} ({d}): " + " + ".join(x["pick"] for x in e["legs"]))
                save("props_card.json", allc); return out
        return [f"No prop parlay {m.group(1)} on the card."]
    m = re.fullmatch(r"parlay (\d)", low)
    if m:
        pars = load("parlays.json", []); d = today_ct()
        x = next((x for x in pars if x["date"] == d and x["name"].endswith(m.group(1))), None)
        if not x:
            return [f"No parlay {m.group(1)} today."]
        x.pop("skipped", None)
        if x.get("decision") != "CASH":
            x["user_placed"] = True
        x["stake"] = amt if amt is not None else (x.get("stake") or 15)
        if x.get("units") is not None:
            x["pl"] = round(x["stake"] * x["units"], 2)
        save("parlays.json", pars)
        return [f"Marked placed: {x['name']}: {' + '.join(x['picks'])} (${x['stake']:g})."]
    for d in days:  # a single on the props card
        it = next((it for it in allc[d]["singles"] if low in it["pick"].lower()), None)
        if it:
            mark(it, f"{it['pick']} ({d})")
            if it["id"] in byid:
                byid[it["id"]]["placed"] = True; byid[it["id"]]["placed_stake"] = it["stake"]
            save("props_card.json", allc); save("props.json", book); return out
    picks = load("picks.json", [])  # a pick on the main card (today first, then the most recent)
    hit = [p for p in picks if p.get("pick") and low in p["pick"].lower()]
    hit.sort(key=lambda p: (p["date"] == today_ct(), p["date"]))
    if hit:
        p = hit[-1]; p.pop("skipped", None)
        if p["decision"] != "CASH":
            p["user_placed"] = True
        p["stake"] = amt if amt is not None else (p.get("stake") or 25)
        if p.get("units") is not None:
            p["pl"] = round(p["stake"] * p["units"], 2)
        save("picks.json", picks)
        return [f"Marked placed: {p['pick']} ({p['date']}) at ${p['stake']:g}. It now counts toward the bankroll." +
                ("" if amt is not None or p["decision"] == "CASH" else " Different amount? Say 'placed " + name + " $15'.")]
    hit = [b for b in book if low in (b.get("pick") or "").lower()]  # any other logged prop (an extra play or a lean)
    if hit:
        b = hit[-1]; b["placed"] = True; b["placed_stake"] = amt if amt is not None else props.PROP_STAKE
        save("props.json", book)
        return [f"Marked placed: {b['pick']} ({b['date']}) at ${b['placed_stake']:g}."]
    return [f"Nothing on the Board matches '{name}'. Use the player or team name as it shows on the Board."]


def skip(arg):
    """You did NOT place it. Mains and $15 parlays stop counting; props go back to paper."""
    name, _ = _amount(arg); low = name.lower()
    m = re.fullmatch(r"(prop )?parlay (\d)", low)
    if m and m.group(1):
        allc, days = _recent_cards()
        for d in days:
            e = next((e for e in allc[d]["parlays"] if e["name"].endswith(m.group(2))), None)
            if e:
                e["placed"] = False; save("props_card.json", allc); return [f"Marked not placed: {e['name']} ({d})."]
        return ["No prop parlay by that number."]
    if m:
        pars = load("parlays.json", []); x = next((x for x in pars if x["date"] == today_ct() and x["name"].endswith(m.group(2))), None)
        if not x:
            return ["No parlay by that number today."]
        x["skipped"] = True; x.pop("user_placed", None); x["pl"] = 0.0; save("parlays.json", pars)
        return [f"Marked not placed: {x['name']}."]
    picks = load("picks.json", [])
    hit = [p for p in picks if p.get("pick") and low in p["pick"].lower() and (p["decision"] == "CASH" or p.get("user_placed"))]
    if hit:
        p = hit[-1]; p["skipped"] = True; p.pop("user_placed", None); p["pl"] = 0.0; save("picks.json", picks)
        return [f"Marked not placed: {p['pick']} ({p['date']})."]
    allc, days = _recent_cards(); book = load("props.json", [])
    for d in days:
        it = next((it for it in allc[d]["singles"] if low in it["pick"].lower() and it.get("placed")), None)
        if it:
            it["placed"] = False
            for b in book:
                if b["id"] == it["id"]:
                    b["placed"] = False
            save("props_card.json", allc); save("props.json", book)
            return [f"Marked not placed: {it['pick']} ({d})."]
    hit = [b for b in book if low in (b.get("pick") or "").lower() and b.get("placed")]
    if hit:
        hit[-1]["placed"] = False; save("props.json", book)
        return [f"Marked not placed: {hit[-1]['pick']}."]
    return [f"No placed ticket matching '{name}'."]


def handle(text):
    st = load("settings.json", {}); out = []
    for line in text.splitlines():
        w = line.strip().split()
        if not w:
            continue
        cmd = w[0].lower(); arg = " ".join(w[1:])
        if cmd == "bankroll" and re.fullmatch(r"\$?\d+(\.\d+)?", arg):
            st["bankroll_base"] = float(arg.lstrip("$")); st["base_date"] = today_ct(); out.append(f"Bankroll set to ${st['bankroll_base']:.2f} as of {st['base_date']}.")
        elif cmd == "goal" and arg.replace(",", "").isdigit():
            st["goal"] = int(arg.replace(",", "")); out.append(f"Goal set to ${st['goal']:,}.")
        elif cmd in ("approve", "unapprove") and arg.upper() in SPORTS:
            s = set(st.get("cash_approved") or [])
            (s.add if cmd == "approve" else s.discard)(arg.upper()); st["cash_approved"] = sorted(s)
            out.append(f"{arg.upper()} {'approved for cash (still needs every pick to pass the gate)' if cmd == 'approve' else 'back to paper'}.")
        elif cmd in ("skip", "unplace") and arg:
            out += skip(arg)
        elif cmd == "props" and arg.lower() in ("auto", "manual"):
            st["props_auto"] = arg.lower() == "auto"
            out.append("Props card now counts as placed every day unless you skip one." if st["props_auto"] else "Props card is paper until you say placed.")
        elif cmd == "refresh":
            out.append("Rebuilding the Board now - give it a few minutes.")
        elif cmd == "prop" and arg:
            res = props.ask(line.strip())
            out += res or ["Format: prop <player> over|under <line> <stat>, e.g. prop Brunson over 25.5 points"]
        elif cmd == "placed" and arg:
            out += placed(arg)
        elif cmd == "help":
            out.append(__doc__)
    if out:
        save("settings.json", st)
    return out


def pending():
    """Every command of yours from the last 3 days that hasn't been applied yet (new issues and comments).
    The Board looks for these on every run, so a tap is never lost even if GitHub drops or cancels the run it started."""
    import datetime
    done = set(load("commands_done.json", []))
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    items = []
    for it in _api("GET", f"/issues?state=all&creator={OWNER}&since={since}&per_page=100") or []:
        if "pull_request" in it or f"i{it['number']}" in done:
            continue
        items.append((it["created_at"], f"i{it['number']}", it["number"], (it.get("title") or "") + "\n" + (it.get("body") or ""), True))
    for c in _api("GET", f"/issues/comments?since={since}&per_page=100") or []:
        if (c.get("user") or {}).get("login") != OWNER or f"c{c['id']}" in done:
            continue
        items.append((c["created_at"], f"c{c['id']}", int(c["issue_url"].rsplit("/", 1)[1]), c.get("body") or "", False))
    return sorted(items)


def main():
    todo = pending()
    done = load("commands_done.json", [])
    for _, key, num, body, is_new in todo:
        try:
            res = handle(body)
        except Exception as e:
            res = [f"That one failed: {e}"]
        done.append(key); save("commands_done.json", done[-500:])
        if not res:
            continue
        log = load("requests_log.json", []); log.append({"date": today_ct(), "text": body.strip()[:200], "result": res}); save("requests_log.json", log[-100:])
        _api("POST", f"/issues/{num}/comments", {"body": "Done:\n" + "\n".join(f"- {r}" for r in res)})
        if is_new:  # a one-tap button opened this issue - answer it and close it so they don't pile up
            _api("PATCH", f"/issues/{num}", {"state": "closed"})
        print(key, res)
    print(f"{len(todo)} command(s) applied")


if __name__ == "__main__":
    main()
