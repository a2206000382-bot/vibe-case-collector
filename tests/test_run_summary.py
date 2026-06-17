import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vibe_case_collector import Config, TokenBudget, build_run_summary, format_summary_sections


class RunSummaryTest(unittest.TestCase):
    def test_run_summary_contains_feedback_sections(self) -> None:
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = Config(
                keywords=["vibe coding indie hacker"],
                daily_budget_cny=0.1,
                llm_api_key="",
                llm_base_url="https://api.deepseek.com",
                llm_model="deepseek-chat",
                llm_input_price_cny_per_1m_tokens=1.0,
                llm_output_price_cny_per_1m_tokens=2.0,
                search_provider="duckduckgo",
                serper_api_key="",
                max_results_per_keyword=1,
                max_pages_per_keyword=1,
                max_source_chars=100,
                max_llm_output_tokens=100,
                request_timeout_seconds=5,
                output_dir=tmp_path,
                run_time="09:00",
                exchange_rates="USD:7.2",
                enable_enrichment=False,
                enrichment_results_per_case=1,
                enrichment_source_chars=100,
                min_completeness_score=0.82,
                rejected_output=True,
            )
            budget = TokenBudget(config, tmp_path, "2026-06-17")

            summary = build_run_summary([], [], budget)
            text = format_summary_sections(summary)

            self.assertIn("运行逻辑总结", text)
            self.assertIn("抓取结果总结", text)
            self.assertIn("下一步关键词优化建议", text)
            self.assertIn("vibe coding indie hacker AI SaaS", text)


if __name__ == "__main__":
    unittest.main()
