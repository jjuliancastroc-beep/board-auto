import datetime
"""Quick checks that run before every Board update. If any fail, the update stops and you get an email from GitHub."""
import unittest
from board.espn import home_line
from board.grade import payout
from board.card import playable, confidence
from board.common import american_to_prob
from board import commands


class Core(unittest.TestCase):
    def test_home_line(self):
        self.assertEqual(home_line("NYG -3.5", "NYG", "WSH"), -3.5)
        self.assertEqual(home_line("WSH -3.5", "NYG", "WSH"), 3.5)
        self.assertEqual(home_line("EVEN", "NYG", "WSH"), 0.0)
        self.assertIsNone(home_line("XYZ -2", "NYG", "WSH"))

    def test_payout(self):
        self.assertAlmostEqual(payout(-110), 0.909, 3)
        self.assertEqual(payout(150), 1.5)

    def test_prob(self):
        self.assertAlmostEqual(american_to_prob(-110), 0.5238, 3)
        self.assertAlmostEqual(american_to_prob(100), 0.5)

    def test_playable_never_better_than_line(self):
        self.assertLessEqual(playable(9.5, 8.0, 4.5), 9.5)
        self.assertEqual(playable(-3, 3.0, 3.0), -3)

    def test_confidence_one_model_capped(self):
        row = {"flags": [], "against": [], "one_model": True, "test_record": {"w": 300, "l": 200, "n": 500}}
        c, _ = confidence(row, 10, 3, False)
        self.assertLessEqual(c, 6.9)

    def test_confidence_failed_test_scores_lower(self):
        good = {"flags": [], "against": [], "test_record": {"w": 300, "l": 200, "n": 500}}
        bad = {"flags": [], "against": [], "test_record": {"w": 200, "l": 300, "n": 500}}
        self.assertGreater(confidence(good, 6, 3, True)[0], confidence(bad, 6, 3, True)[0])

    def test_commands(self):
        store = {"settings.json": {"bankroll_base": 100, "cash_approved": []}, "picks.json": [], "requests_log.json": []}
        commands.load = lambda f, d=None: store.get(f, d)
        commands.save = lambda f, v: store.__setitem__(f, v)
        out = commands.handle("bankroll 650\napprove nba\nrandom words")
        self.assertEqual(store["settings.json"]["bankroll_base"], 650.0)
        self.assertEqual(store["settings.json"]["cash_approved"], ["NBA"])
        self.assertEqual(len(out), 2)


class Props(unittest.TestCase):
    def test_props_parse_and_math(self):
        from board import props
        assert props.parse_request("prop Jalen Brunson over 25.5 points") == ("Jalen Brunson", "higher", 25.5, "points")
        assert props.parse_request("prop Jokic u 11.5 rebounds")[1:] == ("lower", 11.5, "rebounds")
        assert props.parse_request("bankroll 600") is None
        tot = sum(props.nb_cdf(k, 6.0, 1.6) - (props.nb_cdf(k - 1, 6.0, 1.6) if k else 0) for k in range(0, 80))
        assert abs(tot - 1) < 1e-6
        assert 0.4 < props.p_over(5.5, 6.0, 1.5) < 0.65
        assert props.p_over(0.5, 3.0, 1.0) > 0.9 and props.p_over(30.5, 3.0, 1.0) < 0.01
        assert props.weight({"n": 10}) == 0.35



class OldSetup(unittest.TestCase):
    def test_history_nudge_is_small(self):
        from board import history
        history._cache["rows"] = [(history.today_ct(), ["spread fav"], True, "t")] * 500
        r = history.record(["spread fav"])
        assert 0 < r["adj"] <= 0.5
        history._cache["rows"] = [(history.today_ct(), ["spread fav"], False, "t")] * 500
        assert -0.5 <= history.record(["spread fav"])["adj"] < 0
        history._cache["rows"] = [(history.today_ct(), ["spread fav"], True, "t")] * 3 + [(history.today_ct(), ["spread fav"], False, "t")] * 2
        assert abs(history.record(["spread fav"])["adj"]) < 0.1  # 3-2 barely moves it
        history._cache["rows"] = [("2020-01-01", ["spread fav"], True, "t")] * 500
        assert history.record(["spread fav"])["adj"] == 0.0  # older than 60 days doesn't count
        history.reset()

    def test_mains_need_approval_and_cap(self):
        from board import card, run
        base = {"pick": "X -3", "flags": [], "veto": False, "models_agree": True, "one_model": False, "test_record": {"win": 0.5, "n": 300}}
        r = dict(base, conf=8.2); card.finalize(r, "NBA", {"cash_approved": ["NBA"]})
        assert r["decision"] == "CASH" and r["stake"] == 50
        r = dict(base, conf=7.4); card.finalize(r, "NBA", {"cash_approved": ["NBA"]})
        assert r["decision"] == "CASH" and r["stake"] == 25
        r = dict(base, conf=8.2); card.finalize(r, "CBB", {"cash_approved": ["NBA"]})
        assert r["decision"] == "PAPER"
        r = dict(base, conf=7.4, flags=["L-1112-1: midweek"]); card.finalize(r, "CFB", {"cash_approved": ["CFB"]})
        assert r["decision"] == "PAPER"
        rows = [{"decision": "CASH", "stake": 50, "conf": 9 - i * 0.1, "reason": ""} for i in range(5)]
        run.enforce_caps([{"games": rows}])
        assert sum(1 for x in rows if x["decision"] == "CASH") == 3 and sum(x["stake"] for x in rows) <= 150

    def test_props_card_shape(self):
        import datetime
        from board import props, common
        start = (common.now_ct() + datetime.timedelta(hours=3)).isoformat()
        mk = lambda i, call, ev, conf: {"id": f"d|{i}|points", "date": "2099-01-01", "pick": f"P{i} Higher 10.5 Points", "player": f"P{i}", "sport": "NBA",
                                        "game": "A @ B", "event_id": ev, "stat": "points", "side": "higher", "line": 10.5, "p": 0.6, "mkt": 0.5, "edge": 10,
                                        "conf": conf, "playable_to": 11.5, "start": start, "time": "x", "call": call}
        pr = [mk(i, "PLAY", f"e{i}", 8 - i * 0.1) for i in range(6)] + [mk(10 + i, "LEAN", f"e{i}", 6) for i in range(6)]
        saved = common.load("props_card.json", {})
        try:
            pc = props.card(pr, "2099-01-01")
            assert len(pc["singles"]) == 3 and len(pc["parlays"]) == 2
            ids = [x["id"] for x in pc["singles"]] + [x["id"] for e in pc["parlays"] for x in e["legs"]]
            assert len(ids) == len(set(ids))
            per = {}
            for x in pc["singles"] + [x for e in pc["parlays"] for x in e["legs"]]:
                per[x["event_id"]] = per.get(x["event_id"], 0) + 1
            assert max(per.values()) <= 2
            pr2 = [dict(x, call="PASS", reason="gone") if x["id"] == pc["singles"][0]["id"] else x for x in pr]
            pc2 = props.card(pr2, "2099-01-01")
            assert pc2["singles"][0]["status"] == "PULL" and len(pc2["singles"]) == 3
        finally:
            common.save("props_card.json", saved)



class Placed(unittest.TestCase):
    """How the Board learns what you actually put in."""
    def setUp(self):
        from board import commands, common
        self.c = commands; d = common.today_ct()
        self.store = {
            "props_card.json": {d: {"singles": [{"id": "a", "pick": "Davion Mitchell Higher 14.5 Points", "status": "OPEN", "stake": 15, "odds": "-112"}],
                                    "parlays": [{"name": "Prop parlay 1", "status": "OPEN", "stake": 15, "legs": [{"id": "b", "pick": "X Lower 5.5 Points"}, {"id": "c", "pick": "Y Higher 45.5 Rush yards"}]}]}},
            "props.json": [{"id": "a", "pick": "Davion Mitchell Higher 14.5 Points", "date": d, "placed": False, "result": "Won"},
                           {"id": "b", "pick": "X Lower 5.5 Points", "date": d, "result": "Won"}, {"id": "c", "pick": "Y Higher 45.5 Rush yards", "date": d, "result": "Lost"},
                           {"id": "e", "pick": "Tim Extra Lower 0.5 Steals", "date": d, "placed": False, "result": "Lost", "odds": "-120"}],
            "picks.json": [{"date": d, "id": "g", "pick": "Lindenwood Lions +4.5", "decision": "PAPER", "stake": 0, "result": None},
                           {"date": d, "id": "m", "pick": "Chiefs -3", "decision": "CASH", "stake": 50, "result": None}],
            "parlays.json": [], "settings.json": {}}
        self._l, self._s = commands.load, commands.save
        commands.load = lambda n, default=None: self.store.get(n, default)
        commands.save = lambda n, v: self.store.__setitem__(n, v)

    def tearDown(self):
        self.c.load, self.c.save = self._l, self._s

    def test_placed_and_skip(self):
        from board import grade, props
        c = self.c; card = lambda: list(self.store["props_card.json"].values())[0]
        assert "Marked placed" in c.placed("Mitchell")[0] and card()["singles"][0]["placed"] and self.store["props.json"][0]["placed"]
        c.skip("Mitchell"); assert not card()["singles"][0]["placed"]
        c.placed("card"); assert card()["singles"][0]["placed"] and card()["parlays"][0]["placed"]
        c.skip("prop parlay 1"); assert not card()["parlays"][0]["placed"]
        c.placed("prop parlay 1 $10"); assert card()["parlays"][0]["placed"] and card()["parlays"][0]["stake"] == 10
        paper, main = self.store["picks.json"]
        assert not grade.counts(paper) and grade.counts(main)          # mains count by default, paper does not
        c.placed("Lindenwood $20"); assert grade.counts(paper) and paper["stake"] == 20
        c.skip("Lindenwood"); assert not grade.counts(paper)
        c.skip("Chiefs"); assert not grade.counts(main)
        c.placed("Chiefs"); assert grade.counts(main) and main["stake"] == 50
        c.placed("Tim Extra"); assert self.store["props.json"][3]["placed"]
        assert "Nothing on the Board" in c.placed("Nobody Atall")[0]
        r = props.card_record(self.store["props.json"], self.store["props_card.json"])
        assert (r["singles"]["w"], r["parlays"]["l"]) == (1, 1)
        assert (r["placed"]["w"], r["placed"]["l"]) == (1, 2)             # Mitchell won; the $10 parlay and the extra lost
        assert r["placed"]["pl"] == round(15 * 100 / 112 - 10 - 15, 2)

    def test_command_lines(self):
        out = self.c.handle("placed Mitchell\nprops auto\nrefresh")
        assert len(out) == 3 and self.store["settings.json"]["props_auto"] is True



class Moved(unittest.TestCase):
    """A game that changes days keeps its ticket: not voided, not doubled, not counted against the new day's slots."""
    def test_moved_game(self):
        from board import grade, espn, run, common
        d = common.today_ct(); nxt = (common.now_ct() + datetime.timedelta(days=1))
        start = (common.now_ct() + datetime.timedelta(hours=2)).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        new = (common.now_ct() + datetime.timedelta(hours=30)).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        store = {"picks.json": [{"date": d, "id": "9", "sport": "CFB", "pick": "Ole Miss Rebels +2.5", "decision": "CASH", "stake": 25, "conf": 7.0,
                                 "start": start, "result": None, "logged_at": "00:20", "reason": "x"}]}
        keep = (grade.load, grade.save, espn.event_start)
        grade.load = lambda n, default=None: store.get(n, default); grade.save = lambda n, v: store.__setitem__(n, v)
        espn.event_start = lambda sport, eid: new
        try:
            mv = grade.moved_games([{"games": []}], d)                       # the game is off today's slate
            p = store["picks.json"][0]
            assert len(mv) == 1 and p["start"] == new and p["moved_from"] == start and p["decision"] == "CASH" and grade.counts(p)
            assert grade.moved_games([{"games": []}], d) == []                # second run: nothing new to say
            d2 = nxt.strftime("%Y-%m-%d")
            row = lambda i, conf: {"id": i, "decision": "CASH", "pick": "T" + i, "stake": 50, "conf": conf, "reason": "r", "price": -110, "start": new}
            cards = [{"games": [{"id": "9", "decision": "PAPER", "pick": "Oklahoma Sooners -2.5", "stake": 0, "conf": 6.0, "reason": "r", "price": -110, "start": new},
                                row("1", 8.3), row("2", 8.2), row("3", 8.1)]}]
            grade.lock_mains(cards, d2)
            r = cards[0]["games"][0]
            assert r["decision"] == "CASH" and r["pick"] == "Ole Miss Rebels +2.5" and r["carried"] == d and r["stake"] == 25   # same ticket, not flipped
            run.enforce_caps(cards)
            assert [x["decision"] for x in cards[0]["games"]] == ["CASH"] * 4       # doesn't take one of the new day's 3 slots
            grade.log_picks(cards, d2)
            assert sum(1 for x in store["picks.json"] if x["id"] == "9") == 1       # not logged twice
        finally:
            grade.load, grade.save, espn.event_start = keep


if __name__ == "__main__":
    unittest.main()
