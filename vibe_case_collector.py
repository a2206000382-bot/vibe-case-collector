#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vibe Coding 独立创业案例自动采集器。

设计目标：
- 零第三方依赖，普通 Python 安装后即可运行。
- API 密钥、搜索关键词、预算、运行范围全部从 .env 读取，禁止硬编码密钥。
- 默认只做公开网页搜索与规则提取；可选启用 OpenAI 兼容接口做结构化提取。
- 每日 API 预算硬限制 0.10 元人民币，达到阈值立即停止 LLM 调用。
- 同步输出 TXT 与 Word 可打开的 .doc（HTML 格式）报告。
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
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


FIELDS = [
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

SECTION_NAMES = ["正式案例", "候选案例", "今日线索"]

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

DEFAULT_RESEARCH_SCOPE = (
    "仅收录公开可查证的 Vibe Coding / AI Coding 个人或小团队 AI 工具创业真实落地案例；"
    "纯概念设想、无产品名、无来源链接、无关内容不得进入正式案例。"
)

RELATED_MARKERS = [
    "vibe coding",
    "cursor",
    "claude code",
    "bolt.new",
    "lovable",
    "replit agent",
    "ai coding",
    "indie hacker",
    "solo founder",
    "ai saas",
    "独立开发",
    "个人开发者",
    "一人",
    "小团队",
    "无代码",
    "低代码",
    "副业",
    "变现",
]

OFFICIAL_MARKERS = [
    "github.com",
    "cursor.com",
    "lovable.dev",
    "bolt.new",
    "replit.com",
    "vercel.com",
    "producthunt.com",
]

MEDIA_MARKERS = [
    "techcrunch.com",
    "wired.com",
    "theverge.com",
    "forbes.com",
    "36kr.com",
    "sspai.com",
    "medium.com",
    "substack.com",
    "newsletter",
]

FOUNDER_SELF_MARKERS = [
    "x.com",
    "twitter.com",
    "indiehackers.com",
    "reddit.com",
    "youtube.com",
    "blog",
]

PRODUCT_TYPE_OPTIONS = [
    "SaaS订阅工具",
    "本地客户端",
    "网页插件",
    "API服务",
    "免费开源工具",
    "未披露",
]

REVENUE_MODE_OPTIONS = [
    "SaaS月订阅",
    "一次性买断",
    "API按量收费",
    "广告变现",
    "企业定制服务",
    "未披露",
]

FALLBACK_SEED_RESULTS = [
    {
        "title": "Cursor 官方客户与案例入口",
        "url": "https://www.cursor.com/customers",
        "snippet": "官方页面展示使用 Cursor 的客户与团队，可作为后续复核 built with Cursor / AI coding 创业案例的入口。",
        "keyword": "seed: Cursor customers",
    },
    {
        "title": "Lovable 官方博客与产品案例入口",
        "url": "https://lovable.dev/blog",
        "snippet": "Lovable 官方博客常发布用 AI 生成应用、产品上线和创业相关内容，可作为 AI app / no-code SaaS 线索入口。",
        "keyword": "seed: Lovable blog",
    },
    {
        "title": "Bolt.new 官方产品入口",
        "url": "https://bolt.new/",
        "snippet": "Bolt.new 是面向快速生成应用的 AI 开发工具，官方入口可用于追踪 built with Bolt.new 的创业案例。",
        "keyword": "seed: Bolt.new",
    },
    {
        "title": "Replit Agent 官方介绍入口",
        "url": "https://replit.com/agent",
        "snippet": "Replit Agent 官方页面介绍使用自然语言构建软件的 AI Coding 场景，可作为一人 SaaS 线索入口。",
        "keyword": "seed: Replit Agent",
    },
    {
        "title": "Indie Hackers AI 产品案例线索入口",
        "url": "https://www.indiehackers.com/",
        "snippet": "Indie Hackers 社区常见独立开发者收入、MRR、SaaS 上线复盘，可用于检索 AI Coding 与创业变现线索。",
        "keyword": "seed: Indie Hackers",
    },
]


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    keyword: str


@dataclass
class UsageState:
    date: str
    spent_cny: float
    estimated_tokens: int
    calls: int


class DotEnv:
    """Small .env reader/writer-free loader to keep the script dependency-free."""

    def __init__(self, path: Path):
        self.path = path
        self.values: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for raw_line in self.path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            self.values[key] = value
            os.environ.setdefault(key, value)

    def get(self, key: str, default: str = "") -> str:
        return os.environ.get(key, self.values.get(key, default))

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.get(key, str(default)).strip().lower()
        return value in {"1", "true", "yes", "y", "on", "是", "开启"}

    def get_int(self, key: str, default: int) -> int:
        value = self.get(key, str(default)).strip()
        try:
            return int(value)
        except ValueError:
            return default

    def get_float(self, key: str, default: float) -> float:
        value = self.get(key, str(default)).strip()
        try:
            return float(value)
        except ValueError:
            return default


class DuckDuckGoParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results: List[SearchResult] = []
        self._in_result_link = False
        self._current_href = ""
        self._current_title_parts: List[str] = []
        self._in_snippet = False
        self._snippet_parts: List[str] = []
        self._pending: Optional[Tuple[str, str]] = None

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr = {k: v or "" for k, v in attrs}
        classes = attr.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._in_result_link = True
            self._current_href = attr.get("href", "")
            self._current_title_parts = []
        elif "result__snippet" in classes:
            self._in_snippet = True
            self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_result_link:
            self._current_title_parts.append(data)
        elif self._in_snippet:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_result_link:
            title = normalize_space("".join(self._current_title_parts))
            url = clean_ddg_url(self._current_href)
            if title and url:
                self._pending = (title, url)
            self._in_result_link = False
        elif self._in_snippet and tag in {"a", "div"}:
            snippet = normalize_space("".join(self._snippet_parts))
            if self._pending:
                title, url = self._pending
                self.results.append(SearchResult(title=title, url=url, snippet=snippet, keyword=""))
                self._pending = None
            self._in_snippet = False


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def clean_ddg_url(url: str) -> str:
    url = html.unescape(url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        params = urllib.parse.parse_qs(parsed.query)
        if "uddg" in params and params["uddg"]:
            return params["uddg"][0]
    return url


def parse_multiline_list(value: str, fallback: Sequence[str]) -> List[str]:
    if not value.strip():
        return list(fallback)
    normalized = value.replace("\\n", "\n")
    pieces: List[str] = []
    for line in normalized.splitlines():
        for part in line.split("|"):
            item = part.strip()
            if item:
                pieces.append(item)
    return dedupe_keep_order(pieces) or list(fallback)


def dedupe_keep_order(items: Iterable[str]) -> List[str]:
    seen = set()
    output = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            output.append(item)
    return output


def http_get(url: str, timeout: int, max_chars: int = 600_000) -> str:
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
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(max_chars)
    charset = "utf-8"
    content_type = resp.headers.get("Content-Type", "")
    match = re.search(r"charset=([\w.-]+)", content_type)
    if match:
        charset = match.group(1)
    return raw.decode(charset, errors="replace")


def search_duckduckgo(keyword: str, max_results: int, timeout: int) -> List[SearchResult]:
    query = urllib.parse.urlencode({"q": keyword})
    url = f"https://duckduckgo.com/html/?{query}"
    body = http_get(url, timeout=timeout)
    parser = DuckDuckGoParser()
    parser.feed(body)
    results = parser.results[:max_results]
    if not results:
        results = regex_parse_ddg(body, max_results)
    for result in results:
        result.keyword = keyword
    return results


def regex_parse_ddg(body: str, max_results: int) -> List[SearchResult]:
    matches = re.findall(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        body,
        flags=re.I | re.S,
    )
    snippets = re.findall(
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(.*?)</div>',
        body,
        flags=re.I | re.S,
    )
    parsed: List[SearchResult] = []
    for index, (url, title_html) in enumerate(matches[:max_results]):
        snippet_html = ""
        if index < len(snippets):
            snippet_html = snippets[index][0] or snippets[index][1]
        title = normalize_space(re.sub(r"<[^>]+>", " ", title_html))
        snippet = normalize_space(re.sub(r"<[^>]+>", " ", snippet_html))
        parsed.append(SearchResult(title=title, url=clean_ddg_url(url), snippet=snippet, keyword=""))
    return parsed


def collect_search_results(env: DotEnv) -> Tuple[List[SearchResult], List[str]]:
    keywords = parse_multiline_list(env.get("SEARCH_KEYWORDS", ""), DEFAULT_KEYWORDS)
    max_keywords = max(1, env.get_int("MAX_KEYWORDS_PER_RUN", 12))
    max_results = max(1, env.get_int("MAX_RESULTS_PER_KEYWORD", 5))
    timeout = max(5, env.get_int("HTTP_TIMEOUT_SECONDS", 15))
    pause_seconds = max(0.0, env.get_float("SEARCH_PAUSE_SECONDS", 0.8))
    results: List[SearchResult] = []
    errors: List[str] = []

    for keyword in keywords[:max_keywords]:
        try:
            results.extend(search_duckduckgo(keyword, max_results=max_results, timeout=timeout))
            time.sleep(pause_seconds)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"{keyword}: {exc}")

    deduped: List[SearchResult] = []
    seen_urls = set()
    for result in results:
        if not result.url or result.url.lower() in seen_urls:
            continue
        seen_urls.add(result.url.lower())
        deduped.append(result)

    if not deduped:
        deduped = [
            SearchResult(
                title=item["title"],
                url=item["url"],
                snippet=item["snippet"],
                keyword=item["keyword"],
            )
            for item in FALLBACK_SEED_RESULTS
        ]
        errors.append("搜索引擎无返回或被拦截，已启用内置公开入口作为今日线索池。")

    return deduped, errors


def fetch_page_text(url: str, env: DotEnv) -> str:
    if env.get_bool("FETCH_PAGE_DETAILS", True) is False:
        return ""
    timeout = max(5, env.get_int("HTTP_TIMEOUT_SECONDS", 15))
    max_chars = max(10_000, env.get_int("MAX_PAGE_CHARS", 80_000))
    try:
        body = http_get(url, timeout=timeout, max_chars=max_chars)
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeError):
        return ""
    body = re.sub(r"(?is)<script.*?>.*?</script>", " ", body)
    body = re.sub(r"(?is)<style.*?>.*?</style>", " ", body)
    body = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", body)
    body = re.sub(r"(?is)<[^>]+>", " ", body)
    return normalize_space(body)[:max_chars]


def is_related(result: SearchResult, page_text: str = "") -> bool:
    haystack = f"{result.title} {result.snippet} {page_text[:2000]}".lower()
    return any(marker.lower() in haystack for marker in RELATED_MARKERS)


def infer_credibility(url: str) -> Tuple[str, str]:
    domain = urllib.parse.urlparse(url).netloc.lower()
    if any(marker in domain for marker in OFFICIAL_MARKERS):
        return "★★★★ 官方公告", "来源为官网、产品页、GitHub 或官方社区等一手入口。"
    if any(marker in domain for marker in MEDIA_MARKERS):
        return "★★★ 媒体报道", "来源域名属于媒体、Newsletter 或行业文章平台。"
    if any(marker in domain for marker in FOUNDER_SELF_MARKERS):
        return "★★ 创始人自报", "来源为社交平台、开发者社区或个人发布渠道，仍需复核作者身份。"
    return "★ 匿名推测", "来源无法直接确认官方、媒体或创始人身份。"


def infer_product_name(title: str) -> str:
    title = normalize_space(title)
    if not title:
        return "未披露"
    known = ["Cursor", "Claude Code", "Lovable", "Bolt.new", "Replit Agent"]
    for name in known:
        if name.lower() in title.lower():
            return f"{name} 相关线索"
    pieces = re.split(r"\s[-|｜:：]\s| - |\|", title)
    candidate = pieces[0].strip()
    candidate = re.sub(r"^(case study|startup case study|built with)\s+", "", candidate, flags=re.I)
    if len(candidate) < 2:
        return "未披露"
    return candidate[:80]


def infer_product_type(text: str) -> str:
    lowered = text.lower()
    if "github" in lowered or "open source" in lowered or "开源" in lowered:
        return "免费开源工具"
    if "api" in lowered:
        return "API服务"
    if "extension" in lowered or "插件" in lowered:
        return "网页插件"
    if "desktop" in lowered or "client" in lowered or "客户端" in lowered:
        return "本地客户端"
    if "saas" in lowered or "subscription" in lowered or "mrr" in lowered or "arr" in lowered:
        return "SaaS订阅工具"
    return "未披露"


def infer_revenue(text: str, env: DotEnv) -> str:
    source_text = normalize_space(text)
    if not source_text:
        return "未披露"

    mode = "未披露"
    lowered = source_text.lower()
    if "mrr" in lowered or "subscription" in lowered or "订阅" in lowered:
        mode = "SaaS月订阅"
    elif "api" in lowered and ("usage" in lowered or "按量" in source_text):
        mode = "API按量收费"
    elif "lifetime" in lowered or "一次性" in source_text or "买断" in source_text:
        mode = "一次性买断"
    elif "ads" in lowered or "广告" in source_text:
        mode = "广告变现"
    elif "enterprise" in lowered or "企业" in source_text:
        mode = "企业定制服务"

    revenue_patterns = [
        r"(?:MRR|mrr|monthly recurring revenue)[^\n。；;]{0,40}?(\$|USD\s*)\s?([0-9][0-9,]*(?:\.\d+)?)([kK])?",
        r"(\$|USD\s*)\s?([0-9][0-9,]*(?:\.\d+)?)([kK])?[^\n。；;]{0,30}?(?:MRR|mrr)",
        r"(?:ARR|arr)[^\n。；;]{0,40}?(\$|USD\s*)\s?([0-9][0-9,]*(?:\.\d+)?)([kK])?",
    ]
    cny_per_usd = env.get_float("CNY_PER_USD", 7.2)
    values = []
    for pattern in revenue_patterns:
        for match in re.finditer(pattern, source_text):
            raw_number = float(match.group(2).replace(",", ""))
            if match.group(3):
                raw_number *= 1000
            cny = int(round(raw_number * cny_per_usd))
            original = f"${int(raw_number) if raw_number.is_integer() else raw_number:g}美元"
            values.append(f"{cny}元人民币（{original}）")
    if values:
        label = "存疑出现多个：" if len(set(values)) > 1 else ""
        return f"{mode}+{label}{'；'.join(dedupe_keep_order(values))}"
    if mode != "未披露":
        return f"{mode}+收入数据未披露"
    return "未披露"


def standard_risks(value: str) -> str:
    if value and value != "未披露" and all(label in value for label in ["合规风险", "平台依赖风险", "市场风险竞争", "长期运营风险"]):
        return value
    return "\n".join(
        [
            "合规风险：未披露",
            "平台依赖风险：未披露",
            "市场风险竞争：未披露",
            "长期运营风险：未披露",
        ]
    )


def standard_opportunities(value: str) -> str:
    if value and value != "未披露" and all(label in value for label in ["横向延伸场景", "纵向功能衔接", "B端企业转型", "细分生态位卡位"]):
        return value
    return "\n".join(
        [
            "横向延伸场景：未披露",
            "纵向功能衔接：未披露",
            "B端企业转型：未披露",
            "细分生态位卡位：未披露",
        ]
    )


def standard_pains(value: str) -> str:
    value = normalize_space(value)
    if not value or value == "未披露":
        return "未披露"
    parts = re.split(r"[；;。]\s*|\n+", value)
    parts = [part.strip(" -①②③1234567890.、") for part in parts if part.strip()]
    if not parts:
        return "未披露"
    labels = ["①", "②", "③"]
    return "\n".join(f"{labels[index]}{part}" for index, part in enumerate(parts[:3]))


def blank_case() -> Dict[str, str]:
    return {field: "未披露" for field in FIELDS}


def build_heuristic_case(result: SearchResult, page_text: str, env: DotEnv) -> Dict[str, str]:
    combined = normalize_space(f"{result.title}。{result.snippet}。{page_text[:3000]}")
    credibility, reason = infer_credibility(result.url)
    product_name = infer_product_name(result.title)
    product_type = infer_product_type(combined)
    revenue = infer_revenue(combined, env)
    purpose = result.snippet or "未披露"
    if purpose != "未披露":
        purpose = f"从公开标题/摘要看，可能帮助用户处理：{purpose[:160]}"

    case = blank_case()
    case.update(
        {
            "收录级别": "今日线索",
            "产品名称": product_name,
            "创始人+编程背景": "未披露",
            "产品类型": product_type,
            "产品用途": purpose,
            "目标人群": infer_target_users(combined),
            "解决痛点": standard_pains("未披露"),
            "收入模式+MRR/ARR": revenue,
            "AI工具": infer_ai_tools(combined),
            "工具-场景匹配分析": "需人工复核公开来源后确认该工具是否实际用于 Vibe Coding 开发流程。",
            "开发时间": "未披露",
            "来源+链接": f"{result.title}：{result.url}",
            "数据可信度": credibility,
            "可信度理由": reason,
            "是否单人/小团队": "未披露",
            "风险点": standard_risks(""),
            "机会点": standard_opportunities(""),
            "复核建议": f"用关键词「{result.keyword}」继续追踪创始人自述、收入截图、产品官网和开发时间。",
        }
    )
    case["缺失字段"] = missing_fields(case)
    return case


def infer_target_users(text: str) -> str:
    lowered = text.lower()
    targets = []
    if "developer" in lowered or "indie hacker" in lowered or "开发者" in text:
        targets.append("独立开发者")
    if "creator" in lowered or "自媒体" in text or "content" in lowered:
        targets.append("自媒体")
    if "student" in lowered or "学生" in text:
        targets.append("学生")
    if "office" in lowered or "职场" in text or "productivity" in lowered:
        targets.append("职场办公")
    if "startup" in lowered or "founder" in lowered or "创业" in text:
        targets.append("创业者")
    return " / ".join(dedupe_keep_order(targets)) if targets else "未披露"


def infer_ai_tools(text: str) -> str:
    found = []
    checks = ["Cursor", "Claude Code", "Claude", "DeepSeek", "GPT", "OpenAI", "Lovable", "Bolt.new", "Replit Agent"]
    lowered = text.lower()
    for name in checks:
        if name.lower() in lowered:
            found.append(name)
    return " / ".join(dedupe_keep_order(found)) if found else "未披露"


def missing_fields(case: Dict[str, str]) -> str:
    missing = [
        field
        for field in FIELDS
        if field not in {"案例编号", "收录级别", "缺失字段"}
        and normalize_space(case.get(field, "")) in {"", "未披露"}
    ]
    return "无" if not missing else "、".join(missing)


def load_usage(path: Path, today: str) -> UsageState:
    if not path.exists():
        return UsageState(date=today, spent_cny=0.0, estimated_tokens=0, calls=0)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return UsageState(date=today, spent_cny=0.0, estimated_tokens=0, calls=0)
    if raw.get("date") != today:
        return UsageState(date=today, spent_cny=0.0, estimated_tokens=0, calls=0)
    return UsageState(
        date=today,
        spent_cny=float(raw.get("spent_cny", 0.0)),
        estimated_tokens=int(raw.get("estimated_tokens", 0)),
        calls=int(raw.get("calls", 0)),
    )


def save_usage(path: Path, usage: UsageState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "date": usage.date,
                "spent_cny": round(usage.spent_cny, 6),
                "estimated_tokens": usage.estimated_tokens,
                "calls": usage.calls,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def estimate_tokens(text: str) -> int:
    # Conservative mixed Chinese/English approximation: 1 token per 2 characters.
    return max(1, int(len(text) / 2) + 200)


def estimate_cost_cny(input_tokens: int, output_tokens: int, env: DotEnv) -> float:
    input_price = env.get_float("LLM_INPUT_CNY_PER_1K_TOKENS", 0.002)
    output_price = env.get_float("LLM_OUTPUT_CNY_PER_1K_TOKENS", 0.008)
    return (input_tokens / 1000 * input_price) + (output_tokens / 1000 * output_price)


def can_spend_llm(prompt: str, usage: UsageState, env: DotEnv) -> Tuple[bool, float, int]:
    budget = env.get_float("DAILY_API_BUDGET_CNY", 0.10)
    max_output_tokens = env.get_int("LLM_MAX_OUTPUT_TOKENS", 1200)
    tokens = estimate_tokens(prompt) + max_output_tokens
    cost = estimate_cost_cny(estimate_tokens(prompt), max_output_tokens, env)
    if usage.spent_cny + cost > budget:
        return False, cost, tokens
    return True, cost, tokens


def llm_extract_cases(
    packed_sources: List[Dict[str, str]],
    env: DotEnv,
    usage: UsageState,
    usage_path: Path,
) -> Tuple[List[Dict[str, str]], List[str]]:
    if not env.get_bool("ENABLE_LLM_ENRICHMENT", False):
        return [], ["LLM 结构化提取未开启，已使用规则模式生成候选和线索。"]
    api_key = env.get("API_KEY", "")
    if not api_key:
        return [], ["ENABLE_LLM_ENRICHMENT=true 但 .env 未设置 API_KEY，已跳过 LLM 调用。"]

    max_sources = max(1, env.get_int("MAX_LLM_SOURCES", 6))
    max_chars = max(1000, env.get_int("MAX_LLM_SOURCE_CHARS", 3500))
    sources = packed_sources[:max_sources]
    for source in sources:
        source["page_text"] = source.get("page_text", "")[:max_chars]

    prompt = build_llm_prompt(sources, env)
    ok, estimated_cost, estimated_tokens = can_spend_llm(prompt, usage, env)
    if not ok:
        return [], [f"LLM 预算不足：本次预计 {estimated_cost:.4f} 元，今日已用 {usage.spent_cny:.4f} 元，预算上限 {env.get_float('DAILY_API_BUDGET_CNY', 0.10):.2f} 元。"]

    api_base = env.get("API_BASE_URL", "https://api.openai.com/v1/chat/completions")
    model = env.get("API_MODEL", "gpt-4o-mini")
    max_output_tokens = env.get_int("LLM_MAX_OUTPUT_TOKENS", 1200)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是保守的数据提取助手，只能依据给定来源输出 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max_output_tokens,
    }
    req = urllib.request.Request(
        api_base,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=max(20, env.get_int("LLM_TIMEOUT_SECONDS", 45))) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return [], [f"LLM 调用失败：{exc}"]

    usage.spent_cny += estimated_cost
    usage.estimated_tokens += estimated_tokens
    usage.calls += 1
    save_usage(usage_path, usage)

    try:
        data = json.loads(body)
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
        return [], [f"LLM 返回解析失败：{exc}"]

    parsed = parse_json_from_text(content)
    if not isinstance(parsed, list):
        return [], ["LLM 未返回 JSON 数组，已跳过结构化结果。"]
    normalized_cases = []
    for item in parsed:
        if isinstance(item, dict):
            normalized_cases.append(normalize_case(item))
    return normalized_cases, [f"LLM 提取完成：估算消耗 {estimated_cost:.4f} 元，今日累计 {usage.spent_cny:.4f} 元。"]


def build_llm_prompt(sources: List[Dict[str, str]], env: DotEnv) -> str:
    scope = env.get("RESEARCH_SCOPE", DEFAULT_RESEARCH_SCOPE)
    return textwrap.dedent(
        f"""
        请根据以下公开网页搜索结果，提取 Vibe Coding / AI Coding 个人或小团队 AI 工具创业案例。

        调研范围：{scope}

        硬性规则：
        1. 只能依据给定来源，不得猜测、不得编造。
        2. 没有公开资料的字段填写“未披露”。
        3. 没有产品名称或没有来源链接的内容不得进入“正式案例”。
        4. 正式案例必须同时具备：产品名称、产品用途、来源+链接、数据可信度。
        5. 不足以正式收录但产品名称和用途明确，设为“候选案例”。
        6. 仅相关但证据不足，设为“今日线索”。
        7. 收入如有 USD MRR/ARR，换算人民币并保留原始货币；多值冲突写“存疑出现多个”。
        8. 风险点必须包含：合规风险、平台依赖风险、市场风险竞争、长期运营风险。
        9. 机会点必须包含：横向延伸场景、纵向功能衔接、B端企业转型、细分生态位卡位。

        严格返回 JSON 数组。每个对象必须包含这些键：
        {json.dumps(FIELDS, ensure_ascii=False)}

        来源材料：
        {json.dumps(sources, ensure_ascii=False, indent=2)}
        """
    ).strip()


def parse_json_from_text(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\[.*\])", text, flags=re.S)
        if match:
            return json.loads(match.group(1))
        raise


def normalize_case(item: Dict[str, str]) -> Dict[str, str]:
    case = blank_case()
    for field in FIELDS:
        value = item.get(field, "未披露")
        if isinstance(value, list):
            value = "\n".join(str(part) for part in value)
        elif isinstance(value, dict):
            value = "\n".join(f"{key}：{val}" for key, val in value.items())
        case[field] = normalize_space(str(value)) if field not in {"风险点", "机会点", "解决痛点"} else str(value).strip()
        if not case[field]:
            case[field] = "未披露"
    if case["收录级别"] not in SECTION_NAMES:
        case["收录级别"] = "今日线索"
    if case["产品类型"] not in PRODUCT_TYPE_OPTIONS:
        case["产品类型"] = "未披露" if case["产品类型"] == "" else case["产品类型"]
    case["解决痛点"] = standard_pains(case["解决痛点"])
    case["风险点"] = standard_risks(case["风险点"])
    case["机会点"] = standard_opportunities(case["机会点"])
    case["缺失字段"] = missing_fields(case)
    return case


def classify_cases(
    heuristic_cases: List[Dict[str, str]],
    llm_cases: List[Dict[str, str]],
) -> Tuple[List[Dict[str, str]], List[str]]:
    by_source: Dict[str, Dict[str, str]] = {}
    skip_reasons: List[str] = []

    for case in heuristic_cases + llm_cases:
        normalized = normalize_case(case)
        source = normalized.get("来源+链接", "")
        name = normalized.get("产品名称", "")
        key = re.sub(r"\W+", "", f"{name}{source}".lower())
        if not key:
            skip_reasons.append("无法确认产品名称或来源链接：已跳过。")
            continue
        existing = by_source.get(key)
        if existing:
            by_source[key] = prefer_richer_case(existing, normalized)
        else:
            by_source[key] = normalized

    cases = []
    for case in by_source.values():
        if case["收录级别"] == "正式案例" and not is_formal_case(case):
            case["收录级别"] = "候选案例" if is_candidate_case(case) else "今日线索"
            case["复核建议"] = append_sentence(case["复核建议"], "正式收录条件不足，已自动降级。")
        elif case["收录级别"] == "候选案例" and not is_candidate_case(case):
            case["收录级别"] = "今日线索"
        cases.append(case)

    if not any(case["收录级别"] in {"候选案例", "今日线索"} for case in cases):
        seed = build_heuristic_case(
            SearchResult(
                title=FALLBACK_SEED_RESULTS[0]["title"],
                url=FALLBACK_SEED_RESULTS[0]["url"],
                snippet=FALLBACK_SEED_RESULTS[0]["snippet"],
                keyword=FALLBACK_SEED_RESULTS[0]["keyword"],
            ),
            "",
            DotEnv(Path(".env")),
        )
        cases.append(seed)

    ordered = sorted(cases, key=lambda item: SECTION_NAMES.index(item["收录级别"]))
    for index, case in enumerate(ordered, start=1):
        case["案例编号"] = str(index)
        case["缺失字段"] = missing_fields(case)
    return ordered, skip_reasons


def is_formal_case(case: Dict[str, str]) -> bool:
    required = ["产品名称", "产品用途", "来源+链接", "数据可信度"]
    if any(case.get(field, "未披露") in {"", "未披露"} for field in required):
        return False
    if "http" not in case.get("来源+链接", ""):
        return False
    if case.get("数据可信度", "").startswith("★ 匿名推测"):
        return False
    return True


def is_candidate_case(case: Dict[str, str]) -> bool:
    return (
        case.get("产品名称", "未披露") not in {"", "未披露"}
        and case.get("产品用途", "未披露") not in {"", "未披露"}
        and "http" in case.get("来源+链接", "")
    )


def prefer_richer_case(left: Dict[str, str], right: Dict[str, str]) -> Dict[str, str]:
    left_score = sum(1 for field in FIELDS if left.get(field, "未披露") not in {"", "未披露"})
    right_score = sum(1 for field in FIELDS if right.get(field, "未披露") not in {"", "未披露"})
    return right if right_score > left_score else left


def append_sentence(value: str, sentence: str) -> str:
    if not value or value == "未披露":
        return sentence
    if sentence in value:
        return value
    return f"{value} {sentence}"


def build_report(
    cases: List[Dict[str, str]],
    skipped: List[str],
    search_errors: List[str],
    llm_notes: List[str],
    env: DotEnv,
) -> str:
    today = dt.date.today().isoformat()
    lines = [
        f"Vibe Coding 独立创业案例每日采集报告",
        f"生成日期：{today}",
        f"调研范围：{env.get('RESEARCH_SCOPE', DEFAULT_RESEARCH_SCOPE)}",
        "",
    ]
    section_title_map = {
        "正式案例": "一、正式收录案例",
        "候选案例": "二、候选案例",
        "今日线索": "三、今日线索池",
    }
    for level in SECTION_NAMES:
        lines.append(section_title_map[level])
        section_cases = [case for case in cases if case["收录级别"] == level]
        if not section_cases:
            lines.append("本部分今日为 0。")
            lines.append("")
            continue
        for case in section_cases:
            lines.extend(format_case(case))
            lines.append("")

    lines.append("四、跳过案例清单")
    if skipped:
        for index, reason in enumerate(skipped[:50], start=1):
            lines.append(f"{index}. {reason}")
    else:
        lines.append("无。")
    lines.append("")

    formal_count = sum(1 for case in cases if case["收录级别"] == "正式案例")
    candidate_count = sum(1 for case in cases if case["收录级别"] == "候选案例")
    clue_count = sum(1 for case in cases if case["收录级别"] == "今日线索")
    lines.append("五、今日搜索总结")
    lines.append(f"- 正式案例：{formal_count} 个；候选案例：{candidate_count} 个；今日线索：{clue_count} 个。")
    if search_errors:
        lines.append("- 搜索/抓取提示：" + "；".join(search_errors[:8]))
    if llm_notes:
        lines.append("- LLM/预算提示：" + "；".join(llm_notes[:8]))
    lines.append("- 运行逻辑总结：先按关键词搜索公开网页，再抓取页面摘要；有 API 且预算允许时进行结构化提取；证据不足自动降级为候选或线索。")
    lines.append("- 结果质量总结：正式案例宁缺毋滥；缺少产品名、用途、链接或可信来源的信息不会进入正式收录。")
    lines.append("")

    keywords = parse_multiline_list(env.get("SEARCH_KEYWORDS", ""), DEFAULT_KEYWORDS)
    next_keywords = suggest_next_keywords(keywords, cases)
    lines.append("六、下一步建议关键词")
    for index, keyword in enumerate(next_keywords, start=1):
        lines.append(f"{index}. {keyword}")
    lines.append("")
    lines.append("Agent Instructions 优化建议")
    lines.append("- 建议继续强调：正式案例允许为 0，但候选案例或今日线索必须至少保留 1 条。")
    lines.append("- 建议补充优先来源白名单，例如 Product Hunt、Indie Hackers、创始人 X/Twitter、产品官网、GitHub README。")
    lines.append("- 建议在后续指令中明确是否允许采集英文播客/Newsletter，以提高创始人自报与 MRR 线索命中率。")
    return "\n".join(lines).rstrip() + "\n"


def format_case(case: Dict[str, str]) -> List[str]:
    lines = []
    for field in FIELDS:
        value = case.get(field, "未披露")
        lines.append(f"{field}：{value}")
    return lines


def suggest_next_keywords(current_keywords: List[str], cases: List[Dict[str, str]]) -> List[str]:
    suggestions = [
        "site:indiehackers.com Cursor AI SaaS MRR",
        "site:x.com \"built with Cursor\" \"MRR\"",
        "site:producthunt.com \"built with Lovable\"",
        "\"Claude Code\" \"indie hacker\" \"revenue\"",
        "\"Bolt.new\" \"launched\" \"startup\"",
        "\"vibe coded\" \"SaaS\" \"MRR\"",
    ]
    tools = []
    for case in cases:
        ai_tools = case.get("AI工具", "")
        if ai_tools and ai_tools != "未披露":
            tools.extend([tool.strip() for tool in ai_tools.split("/")])
    for tool in dedupe_keep_order(tools):
        suggestions.append(f"\"{tool}\" \"solo founder\" \"MRR\"")
    return dedupe_keep_order(suggestions + current_keywords)[:10]


def write_outputs(report: str, output_dir: Path, today: str) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / f"vibe_coding_cases_{today}.txt"
    doc_path = output_dir / f"vibe_coding_cases_{today}.doc"
    txt_path.write_text(report, encoding="utf-8")
    html_doc = "<!doctype html><html><head><meta charset='utf-8'><title>Vibe Coding Cases</title></head><body><pre>"
    html_doc += html.escape(report)
    html_doc += "</pre></body></html>"
    doc_path.write_text(html_doc, encoding="utf-8")
    return txt_path, doc_path


def run(env_path: Path, output_root: Path) -> int:
    env = DotEnv(env_path)
    today = dt.date.today().isoformat()
    usage_path = output_root / ".usage" / f"{today}.json"
    usage = load_usage(usage_path, today)

    results, search_errors = collect_search_results(env)
    max_pages = max(1, env.get_int("MAX_PAGES_TO_FETCH", 12))
    packed_sources: List[Dict[str, str]] = []
    heuristic_cases: List[Dict[str, str]] = []
    skipped: List[str] = []

    for result in results[:max_pages]:
        page_text = fetch_page_text(result.url, env)
        if not is_related(result, page_text):
            skipped.append(f"{result.title}（{result.url}）：与 Vibe Coding / AI Coding / 独立开发 / AI SaaS 相关性不足。")
            continue
        packed_sources.append(
            {
                "title": result.title,
                "url": result.url,
                "snippet": result.snippet,
                "keyword": result.keyword,
                "page_text": page_text,
            }
        )
        heuristic_cases.append(build_heuristic_case(result, page_text, env))

    if not heuristic_cases:
        for item in FALLBACK_SEED_RESULTS[:2]:
            result = SearchResult(title=item["title"], url=item["url"], snippet=item["snippet"], keyword=item["keyword"])
            heuristic_cases.append(build_heuristic_case(result, "", env))
            packed_sources.append(
                {
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet,
                    "keyword": result.keyword,
                    "page_text": "",
                }
            )
        search_errors.append("未找到可用相关网页，已写入公开入口线索，供人工复核。")

    llm_cases, llm_notes = llm_extract_cases(packed_sources, env, usage, usage_path)
    cases, duplicate_skips = classify_cases(heuristic_cases, llm_cases)
    skipped.extend(duplicate_skips)
    report = build_report(cases, skipped, search_errors, llm_notes, env)
    day_dir = output_root / today
    txt_path, doc_path = write_outputs(report, day_dir, today)

    print(f"已生成 TXT：{txt_path}")
    print(f"已生成 DOC：{doc_path}")
    print(f"正式案例：{sum(1 for case in cases if case['收录级别'] == '正式案例')}")
    print(f"候选案例：{sum(1 for case in cases if case['收录级别'] == '候选案例')}")
    print(f"今日线索：{sum(1 for case in cases if case['收录级别'] == '今日线索')}")
    print(f"今日 API 预算估算已用：{usage.spent_cny:.4f} 元")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="采集 Vibe Coding 独立创业案例并生成每日报告。")
    parser.add_argument("--env", default=".env", help="配置文件路径，默认 .env")
    parser.add_argument("--output", default="reports", help="报告输出目录，默认 reports")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run(Path(args.env), Path(args.output))


if __name__ == "__main__":
    sys.exit(main())
