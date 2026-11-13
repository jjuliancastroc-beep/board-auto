"""One run: grade -> build every sport's card -> log new picks -> pre-game review -> parlays -> health -> weekly report -> emails -> page.
Usage: python -m board.run   (or --date YYYY-MM-DD, --weekly to force the weekly report)
"""
import sys, traceback
from .common import today_ct, load, save, SPORTS, now_ct
from . import card, grade, site, review, notify, props
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
            if r["decision"] == "CASH":
                notify.send(f"cash-{date}-{r['id']}", f"Cash pick: {r['pick']} ${r['stake']}", [f"{r['game']} - {r['time']}", f"Price {r.get('price')}, fair {r.get('fair_line')}, playable to {r.get('playable_to')}", r["reason"], "Pull if: " + "; ".join(r["invalidation"])])
    for p in pulls:
        if p["decision"] == "CASH":
            notify.send(f"pull-{p['date']}-{p['id']}", f"PULL: {p['pick']}", [p["review_log"][-1]])
    if not hl["ok"]:
        notify.send(f"health-{date}-{'|'.join(hl['problems'])[:80]}", "Board problem: a data feed needs a look", hl["problems"], "health")
    # player props (separate from the cash card; you tell the Board if you put any in)
    pr = {"props": [], "note": "Props did not run."}
    try:
        props.grade(); props.grade_lines()
        tmr = (datetime.datetime.strptime(date, "%Y-%m-%d") + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        pr = props.build([date, tmr], cards_by_id={r["id"]: r for c in cards for r in c["games"]})
        props.log(pr["props"]); props.log_lines(pr["props"])
        if not pr.get("ok"):
            hl["notes"].append("Props: " + pr.get("note", "Underdog feed did not load."))
        else:
            hl["notes"].append("Props: " + pr["note"])
        save("health.json", hl)
    except Exception as e:
        traceback.print_exc(); hl["notes"].append(f"Props failed: {e}"); save("health.json", hl)
    print("props:", pr.get("note"))
    if wk:
        notify.send(f"weekly-{wk['week']}", wk["title"], wk["lines"], "weekly")
    site.render(cards, load("picks.json", []), load("parlays.json", []), bt, btl, st, hl, pr)
    print("done", now_ct().strftime("%H:%M"))


def enforce_caps(cards):
    """Max 3 cash singles, 2 tickets per game, $180 day cap - extra cash picks drop to paper."""
    cash = sorted([r for c in cards for r in c["games"] if r["decision"] == "CASH"], key=lambda r: -r["conf"])
    total = 0
    for i, r in enumerate(cash):
        if i >= 3 or total + r["stake"] > 150:  # leave room for two $15 parlays under $180
            r["decision"] = "PAPER"; r["stake"] = 0; r["reason"] += " Dropped to paper by the day cap."
        else:
            total += r["stake"]


if __name__ == "__main__":
    main()
