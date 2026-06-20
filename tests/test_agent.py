import unittest

from market_agent import MarketAnalysisAgent


class MarketAnalysisAgentTest(unittest.TestCase):
    def test_agent_returns_gold_and_stock_predictions(self) -> None:
        result = MarketAnalysisAgent().analyze("RELIANCE")

        self.assertEqual(result["gold_prediction"]["instrument"], "Gold")
        self.assertEqual(
            result["stock_prediction"]["instrument"],
            "Reliance Industries (RELIANCE)",
        )
        self.assertGreaterEqual(result["gold_prediction"]["confidence_score"], 50)
        self.assertIn(result["stock_prediction"]["signal"], {"Buy", "Hold", "Sell"})

    def test_unknown_stock_uses_generic_snapshot(self) -> None:
        result = MarketAnalysisAgent().analyze("ABC")

        self.assertEqual(result["stock_prediction"]["instrument"], "ABC (ABC)")
        self.assertEqual(result["stock_prediction"]["metadata"]["sector"], "Broad Market")


if __name__ == "__main__":
    unittest.main()
