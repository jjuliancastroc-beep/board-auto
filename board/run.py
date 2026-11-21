"""One run: grade -> build every sport's card -> log new picks -> pre-game review -> parlays -> health -> weekly report -> emails -> page.
Usage: python -m board.run   (or --date YYYY-MM-DD, --weekly to force the weekly report)
"""
import sys, traceback
from .common import today_ct, load, save, SPORTS, now_ct
from . import card, grade, site, review, notify, props, entries, learn
import datetime


def main():
    date = sys.argv[sys.argv.index("--date") + 1] if "--date" in sys.argv else today_ct()
    bt = load("backtest.json", {}); btl = load("backtest_live.json", {}); st = load("settings.json", {})
    try:
        grade.grade_all()
    except Exception:
        traceback.print_exc()
    cards = []
    for sport in SPORTS:
        try:
            c = card.build(sport, date, bt, btl, st)
        except Exception as e:
            traceback.print_exc(); c = {"sport": sport, "games": [], "note": f"Build failed: {e}"}
        cards.append(c); print(sport, len(c["games"]), "games", sum(1 for r in c["games"] if r["decision"] in ("CASH", "PAPER")), "calls")
    grade.moved_games(cards, date)
    grade.lock_mains(cards, date)
    mem = {}
    try:  # the Board's memory: refresh what it has learned, then make today's learned decisions
        mem = learn.update(); learn.apply(cards, mem, date, load("picks.json", []))
    except Exception:
        traceback.print_exc()
    enforce_caps(cards)
    save(f"cards/card_{date}.json", cards)
    picks = grade.log_picks(cards, date)
    pulls = review.prelock(picks, cards)
    pars = grade.build_parlays(cards, date, picks)
    hl = review.health(cards, picks); save("health.json", hl)
    wk = review.weekly(picks, load("parlays.json", []), bt, btl, st, force="--weekly" in sys.argv)
    # emails - only what's worth one
    for c in cards:
        for r in c["games"]:
            if r["decision"] == "CASH" and not r.get("carried"):
                notify.send(f"cash-{date}-{r['id']}", f"Main: {r['pick']} ${r['stake']}", [f"{r['game']} - {r['time']}", f"Price {r.get('price')}, fair {r.get('fair_line')}, playable to {r.get('playable_to')}", r["reason"], "Pull if: " + "; ".join(r["invalidation"])])
    for p in picks:
        if p.get("moved") and p["result"] is None and grade.counts(p):
            notify.send(f"moved-{p['id']}-{p['start'][:10]}", f"Game moved: {p['pick']}", [p["moved"], f"Your ${p['stake']} ticket still counts on the Board and will be graded when the game is played.",
                        "Check the ticket in your book - some books cancel bets when a game changes days. If yours was cancelled, comment: skip " + p["pick"]])
    for p in pulls:
        if p["decision"] == "CASH":
            notify.send(f"pull-{p['date']}-{p['id']}", f"PULL: {p['pick']}", [p["review_log"][-1]])
    if not hl["ok"]:
        notify.send(f"health-{date}-{'|'.join(hl['problems'])[:80]}", "Board problem: a data feed needs a look", hl["problems"], "health")
    # player props (separate from the cash card; you tell the Board if you put any in)
    pr = {"props": [], "note": "Props did not run."}
    try:
        props.grade(); props.grade_lines()
        entries.sync(); entries.grade()  # your own prop tickets (My entries)
        tmr = (datetime.datetime.strptime(date, "%Y-%m-%d") + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        pr = props.build([date, tmr], cards_by_id={r["id"]: r for c in cards for r in c["games"]})
        try:
            learn.apply_props(pr["props"], mem)
        except Exception:
            traceback.print_exc()
        props.log(pr["props"]); props.log_lines(pr["props"])
        if pr.get("ok"):
            pr["card"] = props.card(pr["props"], date)
            for it in pr["card"]["singles"] + pr["card"]["parlays"]:  # a prop you placed went bad before the game - tell you
                if it.get("placed") and it.get("status") == "PULL":
                    nm = it.get("pick") or it.get("name")
                    notify.send(f"proppull-{date}-{nm}", f"PULL (prop): {nm}", [it.get("pull_why") or "Went bad before the game."])
        if not pr.get("ok"):
            hl["notes"].append("Props: " + pr.get("note", "Underdog feed did not load."))
        else:
            hl["notes"].append("Props: " + pr["note"])
        save("health.json", hl)
    except Exception as e:
        traceback.print_exc(); hl["notes"].append(f"Props failed: {e}"); save("health.json", hl)
    print("props:", pr.get("note"))
    if wk:
        from .common import calib_verdict
        wk["lines"] += ["Main picks, confidence check: " + calib_verdict(grade.tiers(picks))["text"], "Props, confidence check: " + calib_verdict(props.bands())["text"]]
        notify.send(f"weekly-{wk['week']}", wk["title"], wk["lines"], "weekly")
    site.render(cards, load("picks.json", []), load("parlays.json", []), bt, btl, st, hl, pr)
    print("done", now_ct().strftime("%H:%M"))


def enforce_caps(cards):
    """Max 3 mains, 2 tickets per game, $150 for mains so two $15 parlays fit under $180. Locked mains count first;
    extra cash picks drop to paper.
    Learned $10 plays (11/21 fix) are their own lane: they never take a main's slot. Most 2 a day, and they only stay if
    mains + learned + two $15 parlays fit under $180 - otherwise the learned play is the one that drops."""
    cash = [r for c in cards for r in c["games"] if r["decision"] == "CASH" and not r.get("carried")]
    mains = sorted([r for r in cash if not r.get("learned")], key=lambda r: (not r.get("locked"), -r["conf"]))
    learned = sorted([r for r in cash if r.get("learned")], key=lambda r: (not r.get("locked"), -r["conf"]))
    total = 0; n = 0
    for r in mains:
        if not r.get("locked") and (n >= 3 or total + r["stake"] > 150):
            r["decision"] = "PAPER"; r["stake"] = 0; r["reason"] += " Dropped to paper by the day cap (3 mains, $150)."
        else:
            total += r["stake"]; n += 1
    k = 0
    for r in learned:
        if not r.get("locked") and (k >= 2 or total + r["stake"] + 30 > 180):
            r["decision"] = "PAPER"; r["stake"] = 0; r.pop("learned", None); r["reason"] += " Learned play dropped - no room under the $180 day cap."
        else:
            total += r["stake"]; k += 1

if __name__ == "__main__":
    main()
