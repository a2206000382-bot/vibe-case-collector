#!/usr/bin/env python3
"""Daily public-source Vibe Coding case collector.

The script intentionally uses only Python's standard library so beginners can
run it after installing Python, without learning package managers first.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


CN_UNDISCLOSED = "未披露"
LEVEL_FORMAL = "正式案例"
LEVEL_CANDIDATE = "候选案例"
LEVEL_LEAD = "今日线索"


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source_keyword: str


@dataclass
class CaseItem:
    case_id: int
    level: str
    product_name: str
    founder_and_programming_background: str
    product_type: str
    product_usage: str
    target_users: str
    pain_points: str
    revenue: str
    ai_tools: str
    tool_scene_match: str
    development_time: str
    source: str
    credibility: str
    credibility_reason: str
    solo_or_team: str
    risks: str
    opportunities: str
    missing_fields: str
    review_suggestion: str


@dataclass
class SkippedItem:
    title: str
    url: str
    reason: str


@dataclass
class CollectorConfig:
    llm_api_key: str
    llm_api_base: str
    llm_model: str
    enable_llm_enrichment: bool
    max_daily_api_cost_cny: float
    cny_per_1k_input_tokens: float
    cny_per_1k_output_tokens: float
    max_llm_output_tokens: int
    search_keywords: List[str]
    seed_urls: List[str]
    max_search_results_per_keyword: int
    max_total_items: int
    http_timeout_seconds: int
    run_at: str
    output_dir: Path
    usd_cny_rate: float
    eur_cny_rate: float
    gbp_cny_rate: float


@dataclass
class CollectionStats:
    keyword_count: int = 0
    raw_result_count: int = 0
    accepted_count: int = 0
    skipped_count: int = 0
    search_errors: List[str] = field(default_factory=list)
    llm_calls: int = 0
    llm_skipped_by_budget: int = 0
    api_cost_cny: float = 0.0


class BudgetGuard:
    """Tracks estimated paid-token spend and blocks calls above the daily cap."""

    def __init__(self, config: CollectorConfig, usage_path: Path) -> None:
        self.config = config
        self.usage_path = usage_path
        self.spent_cny = 0.0
        self.calls = 0
        if usage_path.exists():
            try:
                data = json.loads(usage_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            self.spent_cny = float(data.get("spent_cny", 0.0))
            self.calls = int(data.get("calls", 0))

    @staticmethod
    def estimate_tokens(text: str) -> int:
        # A conservative mixed Chinese/English approximation.
        return max(1, int(len(text) / 3) + 1)

    def estimate_cost(self, input_text: str, output_tokens: Optional[int] = None) -> float:
        out_tokens = output_tokens or self.config.max_llm_output_tokens
        input_tokens = self.estimate_tokens(input_text)
        return (
            input_tokens / 1000 * self.config.cny_per_1k_input_tokens
            + out_tokens / 1000 * self.config.cny_per_1k_output_tokens
        )

    def can_spend(self, estimated_cost: float) -> bool:
        return self.spent_cny + estimated_cost <= self.config.max_daily_api_cost_cny

    def record(self, estimated_cost: float) -> None:
        self.spent_cny += estimated_cost
        self.calls += 1
        self.usage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "spent_cny": round(self.spent_cny, 6),
            "calls": self.calls,
            "max_daily_api_cost_cny": self.config.max_daily_api_cost_cny,
            "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
        self.usage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_env_file(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        env[key] = value
    return env


def get_env(name: str, env_file: Dict[str, str], default: str = "") -> str:
    return os.environ.get(name, env_file.get(name, default)).strip()


def to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on", "开启"}


def split_list(value: str) -> List[str]:
    if not value:
        return []
    parts = re.split(r"\|\||\n", value)
    return [part.strip() for part in parts if part.strip()]


def safe_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_config(env_path: Path) -> CollectorConfig:
    env_file = load_env_file(env_path)
    return CollectorConfig(
        llm_api_key=get_env("LLM_API_KEY", env_file),
        llm_api_base=get_env("LLM_API_BASE", env_file, "https://api.deepseek.com/v1"),
        llm_model=get_env("LLM_MODEL", env_file, "deepseek-chat"),
        enable_llm_enrichment=to_bool(get_env("ENABLE_LLM_ENRICHMENT", env_file, "false")),
        max_daily_api_cost_cny=safe_float(get_env("MAX_DAILY_API_COST_CNY", env_file, "0.10"), 0.10),
        cny_per_1k_input_tokens=safe_float(get_env("CNY_PER_1K_INPUT_TOKENS", env_file, "0.002"), 0.002),
        cny_per_1k_output_tokens=safe_float(get_env("CNY_PER_1K_OUTPUT_TOKENS", env_file, "0.008"), 0.008),
        max_llm_output_tokens=safe_int(get_env("MAX_LLM_OUTPUT_TOKENS", env_file, "600"), 600),
        search_keywords=split_list(get_env("SEARCH_KEYWORDS", env_file)),
        seed_urls=split_list(get_env("SEED_URLS", env_file)),
        max_search_results_per_keyword=max(1, safe_int(get_env("MAX_SEARCH_RESULTS_PER_KEYWORD", env_file, "4"), 4)),
        max_total_items=max(1, safe_int(get_env("MAX_TOTAL_ITEMS", env_file, "30"), 30)),
        http_timeout_seconds=max(3, safe_int(get_env("HTTP_TIMEOUT_SECONDS", env_file, "12"), 12)),
        run_at=get_env("RUN_AT", env_file, "08:00"),
        output_dir=Path(get_env("OUTPUT_DIR", env_file, "reports")),
        usd_cny_rate=safe_float(get_env("USD_CNY_RATE", env_file, "7.20"), 7.20),
        eur_cny_rate=safe_float(get_env("EUR_CNY_RATE", env_file, "7.80"), 7.80),
        gbp_cny_rate=safe_float(get_env("GBP_CNY_RATE", env_file, "9.10"), 9.10),
    )


def clean_text(value: str) -> str:
    unescaped = html.unescape(value)
    without_tags = re.sub(r"<[^>]+>", " ", unescaped)
    collapsed = re.sub(r"\s+", " ", without_tags)
    return collapsed.strip()


def domain_from_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return ""
    return parsed.netloc.lower().removeprefix("www.")


def fetch_url(url: str, timeout_seconds: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def decode_duckduckgo_url(raw_url: str) -> str:
    url = html.unescape(raw_url)
    if url.startswith("//"):
        url = "https:" + url
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return query["uddg"][0]
    return url


def search_duckduckgo(keyword: str, config: CollectorConfig) -> List[SearchResult]:
    query = urllib.parse.urlencode({"q": keyword})
    search_url = f"https://html.duckduckgo.com/html/?{query}"
    page = fetch_url(search_url, config.http_timeout_seconds)
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>'
        r".*?(?:<a[^>]+class=\"result__snippet\"[^>]*>|<div[^>]+class=\"result__snippet\"[^>]*>)"
        r"(?P<snippet>.*?)</(?:a|div)>",
        re.IGNORECASE | re.DOTALL,
    )
    results: List[SearchResult] = []
    for match in pattern.finditer(page):
        title = clean_text(match.group("title"))
        url = decode_duckduckgo_url(match.group("url"))
        snippet = clean_text(match.group("snippet"))
        if title and url:
            results.append(SearchResult(title=title, url=url, snippet=snippet, source_keyword=keyword))
        if len(results) >= config.max_search_results_per_keyword:
            break
    if results:
        return results

    # Fallback parser for slightly different DuckDuckGo HTML variants.
    blocks = re.findall(r'<div class="result results_links.*?</div>\s*</div>', page, flags=re.DOTALL)
    for block in blocks:
        title_match = re.search(r'class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
        snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</', block, re.DOTALL)
        if not title_match:
            continue
        title = clean_text(title_match.group(2))
        url = decode_duckduckgo_url(title_match.group(1))
        snippet = clean_text(snippet_match.group(1)) if snippet_match else ""
        results.append(SearchResult(title=title, url=url, snippet=snippet, source_keyword=keyword))
        if len(results) >= config.max_search_results_per_keyword:
            break
    return results


def build_seed_results(config: CollectorConfig) -> List[SearchResult]:
    results: List[SearchResult] = []
    for url in config.seed_urls:
        domain = domain_from_url(url) or url
        title = domain.split("/")[0]
        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet="用户配置的固定公开线索来源，需人工复核是否包含 Vibe Coding / AI Coding / 独立开发 / AI SaaS 案例。",
                source_keyword="SEED_URLS",
            )
        )
    return results


def is_relevant(result: SearchResult) -> bool:
    text = f"{result.title} {result.snippet} {result.url}".lower()
    signals = [
        "vibe coding",
        "cursor",
        "claude code",
        "lovable",
        "bolt.new",
        "replit agent",
        "ai coding",
        "indie hacker",
        "solo founder",
        "ai saas",
        "无代码",
        "独立开发",
        "独立创业",
        "个人开发者",
        "ai工具",
        "创业案例",
        "变现",
    ]
    return any(signal in text for signal in signals)


def is_ad_or_tracking_link(result: SearchResult) -> bool:
    url = result.url.lower()
    domain = domain_from_url(result.url)
    ad_signals = [
        "duckduckgo.com/y.js",
        "bing.com/aclick",
        "ad_domain=",
        "ad_provider=",
        "utm_medium=cpc",
        "utm_campaign=bing",
    ]
    return domain in {"duckduckgo.com", "bing.com"} or any(signal in url for signal in ad_signals)


def is_generic_article(result: SearchResult) -> bool:
    text = f"{result.title} {result.snippet}".lower()
    generic_signals = [
        "what is",
        "什么是",
        "top 5",
        "top 10",
        "best ",
        "工具推荐",
        "横向对比",
        "横评",
        "comparison",
        "vs.",
        "教程",
        "guide",
        "指南",
        "学习规划",
        "实战经验",
        "实战教程",
        "实战全记录",
        "实战演示",
        "普通人",
        "入场券",
        "理念",
        "概念",
        "趋势",
        "how to",
        "如何",
        "一站式搞定",
        "不会写代码",
        "自然语言编程",
        "从零代码",
        "超级个体",
        "接单平台",
        "副业赚钱",
        "完整方案",
        "深度实测",
        "ai编程入门",
        "工具清单",
        "工具盘点",
        "快速搭建",
        "月入过万",
        "micro saas",
        "打工人",
        "启动你的",
        "增长总监",
        "测评",
        "估值",
        "打法",
    ]
    product_case_signals = [
        "case study",
        "mrr",
        "arr",
        "revenue",
        "月收入",
        "公开收入",
        "built with cursor",
        "built with claude",
        "ship with cursor",
    ]
    if any(signal in text for signal in product_case_signals):
        return False
    return any(signal in text for signal in generic_signals)


def extract_product_name(result: SearchResult) -> str:
    if is_generic_article(result):
        domain = domain_from_url(result.url)
        return domain.split(".")[0] if domain else CN_UNDISCLOSED
    title = result.title.strip()
    separators = [" | ", " - ", " — ", " – ", ": "]
    candidate = title
    for sep in separators:
        if sep in candidate:
            candidate = candidate.split(sep, 1)[0]
            break
    candidate = re.sub(
        r"\b(vibe coding|indie hacker|case study|startup|built with|cursor|claude|revenue)\b",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(r"\s+", " ", candidate).strip(" -_:|")
    if not candidate or len(candidate) < 2 or candidate.lower() in {"home", "blog", "github"}:
        domain = domain_from_url(result.url)
        if domain:
            candidate = domain.split(".")[0]
    return candidate[:80] if candidate else CN_UNDISCLOSED


def detect_product_type(result: SearchResult) -> str:
    text = f"{result.title} {result.snippet} {result.url}".lower()
    if "api" in text:
        return "API服务"
    if "extension" in text or "插件" in text or "chrome" in text:
        return "网页插件"
    if "github.com" in text or "open source" in text or "开源" in text:
        return "免费开源工具"
    if "desktop" in text or "mac app" in text or "windows app" in text or "客户端" in text:
        return "本地客户端"
    if any(token in text for token in ["saas", "subscription", "mrr", "arr", "订阅"]):
        return "SaaS订阅工具"
    return CN_UNDISCLOSED


def detect_target_users(result: SearchResult) -> str:
    text = f"{result.title} {result.snippet}".lower()
    targets: List[str] = []
    if any(token in text for token in ["developer", "coding", "github", "api", "开发者"]):
        targets.append("独立开发者")
    if any(token in text for token in ["creator", "newsletter", "content", "自媒体"]):
        targets.append("自媒体")
    if any(token in text for token in ["student", "education", "学生"]):
        targets.append("学生")
    if any(token in text for token in ["business", "team", "office", "productivity", "企业", "办公"]):
        targets.append("职场办公")
    if any(token in text for token in ["founder", "indie hacker", "startup", "solo"]):
        targets.append("独立创业者")
    return "、".join(dict.fromkeys(targets)) if targets else CN_UNDISCLOSED


def detect_ai_tools(result: SearchResult) -> str:
    text = f"{result.title} {result.snippet} {result.url}".lower()
    tools: List[str] = []
    checks = [
        ("Cursor", ["cursor"]),
        ("Claude Code/Claude", ["claude code", "claude"]),
        ("Lovable", ["lovable"]),
        ("Bolt.new", ["bolt.new", "bolt"]),
        ("Replit Agent", ["replit agent"]),
        ("Vibe Coding", ["vibe coding"]),
        ("DeepSeek", ["deepseek"]),
    ]
    for label, tokens in checks:
        if any(token in text for token in tokens):
            tools.append(label)
    return "、".join(dict.fromkeys(tools)) if tools else CN_UNDISCLOSED


def detect_development_time(result: SearchResult) -> str:
    text = f"{result.title} {result.snippet}"
    patterns = [
        r"\b\d+\s*(?:hours?|hrs?)\b",
        r"\b\d+\s*(?:days?)\b",
        r"\b\d+\s*(?:weeks?)\b",
        r"\b\d+\s*(?:months?)\b",
        r"\d+\s*(?:小时|天|周|个月)",
    ]
    matches: List[str] = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    if not matches:
        return CN_UNDISCLOSED
    unique = list(dict.fromkeys(match.strip() for match in matches))
    if len(unique) > 1:
        return "存疑出现多个：" + "；".join(unique)
    return unique[0]


def format_cny(amount: float) -> str:
    if amount >= 10000:
        value = amount / 10000
        if value >= 10:
            return f"约{value:.0f}万元人民币"
        return f"约{value:.1f}万元人民币"
    return f"约{amount:.0f}元人民币"


def detect_revenue(result: SearchResult, config: CollectorConfig) -> str:
    text = f"{result.title} {result.snippet}"
    money_pattern = re.compile(
        r"(?P<symbol>[$€£])\s?(?P<num>\d+(?:,\d{3})*(?:\.\d+)?)\s?(?P<unit>[kKmM]?)"
        r"(?:\s?(?P<period>MRR|ARR|/mo|/month|per month|monthly|revenue))?",
        flags=re.IGNORECASE,
    )
    matches = []
    for match in money_pattern.finditer(text):
        symbol = match.group("symbol")
        num_text = match.group("num").replace(",", "")
        unit = match.group("unit").lower()
        period = (match.group("period") or "收入线索").upper()
        try:
            amount = float(num_text)
        except ValueError:
            continue
        if unit == "k":
            amount *= 1000
        elif unit == "m":
            amount *= 1000000
        if symbol == "$":
            currency = "美元"
            cny = amount * config.usd_cny_rate
            original = f"${amount:,.0f}美元"
        elif symbol == "€":
            currency = "欧元"
            cny = amount * config.eur_cny_rate
            original = f"€{amount:,.0f}欧元"
        else:
            currency = "英镑"
            cny = amount * config.gbp_cny_rate
            original = f"£{amount:,.0f}英镑"
        matches.append(f"{format_cny(cny)}（{original}，{period}，{currency}换算）")
    unique = list(dict.fromkeys(matches))
    if not unique:
        if re.search(r"\b(revenue|mrr|arr|income|收入|营收|月收入)\b", text, re.IGNORECASE):
            return "收入线索：公开摘要提到收入/营收，但未披露明确数值"
        return CN_UNDISCLOSED
    if len(unique) > 1:
        return "存疑出现多个：" + "；".join(unique)
    return unique[0]


def build_product_usage(result: SearchResult) -> str:
    snippet = clean_text(result.snippet)
    if snippet:
        return f"公开摘要显示：{snippet[:180]}"
    return CN_UNDISCLOSED


def build_pain_points(result: SearchResult) -> str:
    snippet = clean_text(result.snippet)
    if not snippet:
        return CN_UNDISCLOSED
    return f"①需复核：{snippet[:70]} ②未披露 ③未披露"


def credibility_for(result: SearchResult) -> Tuple[str, str]:
    domain = domain_from_url(result.url)
    url = result.url.lower()
    if any(token in domain for token in ["github.com", "cursor.com", "lovable.dev", "bolt.new", "replit.com"]):
        return "★★★★ 官方公告", f"来源域名 {domain} 属于产品页、官方页面或 GitHub 一手资料。"
    if any(
        token in domain
        for token in [
            "techcrunch.com",
            "wired.com",
            "theverge.com",
            "forbes.com",
            "businessinsider.com",
            "producthunt.com",
            "ycombinator.com",
            "substack.com",
            "medium.com",
        ]
    ):
        return "★★★ 媒体报道", f"来源域名 {domain} 属于媒体、Newsletter、社区专题或第三方文章。"
    if any(token in domain for token in ["indiehackers.com", "x.com", "twitter.com", "reddit.com"]):
        return "★★ 创始人自报", f"来源域名 {domain} 常见于创始人/开发者自述，需点开核实账号身份。"
    if "blog" in url:
        return "★★ 创始人自报", "来源看起来是博客页面，需确认作者是否为创始人本人。"
    return "★ 匿名推测", "仅根据搜索结果摘要判断，尚未确认是否为一手或权威来源。"


def classify_result(result: SearchResult, product_name: str, usage: str, credibility: str) -> str:
    text = f"{result.title} {result.snippet} {result.url}".lower()
    if result.source_keyword == "SEED_URLS":
        return LEVEL_LEAD
    if is_generic_article(result):
        return LEVEL_LEAD
    has_case_signal = any(
        token in text
        for token in [
            "case study",
            "mrr",
            "arr",
            "revenue",
            "built with cursor",
            "built with claude",
            "ship with cursor",
            "创始人",
            "月收入",
            "变现",
            "独立创业案例",
        ]
    )
    has_required_formal = (
        product_name != CN_UNDISCLOSED
        and usage != CN_UNDISCLOSED
        and bool(result.url)
        and credibility != "★ 匿名推测"
        and detect_product_type(result) != CN_UNDISCLOSED
    )
    if has_case_signal and has_required_formal:
        return LEVEL_FORMAL
    if (
        product_name != CN_UNDISCLOSED
        and usage != CN_UNDISCLOSED
        and detect_product_type(result) != CN_UNDISCLOSED
    ):
        return LEVEL_CANDIDATE
    return LEVEL_LEAD


def standard_risks() -> str:
    return "合规风险：未披露；平台依赖风险：未披露；市场风险竞争：未披露；长期运营风险：未披露"


def standard_opportunities() -> str:
    return "横向延伸场景：未披露；纵向功能衔接：未披露；B端企业转型：未披露；细分生态位卡位：未披露"


def missing_fields_for(item: CaseItem) -> str:
    labels = [
        ("创始人+编程背景", item.founder_and_programming_background),
        ("产品类型", item.product_type),
        ("产品用途", item.product_usage),
        ("目标人群", item.target_users),
        ("解决痛点", item.pain_points),
        ("收入模式+MRR/ARR", item.revenue),
        ("AI工具", item.ai_tools),
        ("开发时间", item.development_time),
        ("是否单人/小团队", item.solo_or_team),
    ]
    missing = [label for label, value in labels if value == CN_UNDISCLOSED or CN_UNDISCLOSED in value]
    return "、".join(missing) if missing else "无"


def build_case_item(result: SearchResult, case_id: int, config: CollectorConfig) -> CaseItem:
    product_name = extract_product_name(result)
    usage = build_product_usage(result)
    credibility, credibility_reason = credibility_for(result)
    level = classify_result(result, product_name, usage, credibility)
    ai_tools = detect_ai_tools(result)
    tool_scene_match = (
        f"公开信息显示与 {ai_tools} 相关，适合复核其在原型开发、代码生成或上线流程中的具体作用。"
        if ai_tools != CN_UNDISCLOSED
        else CN_UNDISCLOSED
    )
    source = f"{result.title}：{result.url}"
    item = CaseItem(
        case_id=case_id,
        level=level,
        product_name=product_name,
        founder_and_programming_background=CN_UNDISCLOSED,
        product_type=detect_product_type(result),
        product_usage=usage,
        target_users=detect_target_users(result),
        pain_points=build_pain_points(result),
        revenue=detect_revenue(result, config),
        ai_tools=ai_tools,
        tool_scene_match=tool_scene_match,
        development_time=detect_development_time(result),
        source=source,
        credibility=credibility,
        credibility_reason=credibility_reason,
        solo_or_team=CN_UNDISCLOSED,
        risks=standard_risks(),
        opportunities=standard_opportunities(),
        missing_fields="",
        review_suggestion=(
            "打开来源链接核验产品名称、创始人身份、收入截图/原文、上线时间；缺失项不得自行补写。"
        ),
    )
    item.missing_fields = missing_fields_for(item)
    return item


def openai_compatible_chat(
    prompt: str,
    config: CollectorConfig,
    budget: BudgetGuard,
    stats: CollectionStats,
) -> Optional[str]:
    if not config.enable_llm_enrichment or not config.llm_api_key:
        return None
    estimated_cost = budget.estimate_cost(prompt)
    if not budget.can_spend(estimated_cost):
        stats.llm_skipped_by_budget += 1
        return None
    endpoint = config.llm_api_base.rstrip("/") + "/chat/completions"
    body = {
        "model": config.llm_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是严谨的数据抽取助手。只根据用户提供的公开摘要抽取字段，"
                    "没有证据的字段必须填未披露，不要编造。"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": config.max_llm_output_tokens,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + config.llm_api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.http_timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    budget.record(estimated_cost)
    stats.llm_calls += 1
    stats.api_cost_cny = budget.spent_cny
    try:
        data = json.loads(raw)
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None


def maybe_enrich_with_llm(
    item: CaseItem,
    result: SearchResult,
    config: CollectorConfig,
    budget: BudgetGuard,
    stats: CollectionStats,
) -> CaseItem:
    prompt = (
        "请从以下搜索结果摘要中抽取 Vibe Coding/AI Coding 独立创业案例信息，"
        "只返回 JSON 对象，可包含 product_usage、target_users、pain_points、ai_tools、"
        "development_time、solo_or_team、review_suggestion 字段。无证据填未披露。\n\n"
        f"标题：{result.title}\n链接：{result.url}\n摘要：{result.snippet}"
    )
    content = openai_compatible_chat(prompt, config, budget, stats)
    if not content:
        return item
    json_match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not json_match:
        return item
    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return item
    allowed_fields = {
        "product_usage": "product_usage",
        "target_users": "target_users",
        "pain_points": "pain_points",
        "ai_tools": "ai_tools",
        "development_time": "development_time",
        "solo_or_team": "solo_or_team",
        "review_suggestion": "review_suggestion",
    }
    for incoming, attr in allowed_fields.items():
        value = str(data.get(incoming, "")).strip()
        if value and value != CN_UNDISCLOSED:
            setattr(item, attr, value)
    item.missing_fields = missing_fields_for(item)
    return item


def dedupe_key(result: SearchResult) -> str:
    product = extract_product_name(result).lower()
    domain = domain_from_url(result.url)
    return product + "|" + domain


def collect_cases(config: CollectorConfig, report_date: dt.date) -> Tuple[List[CaseItem], List[SkippedItem], CollectionStats]:
    stats = CollectionStats(keyword_count=len(config.search_keywords))
    output_day_dir = config.output_dir / report_date.isoformat()
    budget = BudgetGuard(config, output_day_dir / "api_usage.json")
    stats.api_cost_cny = budget.spent_cny

    raw_results: List[SearchResult] = []
    for keyword in config.search_keywords:
        if len(raw_results) >= config.max_total_items:
            break
        try:
            found = search_duckduckgo(keyword, config)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            stats.search_errors.append(f"{keyword}: {exc}")
            continue
        raw_results.extend(found)
        stats.raw_result_count += len(found)
        if config.enable_llm_enrichment and budget.spent_cny >= config.max_daily_api_cost_cny:
            break
        time.sleep(0.8)

    raw_results.extend(build_seed_results(config))
    stats.raw_result_count += len(config.seed_urls)

    seen: set[str] = set()
    items: List[CaseItem] = []
    skipped: List[SkippedItem] = []
    next_id = 1
    for result in raw_results:
        if len(items) >= config.max_total_items:
            skipped.append(SkippedItem(result.title, result.url, "达到 MAX_TOTAL_ITEMS 上限，停止收录。"))
            continue
        key = dedupe_key(result)
        if key in seen:
            skipped.append(SkippedItem(result.title, result.url, "重复产品或重复来源，已跳过。"))
            continue
        seen.add(key)
        if is_ad_or_tracking_link(result):
            skipped.append(SkippedItem(result.title, result.url, "搜索广告或跟踪跳转链接，已跳过。"))
            continue
        if not is_relevant(result):
            skipped.append(SkippedItem(result.title, result.url, "与 Vibe Coding / AI Coding / 独立开发 / AI SaaS 相关性不足。"))
            continue
        item = build_case_item(result, next_id, config)
        item = maybe_enrich_with_llm(item, result, config, budget, stats)
        items.append(item)
        next_id += 1

    if not items:
        fallback_source = config.seed_urls[0] if config.seed_urls else "本地配置检查（无公开链接）"
        fallback = SearchResult(
            title="Vibe Coding / AI Coding 今日线索待人工复核",
            url=fallback_source,
            snippet="本次自动搜索未返回可直接收录结果；请补充 SEED_URLS 或放宽关键词后重新运行。",
            source_keyword="fallback",
        )
        item = build_case_item(fallback, 1, config)
        item.level = LEVEL_LEAD
        item.product_name = "Vibe Coding / AI Coding 今日线索待人工复核"
        item.credibility = "★ 匿名推测"
        item.credibility_reason = "自动搜索无结果时生成的复核提醒，不作为正式案例。"
        item.missing_fields = missing_fields_for(item)
        items.append(item)

    stats.accepted_count = len(items)
    stats.skipped_count = len(skipped)
    stats.api_cost_cny = budget.spent_cny
    return items, skipped, stats


def render_item(item: CaseItem) -> str:
    fields = [
        ("1. 案例编号", str(item.case_id)),
        ("2. 收录级别", item.level),
        ("3. 产品名称", item.product_name),
        ("4. 创始人+编程背景", item.founder_and_programming_background),
        ("5. 产品类型", item.product_type),
        ("6. 产品用途", item.product_usage),
        ("7. 目标人群", item.target_users),
        ("8. 解决痛点", item.pain_points),
        ("9. 收入模式+MRR/ARR", item.revenue),
        ("10. AI工具", item.ai_tools),
        ("11. 工具-场景匹配分析", item.tool_scene_match),
        ("12. 开发时间", item.development_time),
        ("13. 来源+链接", item.source),
        ("14. 数据可信度", item.credibility),
        ("15. 可信度理由", item.credibility_reason),
        ("16. 是否单人/小团队", item.solo_or_team),
        ("17. 风险点", item.risks),
        ("18. 机会点", item.opportunities),
        ("19. 缺失字段", item.missing_fields),
        ("20. 复核建议", item.review_suggestion),
    ]
    return "\n".join(f"{label}：{value}" for label, value in fields)


def section(title: str, items: Sequence[CaseItem]) -> str:
    if not items:
        return f"{title}\n\n本部分今日为 0。"
    return title + "\n\n" + "\n\n".join(render_item(item) for item in items)


def render_skipped(skipped: Sequence[SkippedItem]) -> str:
    if not skipped:
        return "四、跳过案例清单\n\n今日无跳过案例。"
    lines = ["四、跳过案例清单", ""]
    for index, item in enumerate(skipped, start=1):
        lines.append(f"{index}. {item.title}｜{item.url}｜跳过原因：{item.reason}")
    return "\n".join(lines)


def next_keywords(config: CollectorConfig) -> List[str]:
    base = [
        "vibe coded SaaS revenue",
        "made with Cursor MRR",
        "solo founder Claude Code product",
        "Lovable launched startup revenue",
        "Bolt.new indie hacker SaaS",
        "Cursor Product Hunt launch AI tool",
    ]
    existing = {keyword.lower() for keyword in config.search_keywords}
    return [keyword for keyword in base if keyword.lower() not in existing][:6]


def render_summary(
    report_date: dt.date,
    items: Sequence[CaseItem],
    skipped: Sequence[SkippedItem],
    stats: CollectionStats,
    config: CollectorConfig,
    txt_path: Path,
    doc_path: Path,
) -> str:
    formal = sum(1 for item in items if item.level == LEVEL_FORMAL)
    candidate = sum(1 for item in items if item.level == LEVEL_CANDIDATE)
    lead = sum(1 for item in items if item.level == LEVEL_LEAD)
    errors = "；".join(stats.search_errors[:5]) if stats.search_errors else "无"
    keyword_suggestions = "、".join(next_keywords(config)) or "继续沿用当前关键词并增加具体产品名复核"
    return "\n".join(
        [
            "五、今日搜索总结",
            "",
            f"报告日期：{report_date.isoformat()}",
            f"正式案例：{formal}；候选案例：{candidate}；今日线索：{lead}；跳过：{len(skipped)}",
            f"关键词数量：{stats.keyword_count}；原始结果/固定线索：{stats.raw_result_count}",
            f"LLM增强调用：{stats.llm_calls}；因预算跳过：{stats.llm_skipped_by_budget}",
            f"今日API预估花费：{stats.api_cost_cny:.4f}元人民币；预算上限：{config.max_daily_api_cost_cny:.2f}元人民币",
            f"搜索异常：{errors}",
            f"TXT文件：{txt_path}",
            f"DOC文件：{doc_path}",
            "",
            "运行逻辑和结果总结：脚本按 .env 中关键词检索公开页面，先按相关性、重复来源、产品名和来源链接做过滤，再用固定20字段模板输出。未在公开摘要中出现的信息全部保留为「未披露」。正式案例采用更严格的信号，宁可为 0，也不把无关内容凑入正式案例。",
            "",
            "六、下一步建议关键词",
            "",
            keyword_suggestions,
            "",
            "Agent Instructions 优化建议：建议后续补充优先检索站点白名单（Indie Hackers、Product Hunt、GitHub、创始人X账号、产品官网）、明确是否允许使用付费搜索API，以及提供重点国家/语言范围，这样可减少噪音并提升正式案例比例。",
        ]
    )


def render_report(
    report_date: dt.date,
    items: Sequence[CaseItem],
    skipped: Sequence[SkippedItem],
    stats: CollectionStats,
    config: CollectorConfig,
    txt_path: Path,
    doc_path: Path,
) -> str:
    formal_items = [item for item in items if item.level == LEVEL_FORMAL]
    candidate_items = [item for item in items if item.level == LEVEL_CANDIDATE]
    lead_items = [item for item in items if item.level == LEVEL_LEAD]
    parts = [
        f"Vibe Coding 独立创业案例每日采集报告（{report_date.isoformat()}）",
        "",
        section("一、正式收录案例", formal_items),
        "",
        section("二、候选案例", candidate_items),
        "",
        section("三、今日线索池", lead_items),
        "",
        render_skipped(skipped),
        "",
        render_summary(report_date, items, skipped, stats, config, txt_path, doc_path),
    ]
    return "\n".join(parts).strip() + "\n"


def write_doc_file(doc_path: Path, report_text: str) -> None:
    escaped = html.escape(report_text).replace("\n", "<br>\n")
    document = (
        "<html><head><meta charset=\"utf-8\">"
        "<style>body{font-family:Arial,'Microsoft YaHei',sans-serif;line-height:1.55;}"
        "h1{font-size:20px;} .content{white-space:normal;}</style>"
        "</head><body><div class=\"content\">"
        f"{escaped}"
        "</div></body></html>"
    )
    doc_path.write_text(document, encoding="utf-8")


def run_once(config: CollectorConfig, report_date: dt.date) -> Tuple[Path, Path, CollectionStats]:
    day_dir = config.output_dir / report_date.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    txt_path = day_dir / f"vibe_coding_cases_{report_date.isoformat()}.txt"
    doc_path = day_dir / f"vibe_coding_cases_{report_date.isoformat()}.doc"
    items, skipped, stats = collect_cases(config, report_date)
    report = render_report(report_date, items, skipped, stats, config, txt_path, doc_path)
    txt_path.write_text(report, encoding="utf-8")
    write_doc_file(doc_path, report)
    return txt_path, doc_path, stats


def parse_date(value: Optional[str]) -> dt.date:
    if not value:
        return dt.date.today()
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"日期格式错误：{value}，请使用 YYYY-MM-DD") from exc


def wait_until_run_time(run_at: str) -> None:
    try:
        hour_text, minute_text = run_at.split(":", 1)
        target_hour = int(hour_text)
        target_minute = int(minute_text)
    except ValueError as exc:
        raise SystemExit("RUN_AT 格式错误，请使用 HH:MM，例如 08:00") from exc
    now = dt.datetime.now()
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    seconds = max(1, int((target - now).total_seconds()))
    print(f"下一次自动运行时间：{target.isoformat(timespec='minutes')}，脚本将保持等待。")
    time.sleep(seconds)


def daemon_loop(config: CollectorConfig) -> None:
    last_run_date: Optional[dt.date] = None
    print("已进入光标/Cursor 常驻定时模式。按 Ctrl+C 可停止。")
    while True:
        wait_until_run_time(config.run_at)
        today = dt.date.today()
        if last_run_date == today:
            continue
        txt_path, doc_path, stats = run_once(config, today)
        last_run_date = today
        print(
            f"今日采集完成：{txt_path}；{doc_path}；"
            f"API预估花费 {stats.api_cost_cny:.4f} 元。"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Vibe Coding 独立创业案例每日采集脚本")
    parser.add_argument("--env", default=".env", help="配置文件路径，默认 .env")
    parser.add_argument("--date", default=None, help="报告日期，格式 YYYY-MM-DD，默认今天")
    parser.add_argument("--once", action="store_true", help="运行一次后退出")
    parser.add_argument("--daemon", action="store_true", help="按 .env 的 RUN_AT 每天常驻运行")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    config = load_config(Path(args.env))
    if not config.search_keywords:
        print("提醒：SEARCH_KEYWORDS 为空。请复制 .env.example 为 .env 后填写关键词。", file=sys.stderr)
    report_date = parse_date(args.date)
    if args.daemon:
        daemon_loop(config)
        return 0
    txt_path, doc_path, stats = run_once(config, report_date)
    print(f"采集完成：{txt_path}")
    print(f"DOC文件：{doc_path}")
    print(f"今日API预估花费：{stats.api_cost_cny:.4f} 元人民币")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
