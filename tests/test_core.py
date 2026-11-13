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


if __name__ == "__main__":
    unittest.main()
