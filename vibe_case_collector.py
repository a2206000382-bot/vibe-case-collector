#!/usr/bin/env python3
"""Daily Vibe Coding indie startup case collector.

The script searches public web results, keeps API enrichment behind a hard
daily RMB budget, and writes two local report files: TXT and Word-readable DOC.
It intentionally fills unknown fields with "未披露" instead of guessing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


UNKNOWN = "未披露"
LEVEL_FORMAL = "正式案例"
LEVEL_CANDIDATE = "候选案例"
LEVEL_LEAD = "今日线索"
LEVELS = (LEVEL_FORMAL, LEVEL_CANDIDATE, LEVEL_LEAD)

DEFAULT_KEYWORDS = [
    "Vibe Coding 独立创业案例",
    "Vibe Coding 无代码 SaaS 项目",
    "个人开发者 Vibe Coding 变现",
    "轻量化 AI 工具 Vibe Coding 副业",
    "一人 AI SaaS 创业 Vibe Coding",
    "Cursor 独立开发 AI 工具",
    "Claude Code 独立开发 SaaS",
    "Lovable AI 创业案例",
    "Bolt.new 创业案例",
    "Replit Agent 创业案例",
    "vibe coding indie hacker",
    "built with Cursor startup",
    "built with Claude side project",
    "AI coding SaaS solo founder",
    "Cursor AI SaaS revenue",
    "Lovable app revenue",
    "Bolt.new startup case study",
    "Replit Agent SaaS founder",
    "ship with Cursor indie hacker",
    "AI coding tool indie maker revenue",
]

RELEVANCE_TERMS = [
    "vibe coding",
    "cursor",
    "claude code",
    "lovable",
    "bolt.new",
    "replit agent",
    "ai coding",
    "indie hacker",
    "solo founder",
    "side project",
    "ai saas",
    "独立开发",
    "独立创业",
    "个人开发者",
    "无代码",
    "变现",
    "副业",
    "ai工具",
]

CONCEPT_HINTS = [
    "what is",
    "how to",
    "guide",
    "tutorial",
    "指南",
    "教程",
    "是什么",
    "为什么",
]

MEDIA_DOMAINS = (
    "techcrunch.com",
    "wired.com",
    "theverge.com",
    "businessinsider.com",
    "forbes.com",
    "medium.com",
    "substack.com",
    "newsletter",
    "36kr.com",
    "huxiu.com",
    "sspai.com",
    "infoq.cn",
)

FOUNDER_SELF_DOMAINS = (
    "x.com",
    "twitter.com",
    "indiehackers.com",
    "makerlog.com",
    "dev.to",
    "hashnode.dev",
    "reddit.com",
)

OFFICIAL_DOMAINS = (
    "github.com",
    "gitlab.com",
    "producthunt.com",
)

PLATFORM_NEWS_TERMS = (
    "cursor",
    "lovable",
    "replit agent",
    "bolt.new",
    "github copilot",
    "windsurf",
)


@dataclass
class SearchResult:
    keyword: str
    title: str
    url: str
    snippet: str = ""
    fetched_text: str = ""
    fetched_title: str = ""


@dataclass
class CaseRecord:
    level: str
    product_name: str
    founder_and_coding_background: str = UNKNOWN
    product_type: str = UNKNOWN
    product_purpose: str = UNKNOWN
    target_users: str = UNKNOWN
    pain_points: str = UNKNOWN
    revenue: str = UNKNOWN
    ai_tools: str = UNKNOWN
    tool_scene_match: str = UNKNOWN
    development_time: str = UNKNOWN
    source: str = UNKNOWN
    credibility: str = "★ 匿名推测"
    credibility_reason: str = UNKNOWN
    solo_or_small_team: str = UNKNOWN
    risk_points: str = field(default_factory=lambda: "\n".join([
        "合规风险：未披露",
        "平台依赖风险：未披露",
        "市场风险竞争：未披露",
        "长期运营风险：未披露",
    ]))
    opportunity_points: str = field(default_factory=lambda: "\n".join([
        "横向延伸场景：未披露",
        "纵向功能衔接：未披露",
        "B端企业转型：未披露",
        "细分生态位卡位：未披露",
    ]))
    missing_fields: str = UNKNOWN
    review_suggestion: str = "复核来源原文，确认产品是否真实上线、收入是否为创始人或官方披露。"


@dataclass
class SkipItem:
    title: str
    url: str
    reason: str


class DuckDuckGoParser(HTMLParser):
    """Minimal DuckDuckGo HTML result parser using only the standard library."""

    def __init__(self) -> None:
        super().__init__()
        self.links: List[Tuple[str, str]] = []
        self.snippets: List[str] = []
        self._in_result_link = False
        self._in_snippet = False
        self._current_href = ""
        self._current_text: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_dict = {k: v or "" for k, v in attrs}
        classes = attrs_dict.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._in_result_link = True
            self._current_href = attrs_dict.get("href", "")
            self._current_text = []
        elif "result__snippet" in classes:
            self._in_snippet = True
            self._current_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_result_link:
            title = normalize_space(" ".join(self._current_text))
            if title and self._current_href:
                self.links.append((html.unescape(title), normalize_duck_url(self._current_href)))
            self._in_result_link = False
            self._current_href = ""
            self._current_text = []
        elif self._in_snippet and tag in {"a", "div", "td"}:
            snippet = normalize_space(" ".join(self._current_text))
            if snippet:
                self.snippets.append(html.unescape(snippet))
            self._in_snippet = False
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._in_result_link or self._in_snippet:
            self._current_text.append(data)


class BudgetGuard:
    """Hard stop for optional API enrichment spending."""

    def __init__(self, config: Dict[str, str], log_dir: Path, run_date: dt.date) -> None:
        self.max_cny = parse_float(config.get("MAX_DAILY_BUDGET_CNY"), 0.10)
        self.input_price = parse_float(config.get("INPUT_PRICE_CNY_PER_1K"), 0.001)
        self.output_price = parse_float(config.get("OUTPUT_PRICE_CNY_PER_1K"), 0.002)
        self.reserved_output_tokens = parse_int(config.get("RESERVED_OUTPUT_TOKENS"), 700)
        self.log_file = log_dir / f"budget_{run_date.isoformat()}.json"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.usage = self._load_usage()

    @property
    def spent_cny(self) -> float:
        return float(self.usage.get("spent_cny", 0.0))

    @property
    def remaining_cny(self) -> float:
        return max(self.max_cny - self.spent_cny, 0.0)

    def estimate_tokens(self, text: str) -> int:
        # Conservative mixed Chinese/English approximation.
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        non_cjk = max(len(text) - cjk, 0)
        return max(int(cjk / 1.4 + non_cjk / 4) + 1, 1)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens / 1000 * self.input_price) + (output_tokens / 1000 * self.output_price)

    def can_call(self, prompt_text: str) -> Tuple[bool, str, int, int, float]:
        input_tokens = self.estimate_tokens(prompt_text)
        output_tokens = self.reserved_output_tokens
        projected = self.estimate_cost(input_tokens, output_tokens)
        if self.spent_cny + projected > self.max_cny:
            return (
                False,
                f"预算保护触发：预计本次 API 成本 {projected:.4f} 元，"
                f"累计将超过 {self.max_cny:.2f} 元上限。",
                input_tokens,
                output_tokens,
                projected,
            )
        return True, "允许调用", input_tokens, output_tokens, projected

    def record(self, source: str, input_tokens: int, output_tokens: int) -> None:
        cost = self.estimate_cost(input_tokens, output_tokens)
        self.usage["spent_cny"] = round(self.spent_cny + cost, 6)
        self.usage.setdefault("calls", []).append({
            "time": dt.datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_cny": round(cost, 6),
        })
        self._save_usage()

    def _load_usage(self) -> Dict[str, Any]:
        if self.log_file.exists():
            try:
                return json.loads(self.log_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {"spent_cny": 0.0, "calls": []}
        return {"spent_cny": 0.0, "calls": []}

    def _save_usage(self) -> None:
        self.log_file.write_text(json.dumps(self.usage, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_int(value: Optional[str], default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def parse_float(value: Optional[str], default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def parse_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def load_env(path: Path) -> Dict[str, str]:
    config: Dict[str, str] = {}
    if not path.exists():
        return config
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            config[key] = value
    return config


def merged_config(env_file: Path) -> Dict[str, str]:
    config = load_env(env_file)
    for key, value in os.environ.items():
        if key in {
            "API_KEY",
            "OPENAI_COMPATIBLE_BASE_URL",
            "OPENAI_MODEL",
            "ENABLE_LLM_ENRICHMENT",
            "MAX_DAILY_BUDGET_CNY",
            "INPUT_PRICE_CNY_PER_1K",
            "OUTPUT_PRICE_CNY_PER_1K",
            "RESERVED_OUTPUT_TOKENS",
            "MAX_RESULTS_PER_KEYWORD",
            "MAX_FETCH_PAGES",
            "HTTP_TIMEOUT_SECONDS",
            "OUTPUT_DIR",
            "PROMPT_FILE",
            "SEARCH_KEYWORDS",
            "KEYWORDS_FILE",
            "USD_TO_CNY",
            "ALLOW_AUTOMATIC_FORMAL",
        }:
            config[key] = value
    return config


def read_keywords(config: Dict[str, str], repo_root: Path) -> List[str]:
    keyword_file = config.get("KEYWORDS_FILE")
    if keyword_file:
        path = Path(keyword_file)
        if not path.is_absolute():
            path = repo_root / path
        if path.exists():
            keywords = [
                normalize_space(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if normalize_space(line) and not normalize_space(line).startswith("#")
            ]
            if keywords:
                return keywords

    raw = config.get("SEARCH_KEYWORDS", "")
    if raw:
        parts = re.split(r"[|\n]", raw)
        keywords = [normalize_space(part) for part in parts if normalize_space(part)]
        if keywords:
            return keywords
    return DEFAULT_KEYWORDS


def normalize_duck_url(url: str) -> str:
    url = html.unescape(url)
    if url.startswith("//"):
        url = "https:" + url
    if url.startswith("/"):
        url = "https://duckduckgo.com" + url
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return query["uddg"][0]
    return url


def http_get(url: str, timeout: int) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        raw = response.read(650_000)
    charset_match = re.search(r"charset=([\w-]+)", content_type, re.I)
    charset = charset_match.group(1) if charset_match else "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def search_duckduckgo(keyword: str, max_results: int, timeout: int) -> List[SearchResult]:
    url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": keyword})
    parser = DuckDuckGoParser()
    try:
        parser.feed(http_get(url, timeout))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return [SearchResult(keyword=keyword, title=f"搜索失败：{keyword}", url=url, snippet=str(exc))]

    results: List[SearchResult] = []
    for index, (title, link) in enumerate(parser.links[:max_results]):
        snippet = parser.snippets[index] if index < len(parser.snippets) else ""
        results.append(SearchResult(keyword=keyword, title=title, url=link, snippet=snippet))
    if not results:
        results.append(SearchResult(keyword=keyword, title=f"搜索线索：{keyword}", url=url, snippet="搜索页暂无可解析结果，建议人工复核。"))
    return results


def clean_html_text(page_html: str) -> Tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", page_html, re.I | re.S)
    title = html.unescape(normalize_space(strip_tags(title_match.group(1))) if title_match else "")
    page_html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", page_html, flags=re.I | re.S)
    text = html.unescape(strip_tags(page_html))
    text = normalize_space(text)
    return title, text[:7000]


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "")


def fetch_source_text(result: SearchResult, timeout: int) -> SearchResult:
    if not result.url.startswith(("http://", "https://")):
        return result
    try:
        page = http_get(result.url, timeout)
        title, text = clean_html_text(page)
        result.fetched_title = title
        result.fetched_text = text
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError):
        pass
    return result


def is_relevant(result: SearchResult) -> bool:
    haystack = " ".join([result.title, result.snippet, result.fetched_title, result.fetched_text[:1200]]).lower()
    return any(term.lower() in haystack for term in RELEVANCE_TERMS)


def looks_like_pure_concept(result: SearchResult) -> bool:
    title = result.title.lower()
    if any(hint in title for hint in CONCEPT_HINTS):
        return True
    if re.search(r"\b(top|best)\s+\d+", title):
        return True
    return False


def extract_product_name(title: str) -> str:
    title = normalize_space(title)
    if not title:
        return UNKNOWN
    if re.search(r"\b(top|best)\s+\d+", title, flags=re.I) or re.search(r"\bvs\.?\b|\bversus\b", title, flags=re.I):
        return UNKNOWN
    pieces = re.split(r"\s[-|—–:]\s| - | \| ", title)
    candidate = normalize_space(pieces[0])
    candidate = re.sub(r"^(case study|startup case study|built with|ship with)\s+", "", candidate, flags=re.I)
    candidate = candidate.strip(" -|:：")
    if not candidate or len(candidate) < 2:
        return UNKNOWN
    generic = candidate.lower()
    if generic in {"vibe coding", "ai coding", "cursor", "claude code", "lovable", "bolt.new", "replit agent"}:
        return UNKNOWN
    return candidate[:120]


def infer_product_type(text: str) -> str:
    lower = text.lower()
    if "api" in lower:
        return "API服务"
    if "extension" in lower or "插件" in lower:
        return "网页插件"
    if "open source" in lower or "github" in lower or "开源" in lower:
        return "免费开源工具"
    if "desktop" in lower or "mac app" in lower or "windows" in lower or "客户端" in lower:
        return "本地客户端"
    if "saas" in lower or "subscription" in lower or "mrr" in lower or "arr" in lower:
        return "SaaS订阅工具"
    return UNKNOWN


def infer_ai_tools(text: str) -> str:
    tools = []
    patterns = [
        ("Cursor", r"\bcursor\b"),
        ("Claude Code", r"\bclaude code\b"),
        ("Claude", r"\bclaude\b"),
        ("DeepSeek", r"\bdeepseek\b"),
        ("Lovable", r"\blovable\b"),
        ("Bolt.new", r"\bbolt\.new\b|\bbolt new\b"),
        ("Replit Agent", r"\breplit agent\b"),
        ("ChatGPT", r"\bchatgpt\b|\bgpt-4\b|\bgpt-5\b"),
    ]
    for name, pattern in patterns:
        if re.search(pattern, text, re.I):
            tools.append(name)
    return "、".join(dict.fromkeys(tools)) if tools else UNKNOWN


def infer_revenue(text: str, usd_to_cny: float) -> str:
    compact = normalize_space(text)
    lower = compact.lower()
    if not any(word in lower for word in ["revenue", "mrr", "arr", "收入", "营收", "annual recurring", "annualized"]):
        return UNKNOWN

    amount_match = re.search(
        r"\$[\s]*([0-9]+(?:\.[0-9]+)?)(?:\s|-)*(billion|million|k|m|b)?",
        compact,
        flags=re.I,
    )
    if amount_match:
        amount = float(amount_match.group(1))
        unit = (amount_match.group(2) or "").lower()
        multiplier = 1.0
        unit_label = "美元"
        if unit in {"k"}:
            multiplier = 1_000
            unit_label = "千美元"
        elif unit in {"m", "million"}:
            multiplier = 1_000_000
            unit_label = "million 美元"
        elif unit in {"b", "billion"}:
            multiplier = 1_000_000_000
            unit_label = "billion 美元"
        usd = amount * multiplier
        cny = usd * usd_to_cny
        cadence = "收入线索"
        if re.search(r"\bmrr\b|monthly recurring|last month|月", lower):
            cadence = "MRR/月收入线索"
        elif re.search(r"\barr\b|annual recurring|annualized|年", lower):
            cadence = "ARR/年化收入线索"
        return f"{cadence}：约{format_cny(cny)}人民币（${amount:g} {unit_label}，按 1 USD={usd_to_cny:g} CNY 粗略换算；来源摘要/页面片段，需复核）"

    if any(word in lower for word in ["revenue", "mrr", "arr", "收入", "营收"]):
        return "收入线索：来源提到收入/营收，但未解析到明确金额，需复核原文。"
    return UNKNOWN


def format_cny(value: float) -> str:
    if value >= 100_000_000:
        return f"{value / 100_000_000:.2f}亿元"
    if value >= 10_000:
        return f"{value / 10_000:.2f}万元"
    return f"{value:.2f}元"


def infer_target_users(text: str) -> str:
    lower = text.lower()
    targets = []
    if "indie" in lower or "solo founder" in lower or "独立开发" in lower:
        targets.append("独立开发者")
    if "student" in lower or "学生" in lower:
        targets.append("学生")
    if "creator" in lower or "自媒体" in lower or "content" in lower:
        targets.append("自媒体/内容创作者")
    if "enterprise" in lower or "business" in lower or "企业" in lower:
        targets.append("企业/职场办公")
    return "、".join(dict.fromkeys(targets)) if targets else UNKNOWN


def credibility_for_url(url: str, title: str) -> Tuple[str, str]:
    domain = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    if any(domain.endswith(item) for item in OFFICIAL_DOMAINS):
        return "★★★★ 官方公告", f"来源域名 {domain} 属于官网/代码仓库/官方产品页类一手资料。"
    if any(item in domain for item in MEDIA_DOMAINS):
        return "★★★ 媒体报道", f"来源域名 {domain} 属于媒体、Newsletter 或行业专栏。"
    if any(domain.endswith(item) for item in FOUNDER_SELF_DOMAINS):
        return "★★ 创始人自报", f"来源域名 {domain} 可能是一手社交平台/开发者社区，需复核发布者身份。"
    return "★ 匿名推测", "搜索结果未显示官方、媒体或已确认创始人自报信号。"


def is_ad_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    lower_url = url.lower()
    return (
        parsed.netloc.endswith("duckduckgo.com")
        and parsed.path.endswith("/y.js")
    ) or "aclick" in lower_url or "ad_domain=" in lower_url


def is_platform_news(result: SearchResult) -> bool:
    title = result.title.lower()
    return any(term in title for term in PLATFORM_NEWS_TERMS) and not any(
        term in title for term in ["built with", "ship with", "indie", "solo founder", "case study", "creator", "maker"]
    )


def looks_like_article_not_product(result: SearchResult) -> bool:
    title = result.title.lower()
    generic_hints = [
        "vibe coding",
        "什么是",
        "如何",
        "经验",
        "路径",
        "副业",
        "赚钱",
        "专栏",
        "指南",
        "教程",
        "普通人",
        "零代码",
        "无代码",
        "工具",
        "案例",
        "实战",
        "comparison",
        "compare",
        "free",
        "success stories",
        "startup journeys",
        "stories of",
        "roundup",
        "list of",
    ]
    if any(hint in title for hint in generic_hints) and not re.search(r"\bbuilt with\b|\bship with\b|\blaunched\b|\bmrr\b|\barr\b", title):
        return True
    return False


def looks_like_case_signal(result: SearchResult) -> bool:
    text = " ".join([result.title, result.snippet, result.fetched_title, result.fetched_text[:1500]]).lower()
    return any(
        signal in text
        for signal in [
            "built with cursor",
            "built with claude",
            "ship with cursor",
            "indie hacker",
            "solo founder",
            "case study",
            "mrr",
            "arr",
            "revenue",
            "创始人",
            "独立开发",
            "个人开发者",
            "变现",
        ]
    )


def build_case_from_result(result: SearchResult, config: Dict[str, str]) -> Tuple[Optional[CaseRecord], Optional[SkipItem]]:
    if is_ad_url(result.url):
        return None, SkipItem(result.title, result.url, "搜索广告或跳转广告链接")
    if not is_relevant(result):
        return None, SkipItem(result.title, result.url, "与 Vibe Coding / AI Coding / 独立开发 / AI SaaS 相关度不足")

    product_name = extract_product_name(result.title or result.fetched_title)
    text = " ".join([result.title, result.snippet, result.fetched_title, result.fetched_text])
    credibility, credibility_reason = credibility_for_url(result.url, result.title)
    purpose = normalize_space(result.snippet) or UNKNOWN
    source = f"{result.title}：{result.url}" if result.url else result.title or UNKNOWN

    if looks_like_pure_concept(result) and product_name == UNKNOWN:
        return None, SkipItem(result.title, result.url, "偏概念/教程文章，且无法确认具体产品名称")

    level = LEVEL_LEAD
    if (
        product_name != UNKNOWN
        and purpose != UNKNOWN
        and not looks_like_pure_concept(result)
        and not looks_like_article_not_product(result)
        and not is_platform_news(result)
        and looks_like_case_signal(result)
        and credibility.startswith(("★★★★", "★★★", "★★"))
    ):
        level = LEVEL_CANDIDATE
    allow_auto_formal = parse_bool(config.get("ALLOW_AUTOMATIC_FORMAL"), False)
    if level == LEVEL_CANDIDATE and allow_auto_formal and result.url and credibility.startswith(("★★★★", "★★★")):
        level = LEVEL_FORMAL

    case = CaseRecord(
        level=level,
        product_name=product_name,
        product_type=infer_product_type(text),
        product_purpose=purpose,
        target_users=infer_target_users(text),
        source=source,
        credibility=credibility,
        credibility_reason=credibility_reason,
        ai_tools=infer_ai_tools(text),
        revenue=infer_revenue(text, parse_float(config.get("USD_TO_CNY"), 7.20)),
    )
    if case.ai_tools != UNKNOWN and case.product_purpose != UNKNOWN:
        case.tool_scene_match = f"{case.ai_tools} 与该线索描述的开发/AI 产品场景相关；具体开发使用证据仍需复核来源原文。"
    fill_missing_fields(case)
    return case, None


def fill_missing_fields(case: CaseRecord) -> None:
    field_values = {
        "产品名称": case.product_name,
        "创始人+编程背景": case.founder_and_coding_background,
        "产品类型": case.product_type,
        "产品用途": case.product_purpose,
        "目标人群": case.target_users,
        "解决痛点": case.pain_points,
        "收入模式+MRR/ARR": case.revenue,
        "AI工具": case.ai_tools,
        "工具-场景匹配分析": case.tool_scene_match,
        "开发时间": case.development_time,
        "是否单人/小团队": case.solo_or_small_team,
    }
    missing = [name for name, value in field_values.items() if not value or value == UNKNOWN or "未披露" == value.strip()]
    case.missing_fields = "、".join(missing) if missing else "无"


def dedupe_cases(cases: Iterable[CaseRecord]) -> List[CaseRecord]:
    seen: set[str] = set()
    output: List[CaseRecord] = []
    for case in cases:
        key = normalize_space(case.product_name).lower()
        if key == UNKNOWN or not key:
            key = normalize_space(case.source).lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(case)
    return output


def trim_cases(cases: List[CaseRecord], min_leads: int = 1) -> List[CaseRecord]:
    formal = [case for case in cases if case.level == LEVEL_FORMAL][:6]
    candidate = [case for case in cases if case.level == LEVEL_CANDIDATE][:10]
    leads = [case for case in cases if case.level == LEVEL_LEAD][:12]
    return formal + candidate + leads


def ensure_non_empty_leads(cases: List[CaseRecord], keywords: Sequence[str]) -> List[CaseRecord]:
    if any(case.level in {LEVEL_CANDIDATE, LEVEL_LEAD} for case in cases):
        return cases
    keyword = keywords[0] if keywords else "vibe coding indie hacker"
    search_url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": keyword})
    case = CaseRecord(
        level=LEVEL_LEAD,
        product_name=UNKNOWN,
        product_purpose=f"围绕关键词“{keyword}”的公开搜索线索，需人工打开搜索页复核具体产品。",
        source=f"DuckDuckGo 搜索页：{search_url}",
        credibility="★ 匿名推测",
        credibility_reason="仅为搜索入口，尚未确认具体产品和一手来源。",
        review_suggestion="打开搜索页，优先寻找官网、GitHub、创始人自述或媒体案例报道。",
    )
    fill_missing_fields(case)
    return [case]


def call_llm_enrichment(
    result: SearchResult,
    case: CaseRecord,
    config: Dict[str, str],
    prompt_path: Path,
    budget: BudgetGuard,
    timeout: int,
) -> Tuple[CaseRecord, Optional[str]]:
    api_key = config.get("API_KEY", "").strip()
    if not api_key or api_key.startswith("请"):
        return case, "未配置 API_KEY，跳过 API 精读。"

    base_url = config.get("OPENAI_COMPATIBLE_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    model = config.get("OPENAI_MODEL", "deepseek-chat")
    if not prompt_path.exists():
        return case, f"提示词文件不存在：{prompt_path}"

    system_prompt = prompt_path.read_text(encoding="utf-8")
    user_payload = textwrap.dedent(f"""
        请只基于以下公开资料抽取，不要猜测。

        关键词：{result.keyword}
        标题：{result.title}
        摘要：{result.snippet}
        来源链接：{result.url}
        页面标题：{result.fetched_title}
        正文片段：{result.fetched_text[:5000]}

        当前初步记录：
        {json.dumps(case.__dict__, ensure_ascii=False)}
    """).strip()
    full_prompt_for_budget = system_prompt + "\n" + user_payload
    allowed, reason, input_tokens, reserved_output_tokens, _ = budget.can_call(full_prompt_for_budget)
    if not allowed:
        return case, reason

    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response_body = json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return case, f"API 精读失败：{exc}"

    content = response_body.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = response_body.get("usage", {})
    output_tokens = int(usage.get("completion_tokens") or budget.estimate_tokens(content) or reserved_output_tokens)
    prompt_tokens = int(usage.get("prompt_tokens") or input_tokens)
    budget.record(result.url, prompt_tokens, output_tokens)

    try:
        data = json.loads(extract_json_object(content))
    except json.JSONDecodeError as exc:
        return case, f"API 返回无法解析为 JSON：{exc}"

    mapping = {
        "product_name": "product_name",
        "founder_and_coding_background": "founder_and_coding_background",
        "product_type": "product_type",
        "product_purpose": "product_purpose",
        "target_users": "target_users",
        "pain_points": "pain_points",
        "revenue": "revenue",
        "ai_tools": "ai_tools",
        "tool_scene_match": "tool_scene_match",
        "development_time": "development_time",
        "credibility": "credibility",
        "credibility_reason": "credibility_reason",
        "solo_or_small_team": "solo_or_small_team",
        "level": "level",
    }
    for json_key, attr in mapping.items():
        value = data.get(json_key)
        if isinstance(value, str) and value.strip():
            setattr(case, attr, normalize_space(value))
    if case.level not in LEVELS:
        case.level = LEVEL_LEAD
    fill_missing_fields(case)
    return case, None


def extract_json_object(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content, flags=re.I).strip()
        content = re.sub(r"```$", "", content).strip()
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        return content[start : end + 1]
    return content


def render_case(case: CaseRecord, number: int) -> str:
    rows = [
        ("案例编号", str(number)),
        ("收录级别", case.level),
        ("产品名称", case.product_name),
        ("创始人+编程背景", case.founder_and_coding_background),
        ("产品类型", case.product_type),
        ("产品用途", case.product_purpose),
        ("目标人群", case.target_users),
        ("解决痛点", case.pain_points),
        ("收入模式+MRR/ARR", case.revenue),
        ("AI工具", case.ai_tools),
        ("工具-场景匹配分析", case.tool_scene_match),
        ("开发时间", case.development_time),
        ("来源+链接", case.source),
        ("数据可信度", case.credibility),
        ("可信度理由", case.credibility_reason),
        ("是否单人/小团队", case.solo_or_small_team),
        ("风险点", case.risk_points),
        ("机会点", case.opportunity_points),
        ("缺失字段", case.missing_fields),
        ("复核建议", case.review_suggestion),
    ]
    return "\n".join(f"{index}. {label}：{value}" for index, (label, value) in enumerate(rows, 1))


def render_section(title: str, cases: Sequence[CaseRecord], start_number: int) -> Tuple[str, int]:
    lines = [title]
    if not cases:
        lines.append("本次未收录。")
        return "\n".join(lines), start_number
    number = start_number
    for case in cases:
        lines.append("")
        lines.append(render_case(case, number))
        number += 1
    return "\n".join(lines), number


def render_report(
    cases: Sequence[CaseRecord],
    skipped: Sequence[SkipItem],
    keywords: Sequence[str],
    run_date: dt.date,
    budget: BudgetGuard,
    notes: Sequence[str],
) -> str:
    lines = [
        f"Vibe Coding 独立创业案例每日采集报告",
        f"日期：{run_date.isoformat()}",
        "",
        "说明：本报告仅基于公开搜索结果和可抓取页面片段生成；缺失信息统一填写「未披露」。",
        "分级：正式案例要求产品名称、用途、来源链接、可信度完整；候选案例允许创始人、收入、开发时间缺失；今日线索不作为正式案例。",
        "",
    ]
    number = 1
    for title, level in [
        ("一、正式收录案例", LEVEL_FORMAL),
        ("二、候选案例", LEVEL_CANDIDATE),
        ("三、今日线索池", LEVEL_LEAD),
    ]:
        section, number = render_section(title, [case for case in cases if case.level == level], number)
        lines.append(section)
        lines.append("")

    lines.append("四、跳过案例清单")
    if skipped:
        for index, item in enumerate(skipped[:30], 1):
            lines.append(f"{index}. {item.title}：{item.url}；跳过原因：{item.reason}")
    else:
        lines.append("本次无跳过记录。")
    lines.append("")

    lines.extend([
        "五、今日搜索总结",
        f"1. 检索关键词数量：{len(keywords)}",
        f"2. 输出案例/线索数量：{len(cases)}",
        f"3. 正式案例：{sum(1 for case in cases if case.level == LEVEL_FORMAL)}；候选案例：{sum(1 for case in cases if case.level == LEVEL_CANDIDATE)}；今日线索：{sum(1 for case in cases if case.level == LEVEL_LEAD)}",
        f"4. API预算上限：{budget.max_cny:.2f} 元人民币；本日已记录估算消耗：{budget.spent_cny:.6f} 元人民币；剩余额度：{budget.remaining_cny:.6f} 元人民币。",
        "5. 运行逻辑总结：先按关键词公开搜索，再按相关性过滤、按链接/产品去重、按可信度分级；API 精读仅在 .env 开启且预算允许时执行。",
    ])
    if notes:
        lines.append("6. 运行备注：" + "；".join(dict.fromkeys(notes)))
    lines.append("")

    lines.append("六、下一步建议关键词")
    suggestions = [
        "built with Cursor revenue founder interview",
        "site:indiehackers.com Cursor AI SaaS revenue",
        "site:x.com \"built with Cursor\" \"MRR\"",
        "site:github.com \"built with Claude Code\" SaaS",
        "Lovable founder revenue case study",
        "Bolt.new launched startup revenue",
        "Replit Agent indie SaaS founder",
    ]
    for index, suggestion in enumerate(suggestions, 1):
        lines.append(f"{index}. {suggestion}")

    lines.extend([
        "",
        "Agent Instructions 优化建议",
        "1. 建议增加“优先官网/GitHub/创始人原帖，其次媒体报道，最后论坛线索”的来源优先级。",
        "2. 建议把正式案例最低门槛固定为：产品名、产品用途、可访问链接、可信度理由四项齐全。",
        "3. 建议允许正式案例为 0，避免为了凑数混入纯概念文章。",
        "4. 建议把预算、关键词、提示词路径全部保留在 .env 中，便于每日微调且避免密钥硬编码。",
    ])
    return "\n".join(lines).strip() + "\n"


def write_outputs(report: str, output_dir: Path, run_date: dt.date) -> Tuple[Path, Path]:
    day_dir = output_dir / run_date.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    txt_path = day_dir / f"vibe_cases_{run_date.isoformat()}.txt"
    doc_path = day_dir / f"vibe_cases_{run_date.isoformat()}.doc"
    txt_path.write_text(report, encoding="utf-8")

    escaped = html.escape(report).replace("\n", "<br>\n")
    doc_html = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>Vibe Coding 独立创业案例每日采集报告</title>"
        "<style>body{font-family:'Microsoft YaHei',Arial,sans-serif;line-height:1.65;}"
        "h1{font-size:22px;} .report{white-space:normal;}</style>"
        "</head><body><div class=\"report\">"
        f"{escaped}"
        "</div></body></html>"
    )
    doc_path.write_text(doc_html, encoding="utf-8")
    return txt_path, doc_path


def collect_cases(config: Dict[str, str], repo_root: Path, run_date: dt.date) -> Tuple[List[CaseRecord], List[SkipItem], List[str], BudgetGuard]:
    keywords = read_keywords(config, repo_root)
    max_results = parse_int(config.get("MAX_RESULTS_PER_KEYWORD"), 6)
    max_fetch_pages = parse_int(config.get("MAX_FETCH_PAGES"), 10)
    timeout = parse_int(config.get("HTTP_TIMEOUT_SECONDS"), 12)
    output_dir = repo_root / config.get("OUTPUT_DIR", "reports")
    budget = BudgetGuard(config, output_dir / "_logs", run_date)
    prompt_path = Path(config.get("PROMPT_FILE", "prompts/case_extract_prompt.txt"))
    if not prompt_path.is_absolute():
        prompt_path = repo_root / prompt_path

    raw_results: List[SearchResult] = []
    for keyword in keywords:
        raw_results.extend(search_duckduckgo(keyword, max_results, timeout))
        time.sleep(0.5)

    seen_urls: set[str] = set()
    unique_results: List[SearchResult] = []
    for result in raw_results:
        if result.url in seen_urls:
            continue
        seen_urls.add(result.url)
        unique_results.append(result)

    for result in unique_results[:max_fetch_pages]:
        fetch_source_text(result, timeout)
        time.sleep(0.3)

    cases: List[CaseRecord] = []
    skipped: List[SkipItem] = []
    notes: List[str] = []
    enable_llm = parse_bool(config.get("ENABLE_LLM_ENRICHMENT"), False)
    for result in unique_results:
        case, skip = build_case_from_result(result, config)
        if skip:
            skipped.append(skip)
            continue
        if not case:
            continue
        if enable_llm:
            case, note = call_llm_enrichment(result, case, config, prompt_path, budget, timeout)
            if note:
                notes.append(note)
                if note.startswith("预算保护触发"):
                    enable_llm = False
        cases.append(case)

    cases = trim_cases(dedupe_cases(cases))
    cases = ensure_non_empty_leads(cases, keywords)
    return cases, skipped, notes, budget


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Collect public Vibe Coding indie startup cases.")
    parser.add_argument("--env", default=".env", help="Path to .env configuration file.")
    parser.add_argument("--date", default="", help="Report date, YYYY-MM-DD. Defaults to today.")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent
    run_date = dt.date.today()
    if args.date:
        run_date = dt.date.fromisoformat(args.date)

    config = merged_config(repo_root / args.env)
    output_dir = repo_root / config.get("OUTPUT_DIR", "reports")
    cases, skipped, notes, budget = collect_cases(config, repo_root, run_date)
    keywords = read_keywords(config, repo_root)
    report = render_report(cases, skipped, keywords, run_date, budget, notes)
    txt_path, doc_path = write_outputs(report, output_dir, run_date)

    print("采集完成")
    print(f"TXT：{txt_path}")
    print(f"DOC：{doc_path}")
    print(f"案例/线索数量：{len(cases)}")
    print(f"API估算消耗：{budget.spent_cny:.6f} 元人民币 / {budget.max_cny:.2f} 元人民币")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("用户中断。", file=sys.stderr)
        raise SystemExit(130)
