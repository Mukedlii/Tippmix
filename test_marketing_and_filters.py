import unittest

from bot.combo_builder import build_marketing_combos
from bot.filters import apply_tiered_score_filter
from bot.providers.league_filter import is_allowed_league
from bot.telegram_marketing import format_marketing_free, format_marketing_vip
from bot.openai_logic import _cap_per_league


class MarketingAndFiltersTests(unittest.TestCase):
    def test_tiered_score_filter_thresholds(self):
        matches = [
            {"league_tier": 1, "match_score": 5.0},
            {"league_tier": 2, "match_score": 5.9},
            {"league_tier": 2, "match_score": 6.0},
            {"league_tier": 3, "match_score": 7.0},
        ]
        filtered = apply_tiered_score_filter(matches)
        self.assertEqual(len(filtered), 3)

    def test_combo_targets_for_vip_and_free(self):
        vip = [
            {"fixture_id": i, "home_team": f"H{i}", "selection": "Hazai győzelem", "odds_pick": 1.6 + (i * 0.05), "confidence": 4.2}
            for i in range(1, 7)
        ]
        free = [
            {"fixture_id": 100 + i, "home_team": f"F{i}", "selection": "Hazai győzelem", "odds_pick": 1.7 + (i * 0.03), "confidence": 3.8}
            for i in range(1, 4)
        ]
        combos = build_marketing_combos(vip, free)
        self.assertGreaterEqual(len(combos["vip"]), 2)
        self.assertGreaterEqual(len(combos["free"]), 1)

    def test_clean_marketing_format_contains_required_sections(self):
        tips = [
            {
                "home_team": "Arsenal",
                "away_team": "Liverpool",
                "selection": "Hazai győzelem",
                "odds_pick": 2.1,
                "bookmaker": "Bet365",
                "confidence": 4.3,
                "home_form": ["W", "W", "W"],
                "away_form": ["W", "L", "W"],
            }
        ]
        combos = [{"label": "Arsenal H + Real Over", "total_odds": 6.5, "picks": tips}]
        vip_text, _ = format_marketing_vip(tips, combos, "2026.06.26.")
        free_text, _ = format_marketing_free(tips, combos, "2026.06.26.")

        self.assertIn("⚽ VIP TIPPEK", vip_text)
        self.assertIn("💎 KOMBINÁCIÓK", vip_text)
        self.assertIn("Pick: Hazai győzelem | 2.10 (Bet365)", vip_text)
        self.assertIn("⚽ FREE TIPPEK", free_text)
        self.assertIn("🔗 KETTŐS", free_text)

    # ── Új tesztek: Zs kategória szűrés ─────────────────────────────────────

    def test_zs_kategoria_is_blocked(self):
        """Zs kategóriás (Hungarian amateur/regional) leagues must be rejected."""
        blocked_cases = [
            ("Zs kategória A csoport", "Hungary"),
            ("zs-kategória B", "Hungary"),
            ("Zs osztály", "Hungary"),
            ("Amatőr bajnokság Budapest", "Hungary"),
            ("Területi bajnokság Pest megye", "Hungary"),
            ("Városi bajnokság Győr", "Hungary"),
        ]
        for league, country in blocked_cases:
            with self.subTest(league=league):
                self.assertFalse(
                    is_allowed_league(league, country),
                    f"'{league}' should be blocked as a low-tier amateur league",
                )

    def test_top_leagues_still_allowed(self):
        """Top leagues must not be accidentally blocked."""
        allowed_cases = [
            ("Premier League", "England"),
            ("Bundesliga", "Germany"),
            ("La Liga", "Spain"),
            ("Serie A", "Italy"),
            ("Champions League", "Europe"),
            ("OTP Bank Liga", "Hungary"),
        ]
        for league, country in allowed_cases:
            with self.subTest(league=league):
                self.assertTrue(
                    is_allowed_league(league, country),
                    f"'{league}' should be allowed as a reputable league",
                )

    # ── Új teszt: per-liga korlát ─────────────────────────────────────────────

    def test_cap_per_league_limits_concentration(self):
        """_cap_per_league should drop tips exceeding the per-league limit."""
        id_to_match = {
            1: {"league": "Premier League"},
            2: {"league": "Premier League"},
            3: {"league": "Premier League"},
            4: {"league": "Bundesliga"},
            5: {"league": "Bundesliga"},
        }
        tips = [
            {"fixture_id": 1, "selection": "Hazai győzelem"},
            {"fixture_id": 2, "selection": "Hazai győzelem"},
            {"fixture_id": 3, "selection": "Döntetlen"},   # 3rd Premier League - should be dropped
            {"fixture_id": 4, "selection": "Hazai győzelem"},
            {"fixture_id": 5, "selection": "Vendég győzelem"},
        ]
        capped = _cap_per_league(tips, id_to_match, max_per_league=2)
        self.assertEqual(len(capped), 4)
        pl_tips = [t for t in capped if id_to_match[t["fixture_id"]]["league"] == "Premier League"]
        self.assertEqual(len(pl_tips), 2)

    def test_cap_per_league_zero_disables_cap(self):
        """max_per_league=0 should disable the cap and return all tips unchanged."""
        id_to_match = {i: {"league": "Premier League"} for i in range(1, 6)}
        tips = [{"fixture_id": i, "selection": "Hazai győzelem"} for i in range(1, 6)]
        capped = _cap_per_league(tips, id_to_match, max_per_league=0)
        self.assertEqual(len(capped), 5)


if __name__ == "__main__":
    unittest.main()
