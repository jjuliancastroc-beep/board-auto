"""One run: grade finished picks -> build today's card for every sport -> log new picks -> rebuild the page.
Usage: python -m board.run            (normal scheduled run)
       python -m board.run --date 2026-11-12
"""
import sys, traceback
from .common import today_ct, load, save, SPORTS
from . import card, grade, site


def main():
    date = sys.argv[sys.argv.index("--date") + 1] if "--date" in sys.argv else today_ct()
    bt = load("backtest.json", {})
    try:
        grade.grade_all()
    except Exception:
        traceback.print_exc()
    cards = []
    for sport in SPORTS:
        try:
            c = card.build(sport, date, bt)
        except Exception as e:
            traceback.print_exc(); c = {"sport": sport, "games": [], "note": f"Build failed: {e}"}
        cards.append(c); print(sport, len(c["games"]), "games", sum(1 for r in c["games"] if r["decision"] != "PASS"), "calls")
    save(f"cards/card_{date}.json", cards)
    picks = grade.log_picks(cards, date)
    summ = grade.summary(picks)
    cash = [r for c in cards for r in c["games"] if r["decision"] == "CASH"]
    paper = [r for c in cards for r in c["games"] if r["decision"] == "PAPER"]
    headline = (f"{len(cash)} cash pick(s) today: " + ", ".join(r["pick"] for r in cash)) if cash else f"Pass on cash today. {len(paper)} paper pick(s) tracked."
    cfg = load("settings.json", {"bankroll": 636.23, "goal": 10000})
    note = f"Bankroll ${cfg['bankroll']:.2f} (goal ${cfg['goal']:,}). Units: $50 at 8.0+, $25 at 7.0-7.9, $15 parlays. Cash only when the past-games test supports that kind of pick."
    site.render(cards, picks, summ, bt, headline, note)
    print(headline)


if __name__ == "__main__":
    main()
