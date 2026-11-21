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
            capped = [dict(x, call="PASS", capped=True, reason="squeezed off the list") if x["id"] == pc["singles"][1]["id"] else x for x in pr]
            assert props.card(capped, "2099-01-01")["singles"][1]["status"] == "OPEN"   # squeezed off the list is not a reason to pull
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



class MyEntries(unittest.TestCase):
    """Your own prop tickets: logged your way, graded from the box score, never mixed into the bankroll."""
    def setUp(self):
        from board import entries, commands, common
        self.e = entries; self.c = commands; d = self.d = common.today_ct()
        mk = lambda i, name, side, line, actual, res, call="PLAY": {"id": f"{d}|{i}|s", "player": name, "pick": f"{name} {side} {line:g} Points", "label": "Points", "side": side.lower(),
                                                                    "line": line, "date": d, "call": call, "conf": 8.0, "actual": actual, "result": res, "odds": "-110", "placed": False}
        self.store = {"props.json": [mk(1, "Gabe Vilardi", "Higher", 1.5, 7, "Won"), mk(2, "Nolan Traore", "Higher", 10.5, 11, "Won"), mk(3, "Neal Pionk", "Higher", 1.5, 1, "Lost"),
                                     mk(4, "Danny Wolf", "Higher", 7.5, 7, "Lost"), mk(5, "Open Guy", "Lower", 9.5, None, None)],
                      "props_card.json": {d: {"singles": [{"id": f"{d}|5|s", "pick": "Open Guy Lower 9.5 Points", "status": "OPEN", "stake": 15, "odds": "-110"}], "parlays": []}},
                      "parlays.json": [{"date": d, "name": "Parlay 1", "picks": ["A", "B"], "decision": "CASH", "stake": 15, "result": "Won", "units": 2.45, "pl": 36.75}], "settings.json": {}}
        self.keep = (common.load, common.save)
        ld = lambda n, default=None: self.store.get(n, default); sv = lambda n, v: self.store.__setitem__(n, v)
        for m in (entries, commands):
            m.load = ld; m.save = sv

    def tearDown(self):
        for m in (self.e, self.c):
            m.load, m.save = self.keep

    def test_entries(self):
        E = self.e; ents = lambda: self.store["my_entries.json"]
        out = self.c.handle("entry $10 2.75x Vilardi + Traore")
        assert "Entry 1 logged" in out[0] and ents()[0]["result"] == "Won" and ents()[0]["payout"] == 27.5 and ents()[0]["pl"] == 17.5
        E.command("$15 flex 4.38/1.07 Vilardi + Traore + Pionk")          # one miss: the flex still pays its smaller number
        assert ents()[1]["result"] == "Part" and ents()[1]["payout"] == 16.05
        E.command("$15 1.83x Wolf points 6.5")                              # your app's line (6.5) beats the Board's (7.5): 7 points wins
        assert ents()[2]["legs"][0]["line"] == 6.5 and ents()[2]["result"] == "Won" and ents()[2]["payout"] == 27.45
        E.command("$15 2x Wolf + Open Guy")                                 # one leg already lost - dead, even with a leg still to play
        assert ents()[3]["result"] == "Lost" and ents()[3]["pl"] == -15
        E.command("$15 Somebody Else + Vilardi")                            # a pick the Board doesn't have: kept, waits for your word
        assert ents()[4]["result"] is None and ents()[4]["legs"][0]["id"] is None
        assert "paid $48.00" in E.command("5 won $48")[0] and ents()[4]["pl"] == 33
        r = E.record(ents())
        assert (r["w"], r["l"], r["pl"]) == (4, 1, round(17.5 + 1.05 + 12.45 - 15 + 33, 2))
        E.command("4 remove"); assert len(ents()) == 4

    def test_tap_becomes_entry_and_undo_removes_it(self):
        E = self.e
        self.c.placed("Open Guy"); E.sync()
        ents = self.store["my_entries.json"]
        assert len(ents) == 1 and ents[0]["source"] == "tap" and ents[0]["est"] and ents[0]["stake"] == 15
        E.sync(); assert len(self.store["my_entries.json"]) == 1            # not doubled on the next run
        self.c.skip("Open Guy"); E.sync(); assert self.store["my_entries.json"] == []

    def test_skip_an_older_parlay(self):
        import datetime
        y = (datetime.datetime.strptime(self.d, "%Y-%m-%d") - datetime.timedelta(days=1))
        self.store["parlays.json"][0]["date"] = y.strftime("%Y-%m-%d")
        assert "Marked not placed" in self.c.skip(f"parlay 1 {y.month}/{y.day}")[0]
        x = self.store["parlays.json"][0]; assert x["skipped"] and x["pl"] == 0.0
        self.c.placed("parlay 1"); assert not x.get("skipped") and x["pl"] == 36.75   # finds yesterday's when today has none


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


class Books(unittest.TestCase):
    def test_other_books(self):
        from board import books, props
        ath = lambda i: {"$ref": f"http://x/athletes/{i}?lang=en"}
        it = lambda i, name, line, price: {"athlete": ath(i), "type": {"name": name}, "current": {"target": {"value": line}}, "odds": {"american": {"value": price}}}
        dk = books.parse_dk([it(7, "Total Points", 20.5, "-120"), it(7, "Total Points", 20.5, "EVEN"), it(7, "Total Rebounds", 5.5, "-110"),   # one-sided: dropped
                             it(8, "Total Assists", 4.5, "+105"), it(8, "Total Assists", 5.5, "-130"), it(9, "First Basket", 0.5, "+900")])       # two lines / not a total: dropped
        assert dk == {("7", "points"): {"book": "DraftKings", "line": 20.5, "over": -120, "under": 100}}
        mu = [{"id": 1, "type": "special", "special": {"category": "Player Props", "description": "Luka Doncic (Points) Total Points"},
               "participants": [{"id": 11, "name": "Over"}, {"id": 12, "name": "Under"}], "parent": {"participants": [{"name": "Los Angeles Lakers", "alignment": "home"}]}, "startTime": "2099-01-01T01:00:00Z"},
              {"id": 2, "type": "matchup", "participants": []}]
        mk = [{"matchupId": 1, "type": "total", "period": 0, "prices": [{"participantId": 11, "points": 30.5, "price": -115}, {"participantId": 12, "points": 30.5, "price": -105}]}]
        pin = books.parse_pinnacle("NBA", mu, mk)
        assert pin[("NBA", "luka doncic", "points")]["line"] == 30.5 and pin[("NBA", "luka doncic", "points")]["over"] == -115
        sl = [{"sport": "nba", "status": "active", "game_status": "pre_game", "outcome_type": "over_under", "line_type": "normal", "wager_type": "rebounds", "subject_id": "55",
               "options": [{"outcome": "over", "outcome_value": 8.5, "payout_multiplier": "1.8"}, {"outcome": "under", "outcome_value": 8.5, "payout_multiplier": "1.76"}]},
              {"sport": "nba", "status": "active", "game_status": "in_game", "outcome_type": "over_under", "line_type": "normal", "wager_type": "points", "subject_id": "55", "options": []}]
        slp = books.parse_sleeper(sl, {("nba", "55"): "Nikola Jokić Jr."})
        assert slp == {("NBA", "nikola jokic", "rebounds"): {"book": "Sleeper", "line": 8.5, "over_x": 1.8, "under_x": 1.76}}
        # the books' chance: even prices = 50%, vig removed; Sleeper never counts; a far-away line never counts
        even = {"book": "DraftKings", "line": 20.5, "over": -110, "under": -110}
        q, used = books.consensus([even, {"book": "Sleeper", "line": 20.5, "over_x": 1.2, "under_x": 3.0}], 20.5, 1.5, props.p_over)
        assert abs(q - 0.5) < 1e-9 and used == ["DraftKings"]
        q, used = books.consensus([even, {"book": "Pinnacle", "line": 20.5, "over": -150, "under": 120}], 20.5, 1.5, props.p_over)
        assert 0.53 < q < 0.56 and used == ["DraftKings", "Pinnacle"]
        assert books.consensus([{"book": "DraftKings", "line": 2.5, "over": -110, "under": -110}], 3.5, 1.3, props.p_over) == (None, [])
        assert books.consensus([], 3.5, 1.3, props.p_over) == (None, [])
        # a book at a higher line with even prices means Higher at Underdog's lower line is more likely than 50%
        up = books.at_line(0.5, 22.5, 21.5, 2.0, props.p_over)
        assert 0.52 < up < 0.62 and books.at_line(0.5, 21.5, 22.5, 2.0, props.p_over) < 0.48 and books.at_line(0.61, 9.5, 9.5, 2.0, props.p_over) == 0.61
        # how much of the books' gap we believe: all of it until 1,000 graded, then whatever scored best (0 = off)
        assert props.weight_books({}) == 1.0 and props.weight_books({"nb": 999, "llb": {"0.0": 1, "1.0": 2}}) == 1.0
        assert props.weight_books({"nb": 1000, "llb": {"0.0": 5.0, "0.5": 4.0, "1.0": 6.0}}) == 0.5
        assert props.weight_books({"nb": 1000, "llb": {"0.0": 3.0, "0.5": 4.0, "1.0": 6.0}}) == 0.0


class Kept(unittest.TestCase):
    """11/17: a paper parlay you placed at Onyx vanished from the Board once its games started, and a postponed game sat ungraded."""
    def test_paper_parlay_is_kept_once_a_game_starts(self):
        import datetime
        from board import grade, common
        now = common.now_ct(); t = lambda h: (now + datetime.timedelta(hours=h)).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        d = "2099-01-05"
        row = lambda i, conf, h: {"id": i, "date": d, "decision": "PAPER", "price": -110, "pick": f"T{i} +3.5", "conf": conf, "start": t(h), "result": None}
        saved = common.load("parlays.json", [])
        try:
            common.save("parlays.json", [])
            rows = [row("a", 7.2, 2), row("b", 6.7, 3), row("c", 6.5, 4)]
            out = grade.build_parlays([{"games": rows}], d, rows)
            assert [x["legs"] for x in out] == [["a", "b"]] and out[0]["decision"] == "CASH" and out[0]["stake"] == 15  # 11/20: every parlay is a $15 ticket
            late = [row("a", 7.2, -1), row("b", 6.7, -0.5), row("c", 6.5, 4)]          # both games have started
            out = grade.build_parlays([{"games": late}], d, late)
            assert [x["legs"] for x in out] == [["a", "b"]] and [x["legs"] for x in common.load("parlays.json", []) if x["date"] == d] == [["a", "b"]]
        finally:
            common.save("parlays.json", saved)

    def test_postponed_game_and_goalie_text(self):
        from board import espn
        ev = lambda name, done: {"id": "1", "date": "2099-01-05T22:00Z", "competitions": [{"status": {"type": {"name": name, "completed": done, "state": "post"}}, "competitors": [
            {"homeAway": "home", "score": "0", "team": {"displayName": "H", "abbreviation": "H", "id": "1"}}, {"homeAway": "away", "score": "0", "team": {"displayName": "A", "abbreviation": "A", "id": "2"}}]}]}
        assert espn.parse_event(ev("STATUS_POSTPONED", False), "CBB")["off"] and not espn.parse_event(ev("STATUS_FINAL", True), "CBB")["off"]
        import inspect
        from board import review
        assert "was {old or" in inspect.getsource(review.prelock)   # names the goalie who changed, not a raw list


class Review(unittest.TestCase):
    """Is confidence telling the truth, and which parts of the score line up with winning."""
    def test_confidence_check(self):
        from board import common, grade
        v = common.calib_verdict([{"band": "8.0+", "w": 24, "l": 34}, {"band": "7.0-7.9", "w": 57, "l": 55}, {"band": "5.5-6.9", "w": 25, "l": 20}])
        assert v["status"] == "bad" and "8.0+ (24-34, 41%) is winning less than 7.0-7.9" in v["text"]
        v = common.calib_verdict([{"band": "8.0+", "w": 0, "l": 0}, {"band": "7.0-7.9", "w": 9, "l": 9}, {"band": "5.5-6.9", "w": 84, "l": 64}])
        assert v["status"] == "early" and "7.0-7.9 has 18" in v["text"]                       # 18 results is not a verdict
        v = common.calib_verdict([{"band": "8.0+", "w": 40, "l": 20}, {"band": "7.0-7.9", "w": 33, "l": 27}])
        assert v["status"] == "ok"
        assert common.calib_verdict([{"band": "8.0+", "w": 15, "l": 15}])["status"] == "bad"   # 50% over 30 is not beating break-even
        mk = lambda res, eff, price=-110: {"result": res, "price": price, "conf": 6, "components": {"efficiency": eff, "veto": 1.5}}
        picks = [mk("Won", 2.0)] * 8 + [mk("Lost", 2.0)] * 4 + [mk("Won", 0.5)] * 5 + [mk("Lost", 0.5)] * 7 + [{"result": None, "components": {"efficiency": 2}}]
        rows = grade.parts(picks)
        assert len(rows) == 1 and rows[0]["part"] == "efficiency" and rows[0]["hi"] == [8, 4] and rows[0]["lo"] == [5, 7] and rows[0]["diff"] > 0.2   # veto: no low group -> left out
        assert abs(grade.flat(mk("Won", 1, 150)) - 1.5) < 1e-9 and grade.flat(mk("Lost", 1)) == -1.0
        t = {r["band"]: r for r in grade.tiers(picks[:-1])}
        assert t["5.5-6.9"]["w"] == 13 and abs(t["5.5-6.9"]["units"] - (13 * 100 / 110 - 11)) < 0.02

    def test_lean_parlays_and_moves(self):
        import datetime
        from board import props, common
        start = (common.now_ct() + datetime.timedelta(hours=3)).isoformat()
        mk = lambda i, call, ev, conf, p=0.56, mult="1.0": {"id": f"d|{i}|points", "date": "2099-01-02", "pick": f"P{i} Higher 10.5 Points", "player": f"P{i}", "sport": "NBA",
                                        "game": "A @ B", "event_id": ev, "stat": "points", "side": "higher", "line": 10.5, "p": p, "mkt": 0.5, "edge": 5,
                                        "conf": conf, "playable_to": 11.5, "start": start, "time": "x", "call": call, "mult": {"higher": mult, "lower": "1.0"}}
        saved = common.load("props_card.json", {})
        try:
            # no PLAY anywhere: no singles, but the parlay slots take leans from different games (your 11/16 rule)
            pr = [mk(1, "LEAN", "e1", 7.3, 0.53), mk(2, "LEAN", "e2", 6.8, 0.56), mk(3, "LEAN", "e3", 6.7, 0.62, "0.82"), mk(4, "LEAN", "e3", 5.5), mk(5, "PASS", "e5", 5.0)]
            pc = props.card(pr, "2099-01-02")
            assert pc["singles"] == [] and len(pc["parlays"]) == 1   # 4 leans, two share a game with the third -> only one clean pair after the first
            e = pc["parlays"][0]
            assert e["lean_only"] and [x["player"] for x in e["legs"]] == ["P1", "P2"] and e["pays"] == 3.0 and e["chance"] < e["need"] and "your parlay rule" in e["why"]
            assert all(x["event_id"] != e["legs"][0]["event_id"] for x in e["legs"][1:])
            # a favorite that pays less lowers the payout and raises the bar
            pc = props.card(pr + [mk(6, "LEAN", "e6", 6.9, 0.62, "0.82"), mk(7, "LEAN", "e7", 6.0, 0.6)], "2099-01-02")
            assert len(pc["parlays"]) == 2 and [x["player"] for x in pc["parlays"][1]["legs"]] == ["P6", "P3"] and pc["singles"] == []
            assert pc["parlays"][1]["pays"] == 2.02 and pc["parlays"][1]["need"] == round(1 / 2.02, 3)   # two 0.82x favorites: 3 x 0.82 x 0.82
        finally:
            common.save("props_card.json", saved)
        # 11/16: both lean parlays were pulled within an hour on a small wobble, then won. A thin number alone no longer pulls.
        saved = common.load("props_card.json", {})
        try:
            pr = [dict(mk(i, "LEAN", f"e{i}", c, 0.56), date="2099-01-03") for i, c in ((1, 6.8), (2, 6.4), (3, 6.2), (4, 6.0))]
            props.card(pr, "2099-01-03")
            thin = dict(pr[0], call="PASS", edge=2.0, p=0.62, mkt=0.60, reason="Our chance 62% vs Underdog's 60% - not enough.")      # still 2 points our way: keep
            gone = dict(pr[1], call="PASS", edge=0.6, p=0.52, mkt=0.51, reason="Our chance 52% vs Underdog's 51% - not enough.")      # advantage gone: pull
            moved = dict(pr[2], call="PASS", line=11.5, edge=-4, p=0.45, mkt=0.41, reason="Our chance 45% vs Underdog's 41% - not enough.")  # line moved our way, inside playable: keep
            out_ = dict(pr[3], call="PASS", conf=0, reason="Listed Out.")
            pc = props.card([thin, gone, moved, out_], "2099-01-03")
            st = {x["player"]: x for e in pc["parlays"] for x in e["legs"]}
            assert st["P1"]["status"] == "OPEN" and "Thinner now" in st["P1"]["thin"] and st["P2"]["status"] == "PULL"
            assert st["P3"]["status"] == "OPEN" and st["P3"]["line_now"] == 11.5 and st["P4"]["status"] == "PULL" and "Listed Out" in st["P4"]["pull_why"]
        finally:
            common.save("props_card.json", saved)
        row = dict(mk(1, "LEAN", "e1", 6), mkt_higher=0.5, books=[{"book": "DraftKings", "line": 11.5, "p": 0.5}, {"book": "Pinnacle", "line": 10.5, "p": 0.47}])
        first = {"Underdog": [10.5, 0.5], "DraftKings": [10.5, 0.5], "Pinnacle": [10.5, 0.52]}
        mv = props.moves(row, first)
        assert ("DraftKings moved the line from 10.5 to 11.5", True) in mv and any("Pinnacle price moved away from our side" in t and not good for t, good in mv) and len(mv) == 2
        assert props.moves(row, props.snapshot(row)) == [] and props._mult({"side": "higher", "mult": {"higher": "0.82"}}) == 0.82 and props._mult({"mult": 0.9}) == 0.9


if __name__ == "__main__":
    unittest.main()


class Learning(unittest.TestCase):
    def _picks(self, kind_pick, w, l, conf=6.2, sport="CBB"):
        return [{"sport": sport, "pick": kind_pick, "price": -110, "conf": conf, "result": "Won" if i < w else "Lost"} for i in range(w + l)]

    def test_streak_needs_sample(self):
        from board import learn
        b = learn.buckets(self._picks("Team +22.5", 9, 1))["CBB dog 20+"]
        self.assertEqual(b["status"], "learning")  # 9-1 is not proof

    def test_proven_winner_and_loser(self):
        from board import learn
        self.assertEqual(learn.buckets(self._picks("Team +22.5", 23, 9))["CBB dog 20+"]["status"], "proven winner")
        self.assertEqual(learn.buckets(self._picks("Team -4", 12, 22))["CBB fav"]["status"], "proven loser")

    def test_apply_learned_single(self):
        from board import learn
        mem = {"buckets": learn.buckets(self._picks("Team +22.5", 23, 9))}
        rows = [{"id": str(i), "pick": f"T{i} +21.5", "sport": "CBB", "decision": "PAPER", "conf": 6.0, "models_agree": True, "reason": ""} for i in range(4)]
        learn.apply([{"games": rows}], mem, "2026-11-20", [])
        got = [r for r in rows if r.get("learned")]
        self.assertEqual(len(got), learn.MAX_LEARNED)
        self.assertTrue(all(r["decision"] == "CASH" and r["stake"] == learn.LEARN_STAKE for r in got))

    def test_caution_cuts_stake(self):
        from board import learn
        mem = {"buckets": learn.buckets(self._picks("Team -4", 12, 22, conf=7.5))}
        r = {"id": "x", "pick": "Team -3", "sport": "CBB", "decision": "CASH", "conf": 7.5, "stake": 25, "reason": ""}
        learn.apply([{"games": [r]}], mem, "2026-11-20", [])
        self.assertEqual(r["stake"], learn.LEARN_STAKE)

    def test_prop_buckets(self):
        from board import learn
        rows = [{"s": "NBA", "t": "points", "mh": 0.5, "y": 1 if i % 10 < 6 else 0} for i in range(1000)]
        b = learn.prop_buckets(rows)
        self.assertEqual(b["NBA points higher"]["status"], "proven winner")
        self.assertEqual(b["NBA points lower"]["status"], "learning")


class LearnedLane(unittest.TestCase):
    def test_learned_never_blocks_a_main(self):
        """11/21: two learned $10 plays took slots and Northwestern -3 (7.1) got dropped by the 3-main cap."""
        from board import run
        rows = [{"id": "a", "decision": "CASH", "stake": 25, "conf": 7.0, "locked": True, "reason": ""},
                {"id": "b", "decision": "CASH", "stake": 10, "conf": 7.0, "locked": True, "learned": True, "reason": ""},
                {"id": "c", "decision": "CASH", "stake": 10, "conf": 6.6, "locked": True, "learned": True, "reason": ""},
                {"id": "d", "decision": "CASH", "stake": 25, "conf": 7.1, "reason": ""}]
        run.enforce_caps([{"games": rows}])
        self.assertEqual([r["decision"] for r in rows], ["CASH"] * 4)


class PropConfMemory(unittest.TestCase):
    def test_conf_band_bucket(self):
        from board import learn
        rows = [{"s": "NFL", "t": "rush", "mh": 0.5, "c": 7.4, "sd": "higher", "y": 1 if i % 10 < 6 else 0} for i in range(1000)]
        b = learn.prop_buckets(rows)
        self.assertEqual(b["NFL conf 7-7.9 leaned side"]["status"], "proven winner")
