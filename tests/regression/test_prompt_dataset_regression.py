import unittest

from market_agent.prompts.dataset import (
    default_dataset_path,
    enhance_prompt_from_dataset,
    search_prompt_dataset,
    summarize_prompt_dataset,
)


class PromptDatasetRegressionTest(unittest.TestCase):
    """Regression checks for the 100k Indian investment prompt corpus."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset_path = default_dataset_path()
        if cls.dataset_path is None:
            raise unittest.SkipTest(
                "Indian_Investment_Intelligence_100000_Prompts.jsonl was not found."
            )

    def test_jsonl_dataset_has_expected_size_and_schema_coverage(self) -> None:
        summary = summarize_prompt_dataset(self.dataset_path)

        self.assertEqual(summary["record_count"], 100000)
        self.assertGreaterEqual(len(summary["top_asset_classes"]), 12)
        self.assertGreaterEqual(len(summary["top_domains"]), 12)
        self.assertTrue(
            any(item["name"] == "intraday" for item in summary["top_time_horizons"])
        )
        self.assertTrue(
            search_prompt_dataset("gold inflation", self.dataset_path, asset_class="Gold", limit=1)
        )
        self.assertTrue(
            search_prompt_dataset("nse stock target", self.dataset_path, asset_class="NSE Stock", limit=1)
        )
        self.assertTrue(
            search_prompt_dataset("mutual fund allocation", self.dataset_path, asset_class="Mutual Fund", limit=1)
        )

    def test_jsonl_search_and_enhancement_are_relevant(self) -> None:
        gold_matches = search_prompt_dataset(
            "gold inflation USDINR buy sell",
            self.dataset_path,
            asset_class="Gold",
            limit=5,
        )
        stock_matches = search_prompt_dataset(
            "stock target price stop loss news sentiment",
            self.dataset_path,
            asset_class="Stocks",
            limit=5,
        )
        enhanced = enhance_prompt_from_dataset(
            "Should I buy gold this week based on inflation and USDINR?",
            self.dataset_path,
            limit=5,
        )

        self.assertTrue(gold_matches)
        self.assertTrue(all(match["asset_class"] == "Gold" for match in gold_matches))
        self.assertTrue(stock_matches)
        self.assertTrue(
            all("Stock" in match["asset_class"] for match in stock_matches)
        )
        self.assertIn("Gold Agent", enhanced["recommended_agents"])
        self.assertIn("USDINR", enhanced["required_indicators"])
        self.assertTrue(enhanced["matched_training_prompts"])


if __name__ == "__main__":
    unittest.main()
