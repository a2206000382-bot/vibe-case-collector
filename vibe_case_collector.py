#!/usr/bin/env python3
"""
Daily Vibe Coding indie case collector.

The script intentionally uses only Python's standard library so beginners can run
it without installing packages. All secrets, keywords, schedules, and budget
controls are read from .env or environment variables.
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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


UNKNOWN = "未披露"
FORMAL = "正式案例"
CANDIDATE = "候选案例"
LEAD = "今日线索"

FIELD_NAMES = [
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

AI_TOOL_PATTERNS = {
    "Cursor": r"\bCursor\b",
    "Claude Code": r"\bClaude\s+Code\b",
    "Claude": r"\bClaude\b",
    "Lovable": r"\bLovable\b",
    "Bolt.new": r"\bBolt(?:\.new)?\b",
    "Replit Agent": r"\bReplit\s+Agent\b",
    "Windsurf": r"\bWindsurf\b",
    "GitHub Copilot": r"\b(?:GitHub\s+)?Copilot\b",
    "DeepSeek": r"\bDeepSeek\b",
    "v0": r"\bv0\b",
}

RELATED_PATTERNS = [
    r"\bvibe\s+coding\b",
    r"\bCursor\b",
    r"\bClaude\s+Code\b",
    r"\bLovable\b",
    r"\bBolt(?:\.new)?\b",
    r"\bReplit\s+Agent\b",
    r"\bAI\s+coding\b",
    r"\bindie\s+hacker\b",
    r"\bsolo\s+founder\b",
    r"\bAI\s+SaaS\b",
    r"\bside\s+project\b",
    r"\bMRR\b",
    r"\brevenue\b",
    r"\bbuilt\s+with\b",
    r"独立开发",
    r"个人开发者",
    r"变现",
    r"副业",
    r"一人",
    r"小团队",
    r"无代码",
    r"AI工具",
]

CONCEPT_PATTERNS = [
    r"what\s+is\s+vibe\s+coding",
    r"guide\s+to\s+vibe\s+coding",
    r"how\s+to\s+vibe\s+code",
    r"vibe\s+coding\s+is",
    r"trend",
    r"tutorial",
    r"tools?\s+for\s+vibe\s+coding",
    r"指南",
    r"教程",
    r"是什么",
    r"趋势",
    r"概念",
    r"工具选型",
    r"入门",
    r"推荐",
    r"TOP\s?\d+",
    r"top\s?\d+",
]

ARTICLE_TITLE_PATTERNS = [
    r"指南",
    r"教程",
    r"经验总结",
    r"工具选型",
    r"深度体验",
    r"推荐",
    r"盘点",
    r"榜单",
    r"步骤拆解",
    r"完整方案",
    r"横评",
    r"详解",
    r"赚钱",
    r"什么是",
    r"how\s+to",
    r"what\s+is",
    r"podcast|播客",
    r"blog|博客",
    r"article|文章",
    r"TOP\s?\d+|top\s?\d+",
]

MEDIA_DOMAINS = [
    "techcrunch.com",
    "theverge.com",
    "wired.com",
    "forbes.com",
    "businessinsider.com",
    "indiehackers.com",
    "starterstory.com",
    "substack.com",
    "medium.com",
    "latent.space",
    "a16z.com",
    "sspai.com",
    "36kr.com",
    "ithome.com",
]

FOUNDER_DOMAINS = [
    "x.com",
    "twitter.com",
    "reddit.com",
    "threads.net",
    "linkedin.com",
    "personal",
]

OFFICIAL_DOMAINS = [
    "github.com",
    "gitlab.com",
]


def load_env(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        env[key.strip()] = value
    return env


def get_setting(env: Dict[str, str], key: str, default: str = "") -> str:
    return os.environ.get(key, env.get(key, default)).strip()


def split_multi(value: str) -> List[str]:
    if not value:
        return []
    parts = re.split(r"[\n|,，]+", value)
    return [part.strip() for part in parts if part.strip()]


def parse_bool(value: str, default: bool = False) -> bool:
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on", "是"}


def parse_int(value: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return default


def parse_float(value: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(value))
    except (TypeError, ValueError):
        return default


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def strip_tracking_url(url: str) -> str:
    if not url:
        return ""
    url = html.unescape(url)
    if "duckduckgo.com/l/?" in url:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        if query.get("uddg"):
            return query["uddg"][0]
    if url.startswith("//"):
        return "https:" + url
    return url


def canonical_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    kept = {
        key: values
        for key, values in query.items()
        if not key.lower().startswith("utm_")
        and key.lower() not in {"fbclid", "gclid", "ref", "source"}
    }
    rebuilt = parsed._replace(query=urllib.parse.urlencode(kept, doseq=True), fragment="")
    return urllib.parse.urlunparse(rebuilt)


def is_search_ad_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()
    query = parsed.query.lower()
    return (
        ("duckduckgo.com" in domain and ("/y.js" in path or "ad_domain=" in query))
        or ("bing.com" in domain and "/aclick" in path)
        or "utm_campaign=bing" in query
    )


def domain_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def http_get(url: str, timeout: int = 12, max_bytes: int = 350_000) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(max_bytes)
    charset = "utf-8"
    content_type = response.headers.get("content-type", "")
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        charset = match.group(1)
    return raw.decode(charset, errors="replace")


@dataclass
class SearchResult:
    query: str
    title: str
    url: str
    snippet: str = ""
    page_text: str = ""
    reason: str = ""

    @property
    def combined_text(self) -> str:
        return clean_text(" ".join([self.title, self.snippet, self.page_text]))


@dataclass
class BudgetMeter:
    daily_budget_cny: float
    hard_cap_cny: float
    input_price_cny_per_1k: float
    output_price_cny_per_1k: float
    spent_cny: float = 0.0
    calls: int = 0
    skipped_calls: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def effective_budget_cny(self) -> float:
        return min(self.daily_budget_cny, self.hard_cap_cny)

    @property
    def remaining_cny(self) -> float:
        return max(0.0, self.effective_budget_cny - self.spent_cny)

    @staticmethod
    def estimate_tokens(text: str) -> int:
        # A conservative mixed Chinese/English estimate. It intentionally rounds up.
        return max(1, int(len(text) / 3) + 1)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            (input_tokens / 1000.0) * self.input_price_cny_per_1k
            + (output_tokens / 1000.0) * self.output_price_cny_per_1k
        )

    def can_spend(self, prompt: str, max_output_tokens: int) -> Tuple[bool, float, int]:
        input_tokens = self.estimate_tokens(prompt)
        estimated = self.estimate_cost(input_tokens, max_output_tokens)
        if self.spent_cny + estimated > self.effective_budget_cny:
            self.skipped_calls += 1
            self.notes.append(
                f"预算保护：预计本次 {estimated:.4f} 元，剩余额度 {self.remaining_cny:.4f} 元，已跳过。"
            )
            return False, estimated, input_tokens
        return True, estimated, input_tokens

    def record(self, input_tokens: int, output_tokens: int) -> None:
        self.calls += 1
        self.spent_cny += self.estimate_cost(input_tokens, output_tokens)


class LLMClient:
    def __init__(self, env: Dict[str, str], budget: BudgetMeter) -> None:
        self.api_key = get_setting(env, "LLM_API_KEY")
        self.base_url = get_setting(
            env, "LLM_API_BASE_URL", "https://api.openai.com/v1/chat/completions"
        )
        self.model = get_setting(env, "LLM_MODEL", "gpt-4o-mini")
        self.enabled = parse_bool(get_setting(env, "ENABLE_LLM_ENRICHMENT"), False)
        self.timeout = parse_int(get_setting(env, "LLM_TIMEOUT_SECONDS"), 30, 5)
        self.max_output_tokens = parse_int(get_setting(env, "LLM_MAX_OUTPUT_TOKENS"), 900, 100)
        self.budget = budget

    def available(self) -> bool:
        return bool(self.enabled and self.api_key and self.base_url and self.model)

    def enrich(self, result: SearchResult) -> Dict[str, str]:
        if not self.available():
            return {}
        prompt = (
            "你是事实核查助手。只允许使用下面网页标题、摘要、正文片段中的公开信息，"
            "不要猜测。请返回 JSON，不要 Markdown。字段包括：产品名称、创始人+编程背景、"
            "产品类型、产品用途、目标人群、解决痛点、收入模式+MRR/ARR、AI工具、开发时间、"
            "是否单人/小团队、缺失字段、复核建议。没有证据统一填“未披露”。\n\n"
            f"标题：{result.title}\n链接：{result.url}\n摘要：{result.snippet}\n正文片段："
            f"{result.page_text[:5000]}"
        )
        allowed, _estimated, input_tokens = self.budget.can_spend(prompt, self.max_output_tokens)
        if not allowed:
            return {}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "只抽取可核查事实，禁止补全想象信息。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": self.max_output_tokens,
        }
        request = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            self.budget.notes.append(f"LLM调用失败：{exc.__class__.__name__}，已使用启发式规则继续。")
            return {}
        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        output_tokens = int(usage.get("completion_tokens") or self.max_output_tokens)
        input_tokens = int(usage.get("prompt_tokens") or input_tokens)
        self.budget.record(input_tokens, output_tokens)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return {}
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
        return {str(key): str(value) for key, value in parsed.items()}


def duckduckgo_search(query: str, limit: int) -> List[SearchResult]:
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    body = http_get(url)
    blocks = re.split(r'<div class="result', body, flags=re.I)[1:]
    results: List[SearchResult] = []
    for block in blocks:
        title_match = re.search(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            block,
            re.I | re.S,
        )
        if not title_match:
            continue
        snippet_match = re.search(
            r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|'
            r'<div[^>]+class="result__snippet"[^>]*>(.*?)</div>',
            block,
            re.I | re.S,
        )
        snippet = ""
        if snippet_match:
            snippet = clean_text(snippet_match.group(1) or snippet_match.group(2) or "")
        results.append(
            SearchResult(
                query=query,
                title=clean_text(title_match.group(2)),
                url=canonical_url(strip_tracking_url(title_match.group(1))),
                snippet=snippet,
            )
        )
        if len(results) >= limit:
            break
    return results


def bing_search(query: str, limit: int) -> List[SearchResult]:
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query})
    body = http_get(url)
    blocks = re.split(r'<li class="b_algo"', body, flags=re.I)[1:]
    results: List[SearchResult] = []
    for block in blocks:
        title_match = re.search(r"<h2[^>]*>\s*<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, re.I | re.S)
        if not title_match:
            continue
        snippet_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.I | re.S)
        results.append(
            SearchResult(
                query=query,
                title=clean_text(title_match.group(2)),
                url=canonical_url(strip_tracking_url(title_match.group(1))),
                snippet=clean_text(snippet_match.group(1) if snippet_match else ""),
            )
        )
        if len(results) >= limit:
            break
    return results


def manual_source_results(urls: Sequence[str]) -> List[SearchResult]:
    results: List[SearchResult] = []
    for url in urls:
        canonical = canonical_url(url)
        title = canonical
        snippet = "来自 .env SOURCE_URLS 的人工补充公开来源，待脚本抓取正文后复核。"
        try:
            page = http_get(canonical, timeout=10, max_bytes=160_000)
            title = extract_page_title(page) or title
            snippet = extract_meta_description(page) or snippet
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
        results.append(SearchResult(query="SOURCE_URLS", title=title, url=canonical, snippet=snippet))
    return results


def extract_page_title(page: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
    return clean_text(match.group(1)) if match else ""


def extract_meta_description(page: str) -> str:
    match = re.search(
        r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']+)["\']',
        page,
        re.I | re.S,
    )
    if not match:
        match = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:description|og:description)["\']',
            page,
            re.I | re.S,
        )
    return clean_text(match.group(1)) if match else ""


def extract_visible_text(page: str) -> str:
    page = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.I | re.S)
    return clean_text(page)


def contains_any(patterns: Sequence[str], text: str) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def looks_like_article_title(title: str) -> bool:
    return contains_any(ARTICLE_TITLE_PATTERNS, title)


def extract_ai_tools(text: str) -> str:
    tools = [name for name, pattern in AI_TOOL_PATTERNS.items() if re.search(pattern, text, re.I)]
    return "、".join(dict.fromkeys(tools)) if tools else UNKNOWN


def extract_product_name(title: str, url: str, level: str) -> str:
    title = clean_text(title)
    title = re.sub(r"\s*[\-|–|—|:]\s*(Product Hunt|Hacker News|Indie Hackers|Reddit|X|Twitter).*$", "", title, flags=re.I)
    title = re.sub(r"\s*\|.*$", "", title).strip()
    if not title:
        title = domain_of(url)
    if level == LEAD and not title:
        return f"线索：{url}"
    return title or UNKNOWN


def infer_product_type(text: str, url: str) -> str:
    checks = [
        ("网页插件", r"chrome\s+extension|browser\s+extension|插件|扩展"),
        ("API服务", r"\bAPI\b|developer\s+api|按量|接口"),
        ("免费开源工具", r"open\s+source|github\.com|开源|README"),
        ("本地客户端", r"desktop|macOS|Windows|Linux|本地客户端|桌面"),
        ("SaaS订阅工具", r"\bSaaS\b|subscription|subscribe|pricing|MRR|ARR|订阅"),
    ]
    source = text + " " + url
    for label, pattern in checks:
        if re.search(pattern, source, re.I):
            return label
    if re.search(r"app|tool|software|工具|应用", source, re.I):
        return "SaaS订阅工具"
    return UNKNOWN


def infer_purpose(snippet: str, page_text: str) -> str:
    text = clean_text(snippet or page_text[:300])
    if not text:
        return UNKNOWN
    text = re.sub(r"^(This|It|The product)\s+", "这个工具 ", text, flags=re.I)
    if len(text) > 150:
        text = text[:147].rstrip() + "..."
    return text


def infer_audience(text: str) -> str:
    mapping = [
        ("独立开发者", r"indie\s+hacker|developer|founder|startup|solo|独立开发|开发者|创业者"),
        ("职场办公", r"office|team|workflow|productivity|职场|办公|团队协作"),
        ("学生", r"student|education|learning|学生|教育|学习"),
        ("自媒体", r"creator|content|YouTube|TikTok|newsletter|自媒体|内容创作"),
        ("企业客户", r"enterprise|B2B|company|business|企业|公司"),
    ]
    hits = [label for label, pattern in mapping if re.search(pattern, text, re.I)]
    return "、".join(dict.fromkeys(hits)) if hits else UNKNOWN


def extract_revenue(text: str, usd_to_cny: float) -> str:
    money_patterns = [
        r"(?P<currency>\$|USD\s*)\s?(?P<num>\d+(?:\.\d+)?)\s?(?P<unit>k|K|m|M)?\s?(?P<period>MRR|ARR|/mo|per month|monthly revenue|revenue)?",
        r"(?P<num>\d+(?:\.\d+)?)\s?(?P<unit>万|千)?\s?(?P<currency>元|人民币|RMB|CNY)\s?(?P<period>MRR|ARR|月收入|年收入)?",
    ]
    found: List[str] = []
    for pattern in money_patterns:
        for match in re.finditer(pattern, text, re.I):
            raw = clean_text(match.group(0))
            if not raw or len(raw) > 40:
                continue
            currency = (match.groupdict().get("currency") or "").upper()
            period = match.groupdict().get("period") or "收入线索"
            try:
                num = float(match.groupdict().get("num") or "0")
            except ValueError:
                continue
            unit = match.groupdict().get("unit") or ""
            multiplier = 1.0
            if unit.lower() == "k" or unit == "千":
                multiplier = 1000.0
            elif unit.lower() == "m":
                multiplier = 1_000_000.0
            elif unit == "万":
                multiplier = 10_000.0
            amount = num * multiplier
            if "$" in raw or "USD" in currency:
                cny = amount * usd_to_cny
                found.append(f"{cny:,.0f}元人民币（{raw}美元，{period}）")
            elif any(symbol in raw for symbol in ["元", "人民币", "RMB", "CNY"]):
                found.append(f"{amount:,.0f}元人民币（{raw}，{period}）")
    found = list(dict.fromkeys(found))
    if not found:
        if re.search(r"revenue|MRR|ARR|收入|变现", text, re.I):
            return "收入线索：来源提到收入/变现，但未给出可换算金额"
        return UNKNOWN
    if len(found) > 1:
        return "存疑出现多个：" + "；".join(found)
    return found[0]


def extract_dev_time(text: str) -> str:
    patterns = [
        r"\b(?:built|launched|shipped)\s+(?:in|within)\s+[^.。；;]{1,40}",
        r"\b\d+\s?(?:hours?|days?|weeks?|months?)\b",
        r"\d+\s?(?:小时|天|周|个月)",
    ]
    matches: List[str] = []
    for pattern in patterns:
        matches.extend(clean_text(match.group(0)) for match in re.finditer(pattern, text, re.I))
    matches = list(dict.fromkeys(matches))
    return "存疑出现多个：" + "；".join(matches[:5]) if len(matches) > 1 else (matches[0] if matches else UNKNOWN)


def infer_solo_or_team(text: str) -> str:
    if re.search(r"\bsolo\b|one[- ]person|one[- ]man|single founder|一人|单人|个人开发者", text, re.I):
        return "是（单人）"
    if re.search(r"small team|two founders|co[- ]founder|小团队|两人|合伙", text, re.I):
        return "是（小团队）"
    if re.search(r"team of \d+|\d+\s?人团队", text, re.I):
        return "是（小团队，规模见来源）"
    return UNKNOWN


def credibility(url: str, text: str) -> Tuple[str, str]:
    domain = domain_of(url)
    if any(marker in domain for marker in OFFICIAL_DOMAINS):
        return "★★★★ 官方公告", "来源属于官网/代码托管/官方博客等一手资料，但仍需人工确认页面归属。"
    if any(marker in domain for marker in MEDIA_DOMAINS):
        return "★★★ 媒体报道", "来源属于媒体、Newsletter、行业文章或案例库。"
    if any(marker in domain for marker in FOUNDER_DOMAINS) or re.search(r"\bI\s+(built|made|launched)\b|我.*(做了|上线|开发)", text, re.I):
        return "★★ 创始人自报", "来源呈现创始人/开发者自述特征。"
    return "★ 匿名推测", "来源暂未确认是一手资料或权威第三方报道，仅作为线索。"


def fixed_risk_points() -> str:
    return "\n".join(
        [
            "合规风险：未披露",
            "平台依赖风险：未披露",
            "市场风险竞争：未披露",
            "长期运营风险：未披露",
        ]
    )


def fixed_opportunity_points() -> str:
    return "\n".join(
        [
            "横向延伸场景：未披露",
            "纵向功能衔接：未披露",
            "B端企业转型：未披露",
            "细分生态位卡位：未披露",
        ]
    )


def find_missing_fields(case: Dict[str, str]) -> str:
    missing = [name for name in FIELD_NAMES[2:] if case.get(name, UNKNOWN) == UNKNOWN]
    return "、".join(missing) if missing else "无"


def classify(result: SearchResult) -> Tuple[str, str]:
    text = result.combined_text
    if not contains_any(RELATED_PATTERNS, text):
        return "", "与 Vibe Coding / AI Coding / 独立开发 / AI SaaS 主题关联不足"
    title = result.title or ""
    is_concept = contains_any(CONCEPT_PATTERNS, text) or looks_like_article_title(title)
    has_productish = bool(re.search(r"\b(app|tool|SaaS|startup|product|extension|API)\b|工具|应用|项目|产品", text, re.I))
    has_case_signal = bool(re.search(r"\b(built|launched|shipped|founder|solo|MRR|ARR|revenue)\b|上线|收入|创始|变现", text, re.I))
    has_name_signal = bool(
        re.search(r"Product\s+Hunt|GitHub\s+-|launch(?:ed|es)?\s+[A-Z][\w.-]+|built\s+[A-Z][\w.-]+", text, re.I)
        or (title and not looks_like_article_title(title) and len(title) <= 90)
    )
    if is_concept:
        return LEAD, "相关内容偏概念、教程、盘点或经验文章，不作为案例收录"
    if has_productish and has_case_signal and has_name_signal:
        cred, _reason = credibility(result.url, text)
        if cred.startswith("★★★") or cred.startswith("★★★★"):
            return FORMAL, ""
        return CANDIDATE, "产品案例信号存在，但来源可信度或关键字段不足以进入正式案例"
    if has_productish and has_name_signal:
        return CANDIDATE, "产品或用途有线索，但创始人、收入、开发时间等字段不足"
    return LEAD, "仅作为相关线索，尚未确认具体产品案例"


def build_case(result: SearchResult, level: str, usd_to_cny: float, llm_data: Dict[str, str]) -> Dict[str, str]:
    text = result.combined_text
    cred, cred_reason = credibility(result.url, text)
    product_name = llm_data.get("产品名称") or extract_product_name(result.title, result.url, level)
    purpose = llm_data.get("产品用途") or infer_purpose(result.snippet, result.page_text)
    ai_tools = llm_data.get("AI工具") or extract_ai_tools(text)
    tool_scene = UNKNOWN
    if ai_tools != UNKNOWN and purpose != UNKNOWN:
        tool_scene = f"来源可见 {ai_tools} 相关线索；需复核其是否直接用于构建该产品，当前场景为：{purpose}"
    case = {
        "案例编号": "",
        "收录级别": level,
        "产品名称": product_name or UNKNOWN,
        "创始人+编程背景": llm_data.get("创始人+编程背景", UNKNOWN),
        "产品类型": llm_data.get("产品类型") or infer_product_type(text, result.url),
        "产品用途": purpose or UNKNOWN,
        "目标人群": llm_data.get("目标人群") or infer_audience(text),
        "解决痛点": llm_data.get("解决痛点", UNKNOWN),
        "收入模式+MRR/ARR": llm_data.get("收入模式+MRR/ARR") or extract_revenue(text, usd_to_cny),
        "AI工具": ai_tools,
        "工具-场景匹配分析": llm_data.get("工具-场景匹配分析", tool_scene),
        "开发时间": llm_data.get("开发时间") or extract_dev_time(text),
        "来源+链接": f"{result.title}：{result.url}",
        "数据可信度": cred,
        "可信度理由": cred_reason,
        "是否单人/小团队": llm_data.get("是否单人/小团队") or infer_solo_or_team(text),
        "风险点": fixed_risk_points(),
        "机会点": fixed_opportunity_points(),
        "缺失字段": "",
        "复核建议": llm_data.get("复核建议") or "人工打开来源链接，确认产品名称、创始人身份、是否真实使用 Vibe Coding 工具及收入口径。",
    }
    case["缺失字段"] = llm_data.get("缺失字段") or find_missing_fields(case)
    return case


def enforce_collection_rules(case: Dict[str, str]) -> None:
    """Keep formal/candidate sections strict after all fields are extracted."""
    product_name = case.get("产品名称", UNKNOWN)
    purpose = case.get("产品用途", UNKNOWN)
    source = case.get("来源+链接", UNKNOWN)
    credibility_value = case.get("数据可信度", UNKNOWN)
    article_like = looks_like_article_title(product_name)
    if case.get("收录级别") == FORMAL:
        required_missing = (
            product_name == UNKNOWN
            or purpose == UNKNOWN
            or source == UNKNOWN
            or credibility_value == UNKNOWN
            or article_like
        )
        if required_missing:
            case["收录级别"] = CANDIDATE if purpose != UNKNOWN and not article_like else LEAD
            case["复核建议"] = "正式案例字段不足或标题偏文章型，已自动降级；请人工确认是否存在具体产品案例。"
    if case.get("收录级别") == CANDIDATE:
        if product_name == UNKNOWN or purpose == UNKNOWN or article_like:
            case["收录级别"] = LEAD
            case["复核建议"] = "候选案例必须具备明确产品名称和用途；当前信息不足，已自动降级为今日线索。"
    case["缺失字段"] = find_missing_fields(case)


def collect_search_results(env: Dict[str, str]) -> Tuple[List[SearchResult], List[str]]:
    keywords = split_multi(get_setting(env, "SEARCH_KEYWORDS")) + split_multi(get_setting(env, "SEARCH_KEYWORDS_EN"))
    source_urls = split_multi(get_setting(env, "SOURCE_URLS"))
    max_per_keyword = parse_int(get_setting(env, "MAX_SEARCH_RESULTS_PER_KEYWORD"), 5, 1)
    max_total = parse_int(get_setting(env, "MAX_TOTAL_RESULTS"), 45, 1)
    errors: List[str] = []
    all_results: List[SearchResult] = []
    seen_urls: set[str] = set()
    for query in keywords:
        if len(all_results) >= max_total:
            break
        providers = [duckduckgo_search, bing_search]
        provider_results: List[SearchResult] = []
        for provider in providers:
            try:
                provider_results = provider(query, max_per_keyword)
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                errors.append(f"{provider.__name__} 检索失败：{query}（{exc.__class__.__name__}）")
                continue
            if provider_results:
                break
        for item in provider_results:
            if not item.url or item.url in seen_urls or is_search_ad_url(item.url):
                continue
            seen_urls.add(item.url)
            all_results.append(item)
            if len(all_results) >= max_total:
                break
    for item in manual_source_results(source_urls):
        if item.url and item.url not in seen_urls and len(all_results) < max_total:
            seen_urls.add(item.url)
            all_results.append(item)
    return all_results, errors


def enrich_pages(results: List[SearchResult], env: Dict[str, str]) -> List[str]:
    max_deep_pages = parse_int(get_setting(env, "MAX_DEEP_PAGES"), 8, 0)
    errors: List[str] = []
    fetched = 0
    for result in results:
        if fetched >= max_deep_pages:
            break
        if not result.url.startswith(("http://", "https://")):
            continue
        try:
            page = http_get(result.url, timeout=10, max_bytes=220_000)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            errors.append(f"正文抓取失败：{result.url}（{exc.__class__.__name__}）")
            continue
        fetched += 1
        page_title = extract_page_title(page)
        meta = extract_meta_description(page)
        visible = extract_visible_text(page)
        if page_title and (not result.title or result.title.startswith("http")):
            result.title = page_title
        if meta and not result.snippet:
            result.snippet = meta
        result.page_text = visible[:6000]
    return errors


def collect_cases(env: Dict[str, str]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], Dict[str, Any]]:
    budget = BudgetMeter(
        daily_budget_cny=parse_float(get_setting(env, "DAILY_BUDGET_CNY"), 0.10),
        hard_cap_cny=parse_float(get_setting(env, "HARD_DAILY_BUDGET_CNY"), 0.10),
        input_price_cny_per_1k=parse_float(get_setting(env, "LLM_INPUT_PRICE_CNY_PER_1K"), 0.0015),
        output_price_cny_per_1k=parse_float(get_setting(env, "LLM_OUTPUT_PRICE_CNY_PER_1K"), 0.0060),
    )
    llm = LLMClient(env, budget)
    usd_to_cny = parse_float(get_setting(env, "USD_TO_CNY_RATE"), 7.20, 0.1)
    results, search_errors = collect_search_results(env)
    fetch_errors = enrich_pages(results, env)
    cases: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []
    seen_names: set[str] = set()
    for result in results:
        level, reason = classify(result)
        if not level:
            skipped.append({"title": result.title or result.url, "url": result.url, "reason": reason})
            continue
        name_key = re.sub(r"\W+", "", extract_product_name(result.title, result.url, level).lower())
        if name_key and name_key in seen_names:
            skipped.append({"title": result.title or result.url, "url": result.url, "reason": "重复产品或重复线索"})
            continue
        seen_names.add(name_key)
        llm_data = llm.enrich(result)
        case = build_case(result, level, usd_to_cny, llm_data)
        enforce_collection_rules(case)
        cases.append(case)
    if not any(case["收录级别"] in {CANDIDATE, LEAD} for case in cases) and results:
        fallback = results[0]
        cases.append(build_case(fallback, LEAD, usd_to_cny, {}))
        cases[-1]["复核建议"] = "搜索结果不足，自动保留首条相关来源作为今日线索，请人工复核。"
    for index, case in enumerate(cases, start=1):
        case["案例编号"] = str(index)
    summary = {
        "search_errors": search_errors,
        "fetch_errors": fetch_errors,
        "budget": budget,
        "result_count": len(results),
        "keywords": split_multi(get_setting(env, "SEARCH_KEYWORDS")) + split_multi(get_setting(env, "SEARCH_KEYWORDS_EN")),
    }
    return cases, skipped, summary


def render_case(case: Dict[str, str]) -> str:
    lines: List[str] = []
    for field in FIELD_NAMES:
        value = case.get(field, UNKNOWN)
        lines.append(f"{field}：{value}")
    return "\n".join(lines)


def section_cases(title: str, cases: Sequence[Dict[str, str]]) -> str:
    if not cases:
        return f"{title}\n（今日无符合该级别且可公开溯源的案例。）\n"
    body = "\n\n".join(render_case(case) for case in cases)
    return f"{title}\n{body}\n"


def render_report(report_date: str, cases: List[Dict[str, str]], skipped: List[Dict[str, str]], summary: Dict[str, Any]) -> str:
    formal = [case for case in cases if case["收录级别"] == FORMAL]
    candidates = [case for case in cases if case["收录级别"] == CANDIDATE]
    leads = [case for case in cases if case["收录级别"] == LEAD]
    budget: BudgetMeter = summary["budget"]
    keyword_text = "、".join(summary.get("keywords", [])) or "未配置"
    errors = summary.get("search_errors", []) + summary.get("fetch_errors", []) + budget.notes
    error_text = "\n".join(f"- {item}" for item in errors[:20]) if errors else "- 无"
    skipped_text = (
        "\n".join(
            f"- {item.get('title', UNKNOWN)} | {item.get('url', UNKNOWN)} | 跳过原因：{item.get('reason', UNKNOWN)}"
            for item in skipped
        )
        if skipped
        else "- 无"
    )
    suggestions = [
        "built with Cursor MRR solo founder",
        "Claude Code indie SaaS revenue",
        "Lovable app founder revenue",
        "Bolt.new startup case study",
        "AI coding tool side project revenue",
        "Cursor 独立开发 收入",
        "Claude Code 一人 SaaS",
    ]
    report = [
        f"Vibe Coding 独立创业案例每日采集报告（{report_date}）",
        "=" * 38,
        "说明：本报告仅收录脚本从公开网页检索到的可追溯信息。缺失字段统一填「未披露」；正式案例从严，无法确认产品名称或来源链接的内容不进入正式案例。",
        "",
        section_cases("一、正式收录案例", formal),
        section_cases("二、候选案例", candidates),
        section_cases("三、今日线索池", leads),
        "四、跳过案例清单",
        skipped_text,
        "",
        "五、今日搜索总结",
        f"- 检索关键词：{keyword_text}",
        f"- 检索结果数：{summary.get('result_count', 0)}；正式案例：{len(formal)}；候选案例：{len(candidates)}；今日线索：{len(leads)}；跳过：{len(skipped)}",
        f"- API预算硬上限：{budget.effective_budget_cny:.2f} 元人民币；估算已用：{budget.spent_cny:.4f} 元；LLM调用次数：{budget.calls}；预算保护跳过：{budget.skipped_calls}",
        "- 运行逻辑：先按 .env 关键词检索，再有限抓取网页正文，随后用证据优先规则分类；字段没有公开佐证时统一写「未披露」。",
        "- 运行/抓取提示：",
        error_text,
        "",
        "六、下一步建议关键词",
        "\n".join(f"- {item}" for item in suggestions),
        "",
        "Agent Instructions 优化建议",
        "- 将正式案例定义继续保持从严：必须具备产品名称、用途、来源链接、可信度理由。",
        "- 建议后续补充允许访问的一手来源白名单，例如创始人 X、Indie Hackers、GitHub、产品官网，以提高正式案例比例。",
        "- 如需控制成本，继续保持 DAILY_BUDGET_CNY <= 0.10，并限制 MAX_DEEP_PAGES 与 LLM_MAX_OUTPUT_TOKENS。",
    ]
    return "\n".join(report).rstrip() + "\n"


def write_outputs(report_text: str, report_date: str, output_dir: Path) -> Tuple[Path, Path]:
    day_dir = output_dir / report_date
    day_dir.mkdir(parents=True, exist_ok=True)
    txt_path = day_dir / f"vibe_coding_cases_{report_date}.txt"
    doc_path = day_dir / f"vibe_coding_cases_{report_date}.doc"
    txt_path.write_text(report_text, encoding="utf-8")
    doc_html = (
        "<html><head><meta charset=\"utf-8\"><title>Vibe Coding Daily Report</title>"
        "<style>body{font-family:Microsoft YaHei,Arial,sans-serif;line-height:1.55;}"
        "pre{white-space:pre-wrap;font-family:Microsoft YaHei,Arial,sans-serif;}</style>"
        "</head><body><pre>"
        + html.escape(report_text)
        + "</pre></body></html>"
    )
    doc_path.write_text(doc_html, encoding="utf-8")
    return txt_path, doc_path


def run_once(args: argparse.Namespace, env: Dict[str, str]) -> int:
    report_date = args.date or dt.date.today().isoformat()
    output_dir = Path(args.output_dir or get_setting(env, "OUTPUT_DIR", "reports"))
    cases, skipped, summary = collect_cases(env)
    report_text = render_report(report_date, cases, skipped, summary)
    if args.dry_run:
        print(report_text)
        return 0
    txt_path, doc_path = write_outputs(report_text, report_date, output_dir)
    print(f"已生成：{txt_path}")
    print(f"已生成：{doc_path}")
    budget: BudgetMeter = summary["budget"]
    print(
        f"结果：共 {len(cases)} 条，预算已用 {budget.spent_cny:.4f} 元，"
        f"有效预算上限 {budget.effective_budget_cny:.2f} 元。"
    )
    return 0


def seconds_until(run_at: str) -> int:
    now = dt.datetime.now()
    try:
        hour, minute = [int(part) for part in run_at.split(":", 1)]
    except ValueError:
        hour, minute = 8, 0
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return max(1, int((target - now).total_seconds()))


def run_daemon(args: argparse.Namespace, env: Dict[str, str]) -> int:
    run_at = args.run_at or get_setting(env, "RUN_AT", "08:00")
    print(f"常驻定时模式已启动，每天 {run_at} 运行。按 Ctrl+C 停止。")
    try:
        while True:
            sleep_seconds = seconds_until(run_at)
            print(f"距离下次运行约 {sleep_seconds} 秒。")
            time.sleep(sleep_seconds)
            run_once(args, env)
            time.sleep(60)
    except KeyboardInterrupt:
        print("已停止常驻定时模式。")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Vibe Coding 独立创业案例每日采集脚本")
    parser.add_argument("--config", default=".env", help="配置文件路径，默认 .env")
    parser.add_argument("--once", action="store_true", help="立即运行一次")
    parser.add_argument("--daemon", action="store_true", help="常驻定时运行")
    parser.add_argument("--run-at", default="", help="常驻模式每天运行时间，例如 08:00")
    parser.add_argument("--date", default="", help="报告日期，例如 2026-06-22")
    parser.add_argument("--output-dir", default="", help="报告输出目录，默认读取 .env 的 OUTPUT_DIR")
    parser.add_argument("--dry-run", action="store_true", help="只在屏幕显示，不写文件")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    env = load_env(Path(args.config))
    if not args.once and not args.daemon:
        args.once = True
    keywords = split_multi(get_setting(env, "SEARCH_KEYWORDS")) + split_multi(get_setting(env, "SEARCH_KEYWORDS_EN"))
    if not keywords and not split_multi(get_setting(env, "SOURCE_URLS")):
        print("错误：请先在 .env 配置 SEARCH_KEYWORDS、SEARCH_KEYWORDS_EN 或 SOURCE_URLS。", file=sys.stderr)
        return 2
    if args.daemon:
        return run_daemon(args, env)
    return run_once(args, env)


if __name__ == "__main__":
    raise SystemExit(main())
