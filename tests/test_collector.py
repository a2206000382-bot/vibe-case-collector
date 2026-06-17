import datetime as dt
from pathlib import Path

from vibe_case_collector import (
    BudgetController,
    Config,
    SearchHit,
    assign_case_ids,
    build_creator_hunter,
    extract_known_cases,
    render_report,
)


def make_config(tmp_path: Path) -> Config:
    return Config(
        env_path=tmp_path / ".env",
        output_dir=tmp_path / "reports",
        prepared_scope="测试范围",
        run_at_hhmm="09:00",
        search_provider="duckduckgo",
        keywords=["built with Cursor startup"],
        seed_sources=[],
        max_results_per_keyword=5,
        fetch_result_pages=False,
        max_fetched_pages=0,
        http_timeout_seconds=1,
        request_delay_seconds=0,
        use_llm_extraction=False,
        require_llm_extraction=False,
        api_key="",
        api_base_url="https://api.example.com",
        llm_model="test-model",
        daily_api_budget_rmb=0.10,
        input_cost_rmb_per_1k=0.001,
        output_cost_rmb_per_1k=0.002,
        max_llm_source_chars=1000,
        usd_to_cny=7.20,
        gbp_to_cny=9.20,
        eur_to_cny=7.80,
    )


def test_budget_controller_caps_daily_budget(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.daily_api_budget_rmb = 5.0
    budget = BudgetController(config)
    assert budget.limit_rmb == 0.10
    expensive = budget.quote("字" * 200000, expected_output_tokens=200000)
    assert not budget.can_spend(expensive)


def test_known_profile_creator_hunter_extraction(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    hits = [
        SearchHit(
            query="Creator Hunter Cursor",
            title="How Paulius Built Creator Hunter to $17K in 90 Days Using Cursor and Bolt",
            url="https://example.com/creator-hunter",
            snippet="Paulius Masalskas built Creator Hunter using Bolt and Cursor.",
        )
    ]
    cases, consumed = extract_known_cases(hits, config)
    names = {case.product_name for case in cases}
    assert any("Creator Hunter" in name for name in names)
    assert "https://example.com/creator-hunter" in consumed


def test_report_keeps_twenty_numbered_fields(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    budget = BudgetController(config)
    case = build_creator_hunter(
        [
            SearchHit(
                query="Creator Hunter Cursor",
                title="Creator Hunter source",
                url="https://example.com/creator-hunter",
                snippet="Creator Hunter using Cursor and Bolt.",
            )
        ],
        config,
    )
    assign_case_ids([case])
    report = render_report(
        dt.date(2026, 6, 17),
        [case],
        [],
        [],
        config,
        budget,
        hit_count=1,
        api_assist_note="API辅助整理：测试未启用。",
    )
    for index, label in enumerate(
        [
            "案例编号",
            "收录级别",
            "产品名称",
            "创始人+编程背景",
            "产品类型",
            "产品用途",
            "目标人群",
            "解决痛点",
            "收入模式+MRR/ARR",
            "AI工具",
            "工具-场景匹配分析",
            "开发时间",
            "来源+链接",
            "数据可信度",
            "可信度理由",
            "是否单人/小团队",
            "风险点",
            "机会点",
            "缺失字段",
            "复核建议",
        ],
        1,
    ):
        assert f"{label}：" in report, f"field {index} missing"
    assert "一、正式收录案例" in report
    assert "六、下一步建议关键词" in report
