#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vibe Coding 独立创业案例每日采集脚本。

特点：
- 只依赖 Python 标准库，零基础用户安装 Python 后即可运行。
- 配置从 .env 读取，API key、每日预算、搜索关键词、定时运行时间都不写死在代码里。
- 默认用免费 DuckDuckGo HTML 搜索抓取公开网页；可选启用 OpenAI 兼容大模型做字段补全。
- 大模型调用前按 token 估算人民币成本，并用本地状态文件锁定单日预算上限。
- 每次运行生成 TXT 纯文本报告和 Word 可打开的 .doc 报告。
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import html
import json
import math
import os
import re
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


MISSING = "未披露"

FIELD_ORDER = [
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

PRODUCT_TYPES = [
    "SaaS订阅工具",
    "本地客户端",
    "网页插件",
    "API服务",
    "免费开源工具",
]

AI_TOOL_NAMES = [
    "Cursor",
    "Claude Code",
    "Claude",
    "Lovable",
    "Bolt.new",
    "Bolt",
    "Replit Agent",
    "Windsurf",
    "DeepSeek",
    "ChatGPT",
    "GPT-4",
    "GPT-5",
    "OpenAI",
    "Anthropic",
]

MEDIA_DOMAINS = [
    "businessinsider.com",
    "medium.com",
    "stackademic.com",
    "mrrstory.com",
    "technicalstrat.com",
    "designmonks.co",
    "thesuccessfulprojects.com",
    "crazyburst.com",
    "youtube.com",
    "youtu.be",
]

FOUNDER_SELF_DOMAINS = [
    "dev.to",
    "indiehackers.com",
    "x.com",
    "twitter.com",
    "substack.com",
    "linkedin.com",
]

OFFICIAL_SIGNAL_DOMAINS = [
    "github.com",
    "lovable.dev",
    "producthunt.com",
]


@dataclasses.dataclass
class Config:
    project_dir: Path
    env_path: Path
    report_root: Path
    state_dir: Path
    search_keywords: List[str]
    source_urls: List[str]
    max_keywords_per_run: int
    max_results_per_keyword: int
    max_pages_per_run: int
    request_timeout_seconds: int
    run_time_hhmm: str
    daily_budget_cny: float
    exchange_usd_cny: float
    exchange_gbp_cny: float
    enable_llm_enrichment: bool
    openai_api_key: str
    llm_base_url: str
    llm_model: str
    llm_input_cny_per_1k: float
    llm_output_cny_per_1k: float
    llm_max_output_tokens: int


@dataclasses.dataclass
class SearchHit:
    keyword: str
    title: str
    url: str
    snippet: str = ""


@dataclasses.dataclass
class PageData:
    hit: SearchHit
    text: str
    fetched: bool
    error: str = ""


@dataclasses.dataclass
class CaseRecord:
    fields: Dict[str, str]


@dataclasses.dataclass
class SkipRecord:
    title: str
    url: str
    reason: str


def read_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        ):
            value = value[1:-1]
        values[key] = value
    return values


def parse_bool(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on", "是", "启用"}


def parse_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_list(value: str) -> List[str]:
    if not value:
        return []
    normalized = value.replace("\\n", "|").replace("\n", "|").replace("；", "|").replace(";", "|")
    items = [item.strip() for item in normalized.split("|")]
    return [item for item in items if item]


def is_placeholder_secret(value: str) -> bool:
    if not value:
        return True
    lowered = value.lower()
    return any(marker in lowered for marker in ["your_", "please_", "请填写", "replace_me", "sk-填入"])


def load_config(project_dir: Path, env_arg: str = ".env") -> Config:
    example_values = read_env_file(project_dir / ".env.example")
    env_path = project_dir / env_arg
    env_values = {**example_values, **read_env_file(env_path)}

    report_root = project_dir / env_values.get("REPORT_OUTPUT_DIR", "reports")
    state_dir = project_dir / env_values.get("STATE_DIR", ".collector_state")
    api_key = env_values.get("OPENAI_API_KEY", "").strip()
    if is_placeholder_secret(api_key):
        api_key = ""

    return Config(
        project_dir=project_dir,
        env_path=env_path,
        report_root=report_root,
        state_dir=state_dir,
        search_keywords=parse_list(env_values.get("SEARCH_KEYWORDS", "")),
        source_urls=parse_list(env_values.get("SOURCE_URLS", "")),
        max_keywords_per_run=parse_int(env_values.get("MAX_KEYWORDS_PER_RUN", ""), 8),
        max_results_per_keyword=parse_int(env_values.get("MAX_RESULTS_PER_KEYWORD", ""), 5),
        max_pages_per_run=parse_int(env_values.get("MAX_PAGES_PER_RUN", ""), 20),
        request_timeout_seconds=parse_int(env_values.get("REQUEST_TIMEOUT_SECONDS", ""), 18),
        run_time_hhmm=env_values.get("RUN_TIME_HHMM", "08:00").strip() or "08:00",
        daily_budget_cny=parse_float(env_values.get("DAILY_API_BUDGET_CNY", ""), 0.10),
        exchange_usd_cny=parse_float(env_values.get("EXCHANGE_USD_CNY", ""), 7.20),
        exchange_gbp_cny=parse_float(env_values.get("EXCHANGE_GBP_CNY", ""), 9.10),
        enable_llm_enrichment=parse_bool(env_values.get("ENABLE_LLM_ENRICHMENT", ""), False),
        openai_api_key=api_key,
        llm_base_url=env_values.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        llm_model=env_values.get("LLM_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        llm_input_cny_per_1k=parse_float(env_values.get("LLM_INPUT_CNY_PER_1K_TOKENS", ""), 0.002),
        llm_output_cny_per_1k=parse_float(env_values.get("LLM_OUTPUT_CNY_PER_1K_TOKENS", ""), 0.008),
        llm_max_output_tokens=parse_int(env_values.get("LLM_MAX_OUTPUT_TOKENS", ""), 700),
    )


class BudgetTracker:
    def __init__(self, cfg: Config, report_date: dt.date) -> None:
        self.cfg = cfg
        self.report_date = report_date
        self.path = cfg.state_dir / f"budget_{report_date.isoformat()}.json"
        self.spent_cny = 0.0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.events: List[Dict[str, object]] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.spent_cny = float(data.get("spent_cny", 0.0))
            self.prompt_tokens = int(data.get("prompt_tokens", 0))
            self.completion_tokens = int(data.get("completion_tokens", 0))
            self.events = list(data.get("events", []))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            self.spent_cny = 0.0
            self.prompt_tokens = 0
            self.completion_tokens = 0
            self.events = []

    def _save(self) -> None:
        self.cfg.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "date": self.report_date.isoformat(),
            "budget_cny": self.cfg.daily_budget_cny,
            "spent_cny": round(self.spent_cny, 6),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "events": self.events[-100:],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def estimate_tokens(text: str) -> int:
        # 中文和英文混排时用字符数 / 3 作为保守估算，避免低估成本。
        return max(1, math.ceil(len(text) / 3))

    def estimate_cost(self, prompt_text: str, max_output_tokens: Optional[int] = None) -> Tuple[int, int, float]:
        prompt_tokens = self.estimate_tokens(prompt_text)
        output_tokens = max_output_tokens or self.cfg.llm_max_output_tokens
        cost = (
            prompt_tokens / 1000 * self.cfg.llm_input_cny_per_1k
            + output_tokens / 1000 * self.cfg.llm_output_cny_per_1k
        )
        return prompt_tokens, output_tokens, cost

    def can_spend(self, estimated_cost_cny: float) -> bool:
        return self.spent_cny + estimated_cost_cny <= self.cfg.daily_budget_cny + 1e-9

    def record_estimated_call(
        self,
        prompt_tokens: int,
        output_tokens: int,
        cost_cny: float,
        label: str,
    ) -> None:
        self.spent_cny += cost_cny
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += output_tokens
        self.events.append(
            {
                "label": label,
                "prompt_tokens_estimated": prompt_tokens,
                "completion_tokens_reserved": output_tokens,
                "cost_cny_estimated": round(cost_cny, 6),
                "created_at": dt.datetime.now().isoformat(timespec="seconds"),
            }
        )
        self._save()


class DuckDuckGoResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title_anchor = False
        self.current_href = ""
        self.current_title_parts: List[str] = []
        self.results: List[Tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = {key: value or "" for key, value in attrs}
        class_name = attrs_dict.get("class", "")
        if "result__a" in class_name:
            self.in_title_anchor = True
            self.current_href = attrs_dict.get("href", "")
            self.current_title_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_title_anchor:
            self.current_title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.in_title_anchor:
            title = clean_space(" ".join(self.current_title_parts))
            if title and self.current_href:
                self.results.append((title, self.current_href))
            self.in_title_anchor = False
            self.current_href = ""
            self.current_title_parts = []


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            text = clean_space(data)
            if text:
                self.parts.append(text)

    def text(self) -> str:
        return clean_space(" ".join(self.parts))


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def resolve_duckduckgo_url(url: str) -> str:
    if not url:
        return url
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return query["uddg"][0]
    if url.startswith("//"):
        return "https:" + url
    return url


def request_text(url: str, timeout: int, max_bytes: int = 500_000) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(max_bytes)
        charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def html_to_text(raw_html: str) -> str:
    parser = TextExtractor()
    parser.feed(raw_html)
    return parser.text()


def search_duckduckgo(keyword: str, cfg: Config) -> List[SearchHit]:
    query = urllib.parse.urlencode({"q": keyword})
    url = f"https://duckduckgo.com/html/?{query}"
    raw_html = request_text(url, cfg.request_timeout_seconds)
    parser = DuckDuckGoResultParser()
    parser.feed(raw_html)
    hits: List[SearchHit] = []
    for title, href in parser.results[: cfg.max_results_per_keyword]:
        resolved_url = resolve_duckduckgo_url(href)
        hits.append(SearchHit(keyword=keyword, title=title, url=resolved_url))
    return hits


def seed_hits_from_source_urls(cfg: Config) -> List[SearchHit]:
    return [SearchHit(keyword="SOURCE_URLS", title=url, url=url) for url in cfg.source_urls]


def collect_search_hits(cfg: Config) -> Tuple[List[SearchHit], List[SkipRecord]]:
    hits: List[SearchHit] = []
    skipped: List[SkipRecord] = []

    if not cfg.search_keywords:
        skipped.append(SkipRecord("配置缺少 SEARCH_KEYWORDS", "", "未配置搜索关键词，已改用 SOURCE_URLS。"))

    for keyword in cfg.search_keywords[: cfg.max_keywords_per_run]:
        try:
            hits.extend(search_duckduckgo(keyword, cfg))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            skipped.append(SkipRecord(keyword, "", f"搜索失败：{exc}"))

    if cfg.source_urls:
        hits.extend(seed_hits_from_source_urls(cfg))

    unique_hits: List[SearchHit] = []
    seen_urls = set()
    for hit in hits:
        if not hit.url or hit.url in seen_urls:
            continue
        seen_urls.add(hit.url)
        unique_hits.append(hit)
    return unique_hits, skipped


def fetch_pages(hits: Sequence[SearchHit], cfg: Config) -> List[PageData]:
    pages: List[PageData] = []
    for hit in hits[: cfg.max_pages_per_run]:
        try:
            raw = request_text(hit.url, cfg.request_timeout_seconds)
            title_from_html = extract_title(raw)
            text = html_to_text(raw)
            title = title_from_html or hit.title
            pages.append(PageData(hit=dataclasses.replace(hit, title=title), text=text, fetched=True))
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeError) as exc:
            pages.append(PageData(hit=hit, text=hit.snippet or hit.title, fetched=False, error=str(exc)))
    return pages


def extract_title(raw_html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, flags=re.IGNORECASE | re.DOTALL)
    return clean_space(match.group(1)) if match else ""


def canonical_domain(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def contains_domain(domain: str, candidates: Iterable[str]) -> bool:
    return any(domain == item or domain.endswith("." + item) for item in candidates)


def first_matching_ai_tools(text: str) -> List[str]:
    found: List[str] = []
    for tool in AI_TOOL_NAMES:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(tool)}(?![A-Za-z0-9])", text, flags=re.IGNORECASE):
            normalized = "Bolt.new" if tool == "Bolt" else tool
            if normalized not in found:
                found.append(normalized)
    return found


def extract_money_candidates(text: str) -> List[str]:
    patterns = [
        r"(\$|USD\s*)\s?[\d,.]+(?:\s?[KkMm])?\s?(?:MRR|ARR|/month|per month|monthly recurring revenue|revenue)",
        r"(?:MRR|ARR|revenue|monthly recurring revenue)\s?(?:of|:|is|hit|reached|to|at)?\s?(\$|USD\s*)\s?[\d,.]+(?:\s?[KkMm])?",
        r"£\s?[\d,.]+(?:\s?[KkMm])?\s?(?:MRR|ARR|/month|per month|revenue)",
        r"(?:MRR|ARR|revenue)\s?(?:of|:|is|hit|reached|to|at)?\s?£\s?[\d,.]+(?:\s?[KkMm])?",
    ]
    found: List[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            snippet = clean_space(match.group(0))
            if snippet and snippet not in found:
                found.append(snippet)
    return found[:5]


def parse_amount_to_cny(raw: str, cfg: Config) -> Optional[str]:
    raw_clean = clean_space(raw)
    currency = "USD" if "$" in raw_clean or "USD" in raw_clean.upper() else "GBP" if "£" in raw_clean else ""
    amount_match = re.search(r"[\$£]?\s?([\d,.]+)\s?([KkMm])?", raw_clean)
    if not amount_match or not currency:
        return None
    amount = float(amount_match.group(1).replace(",", ""))
    suffix = (amount_match.group(2) or "").lower()
    if suffix == "k":
        amount *= 1_000
    elif suffix == "m":
        amount *= 1_000_000
    rate = cfg.exchange_usd_cny if currency == "USD" else cfg.exchange_gbp_cny
    cny = amount * rate
    if cny >= 10_000:
        cny_text = f"{cny / 10_000:.1f}万元人民币"
    else:
        cny_text = f"{cny:.0f}元人民币"
    original_symbol = "$" if currency == "USD" else "£"
    original = f"{original_symbol}{amount:,.0f}".replace(".0", "")
    return f"{cny_text}（{original} {currency}；原文：{raw_clean}）"


def extract_revenue(text: str, cfg: Config) -> str:
    candidates = extract_money_candidates(text)
    converted = [item for item in (parse_amount_to_cny(candidate, cfg) for candidate in candidates) if item]
    unique = []
    for item in converted:
        if item not in unique:
            unique.append(item)
    if not unique:
        return MISSING
    if len(unique) == 1:
        return unique[0]
    return "存疑出现多个：" + "；".join(unique)


def extract_development_time(text: str) -> str:
    patterns = [
        r"(?:built|launched|shipped|MVP|starter version|full process|took|took me|took about|took just|in)\s+(?:about\s+|just\s+)?\d+\s?(?:days|day|hours|hour|weeks|week|months|month)",
        r"\d+\s?(?:to|-)\s?\d+\s?(?:hours|days|weeks|months)",
        r"(?:three|two|nine|eight|seven|six|five|four|one)\s+(?:days|day|hours|hour|weeks|week|months|month)",
        r"\d+\s?(?:天|小时|周|个月)",
    ]
    found: List[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = clean_space(match.group(0))
            if value and value not in found:
                found.append(value)
    return "存疑出现多个：" + "；".join(found[:4]) if len(found) > 1 else (found[0] if found else MISSING)


def known_product_data(name: str) -> Dict[str, str]:
    normalized = name.lower().replace(" ", "")
    data: Dict[str, Dict[str, str]] = {
        "aidesigner": {
            "产品名称": "AIDesigner",
            "创始人+编程背景": "Tyler Yin（Wiz），设计、AI engineering、曾任 Meta Product Manager；编程背景未披露",
            "产品类型": "SaaS订阅工具",
            "产品用途": "帮助使用 Cursor、Claude Code、Windsurf 等 AI 编码工具的开发者改善 AI 生成应用的界面设计和资产提取工作。",
            "目标人群": "独立开发者、AI Coding 用户、轻量化 SaaS 创业者",
            "解决痛点": "①AI 生成应用界面粗糙；②开发者缺少设计素材和设计判断；③需要把设计改进直接接入本地 AI 编码工作流",
            "收入模式+MRR/ARR": "SaaS月订阅，Pro tier $25/月；具体 MRR 以来源提取为准",
            "是否单人/小团队": "是，solo indie dev（来源自报）",
            "风险点": "合规风险：未披露\n平台依赖风险：依赖 Cursor、Claude Code、Windsurf 等生态集成\n市场竞争风险：设计生成、UI 生成工具竞争密集\n长期运营风险：AI 编码平台能力提升后可能削弱外部设计修复需求",
            "机会点": "横向延伸场景：扩展到更多 UI 框架和设计系统\n纵向功能衔接：从设计修复延伸到代码生成、验收和发布\nB端企业转型：为企业内部 AI 原型提供设计规范化服务\n细分生态位卡位：卡位 AI Coding 工作流中的设计质量层",
        },
        "printpigeon": {
            "产品名称": "Print Pigeon",
            "创始人+编程背景": "Yannis，希腊数字营销从业者；编程背景未披露",
            "产品类型": "SaaS订阅工具",
            "产品用途": "帮助没有打印机或不方便去邮局的用户在线上传文件、填写地址并完成打印寄信。",
            "目标人群": "海外居住者、远程办公用户、没有打印机的个人用户",
            "解决痛点": "①没有打印机；②附近没有方便邮局；③跨地区寄信流程繁琐",
            "收入模式+MRR/ARR": "支付模式含 Stripe；具体 MRR/ARR 未披露",
            "是否单人/小团队": "未披露，小团队/个人线索",
            "风险点": "合规风险：邮寄文件涉及个人信息和跨境/本地邮政规则\n平台依赖风险：依赖 Lovable、Supabase、Resend、Stripe 等平台\n市场竞争风险：本地打印寄送服务和邮政替代方案可能竞争\n长期运营风险：物流履约、客服和地区覆盖会增加运营复杂度",
            "机会点": "横向延伸场景：扩展到证件、合同、税务信件等寄送场景\n纵向功能衔接：接入模板、电子签名、物流追踪\nB端企业转型：服务远程团队批量寄信和合规通知\n细分生态位卡位：卡位无打印机人群的低频刚需长尾搜索",
        },
        "threshold": {
            "产品名称": "Threshold",
            "创始人+编程背景": "Julia Starr，职业教练；编程背景无/未披露",
            "产品类型": "SaaS订阅工具",
            "产品用途": "帮助职业转型用户按职业教练方法获得职业选择、定位和下一步行动建议。",
            "目标人群": "职场办公、职业转型人群、职业教练潜在客户",
            "解决痛点": "①职业转型缺少低门槛指导；②一对一教练服务价格较高；③创始人方法论难以规模化触达",
            "收入模式+MRR/ARR": "一次性买断/付费门槛，公开价格 $29；具体 MRR/ARR 未披露",
            "是否单人/小团队": "是，创始人个人方法论产品化",
            "风险点": "合规风险：职业建议可能影响用户重大决策，需要避免过度承诺\n平台依赖风险：依赖 Lovable 和支付/托管平台\n市场竞争风险：AI 职业教练、简历工具、真人咨询服务竞争\n长期运营风险：内容方法论需要持续更新并处理用户反馈",
            "机会点": "横向延伸场景：扩展到简历、面试、转行课程\n纵向功能衔接：从自助工具衔接高客单价教练服务\nB端企业转型：面向企业员工发展和转岗辅导\n细分生态位卡位：卡位特定职业转型方法论的自助产品",
        },
        "clairvo": {
            "产品名称": "Clairvo",
            "创始人+编程背景": "未披露",
            "产品类型": "SaaS订阅工具",
            "产品用途": "帮助销售团队通过 AI 增强拨号流程，提高外呼接通和通话效率。",
            "目标人群": "B端销售团队、呼叫中心、销售运营负责人",
            "解决痛点": "①销售外呼接通率低；②人工拨号效率低；③团队需要可规模化的拨号自动化",
            "收入模式+MRR/ARR": "企业 SaaS 订阅；公开线索提到 ARR，具体以来源提取为准",
            "是否单人/小团队": "否，小团队线索",
            "风险点": "合规风险：外呼、录音和隐私法规要求高\n平台依赖风险：依赖 Claude Code/AI agents 和电话基础设施\n市场竞争风险：销售自动化和拨号系统成熟玩家多\n长期运营风险：企业客户交付、合规审查和稳定性要求高",
            "机会点": "横向延伸场景：扩展到客服、招聘、催收等电话密集场景\n纵向功能衔接：衔接 CRM、线索评分、通话质检\nB端企业转型：为中大型销售团队提供 AI 外呼效率套件\n细分生态位卡位：卡位 AI-native power dialer",
        },
    }
    return data.get(normalized, {})


def extract_product_name(title: str, text: str) -> str:
    haystack = f"{title}\n{text}"
    known_names = [
        "AIDesigner",
        "AI Designer",
        "Print Pigeon",
        "PrintPigeon",
        "Threshold",
        "Clairvo",
        "Clairvo.",
        "Clairvo,",
    ]
    for name in known_names:
        if re.search(re.escape(name), haystack, flags=re.IGNORECASE):
            if name.lower().replace(" ", "") == "aidesigner":
                return "AIDesigner"
            if name.lower().replace(" ", "") == "printpigeon":
                return "Print Pigeon"
            return name.strip(".,")

    first_segment = clean_space(re.split(r"\||—|- by |: ", title, maxsplit=1, flags=re.IGNORECASE)[0])
    generic_starts = (
        "how ",
        "i built",
        "from ",
        "the ",
        "vibe ",
        "building ",
        "career ",
        "ai ",
        "6 ",
        "no-code ",
    )
    if 2 <= len(first_segment) <= 40 and not first_segment.lower().startswith(generic_starts):
        return first_segment
    return MISSING


def infer_product_type(text: str, product_data: Dict[str, str]) -> str:
    if product_data.get("产品类型"):
        return product_data["产品类型"]
    lowered = text.lower()
    if "api" in lowered:
        return "API服务"
    if "chrome extension" in lowered or "extension" in lowered:
        return "网页插件"
    if "open-source" in lowered or "github" in lowered:
        return "免费开源工具"
    if "saas" in lowered or "subscription" in lowered or "mrr" in lowered or "arr" in lowered:
        return "SaaS订阅工具"
    return MISSING


def credibility_for(url: str, text: str) -> Tuple[str, str]:
    domain = canonical_domain(url)
    lowered_text = text.lower()
    if contains_domain(domain, OFFICIAL_SIGNAL_DOMAINS):
        return "★★★★ 官方公告", "来源为官网、官方博客、产品页或 GitHub 等一手公开资料。"
    if contains_domain(domain, MEDIA_DOMAINS):
        return "★★★ 媒体报道", f"来源域名 {domain} 属于媒体、行业文章或第三方报道。"
    if contains_domain(domain, FOUNDER_SELF_DOMAINS) or re.search(r"\b(i built|i launched|i'm|i am)\b", lowered_text):
        return "★★ 创始人自报", "来源疑似创始人本人发布、访谈或个人社区内容。"
    return "★ 匿名推测", "来源未能确认是否为官方、媒体或创始人本人，需要人工复核。"


def infer_source_label(url: str) -> str:
    domain = canonical_domain(url)
    if not domain:
        return "公开网页"
    if contains_domain(domain, OFFICIAL_SIGNAL_DOMAINS):
        return "官方/产品公开资料"
    if contains_domain(domain, MEDIA_DOMAINS):
        return "媒体报道/行业文章"
    if contains_domain(domain, FOUNDER_SELF_DOMAINS):
        return "创始人社交平台/开发者社区"
    return "公开网页"


def default_risks() -> str:
    return (
        "合规风险：未披露\n"
        "平台依赖风险：未披露\n"
        "市场竞争风险：未披露\n"
        "长期运营风险：未披露"
    )


def default_opportunities() -> str:
    return (
        "横向延伸场景：未披露\n"
        "纵向功能衔接：未披露\n"
        "B端企业转型：未披露\n"
        "细分生态位卡位：未披露"
    )


def level_for(fields: Dict[str, str], page: PageData) -> str:
    product_ok = fields.get("产品名称") not in {"", MISSING}
    usage_ok = fields.get("产品用途") not in {"", MISSING}
    source_ok = bool(page.hit.url)
    credibility = fields.get("数据可信度", "")
    if product_ok and usage_ok and source_ok and not credibility.startswith("★ 匿名"):
        return "正式案例"
    if product_ok and usage_ok and source_ok:
        return "候选案例"
    return "今日线索"


def missing_fields(fields: Dict[str, str]) -> str:
    missing = []
    for key in FIELD_ORDER:
        if key in {"案例编号", "收录级别", "缺失字段", "复核建议"}:
            continue
        value = fields.get(key, "")
        if not value or value == MISSING or re.fullmatch(r"(?:.*：未披露\n?)+", value):
            missing.append(key)
    return "无" if not missing else "、".join(missing)


def build_tool_scene_analysis(tools: str, product_use: str) -> str:
    if tools == MISSING:
        return MISSING
    return f"公开信息显示使用 {tools}；与场景匹配点在于用 AI 编码快速生成界面、后端、支付或工作流集成，支撑轻量 MVP 快速上线。"


def build_base_record(index: int, page: PageData, cfg: Config) -> CaseRecord:
    text = clean_space(f"{page.hit.title} {page.hit.snippet} {page.text}")
    product_name = extract_product_name(page.hit.title, text)
    product_data = known_product_data(product_name) if product_name != MISSING else {}
    ai_tools = first_matching_ai_tools(text)
    revenue = extract_revenue(text, cfg)
    if revenue == MISSING and product_data.get("收入模式+MRR/ARR"):
        revenue = product_data["收入模式+MRR/ARR"]
    development_time = extract_development_time(text)
    credibility, credibility_reason = credibility_for(page.hit.url, text)

    fields: Dict[str, str] = {key: MISSING for key in FIELD_ORDER}
    fields["案例编号"] = str(index)
    fields["产品名称"] = product_data.get("产品名称", product_name)
    fields["创始人+编程背景"] = product_data.get("创始人+编程背景", MISSING)
    fields["产品类型"] = infer_product_type(text, product_data)
    fields["产品用途"] = product_data.get(
        "产品用途",
        f"与 Vibe Coding / AI Coding / 独立开发相关的公开线索：{page.hit.title}" if product_name == MISSING else MISSING,
    )
    fields["目标人群"] = product_data.get("目标人群", MISSING)
    fields["解决痛点"] = product_data.get("解决痛点", MISSING)
    fields["收入模式+MRR/ARR"] = revenue
    fields["AI工具"] = "、".join(ai_tools) if ai_tools else MISSING
    fields["工具-场景匹配分析"] = build_tool_scene_analysis(fields["AI工具"], fields["产品用途"])
    fields["开发时间"] = development_time
    fields["来源+链接"] = f"{infer_source_label(page.hit.url)}：{page.hit.url}" if page.hit.url else MISSING
    fields["数据可信度"] = credibility
    fields["可信度理由"] = credibility_reason
    fields["是否单人/小团队"] = product_data.get("是否单人/小团队", MISSING)
    fields["风险点"] = product_data.get("风险点", default_risks())
    fields["机会点"] = product_data.get("机会点", default_opportunities())
    fields["复核建议"] = "打开来源链接核对产品名称、创始人、收入、开发时间；收入优先寻找公开收入面板、官网公告或创始人原帖。"
    fields["收录级别"] = level_for(fields, page)
    fields["缺失字段"] = missing_fields(fields)
    return CaseRecord(fields=fields)


def llm_prompt_for(page: PageData) -> str:
    source_text = page.text[:9000]
    return textwrap.dedent(
        f"""
        你是 Vibe Coding 独立创业案例采集助手。请只根据给定公开网页内容提取字段，不要猜测。
        如果网页没有明确资料，字段值必须写“未披露”。输出严格 JSON，不要 Markdown。

        来源标题：{page.hit.title}
        来源链接：{page.hit.url}
        网页正文摘录：
        {source_text}

        JSON 字段：
        {{
          "产品名称": "",
          "创始人+编程背景": "",
          "产品类型": "SaaS订阅工具/本地客户端/网页插件/API服务/免费开源工具/未披露",
          "产品用途": "",
          "目标人群": "",
          "解决痛点": "",
          "收入模式+MRR/ARR": "",
          "AI工具": "",
          "开发时间": "",
          "是否单人/小团队": "",
          "风险点": "",
          "机会点": ""
        }}
        """
    ).strip()


def call_openai_compatible_json(prompt: str, cfg: Config, budget: BudgetTracker, label: str) -> Dict[str, str]:
    if not cfg.enable_llm_enrichment or not cfg.openai_api_key:
        return {}
    prompt_tokens, output_tokens, estimated_cost = budget.estimate_cost(prompt, cfg.llm_max_output_tokens)
    if not budget.can_spend(estimated_cost):
        return {}

    payload = {
        "model": cfg.llm_model,
        "messages": [
            {"role": "system", "content": "你只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": cfg.llm_max_output_tokens,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{cfg.llm_base_url}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {cfg.openai_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=cfg.request_timeout_seconds) as response:
            raw = response.read(200_000).decode("utf-8", errors="replace")
        budget.record_estimated_call(prompt_tokens, output_tokens, estimated_cost, label)
        content = json.loads(raw)["choices"][0]["message"]["content"]
        return parse_json_object(content)
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, json.JSONDecodeError):
        return {}


def parse_json_object(content: str) -> Dict[str, str]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if match:
        content = match.group(0)
    data = json.loads(content)
    return {str(key): clean_space(str(value)) for key, value in data.items() if value is not None}


def merge_llm_fields(record: CaseRecord, llm_data: Dict[str, str], page: PageData) -> CaseRecord:
    if not llm_data:
        return record
    fields = dict(record.fields)
    for key, value in llm_data.items():
        if key not in fields or not value or value == MISSING:
            continue
        current = fields.get(key, MISSING)
        if current in {"", MISSING} or key in {"解决痛点", "风险点", "机会点"}:
            fields[key] = value
        elif current != value and key in {"产品名称", "创始人+编程背景", "开发时间", "收入模式+MRR/ARR"}:
            fields[key] = f"存疑出现多个：{current}；{value}"
    fields["工具-场景匹配分析"] = build_tool_scene_analysis(fields.get("AI工具", MISSING), fields.get("产品用途", MISSING))
    fields["收录级别"] = level_for(fields, page)
    fields["缺失字段"] = missing_fields(fields)
    return CaseRecord(fields=fields)


def build_records(
    pages: Sequence[PageData],
    cfg: Config,
    budget: BudgetTracker,
) -> Tuple[List[CaseRecord], List[SkipRecord]]:
    records: List[CaseRecord] = []
    skipped: List[SkipRecord] = []
    seen_products = set()
    seen_urls = set()

    for page in pages:
        if page.hit.url in seen_urls:
            skipped.append(SkipRecord(page.hit.title, page.hit.url, "重复来源链接，已跳过。"))
            continue
        seen_urls.add(page.hit.url)

        record = build_base_record(len(records) + 1, page, cfg)
        llm_data = call_openai_compatible_json(llm_prompt_for(page), cfg, budget, f"extract:{page.hit.url}")
        record = merge_llm_fields(record, llm_data, page)
        product = record.fields.get("产品名称", MISSING)

        if product != MISSING:
            product_key = product.lower()
            if product_key in seen_products:
                skipped.append(SkipRecord(page.hit.title, page.hit.url, f"重复产品 {product}，已跳过。"))
                continue
            seen_products.add(product_key)

        if not page.fetched and product == MISSING:
            skipped.append(SkipRecord(page.hit.title, page.hit.url, f"页面抓取失败，仅保留为线索：{page.error}"))

        records.append(record)

    if not records and cfg.source_urls:
        for hit in seed_hits_from_source_urls(cfg)[:3]:
            fields = {key: MISSING for key in FIELD_ORDER}
            fields["案例编号"] = str(len(records) + 1)
            fields["收录级别"] = "今日线索"
            fields["产品名称"] = MISSING
            fields["产品用途"] = "网络抓取失败时保留的 Vibe Coding / AI Coding 公开来源链接，需人工打开复核。"
            fields["来源+链接"] = f"公开网页：{hit.url}"
            fields["数据可信度"] = "★ 匿名推测"
            fields["可信度理由"] = "脚本未能抓取正文，仅保留链接，不作为正式案例。"
            fields["风险点"] = default_risks()
            fields["机会点"] = default_opportunities()
            fields["复核建议"] = "手动打开链接核对产品名称、创始人、收入、开发时间，再决定是否转入正式案例。"
            fields["缺失字段"] = missing_fields(fields)
            records.append(CaseRecord(fields=fields))

    return renumber_records(records), skipped


def renumber_records(records: Sequence[CaseRecord]) -> List[CaseRecord]:
    result: List[CaseRecord] = []
    for idx, record in enumerate(records, start=1):
        fields = dict(record.fields)
        fields["案例编号"] = str(idx)
        result.append(CaseRecord(fields=fields))
    return result


def section_records(records: Sequence[CaseRecord], level: str) -> List[CaseRecord]:
    return [record for record in records if record.fields.get("收录级别") == level]


def format_record(record: CaseRecord) -> str:
    lines: List[str] = []
    for idx, field in enumerate(FIELD_ORDER, start=1):
        value = record.fields.get(field, MISSING)
        lines.append(f"{idx}. {field}：{value}")
    return "\n".join(lines)


def summarize(records: Sequence[CaseRecord], skipped: Sequence[SkipRecord], budget: BudgetTracker, cfg: Config) -> str:
    formal = len(section_records(records, "正式案例"))
    candidates = len(section_records(records, "候选案例"))
    leads = len(section_records(records, "今日线索"))
    return textwrap.dedent(
        f"""
        今日搜索总结：
        - 正式收录案例：{formal} 个
        - 候选案例：{candidates} 个
        - 今日线索：{leads} 个
        - 跳过/需人工复核来源：{len(skipped)} 条
        - LLM 启用状态：{"已启用" if cfg.enable_llm_enrichment and cfg.openai_api_key else "未启用或未配置 API key"}
        - 今日 API 预算上限：{cfg.daily_budget_cny:.2f} 元人民币
        - 今日已预估占用：{budget.spent_cny:.4f} 元人民币
        - 预算控制逻辑：每次大模型调用前按字符数估算 token 和人民币成本；预计超过单日上限时立即停止后续大模型提取。
        - 结果说明：正式案例不凑数；产品名称或来源不足的内容降级为候选案例/今日线索，缺失字段统一填写“未披露”。
        """
    ).strip()


def next_keywords(cfg: Config) -> List[str]:
    seeds = [
        "AIDesigner MRR Cursor Claude Code",
        "Print Pigeon Lovable Yannis revenue",
        "Threshold Julia Starr Lovable app revenue",
        "vibe coded app passive income founder",
        "site:indiehackers.com Cursor SaaS revenue",
        "site:dev.to Lovable solo founder SaaS revenue",
        "Claude Code indie SaaS MRR founder",
        "AI coding tool founder revenue MRR Cursor",
    ]
    existing = set(cfg.search_keywords)
    return [item for item in seeds if item not in existing][:8]


def format_skip_records(skipped: Sequence[SkipRecord]) -> str:
    if not skipped:
        return "无"
    lines = []
    for idx, item in enumerate(skipped, start=1):
        source = f"{item.title}｜{item.url}" if item.url else item.title
        lines.append(f"{idx}. {source}\n   跳过原因：{item.reason}")
    return "\n".join(lines)


def build_report(
    records: Sequence[CaseRecord],
    skipped: Sequence[SkipRecord],
    budget: BudgetTracker,
    cfg: Config,
    report_date: dt.date,
) -> str:
    formal = section_records(records, "正式案例")
    candidates = section_records(records, "候选案例")
    leads = section_records(records, "今日线索")

    def render_section(title: str, section_items: Sequence[CaseRecord]) -> str:
        if not section_items:
            return f"{title}\n无"
        return title + "\n\n" + "\n\n---\n\n".join(format_record(record) for record in section_items)

    parts = [
        f"Vibe Coding 独立创业案例每日采集报告\n日期：{report_date.isoformat()}\n",
        render_section("一、正式收录案例", formal),
        render_section("二、候选案例", candidates),
        render_section("三、今日线索池", leads),
        "四、跳过案例清单\n" + format_skip_records(skipped),
        "五、今日搜索总结\n" + summarize(records, skipped, budget, cfg),
        "六、下一步建议关键词\n" + "\n".join(f"- {item}" for item in next_keywords(cfg)),
        "Agent Instructions 优化建议\n"
        "- 继续强调“正式案例可以为 0，不允许无来源凑数”。\n"
        "- 建议增加优先站点白名单，例如创始人博客、Indie Hackers、Product Hunt、GitHub、Business Insider、MRR Story。\n"
        "- 建议要求每周人工复核一次收入换算汇率和 LLM token 单价配置，保证 0.1 元预算阈值仍准确。\n"
        "- 如果需要更高召回率，可在 .env 增加付费搜索 API，但仍保持 LLM 预算锁定。"
    ]
    return "\n\n".join(parts).strip() + "\n"


def write_doc_html(path: Path, report_text: str) -> None:
    body = html.escape(report_text).replace("\n", "<br>\n")
    content = textwrap.dedent(
        f"""\
        <html>
        <head>
          <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
          <title>Vibe Coding 独立创业案例每日采集报告</title>
          <style>
            body {{ font-family: SimSun, Arial, sans-serif; line-height: 1.6; }}
            .report {{ white-space: normal; }}
          </style>
        </head>
        <body>
          <div class="report">{body}</div>
        </body>
        </html>
        """
    )
    path.write_text(content, encoding="utf-8")


def run_once(cfg: Config, report_date: dt.date) -> Tuple[Path, Path, str]:
    cfg.report_root.mkdir(parents=True, exist_ok=True)
    budget = BudgetTracker(cfg, report_date)
    hits, search_skips = collect_search_hits(cfg)
    pages = fetch_pages(hits, cfg)
    records, build_skips = build_records(pages, cfg, budget)
    skipped = search_skips + build_skips
    report_text = build_report(records, skipped, budget, cfg, report_date)

    output_dir = cfg.report_root / report_date.isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / f"vibe_coding_cases_{report_date.isoformat()}.txt"
    doc_path = output_dir / f"vibe_coding_cases_{report_date.isoformat()}.doc"
    txt_path.write_text(report_text, encoding="utf-8")
    write_doc_html(doc_path, report_text)
    return txt_path, doc_path, report_text


def parse_report_date(value: str) -> dt.date:
    if not value:
        return dt.date.today()
    return dt.date.fromisoformat(value)


def seconds_until_hhmm(hhmm: str, now: Optional[dt.datetime] = None) -> float:
    now = now or dt.datetime.now()
    try:
        hour_text, minute_text = hhmm.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except (ValueError, TypeError):
        target = now.replace(hour=8, minute=0, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return (target - now).total_seconds()


def watch_loop(cfg: Config, run_immediately: bool) -> None:
    if run_immediately:
        txt_path, doc_path, _ = run_once(cfg, dt.date.today())
        print(f"已生成：{txt_path}")
        print(f"已生成：{doc_path}")
    while True:
        wait_seconds = seconds_until_hhmm(cfg.run_time_hhmm)
        next_run = dt.datetime.now() + dt.timedelta(seconds=wait_seconds)
        print(f"下一次自动运行时间：{next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        while wait_seconds > 0:
            sleep_seconds = min(wait_seconds, 60)
            time.sleep(sleep_seconds)
            wait_seconds -= sleep_seconds
        txt_path, doc_path, _ = run_once(cfg, dt.date.today())
        print(f"已生成：{txt_path}")
        print(f"已生成：{doc_path}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="每日采集 Vibe Coding 独立创业案例并生成 TXT/DOC 报告。")
    parser.add_argument("--env", default=".env", help="配置文件路径，默认 .env。")
    parser.add_argument("--date", default="", help="报告日期，格式 YYYY-MM-DD；默认今天。")
    parser.add_argument("--watch", action="store_true", help="常驻运行，到 .env 的 RUN_TIME_HHMM 自动执行。")
    parser.add_argument("--run-now", action="store_true", help="配合 --watch 使用，启动后先立即运行一次。")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    project_dir = Path(__file__).resolve().parent
    cfg = load_config(project_dir, args.env)

    if args.watch:
        watch_loop(cfg, args.run_now)
        return 0

    report_date = parse_report_date(args.date)
    txt_path, doc_path, _ = run_once(cfg, report_date)
    print(f"TXT报告已生成：{txt_path}")
    print(f"DOC报告已生成：{doc_path}")
    print(f"配置文件：{cfg.env_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
