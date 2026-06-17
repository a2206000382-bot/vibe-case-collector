import unittest

from vibe_case_collector import (
    FIELD_SPECS,
    BudgetLedger,
    is_case_publishable,
    normalize_case,
    render_case,
)


class TemplateTests(unittest.TestCase):
    def test_prompt_field_list_contains_all_user_listed_fields(self):
        self.assertEqual(len(FIELD_SPECS), 17)
        self.assertEqual(FIELD_SPECS[0][0], "案例编号")
        self.assertEqual(FIELD_SPECS[-1][0], "机会点")

    def test_case_normalization_fills_required_risk_and_opportunity_categories(self):
        normalized = normalize_case(
            {
                "产品名称": "Example AI Tool",
                "数据来源+链接": "产品官网：https://example.com",
                "编程背景": "自学开发",
                "产品类型": "SaaS订阅工具",
                "收入模式": "SaaS月订阅",
                "解决痛点": ["节省整理资料时间", "降低写作门槛", "减少重复操作"],
                "风险点": {"合规风险": "用户数据处理需合规"},
                "机会点": {"横向延伸场景": "扩展到自媒体工作流"},
            },
            1,
        )

        self.assertEqual(normalized["案例编号"], "1")
        self.assertEqual(normalized["编程背景"], "自学")
        self.assertIn("①节省整理资料时间", normalized["解决痛点"])
        self.assertIn("合规风险：用户数据处理需合规", normalized["风险点"])
        self.assertIn("平台依赖风险：未披露", normalized["风险点"])
        self.assertIn("横向延伸场景：扩展到自媒体工作流", normalized["机会点"])
        self.assertIn("细分生态位卡位：未披露", normalized["机会点"])

    def test_render_case_keeps_fixed_numbered_template(self):
        normalized = normalize_case({"产品名称": "Example", "数据来源+链接": "https://example.com"}, 1)
        rendered = render_case(normalized)
        self.assertIn("1. 案例编号：1", rendered)
        self.assertIn("17. 机会点（四类各1条，缺一不可）：", rendered)

    def test_publishable_case_requires_disclosed_product_name(self):
        self.assertFalse(
            is_case_publishable({"产品名称": "未披露（恋爱测评应用）", "数据来源+链接": "https://example.com"})
        )
        self.assertTrue(is_case_publishable({"产品名称": "sensaro.ai", "数据来源+链接": "https://example.com"}))


class BudgetTests(unittest.TestCase):
    def test_budget_reservation_stops_before_exceeding_cap(self):
        ledger = BudgetLedger(
            max_cny=0.0001,
            input_price_cny_per_1m=1000,
            output_price_cny_per_1m=1000,
        )

        reservation = ledger.reserve("很长的提示词" * 10, 1000)

        self.assertIsNone(reservation)
        self.assertTrue(ledger.stopped_by_budget)
        self.assertEqual(ledger.used_cny, 0)


if __name__ == "__main__":
    unittest.main()
