import json
import os
import unittest
from pathlib import Path

from market_agent.cli import (
    _analyze_top_stocks,
    _category_prompt_response,
    _format_category_prompt_text,
    _format_text,
    _prompt_training_context,
)
from market_agent.data.realtime_sources import RealtimeIndiaMarketDataSource
from market_agent.interfaces.query_parser import parse_market_query
from market_agent.prompts.dataset import default_dataset_path
from market_agent.reports.html_report import save_html_report
from market_agent.services.agent import MarketAnalysisAgent


RUN_LIVE_USER_TESTS = os.environ.get("RUN_USER_TESTS") == "1"


@unittest.skipUnless(
    RUN_LIVE_USER_TESTS,
    "Set RUN_USER_TESTS=1 to run realtime UserTest scenarios.",
)
class UserTest(unittest.TestCase):
    """User-facing realtime validation using the 100+ trusted feed repository file."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset_path = default_dataset_path()
        if cls.dataset_path is None:
            raise unittest.SkipTest(
                "Indian_Investment_Intelligence_100000_Prompts.jsonl was not found."
            )
        cls.source = RealtimeIndiaMarketDataSource(timeout_seconds=8)
        cls.agent = MarketAnalysisAgent(data_source=cls.source)
        cls.output_dir = Path("outputs/user_tests")
        cls.output_dir.mkdir(parents=True, exist_ok=True)

    def test_user_realtime_source_master_has_100_plus_feeds(self) -> None:
        resource_path = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "market_agent"
            / "resources"
            / "trusted_financial_sources.json"
        )
        sources = json.loads(resource_path.read_text(encoding="utf-8"))
        ranked_gold = self.source._ranked_trusted_master_sources("Gold")
        ranked_stock = self.source._ranked_trusted_master_sources("TCS")

        self.assertGreaterEqual(len(sources), 100)
        self.assertGreaterEqual(len(ranked_gold), 100)
        self.assertGreaterEqual(len(ranked_stock), 100)
        self.assertTrue(any(item.get("source_name") == "RBI" for item in sources))
        self.assertTrue(any(item.get("source_name") == "SEBI" for item in sources))

    def test_user_gold_stock_report_uses_realtime_feeds_and_prompt_dataset(self) -> None:
        query = parse_market_query(
            "Should I buy gold this week based on inflation and USDINR?"
        )
        prompt_training = _prompt_training_context(
            query,
            _Args(prompt_dataset=str(self.dataset_path), prompt_limit=5),
        )
        result = self.agent.analyze("TCS")
        result["user_query"] = {
            "text": query.raw_text,
            "instrument_type": "gold",
            "data_source": "realtime",
            "prompt_training": prompt_training,
        }
        report_path = save_html_report(result, "gold")
        text = _format_text(result, query)

        self.assertIn(str(self.dataset_path), text)
        self.assertIn("Prompt Training Context", text)
        self.assertGreaterEqual(
            result["gold_prediction"]["metadata"]["institutional_report"]["source_count"],
            10,
        )
        self.assertGreaterEqual(len(result["research_source_links_by_instrument"]["gold"]), 5)
        self.assertTrue(report_path.exists())

    def test_user_top_stocks_and_category_outputs(self) -> None:
        top_query = parse_market_query("suggest me top 3 stocks to buy on 22 June 2026")
        top_result = _analyze_top_stocks(self.agent, top_query, "realtime")
        top_result["user_query"]["prompt_training"] = _prompt_training_context(
            top_query,
            _Args(prompt_dataset=str(self.dataset_path), prompt_limit=5),
        )
        top_report_path = save_html_report(top_result, "top_stocks")

        mf_query = parse_market_query(
            "Suggest best mutual funds for SIP for a medium-risk investor with 5-year horizon."
        )
        mf_result = _category_prompt_response(mf_query)
        mf_result["user_query"]["prompt_training"] = _prompt_training_context(
            mf_query,
            _Args(prompt_dataset=str(self.dataset_path), prompt_limit=5),
        )
        mf_report_path = save_html_report(mf_result, mf_query.perspective)
        mf_text = _format_category_prompt_text(mf_result)

        self.assertEqual(len(top_result["top_buy_stocks"]), 3)
        self.assertTrue(top_report_path.exists())
        self.assertIn("Prompt Training Context", mf_text)
        self.assertIn("Suggested SIP Allocation", mf_text)
        self.assertTrue(mf_report_path.exists())


class _Args:
    def __init__(self, prompt_dataset: str, prompt_limit: int) -> None:
        self.no_prompt_training = False
        self.use_prompt_training = True
        self.prompt_dataset = prompt_dataset
        self.prompt_limit = prompt_limit
        self.scan_limit = None


if __name__ == "__main__":
    unittest.main()
