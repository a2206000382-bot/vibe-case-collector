#!/usr/bin/env python3
"""Collect public Vibe Coding indie/small-team case clues and render reports.

The script is intentionally conservative: source-backed profile rules can create
formal/candidate cases, while generic search hits become today's clue pool or
skipped items. Missing facts are rendered as "未披露" instead of guessed.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import html
import json
import os
import re
import sys
import textwrap
import time
import urllib.parse
from pathlib import Path
from typing import Callable, Iterable, Optional

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover - exercised by users before install
    print("缺少依赖，请先运行：pip install -r requirements.txt", file=sys.stderr)
    raise SystemExit(2) from exc

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


UNKNOWN = "未披露"
MAX_ALLOWED_DAILY_BUDGET_RMB = 0.10

FIELD_LABELS = [
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
]

SECTION_TITLES = [
    "一、正式收录案例",
    "二、候选案例",
    "三、今日线索池",
    "四、跳过案例清单",
    "五、今日搜索总结",
    "六、下一步建议关键词",
]


def split_env_list(value: str) -> list[str]:
    """Split a human-editable env list separated by |, comma, or newlines."""
    if not value:
        return []
    parts = re.split(r"[|\n,]+", value)
    return [part.strip() for part in parts if part.strip()]


def str_to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def load_env_file(env_path: Path) -> None:
    """Load .env without forcing python-dotenv for simple deployments."""
    if load_dotenv is not None:
        load_dotenv(env_path)
        return
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclasses.dataclass
class Config:
    env_path: Path
    output_dir: Path
    prepared_scope: str
    run_at_hhmm: str
    search_provider: str
    keywords: list[str]
    seed_sources: list[tuple[str, str]]
    max_results_per_keyword: int
    fetch_result_pages: bool
    max_fetched_pages: int
    http_timeout_seconds: float
    request_delay_seconds: float
    use_llm_extraction: bool
    require_llm_extraction: bool
    api_key: str
    api_base_url: str
    llm_model: str
    daily_api_budget_rmb: float
    input_cost_rmb_per_1k: float
    output_cost_rmb_per_1k: float
    max_llm_source_chars: int
    usd_to_cny: float
    gbp_to_cny: float
    eur_to_cny: float

    @classmethod
    def from_env(cls, env_path: Path) -> "Config":
        load_env_file(env_path)
        keywords = split_env_list(os.getenv("SEARCH_KEYWORDS_ZH", "")) + split_env_list(
            os.getenv("SEARCH_KEYWORDS_EN", "")
        )
        if not keywords:
            raise ValueError(
                "未找到搜索关键词。请复制 .env.example 为 .env，并填写 SEARCH_KEYWORDS_ZH / SEARCH_KEYWORDS_EN。"
            )

        budget = float(os.getenv("DAILY_API_BUDGET_RMB", "0.10") or "0.10")
        budget = min(budget, MAX_ALLOWED_DAILY_BUDGET_RMB)
        output_dir = Path(os.getenv("OUTPUT_DIR", "reports")).expanduser()
        if not output_dir.is_absolute():
            output_dir = Path.cwd() / output_dir

        return cls(
            env_path=env_path,
            output_dir=output_dir,
            prepared_scope=os.getenv("PREPARED_SCOPE", UNKNOWN),
            run_at_hhmm=os.getenv("RUN_AT_HHMM", "09:00"),
            search_provider=os.getenv("SEARCH_PROVIDER", "duckduckgo").strip().lower(),
            keywords=keywords,
            seed_sources=parse_seed_sources(os.getenv("SEED_SOURCE_URLS", "")),
            max_results_per_keyword=int(os.getenv("MAX_RESULTS_PER_KEYWORD", "5") or "5"),
            fetch_result_pages=str_to_bool(os.getenv("FETCH_RESULT_PAGES", "true"), True),
            max_fetched_pages=int(os.getenv("MAX_FETCHED_PAGES", "18") or "18"),
            http_timeout_seconds=float(os.getenv("HTTP_TIMEOUT_SECONDS", "12") or "12"),
            request_delay_seconds=float(os.getenv("REQUEST_DELAY_SECONDS", "0.8") or "0.8"),
            use_llm_extraction=str_to_bool(os.getenv("USE_LLM_EXTRACTION", "false"), False),
            require_llm_extraction=str_to_bool(os.getenv("REQUIRE_LLM_EXTRACTION", "false"), False),
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            api_base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            llm_model=os.getenv("LLM_MODEL", "deepseek-chat").strip(),
            daily_api_budget_rmb=budget,
            input_cost_rmb_per_1k=float(os.getenv("LLM_INPUT_COST_RMB_PER_1K", "0.001") or "0.001"),
            output_cost_rmb_per_1k=float(os.getenv("LLM_OUTPUT_COST_RMB_PER_1K", "0.002") or "0.002"),
            max_llm_source_chars=int(os.getenv("MAX_LLM_SOURCE_CHARS", "5000") or "5000"),
            usd_to_cny=float(os.getenv("USD_TO_CNY", "7.20") or "7.20"),
            gbp_to_cny=float(os.getenv("GBP_TO_CNY", "9.20") or "9.20"),
            eur_to_cny=float(os.getenv("EUR_TO_CNY", "7.80") or "7.80"),
        )


def parse_seed_sources(value: str) -> list[tuple[str, str]]:
    """Parse optional public seed sources.

    Format:
    - title@@https://example.com/article
    - https://example.com/article
    """
    sources: list[tuple[str, str]] = []
    for item in split_env_list(value):
        if "@@" in item:
            title, url = item.split("@@", 1)
        else:
            title, url = "", item
        url = url.strip()
        if url.startswith(("http://", "https://")):
            sources.append((title.strip(), url))
    return sources


class BudgetController:
    """Track estimated API-token spending and enforce the 0.10 RMB hard cap."""

    def __init__(self, config: Config) -> None:
        self.limit_rmb = min(config.daily_api_budget_rmb, MAX_ALLOWED_DAILY_BUDGET_RMB)
        self.input_cost_rmb_per_1k = config.input_cost_rmb_per_1k
        self.output_cost_rmb_per_1k = config.output_cost_rmb_per_1k
        self.spent_rmb = 0.0
        self.api_calls = 0
        self.skipped_calls = 0

    @staticmethod
    def estimate_tokens(text: str) -> int:
        if not text:
            return 0
        # Conservative enough for budget gating without depending on tokenizer libs.
        ascii_chars = sum(1 for ch in text if ord(ch) < 128)
        non_ascii_chars = len(text) - ascii_chars
        return max(1, (ascii_chars // 4) + non_ascii_chars)

    def quote(self, input_text: str, expected_output_tokens: int = 800) -> float:
        input_tokens = self.estimate_tokens(input_text)
        return (input_tokens / 1000 * self.input_cost_rmb_per_1k) + (
            expected_output_tokens / 1000 * self.output_cost_rmb_per_1k
        )

    def can_spend(self, estimated_cost_rmb: float) -> bool:
        return self.spent_rmb + estimated_cost_rmb <= self.limit_rmb

    def record(self, actual_cost_rmb: float) -> None:
        self.spent_rmb += actual_cost_rmb
        self.api_calls += 1

    def record_skip(self) -> None:
        self.skipped_calls += 1

    def summary(self) -> str:
        return (
            f"API预算上限：{self.limit_rmb:.2f}元人民币；"
            f"估算已用：{self.spent_rmb:.4f}元；"
            f"已调用：{self.api_calls}次；因预算跳过：{self.skipped_calls}次。"
        )


@dataclasses.dataclass
class SearchHit:
    query: str
    title: str
    url: str
    snippet: str
    page_text: str = ""

    @property
    def combined_text(self) -> str:
        return " ".join([self.title, self.url, self.snippet, self.page_text]).strip()


@dataclasses.dataclass
class CaseRecord:
    case_id: int
    level: str
    product_name: str
    founder_and_coding_background: str
    product_type: str
    purpose: str
    audience: str
    pain_points: str
    revenue: str
    ai_tools: str
    tool_scene_analysis: str
    development_time: str
    sources: str
    credibility: str
    credibility_reason: str
    team_size: str
    risks: str
    opportunities: str
    missing_fields: str
    review_suggestion: str
    sort_key: int = 0

    def ensure_missing_fields(self) -> None:
        values = [
            self.case_id,
            self.level,
            self.product_name,
            self.founder_and_coding_background,
            self.product_type,
            self.purpose,
            self.audience,
            self.pain_points,
            self.revenue,
            self.ai_tools,
            self.tool_scene_analysis,
            self.development_time,
            self.sources,
            self.credibility,
            self.credibility_reason,
            self.team_size,
            self.risks,
            self.opportunities,
            self.missing_fields,
            self.review_suggestion,
        ]
        missing = []
        for label, value in zip(FIELD_LABELS, values):
            if label in {"案例编号", "缺失字段"}:
                continue
            if value is None or str(value).strip() == "" or UNKNOWN in str(value):
                missing.append(label)
        self.missing_fields = "无" if not missing else "、".join(missing)


@dataclasses.dataclass(frozen=True)
class KnownCaseProfile:
    name: str
    level: str
    match_terms: tuple[str, ...]
    min_match_count: int
    build_record: Callable[[list[SearchHit], Config], CaseRecord]


def numbered(items: Iterable[str]) -> str:
    symbols = "①②③④⑤⑥⑦⑧⑨"
    rendered = []
    for index, item in enumerate(items):
        prefix = symbols[index] if index < len(symbols) else f"{index + 1}."
        rendered.append(f"{prefix}{item}")
    return " ".join(rendered) if rendered else UNKNOWN


def four_category_text(values: dict[str, str]) -> str:
    categories = list(values.items())
    return "\n".join(f"{idx}.{label}：{value or UNKNOWN}" for idx, (label, value) in enumerate(categories, 1))


def cny_amount(amount: float) -> str:
    if amount >= 10000:
        return f"{amount / 10000:.2f}万元人民币"
    return f"{amount:.0f}元人民币"


def source_text(hits: list[SearchHit], extra_sources: Optional[list[tuple[str, str]]] = None) -> str:
    pairs: list[tuple[str, str]] = []
    if extra_sources:
        pairs.extend(extra_sources)
    for hit in hits:
        pairs.append((hit.title.strip() or "公开网页", hit.url.strip()))
    seen = set()
    rendered = []
    for title, url in pairs:
        if not url or url in seen:
            continue
        seen.add(url)
        rendered.append(f"{title}：{url}")
    return "\n".join(rendered) if rendered else UNKNOWN


def make_case(**kwargs: object) -> CaseRecord:
    defaults = {
        "case_id": 0,
        "level": UNKNOWN,
        "product_name": UNKNOWN,
        "founder_and_coding_background": UNKNOWN,
        "product_type": UNKNOWN,
        "purpose": UNKNOWN,
        "audience": UNKNOWN,
        "pain_points": UNKNOWN,
        "revenue": UNKNOWN,
        "ai_tools": UNKNOWN,
        "tool_scene_analysis": UNKNOWN,
        "development_time": UNKNOWN,
        "sources": UNKNOWN,
        "credibility": UNKNOWN,
        "credibility_reason": UNKNOWN,
        "team_size": UNKNOWN,
        "risks": four_category_text(
            {
                "合规风险": UNKNOWN,
                "平台依赖风险": UNKNOWN,
                "市场风险竞争": UNKNOWN,
                "长期运营风险": UNKNOWN,
            }
        ),
        "opportunities": four_category_text(
            {
                "横向延伸场景": UNKNOWN,
                "纵向功能衔接": UNKNOWN,
                "B端企业转型": UNKNOWN,
                "细分生态位卡位": UNKNOWN,
            }
        ),
        "missing_fields": UNKNOWN,
        "review_suggestion": UNKNOWN,
        "sort_key": 0,
    }
    defaults.update(kwargs)
    record = CaseRecord(**defaults)  # type: ignore[arg-type]
    record.ensure_missing_fields()
    return record


def build_creator_hunter(hits: list[SearchHit], config: Config) -> CaseRecord:
    usd17k = cny_amount(17000 * config.usd_to_cny)
    usd30k = cny_amount(30000 * config.usd_to_cny)
    return make_case(
        level="正式案例",
        product_name="Creator Hunter / CreatorHunter",
        founder_and_coding_background="Paulius Masalskas；编程背景：未披露（公开来源称使用 Bolt 和 Cursor 让 AI 处理 99.9% 编码）",
        product_type="SaaS订阅工具",
        purpose="从用户视角：帮助软件创业者查找和筛选适合推广应用/工具的内容创作者，减少手工找达人和验证名单的工作。",
        audience="独立开发者、AI/软件创业者、需要创作者营销的初创团队",
        pain_points=numbered(
            [
                "传统 influencer 数据库偏美妆电商，和软件/AI产品推广不匹配",
                "现有数据库价格高且创作者活跃度难确认",
                "独立创业者需要更快找到可触达、可转化的创作者名单",
            ]
        ),
        revenue=(
            "一次性买断/早鸟终身访问；存疑出现多个："
            f"收入线索 {usd17k}（$17,000美元，90天收入）；"
            f"收入线索 {usd30k}（$30,000美元，Starter Story/访谈口径）；未披露稳定MRR。"
        ),
        ai_tools="Perplexity、Bolt.new、Cursor、Framer、Make、Airtable、Supabase、Clerk",
        tool_scene_analysis="Perplexity用于调研和计划；Bolt.new用于生成可运行MVP；Cursor用于接入后端、认证和生产化修正，匹配从验证到上线的轻量SaaS流程。",
        development_time="存疑出现多个：公开来源称V1用1周构建、另1周打磨；另有来源称项目上线并营销约30天后获得牵引。",
        sources=source_text(hits),
        credibility="★★ 创始人自报",
        credibility_reason="来源包含创始人口述/访谈转写及案例复述；收入口径在不同来源中出现 $17K/90天 与 $30K 总收入差异，已标注存疑。",
        team_size="是（公开来源描述为 solo founder/自己构建和营销）",
        risks=four_category_text(
            {
                "合规风险": "创作者数据采集、联系方式使用和隐私合规需要复核",
                "平台依赖风险": "依赖 Bolt.new、Cursor、Supabase、Clerk 等第三方工具和价格策略",
                "市场风险竞争": "创作者数据库、达人营销平台竞争充分，数据质量容易被复制",
                "长期运营风险": "需要持续更新创作者活跃度和垂类标签，否则数据库快速过期",
            }
        ),
        opportunities=four_category_text(
            {
                "横向延伸场景": "可扩展到播客、Newsletter、TikTok、YouTube Shorts 等创作者渠道",
                "纵向功能衔接": "可加入外联邮件、投放追踪、成交归因和CRM",
                "B端企业转型": "可为SaaS公司提供定制创作者名单和营销代运营",
                "细分生态位卡位": "聚焦AI工具、开发者工具、学生工具等垂类创作者库",
            }
        ),
        review_suggestion="优先复核创始人原始访谈、产品官网当前定价、Stripe/公开收入截图，确认 $17K 与 $30K 是否为不同阶段口径。",
        sort_key=10,
    )


def build_trendfeed(hits: list[SearchHit], config: Config) -> CaseRecord:
    usd12k = cny_amount(12000 * config.usd_to_cny)
    gbp9222 = cny_amount(9222 * config.gbp_to_cny)
    gbp5500 = cny_amount(5500 * config.gbp_to_cny)
    return make_case(
        level="正式案例",
        product_name="TrendFeed / TrendFeed.app",
        founder_and_coding_background="Sebastian Volkis；编程背景：自学（公开转载来源称 self-taught developer，需复核一手资料）",
        product_type="SaaS订阅工具",
        purpose="从用户视角：聚合正在走红的新闻/趋势，并用AI辅助生成适合短视频平台发布的内容素材。",
        audience="短视频创作者、自媒体、内容营销人员、想做TikTok/Instagram内容变现的个人",
        pain_points=numbered(
            [
                "创作者每天找热门选题和可信新闻源耗时",
                "把新闻趋势改写成短视频脚本/内容素材需要重复劳动",
                "新手难以快速验证短视频选题是否有传播潜力",
            ]
        ),
        revenue=(
            "一次性买断/终身访问销售漏斗；"
            f"存疑出现多个：收入线索 {gbp9222}（£9,222英镑，前4周）；"
            f"约{usd12k}（$12,000美元，前4周）；首日 {gbp5500}（£5,500英镑）。未披露稳定MRR。"
        ),
        ai_tools="AI-generated code、Next.js、React、Supabase、Vercel；公开来源未完整披露具体Vibe编码器名称",
        tool_scene_analysis="AI编码用于压缩MVP开发周期；Supabase/Vercel降低上线门槛；场景适合快速验证内容工具和付费意愿。",
        development_time="4天构建MVP；公开来源称给自己1周上线窗口，前4周产生收入。",
        sources=source_text(hits),
        credibility="★★ 创始人自报",
        credibility_reason="Indie Hackers 等来源给出创始人、产品、开发周期和收入口径；部分二次转载补充技术栈，需以原文/创始人渠道复核。",
        team_size="否（2人小团队：Sebastian Volkis 负责构建，Matthew 负责营销/导流）",
        risks=four_category_text(
            {
                "合规风险": "新闻聚合、内容改写、短视频收益承诺和版权归属需要复核",
                "平台依赖风险": "依赖短视频平台流量规则、AI模型能力、Supabase/Vercel等基础设施",
                "市场风险竞争": "热点发现、AI脚本生成和短视频工具竞争密集",
                "长期运营风险": "需要持续维护趋势源质量、生成效果和付费转化漏斗",
            }
        ),
        opportunities=four_category_text(
            {
                "横向延伸场景": "可扩展到Newsletter、播客脚本、图文小红书/LinkedIn内容",
                "纵向功能衔接": "可衔接选题评分、脚本生成、排期发布、数据复盘",
                "B端企业转型": "可为MCN、品牌内容团队提供趋势监控和批量内容方案",
                "细分生态位卡位": "可深耕AI工具、财经、体育、教育等垂类趋势内容",
            }
        ),
        review_suggestion="复核 TrendFeed 官网、创始人社交账号、支付/收入截图，确认技术栈里具体使用的 Cursor/Claude/Bolt 等工具名称。",
        sort_key=20,
    )


def build_sensaro(hits: list[SearchHit], _config: Config) -> CaseRecord:
    return make_case(
        level="候选案例",
        product_name="sensaro.ai",
        founder_and_coding_background="未披露姓名；15年产品经理（PM）背景；编程背景：自学/有基础（曾为小企业建基础网站，需复核）",
        product_type="SaaS订阅工具",
        purpose="从用户视角：公开来源仅说明是作者从零构建的SaaS，具体功能需进入官网复核。",
        audience="未披露",
        pain_points=UNKNOWN,
        revenue="未披露",
        ai_tools="Cursor、AI Dev Tasks PRD/任务拆解流程",
        tool_scene_analysis="Cursor用于把PRD、任务清单和功能描述转为代码，适合PM把需求拆解能力转化为可运行SaaS。",
        development_time="一个多月（side project）",
        sources=source_text(hits),
        credibility="★★ 创始人自报",
        credibility_reason="Indie Hackers 帖子为作者自述，披露了背景、工具和开发周期，但未披露产品用途与收入。",
        team_size="是（公开帖子以第一人称描述个人构建）",
        risks=four_category_text(
            {
                "合规风险": UNKNOWN,
                "平台依赖风险": "依赖 Cursor 生成与维护核心代码",
                "市场风险竞争": UNKNOWN,
                "长期运营风险": "未披露收入和用户数据，需验证是否有持续运营牵引",
            }
        ),
        opportunities=four_category_text(
            {
                "横向延伸场景": UNKNOWN,
                "纵向功能衔接": UNKNOWN,
                "B端企业转型": UNKNOWN,
                "细分生态位卡位": UNKNOWN,
            }
        ),
        review_suggestion="打开 sensaro.ai 官网和作者主页，补齐产品用途、目标人群、定价页和创始人姓名后再考虑升级为正式案例。",
        sort_key=30,
    )


def build_fly_pieter(hits: list[SearchHit], config: Config) -> CaseRecord:
    usd87k = cny_amount(87000 * config.usd_to_cny)
    usd1m = cny_amount(1_000_000 * config.usd_to_cny)
    return make_case(
        level="候选案例",
        product_name="fly.pieter.com",
        founder_and_coding_background="Pieter Levels（@levelsio），独立开发者/连续创业者；编程背景：有/自学（公开来源称无游戏开发经验）",
        product_type="免费网页工具（浏览器游戏，和限定产品类型不完全匹配）",
        purpose="从用户视角：不用下载客户端，直接在浏览器里进入多人在线飞行模拟器并购买高级飞机/广告位。",
        audience="独立游戏玩家、技术社区、AI创业公司广告主",
        pain_points=numbered(
            [
                "传统飞行模拟器下载安装和更新成本高",
                "小团队难以用传统方式快速上线多人3D游戏",
                "AI创业公司需要面向技术人群的低摩擦广告位",
            ]
        ),
        revenue=f"SaaS外广告/一次性购买；收入线索 {usd87k}（$87,000美元MRR）/ {usd1m}（$1,000,000美元ARR），需以创始人原帖复核。",
        ai_tools="Cursor、Claude、Grok 3、Three.js",
        tool_scene_analysis="Cursor/Claude/Grok用于快速生成和迭代前端游戏代码；Three.js匹配浏览器3D场景，适合原型速度优先的Vibe Coding项目。",
        development_time="存疑出现多个：3小时原型；17天达到公开ARR里程碑。",
        sources=source_text(hits, [("产品官网", "https://fly.pieter.com/")]),
        credibility="★★★ 媒体报道",
        credibility_reason="产品官网可验证产品和工具标识，收入与开发周期主要来自媒体/社区文章和创始人社交线索；因产品是游戏而非AI工具，放入候选。",
        team_size="是（公开来源描述为Pieter Levels个人项目）",
        risks=four_category_text(
            {
                "合规风险": "游戏内广告、品牌露出、支付和用户生成行为需要合规审核",
                "平台依赖风险": "依赖浏览器、Three.js、AI编码工具和第三方支付",
                "市场风险竞争": "游戏热度可能快速衰减，广告主预算受流量波动影响",
                "长期运营风险": "多人在线稳定性、作弊治理和内容更新会持续消耗维护精力",
            }
        ),
        opportunities=four_category_text(
            {
                "横向延伸场景": "可扩展到其他浏览器轻量游戏和品牌互动广告",
                "纵向功能衔接": "可加入账号、任务、地图、赛事和创作者皮肤系统",
                "B端企业转型": "可为AI/开发者工具公司定制互动广告场景",
                "细分生态位卡位": "卡位技术社区里的轻量网页多人游戏广告库存",
            }
        ),
        review_suggestion="复核 @levelsio 原始X帖、Stripe/公开收入截图和官网当前广告位价格；因品类不完全符合AI工具，正式收录前需人工确认范围。",
        sort_key=40,
    )


def build_landpmjob(hits: list[SearchHit], config: Config) -> CaseRecord:
    usd1m = cny_amount(1_000_000 * config.usd_to_cny)
    return make_case(
        level="今日线索",
        product_name="landpmjob.com",
        founder_and_coding_background="Aakash Gupta；编程背景：未披露",
        product_type="网页工具/课程平台（不完全匹配限定产品类型）",
        purpose="从用户视角：为产品经理求职训练营承载课程内容、简历分析、面试准备和支付流程。",
        audience="产品经理求职者、职业转型人群",
        pain_points=numbered(
            [
                "求职训练营需要课程、支付和学员工具集中承载",
                "非工程团队需要快速上线可用平台",
                "简历和面试准备流程需要自动化支持",
            ]
        ),
        revenue=f"收入线索：{usd1m}以上/年（>$1M/year，业务收入口径，不等同软件MRR/ARR）",
        ai_tools="Bolt.new",
        tool_scene_analysis="Bolt.new用于浏览器内构建和托管全栈网站，适合非复杂工程团队快速维护课程业务平台。",
        development_time="未披露",
        sources=source_text(hits),
        credibility="★★ 创始人自报",
        credibility_reason="来源为作者/创始人教程中的自述案例；产品是课程业务平台，不是独立AI工具，因此只进入线索池。",
        team_size="未披露",
        risks=four_category_text(
            {
                "合规风险": "教育培训宣传、支付和个人求职数据处理需要复核",
                "平台依赖风险": "依赖 Bolt.new 托管与生成能力",
                "市场风险竞争": "PM求职培训竞争较强，平台本身难构成壁垒",
                "长期运营风险": "课程内容、学员服务和技术平台都需要持续维护",
            }
        ),
        opportunities=four_category_text(
            {
                "横向延伸场景": "可扩展到设计、运营、数据分析等求职训练营",
                "纵向功能衔接": "可加入AI简历打分、模拟面试、学员进度和就业追踪",
                "B端企业转型": "可为企业内训或招聘训练提供白标平台",
                "细分生态位卡位": "卡位PM职业训练营的AI辅助学习工具",
            }
        ),
        review_suggestion="若要正式收录，应确认平台是否是独立软件产品、收入是否来自软件订阅，以及是否由小团队长期运营。",
        sort_key=50,
    )


def build_lovable(hits: list[SearchHit], config: Config) -> CaseRecord:
    arr100m = cny_amount(100_000_000 * config.usd_to_cny)
    return make_case(
        level="今日线索",
        product_name="Lovable",
        founder_and_coding_background="Anton Osika、Fabian Hedin；编程背景：有（AI研究/工程背景）",
        product_type="SaaS订阅工具",
        purpose="从用户视角：用自然语言提示生成和迭代全栈应用，让非技术用户也能把想法变成可运行软件。",
        audience="非技术创业者、独立开发者、产品经理、企业团队",
        pain_points=numbered(
            [
                "不会写代码也想快速做出软件原型",
                "传统MVP开发需要工程团队和较高成本",
                "业务团队需要更快验证应用想法",
            ]
        ),
        revenue=f"SaaS月订阅/团队计划；收入线索 {arr100m}（$100M美元ARR，8个月口径，非个人项目）",
        ai_tools="GPT Engineer、Lovable平台内置模型能力",
        tool_scene_analysis="Lovable本身是AI软件构建平台，是Vibe Coding生态上游工具，不是用Vibe Coding构建的小型AI工具案例。",
        development_time="未披露",
        sources=source_text(hits),
        credibility="★★★ 媒体报道",
        credibility_reason="多家媒体/行业文章报道增长数据；因公司已非个人/小团队阶段，只进入线索池用于生态跟踪。",
        team_size="否（公司化团队）",
        risks=four_category_text(
            {
                "合规风险": "用户生成应用的版权、安全和数据合规责任边界需要明确",
                "平台依赖风险": "高度依赖底层模型成本、稳定性和供应商策略",
                "市场风险竞争": "与Bolt.new、Replit、Cursor、Claude Code等竞争",
                "长期运营风险": "从原型工具升级到生产级平台需要安全、权限、部署和维护能力",
            }
        ),
        opportunities=four_category_text(
            {
                "横向延伸场景": "覆盖内部工具、电商、教育、社区、营销页等应用",
                "纵向功能衔接": "可衔接数据库、支付、部署、监控、团队协作",
                "B端企业转型": "为企业业务部门提供低代码/AI开发治理平台",
                "细分生态位卡位": "卡位非技术创业者的prompt-to-app入口",
            }
        ),
        review_suggestion="仅作为生态平台线索；不要和个人/小团队Vibe Coding落地项目混入正式案例。",
        sort_key=60,
    )


def build_bolt(hits: list[SearchHit], config: Config) -> CaseRecord:
    arr40m = cny_amount(40_000_000 * config.usd_to_cny)
    return make_case(
        level="今日线索",
        product_name="Bolt.new",
        founder_and_coding_background="Eric Simons、Albert Pai；编程背景：有（StackBlitz/WebContainers工程背景）",
        product_type="SaaS订阅工具",
        purpose="从用户视角：在浏览器中用提示词生成、运行、编辑并部署全栈Web应用，无需本地开发环境。",
        audience="产品经理、设计师、创始人、开发者、营销人员",
        pain_points=numbered(
            [
                "非技术人员本地配置开发环境门槛高",
                "原型到可演示应用的周期长",
                "AI代码助手如果不能控制运行环境，调试闭环慢",
            ]
        ),
        revenue=f"SaaS月订阅/AI credits；收入线索 {arr40m}（$40M美元ARR，约5个月口径，非个人项目）",
        ai_tools="Bolt.new、Anthropic/大模型、WebContainers",
        tool_scene_analysis="Bolt.new本身是AI开发平台，可作为寻找下游个人项目的关键词入口。",
        development_time="未披露",
        sources=source_text(hits, [("GitHub README", "https://github.com/stackblitz/bolt.new")]),
        credibility="★★★★ 官方公告",
        credibility_reason="GitHub README/官网可验证产品能力；收入数据来自第三方研究/报道，作为线索而非正式小团队案例。",
        team_size="否（公司化团队）",
        risks=four_category_text(
            {
                "合规风险": "用户生成代码、依赖安装和部署安全边界需要治理",
                "平台依赖风险": "依赖底层模型、浏览器WebContainers和云部署伙伴",
                "市场风险竞争": "AI应用生成器竞争激烈且价格战风险高",
                "长期运营风险": "推理成本、滥用防控和生产级可靠性会影响毛利",
            }
        ),
        opportunities=four_category_text(
            {
                "横向延伸场景": "覆盖企业内部工具、营销站点、教育项目和SaaS原型",
                "纵向功能衔接": "可衔接数据库、认证、支付、日志和一键部署",
                "B端企业转型": "成为企业产品/设计团队原型和轻应用平台",
                "细分生态位卡位": "卡位浏览器内prompt-to-deploy开发体验",
            }
        ),
        review_suggestion="用作发现下游创业项目的搜索入口；正式收录时应寻找使用Bolt.new构建的具体个人产品。",
        sort_key=70,
    )


KNOWN_PROFILES = [
    KnownCaseProfile(
        name="Creator Hunter",
        level="正式案例",
        match_terms=("creator hunter", "creatorhunter", "paulius", "masalskas"),
        min_match_count=1,
        build_record=build_creator_hunter,
    ),
    KnownCaseProfile(
        name="TrendFeed",
        level="正式案例",
        match_terms=("trendfeed", "trendfeed.app", "sebastian volkis"),
        min_match_count=1,
        build_record=build_trendfeed,
    ),
    KnownCaseProfile(
        name="sensaro.ai",
        level="候选案例",
        match_terms=("sensaro.ai", "sensaro"),
        min_match_count=1,
        build_record=build_sensaro,
    ),
    KnownCaseProfile(
        name="fly.pieter.com",
        level="候选案例",
        match_terms=("fly.pieter.com", "levelsio", "pieter levels"),
        min_match_count=1,
        build_record=build_fly_pieter,
    ),
    KnownCaseProfile(
        name="landpmjob.com",
        level="今日线索",
        match_terms=("landpmjob.com", "landpmjob"),
        min_match_count=1,
        build_record=build_landpmjob,
    ),
    KnownCaseProfile(
        name="Lovable",
        level="今日线索",
        match_terms=("lovable", "gpt-engineer", "anton osika"),
        min_match_count=1,
        build_record=build_lovable,
    ),
    KnownCaseProfile(
        name="Bolt.new",
        level="今日线索",
        match_terms=("bolt.new", "stackblitz/bolt.new", "eric simons"),
        min_match_count=1,
        build_record=build_bolt,
    ),
]


class SearchClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
                )
            }
        )

    def search(self, query: str) -> list[SearchHit]:
        if self.config.search_provider != "duckduckgo":
            raise ValueError("当前脚本仅内置 duckduckgo 搜索；可在代码中扩展其他公开搜索源。")
        params = {"q": query, "kl": "wt-wt"}
        response = self.session.get(
            "https://duckduckgo.com/html/",
            params=params,
            timeout=self.config.http_timeout_seconds,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        hits: list[SearchHit] = []
        results = soup.select(".result")
        if not results:
            results = soup.select("div")
        for result in results:
            link = result.select_one("a.result__a") or result.find("a", href=True)
            if not link:
                continue
            title = " ".join(link.get_text(" ", strip=True).split())
            url = normalize_duckduckgo_url(link.get("href", ""))
            snippet_node = result.select_one(".result__snippet")
            snippet = " ".join(snippet_node.get_text(" ", strip=True).split()) if snippet_node else ""
            if not title or not url.startswith(("http://", "https://")):
                continue
            hits.append(SearchHit(query=query, title=title, url=url, snippet=snippet))
            if len(hits) >= self.config.max_results_per_keyword:
                break
        return hits

    def fetch_page_text(self, url: str) -> str:
        response = self.session.get(url, timeout=self.config.http_timeout_seconds)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return ""
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = " ".join(soup.get_text(" ", strip=True).split())
        return text[:20000]


def normalize_duckduckgo_url(raw_url: str) -> str:
    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url
    parsed = urllib.parse.urlparse(raw_url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        params = urllib.parse.parse_qs(parsed.query)
        uddg = params.get("uddg", [""])[0]
        if uddg:
            return urllib.parse.unquote(uddg)
    return raw_url


def gather_hits(config: Config) -> tuple[list[SearchHit], list[str]]:
    client = SearchClient(config)
    all_hits: list[SearchHit] = []
    errors: list[str] = []
    seen_urls: set[str] = set()
    fetched_count = 0

    for query in config.keywords:
        try:
            hits = client.search(query)
        except Exception as exc:  # noqa: BLE001 - report and continue other queries
            errors.append(f"搜索失败：{query} -> {exc}")
            continue
        for hit in hits:
            if hit.url in seen_urls:
                continue
            seen_urls.add(hit.url)
            all_hits.append(hit)
        time.sleep(config.request_delay_seconds)

    for title, url in config.seed_sources:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        all_hits.append(
            SearchHit(
                query="SEED_SOURCE_URLS",
                title=title or "公开种子来源",
                url=url,
                snippet="来自 .env 配置的公开可访问来源，用于搜索引擎返回为空或结果不稳定时兜底复核。",
            )
        )

    if config.fetch_result_pages:
        for hit in all_hits:
            if fetched_count >= config.max_fetched_pages:
                break
            if should_skip_fetch(hit.url):
                continue
            try:
                hit.page_text = client.fetch_page_text(hit.url)
                if hit.title == "公开种子来源" and hit.page_text:
                    hit.title = hit.page_text[:80]
                fetched_count += 1
                time.sleep(config.request_delay_seconds)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"页面读取失败：{hit.url} -> {exc}")

    return all_hits, errors


def should_skip_fetch(url: str) -> bool:
    blocked_domains = ("linkedin.com", "youtube.com", "x.com", "twitter.com")
    parsed = urllib.parse.urlparse(url)
    return any(domain in parsed.netloc for domain in blocked_domains)


def profile_match_count(profile: KnownCaseProfile, hit: SearchHit) -> int:
    primary_text = " ".join([hit.title, hit.url, hit.snippet]).lower()
    primary_count = sum(1 for term in profile.match_terms if term.lower() in primary_text)
    if primary_count:
        return primary_count

    # Page bodies can mention many platforms incidentally. Only use them for
    # ordinary search results when at least two profile markers appear.
    if hit.query != "SEED_SOURCE_URLS" and hit.page_text:
        page_text = hit.page_text.lower()
        page_count = sum(1 for term in profile.match_terms if term.lower() in page_text)
        if page_count >= 2:
            return page_count
    return 0


def extract_known_cases(hits: list[SearchHit], config: Config) -> tuple[list[CaseRecord], set[str]]:
    cases: list[CaseRecord] = []
    consumed_urls: set[str] = set()

    for profile in KNOWN_PROFILES:
        matched = [hit for hit in hits if profile_match_count(profile, hit) >= profile.min_match_count]
        if not matched:
            continue
        record = profile.build_record(matched, config)
        cases.append(record)
        consumed_urls.update(hit.url for hit in matched)

    cases.sort(key=lambda item: item.sort_key)
    return cases, consumed_urls


def is_scope_related(hit: SearchHit) -> bool:
    text = hit.combined_text.lower()
    include_terms = (
        "vibe coding",
        "cursor",
        "claude code",
        "bolt.new",
        "lovable",
        "replit agent",
        "ai coding",
        "indie hacker",
        "solo founder",
        "saas",
        "mrr",
        "arr",
    )
    return any(term in text for term in include_terms)


def is_concept_only(hit: SearchHit) -> bool:
    text = f"{hit.title} {hit.snippet}".lower()
    concept_terms = (
        "roadmap",
        "guide",
        "tutorial",
        "what is",
        "everything you need to know",
        "how to build",
        "complete guide",
        "playbook",
    )
    product_markers = ("built", "launched", "mrr", "arr", "$", "revenue", ".ai", ".com", "founder")
    return any(term in text for term in concept_terms) and not any(marker in text for marker in product_markers)


def extract_product_name_from_hit(hit: SearchHit) -> str:
    text = f"{hit.title} {hit.snippet}"
    domain_matches = re.findall(r"\b[a-z0-9][a-z0-9-]{1,40}\.(?:ai|app|com|io|dev)\b", text, flags=re.I)
    if domain_matches:
        return domain_matches[0]
    titled = re.split(r"\s[-|–—]\s", hit.title)[0].strip()
    titled = re.sub(r"^(how|why|what|the complete guide to)\s+", "", titled, flags=re.I).strip()
    return titled[:80] if titled else UNKNOWN


def generic_clue_from_hit(hit: SearchHit) -> CaseRecord:
    product_name = extract_product_name_from_hit(hit)
    purpose = hit.snippet or "与 Vibe Coding / AI Coding / 独立开发 / AI SaaS 相关，需人工打开链接复核具体产品用途。"
    if len(purpose) > 220:
        purpose = purpose[:217] + "..."
    return make_case(
        level="今日线索",
        product_name=product_name,
        founder_and_coding_background=UNKNOWN,
        product_type=UNKNOWN,
        purpose=f"从用户视角：{purpose}",
        audience=UNKNOWN,
        pain_points=UNKNOWN,
        revenue=UNKNOWN,
        ai_tools=UNKNOWN,
        tool_scene_analysis="命中关键词但信息不足，暂不做工具-场景结论。",
        development_time=UNKNOWN,
        sources=source_text([hit]),
        credibility="★ 匿名推测",
        credibility_reason="仅由搜索结果或单个网页线索触发，未完成创始人/官方/媒体交叉复核。",
        team_size=UNKNOWN,
        review_suggestion="人工打开来源链接，确认产品名称、创始人、是否使用AI编码工具、收入和上线时间；不满足条件则移入跳过清单。",
        sort_key=900,
    )


def build_generic_clues_and_skips(
    hits: list[SearchHit], consumed_urls: set[str], allow_fallback: bool = True
) -> tuple[list[CaseRecord], list[tuple[str, str, str]]]:
    clues: list[CaseRecord] = []
    skipped: list[tuple[str, str, str]] = []
    seen_names: set[str] = set()
    for hit in hits:
        if hit.url in consumed_urls:
            continue
        if not is_scope_related(hit):
            skipped.append((hit.title, hit.url, "与 Vibe Coding / AI Coding / 独立开发 / AI SaaS 范围不够相关"))
            continue
        if is_concept_only(hit):
            skipped.append((hit.title, hit.url, "方法论/概念文章，未确认具体产品案例"))
            continue
        clue = generic_clue_from_hit(hit)
        name_key = clue.product_name.lower()
        if name_key in seen_names:
            skipped.append((hit.title, hit.url, "重复线索，已合并或已出现同名产品"))
            continue
        seen_names.add(name_key)
        clues.append(clue)
        if len(clues) >= 8:
            break

    if not clues and allow_fallback:
        clues.append(
            make_case(
                level="今日线索",
                product_name="今日搜索无足够结构化新增线索",
                founder_and_coding_background=UNKNOWN,
                product_type=UNKNOWN,
                purpose="从用户视角：本条用于提示今天需要人工扩大关键词，未作为正式案例。",
                audience=UNKNOWN,
                pain_points=UNKNOWN,
                revenue=UNKNOWN,
                ai_tools=UNKNOWN,
                tool_scene_analysis="搜索结果不足或被搜索引擎限制，未产生可结构化线索。",
                development_time=UNKNOWN,
                sources=UNKNOWN,
                credibility="★ 匿名推测",
                credibility_reason="系统兜底占位，避免线索池为空；不能作为案例使用。",
                team_size=UNKNOWN,
                review_suggestion="更换网络环境或补充英文关键词，例如 built with Cursor MRR、vibe coded SaaS revenue。",
                sort_key=999,
            )
        )
    return clues, skipped


def maybe_llm_extract_extra_clues(
    hits: list[SearchHit],
    config: Config,
    budget: BudgetController,
    consumed_urls: set[str],
) -> list[CaseRecord]:
    """Optional OpenAI-compatible extraction with hard budget gating.

    The deterministic rules above are the default. This optional pass is for
    users who explicitly enable USE_LLM_EXTRACTION=true in .env.
    """
    if not config.use_llm_extraction or not config.api_key:
        return []

    extra_cases: list[CaseRecord] = []
    candidates = [hit for hit in hits if hit.url not in consumed_urls and is_scope_related(hit)][:3]
    for hit in candidates:
        source_text_for_llm = hit.combined_text[: config.max_llm_source_chars]
        prompt = textwrap.dedent(
            f"""
            你是严格的数据抽取助手。只根据下面公开来源文本抽取 Vibe Coding/AI Coding 创业线索。
            不知道的字段必须填“未披露”，禁止猜测。
            请只输出 JSON，字段：product_name, purpose, ai_tools, founder, revenue, development_time, reason。

            来源URL：{hit.url}
            来源标题：{hit.title}
            来源文本：
            {source_text_for_llm}
            """
        ).strip()
        estimated_cost = budget.quote(prompt, expected_output_tokens=600)
        if not budget.can_spend(estimated_cost):
            budget.record_skip()
            break
        try:
            data = call_openai_compatible(config, prompt)
            budget.record(estimated_cost)
            extra_cases.append(case_from_llm_json(data, hit))
        except Exception:  # noqa: BLE001 - optional extraction must not break report
            budget.record_skip()
    return extra_cases


def maybe_llm_review_cases(
    cases: list[CaseRecord],
    config: Config,
    budget: BudgetController,
) -> str:
    """Run a mandatory/optional API-assisted organization pass before output."""
    if not config.use_llm_extraction:
        return "API辅助整理：未启用（USE_LLM_EXTRACTION=false）。"
    if not config.api_key:
        message = "API辅助整理失败：已启用 USE_LLM_EXTRACTION，但 .env 缺少 OPENAI_API_KEY。"
        if config.require_llm_extraction:
            raise ValueError(message)
        return message

    compact_cases = []
    for case in cases:
        compact_cases.append(
            {
                "编号": case.case_id,
                "级别": case.level,
                "产品": case.product_name,
                "用途": case.purpose[:180],
                "收入": case.revenue[:160],
                "来源": extract_urls(case.sources)[:3],
                "缺失字段": case.missing_fields,
            }
        )

    prompt = textwrap.dedent(
        f"""
        你是 Vibe Coding 案例报告整理复核助手。只基于下面已抽取的结构化内容做整理检查，
        不要新增未经来源支持的事实。请输出 JSON 对象，字段固定为：
        {{
          "status": "ok/needs_review",
          "summary": "一句话说明本轮整理结论",
          "quality_warnings": ["最多3条风险或缺口"],
          "next_keywords": ["最多5个下一轮建议关键词"],
          "agent_instruction_suggestion": "一句话建议如何优化后续Agent Instructions"
        }}

        已抽取案例：
        {json.dumps(compact_cases, ensure_ascii=False)}
        """
    ).strip()
    estimated_cost = budget.quote(prompt, expected_output_tokens=700)
    if not budget.can_spend(estimated_cost):
        message = f"API辅助整理失败：预计费用会超过 {budget.limit_rmb:.2f} 元人民币预算上限。"
        budget.record_skip()
        if config.require_llm_extraction:
            raise ValueError(message)
        return message

    try:
        data = call_openai_compatible(config, prompt)
        budget.record(estimated_cost)
    except Exception as exc:  # noqa: BLE001
        budget.record_skip()
        message = f"API辅助整理失败：{exc}"
        if config.require_llm_extraction:
            raise RuntimeError(message) from exc
        return message

    warnings = data.get("quality_warnings", "")
    next_keywords_value = data.get("next_keywords", "")
    if isinstance(warnings, list):
        warning_text = "；".join(str(item) for item in warnings[:3])
    else:
        warning_text = str(warnings)
    if isinstance(next_keywords_value, list):
        keyword_text = "；".join(str(item) for item in next_keywords_value[:5])
    else:
        keyword_text = str(next_keywords_value)
    return (
        f"API辅助整理：已调用 {config.llm_model} 完成输出前复核。"
        f"结论：{data.get('summary', UNKNOWN)}"
        f" 风险提示：{warning_text or UNKNOWN}"
        f" 下一轮关键词：{keyword_text or UNKNOWN}"
        f" Agent Instructions建议：{data.get('agent_instruction_suggestion', UNKNOWN)}"
    )


def call_openai_compatible(config: Config, prompt: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": config.llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 700,
    }
    if config.llm_model.startswith("kimi-"):
        # Kimi K2.x models require provider-specific temperature values. Disable thinking so the
        # response stays concise JSON for this small report-review task.
        payload["temperature"] = 0.6
        payload["thinking"] = {"type": "disabled"}
    else:
        payload["temperature"] = 0

    response = requests.post(
        f"{config.api_base_url}/chat/completions",
        headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=config.http_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.I | re.M).strip()
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("LLM返回不是JSON对象")
    return {str(key): value for key, value in parsed.items()}


def as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "；".join(str(item) for item in value)
    return str(value)


def case_from_llm_json(data: dict[str, object], hit: SearchHit) -> CaseRecord:
    return make_case(
        level="今日线索",
        product_name=as_text(data.get("product_name")) or extract_product_name_from_hit(hit),
        founder_and_coding_background=f"{as_text(data.get('founder')) or UNKNOWN}；编程背景：{UNKNOWN}",
        product_type=UNKNOWN,
        purpose=f"从用户视角：{as_text(data.get('purpose')) or UNKNOWN}",
        audience=UNKNOWN,
        pain_points=UNKNOWN,
        revenue=as_text(data.get("revenue")) or UNKNOWN,
        ai_tools=as_text(data.get("ai_tools")) or UNKNOWN,
        tool_scene_analysis=as_text(data.get("reason")) or "LLM基于单一来源抽取，需人工复核。",
        development_time=as_text(data.get("development_time")) or UNKNOWN,
        sources=source_text([hit]),
        credibility="★ 匿名推测",
        credibility_reason="由可选LLM在预算内基于单一来源抽取，未交叉复核。",
        team_size=UNKNOWN,
        review_suggestion="人工复核来源原文后，再决定是否升级为候选或正式案例。",
        sort_key=850,
    )


def assign_case_ids(cases: list[CaseRecord]) -> None:
    for index, record in enumerate(cases, 1):
        record.case_id = index
        record.ensure_missing_fields()


def format_case(record: CaseRecord) -> str:
    values = [
        str(record.case_id),
        record.level,
        record.product_name,
        record.founder_and_coding_background,
        record.product_type,
        record.purpose,
        record.audience,
        record.pain_points,
        record.revenue,
        record.ai_tools,
        record.tool_scene_analysis,
        record.development_time,
        record.sources,
        record.credibility,
        record.credibility_reason,
        record.team_size,
        record.risks,
        record.opportunities,
        record.missing_fields,
        record.review_suggestion,
    ]
    lines = [f"{label}：{value}" for label, value in zip(FIELD_LABELS, values)]
    return "\n".join(lines)


def render_section(title: str, records: list[CaseRecord], empty_text: str) -> str:
    parts = [title]
    if not records:
        parts.append(empty_text)
    else:
        for record in records:
            parts.append(f"\n### 案例 {record.case_id}：{record.product_name}\n{format_case(record)}")
    return "\n".join(parts)


def render_skips(skipped: list[tuple[str, str, str]]) -> str:
    if not skipped:
        return "四、跳过案例清单\n今日没有额外跳过项。"
    lines = ["四、跳过案例清单"]
    for index, (title, url, reason) in enumerate(skipped, 1):
        lines.append(f"{index}. {title}\n   链接：{url or UNKNOWN}\n   跳过原因：{reason}")
    return "\n".join(lines)


def next_keywords() -> str:
    suggestions = [
        "site:indiehackers.com \"built with Cursor\" \"MRR\"",
        "\"vibe coded\" \"MRR\" \"solo founder\"",
        "\"Bolt.new\" \"built\" \"revenue\" \"founder\"",
        "\"Lovable\" \"built\" \"launched\" \"revenue\"",
        "\"Claude Code\" \"SaaS\" \"indie hacker\"",
        "\"Cursor\" \"AI tool\" \"paid users\"",
    ]
    return "\n".join(f"{index}. {keyword}" for index, keyword in enumerate(suggestions, 1))


def render_report(
    report_date: dt.date,
    all_cases: list[CaseRecord],
    skipped: list[tuple[str, str, str]],
    errors: list[str],
    config: Config,
    budget: BudgetController,
    hit_count: int,
    api_assist_note: str,
) -> str:
    formal = [case for case in all_cases if case.level == "正式案例"]
    candidates = [case for case in all_cases if case.level == "候选案例"]
    clues = [case for case in all_cases if case.level == "今日线索"]
    summary_lines = [
        "五、今日搜索总结",
        f"报告日期：{report_date.isoformat()}",
        f"聚焦范围：{config.prepared_scope}",
        f"关键词数量：{len(config.keywords)}；去重搜索结果：{hit_count}条。",
        f"正式案例：{len(formal)}；候选案例：{len(candidates)}；今日线索：{len(clues)}；跳过：{len(skipped)}。",
        f"预算执行：{budget.summary()}",
        api_assist_note,
        "运行逻辑总结：先用 .env 关键词执行公开网页检索，再用来源触发的保守规则生成正式/候选案例；缺少产品名、用途、来源链接或范围不匹配的内容进入线索池或跳过清单。",
        "结果总结：正式案例不为凑数而扩展范围；收入、开发周期、团队规模等冲突数据保留“存疑出现多个”并列口径。",
        "Agent Instructions 优化建议：后续可要求“正式案例必须同时有产品官网/创始人自述/第三方报道中至少两类来源”，并补充优先国家、产品类型黑名单、最低收入口径要求。",
    ]
    if errors:
        summary_lines.append("运行警告：")
        summary_lines.extend(f"- {error}" for error in errors[:20])

    return "\n\n".join(
        [
            f"# Vibe Coding 独立创业案例每日采集报告（{report_date.isoformat()}）",
            render_section(
                "一、正式收录案例",
                formal,
                "今日正式收录案例为 0：未发现同时满足产品名称、产品用途、来源链接、可信度完整且范围匹配的新增案例。",
            ),
            render_section("二、候选案例", candidates, "今日候选案例为 0。"),
            render_section("三、今日线索池", clues, "今日线索池为 0。"),
            render_skips(skipped),
            "\n".join(summary_lines),
            "六、下一步建议关键词\n" + next_keywords(),
        ]
    )


def save_reports(report_text: str, output_dir: Path, report_date: dt.date) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"vibe_cases_{report_date.isoformat()}"
    txt_path = output_dir / f"{stem}.txt"
    doc_path = output_dir / f"{stem}.doc"
    txt_path.write_text(report_text, encoding="utf-8")
    doc_html = "\n".join(
        [
            "<html><head><meta charset='utf-8'>",
            "<style>body{font-family:Microsoft YaHei,Arial,sans-serif;line-height:1.55;white-space:pre-wrap;} h1{font-size:22px;} h2{font-size:18px;}</style>",
            "</head><body>",
            html.escape(report_text),
            "</body></html>",
        ]
    )
    doc_path.write_text(doc_html, encoding="utf-8")
    return txt_path, doc_path


def run_collection(config: Config, report_date: dt.date) -> tuple[Path, Path, str]:
    budget = BudgetController(config)
    hits, errors = gather_hits(config)
    known_cases, consumed_urls = extract_known_cases(hits, config)
    llm_cases = maybe_llm_extract_extra_clues(hits, config, budget, consumed_urls)
    consumed_urls.update(url for case in llm_cases for url in extract_urls(case.sources))
    existing_clues = any(case.level == "今日线索" for case in known_cases + llm_cases)
    generic_clues, skipped = build_generic_clues_and_skips(
        hits, consumed_urls, allow_fallback=not existing_clues
    )

    all_cases = known_cases + llm_cases + generic_clues
    all_cases.sort(key=lambda item: ({"正式案例": 0, "候选案例": 1, "今日线索": 2}.get(item.level, 9), item.sort_key))
    assign_case_ids(all_cases)
    api_assist_note = maybe_llm_review_cases(all_cases, config, budget)

    report_text = render_report(report_date, all_cases, skipped, errors, config, budget, len(hits), api_assist_note)
    txt_path, doc_path = save_reports(report_text, config.output_dir, report_date)
    return txt_path, doc_path, report_text


def extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s)）]+", text or "")


def seconds_until_next_run(run_at_hhmm: str, now: Optional[dt.datetime] = None) -> float:
    now = now or dt.datetime.now()
    try:
        hour_text, minute_text = run_at_hhmm.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise ValueError("RUN_AT_HHMM 格式应为 HH:MM，例如 09:00") from exc
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return (target - now).total_seconds()


def watch_loop(config: Config) -> None:
    print(f"常驻定时已启动。每天 {config.run_at_hhmm} 运行；按 Ctrl+C 停止。")
    while True:
        sleep_seconds = seconds_until_next_run(config.run_at_hhmm)
        print(f"距离下次运行约 {sleep_seconds / 3600:.2f} 小时。")
        time.sleep(sleep_seconds)
        today = dt.date.today()
        try:
            txt_path, doc_path, _ = run_collection(config, today)
            print(f"完成：{txt_path}；{doc_path}")
        except Exception as exc:  # noqa: BLE001
            print(f"运行失败：{exc}", file=sys.stderr)
        time.sleep(60)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vibe Coding 独立创业案例每日采集器")
    parser.add_argument("--env", default=".env", help="配置文件路径，默认 .env")
    parser.add_argument("--date", default="", help="报告日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--watch", action="store_true", help="常驻定时模式：每天按 RUN_AT_HHMM 自动运行")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    env_path = Path(args.env).expanduser()
    if not env_path.is_absolute():
        env_path = Path.cwd() / env_path
    config = Config.from_env(env_path)

    if args.watch:
        watch_loop(config)
        return 0

    report_date = dt.date.today()
    if args.date:
        report_date = dt.date.fromisoformat(args.date)
    txt_path, doc_path, report_text = run_collection(config, report_date)
    print(f"TXT 已生成：{txt_path}")
    print(f"DOC 已生成：{doc_path}")
    print("\n--- 今日搜索总结预览 ---")
    summary_match = re.search(r"五、今日搜索总结(.+?)六、下一步建议关键词", report_text, flags=re.S)
    print(("五、今日搜索总结" + summary_match.group(1)).strip() if summary_match else "报告已生成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
