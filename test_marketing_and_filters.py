import unittest

from bot.combo_builder import build_marketing_combos
from bot.filters import apply_tiered_score_filter
from bot.telegram_marketing import format_marketing_free, format_marketing_vip


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


if __name__ == "__main__":
    unittest.main()
