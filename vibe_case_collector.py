#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collect public Vibe Coding solo/small-team AI tool startup cases.

The script intentionally uses only Python's standard library so beginners can
run it after installing Python. Configuration lives in .env, and the LLM budget
gate reserves the worst-case token spend before every API request.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib import error, parse, request


UNDISCLOSED = "未披露"

FIELD_SPECS: List[Tuple[str, str]] = [
    ("案例编号", "案例编号"),
    ("产品名称", "产品名称"),
    ("创始人姓名+背景", "创始人姓名+背景"),
    ("编程背景", "编程背景"),
    ("产品类型", "产品类型"),
    ("产品用途", "产品用途"),
    ("目标人群", "目标人群"),
    ("解决痛点", "解决痛点"),
    ("收入模式", "收入模式"),
    ("月收入", "月收入"),
    ("使用的AI工具", "使用的AI工具"),
    ("开发时间", "开发时间"),
    ("数据来源+链接", "数据来源+链接"),
    ("数据可信度", "数据可信度（明星标准，仅限4档任选）"),
    ("是否单人项目", "是否单人项目"),
    ("风险点", "风险点（四类各1条，缺一不可）"),
    ("机会点", "机会点（四类各1条，缺一不可）"),
]

FIELD_NAMES = [field_name for field_name, _ in FIELD_SPECS]
PRODUCT_TYPES = {"SaaS订阅工具", "本地客户端", "网页插件", "API服务", "免费开源工具", UNDISCLOSED}
PROGRAMMING_BACKGROUNDS = {"有", "无", "自学", UNDISCLOSED}
REVENUE_MODE_OPTIONS = {"SaaS月订阅", "一次性买断", "API按量收费", "广告变现", "企业定制服务", UNDISCLOSED}
CREDIBILITY_OPTIONS = {"★推测", "★★创始人自报", "★★★媒体报道", "★★★★官方公告", UNDISCLOSED}
RISK_KEYS = ["合规风险", "平台依赖风险", "市场风险竞争", "长期运营风险"]
OPPORTUNITY_KEYS = ["横向延伸场景", "纵向功能衔接", "B端企业转型", "细分生态位卡位"]
PAIN_MARKERS = ["①", "②", "③"]
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


@dataclass
class SourcePage:
    keyword: str
    title: str
    url: str
    text: str


@dataclass
class BudgetReservation:
    input_tokens: int
    output_tokens: int
    cny: float


@dataclass
class BudgetLedger:
    max_cny: float
    input_price_cny_per_1m: float
    output_price_cny_per_1m: float
    input_tokens: int = 0
    output_tokens: int = 0
    used_cny: float = 0.0
    stopped_by_budget: bool = False

    @staticmethod
    def estimate_tokens(text: str) -> int:
        # CJK-heavy prompts can approach one token per character; this is a
        # deliberately conservative estimate to avoid crossing the budget cap.
        return max(1, len(text))

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_price_cny_per_1m / 1_000_000
            + output_tokens * self.output_price_cny_per_1m / 1_000_000
        )

    def reserve(self, prompt: str, max_output_tokens: int) -> Optional[BudgetReservation]:
        input_tokens = self.estimate_tokens(prompt)
        reservation = BudgetReservation(
            input_tokens=input_tokens,
            output_tokens=max_output_tokens,
            cny=self.cost(input_tokens, max_output_tokens),
        )
        if self.used_cny + reservation.cny > self.max_cny:
            self.stopped_by_budget = True
            return None
        self.input_tokens += input_tokens
        self.output_tokens += max_output_tokens
        self.used_cny += reservation.cny
        return reservation

    def release(self, reservation: BudgetReservation) -> None:
        self.input_tokens = max(0, self.input_tokens - reservation.input_tokens)
        self.output_tokens = max(0, self.output_tokens - reservation.output_tokens)
        self.used_cny = max(0.0, self.used_cny - reservation.cny)

    def replace_with_actual(
        self,
        reservation: BudgetReservation,
        actual_input_tokens: Optional[int],
        actual_output_tokens: Optional[int],
    ) -> None:
        if actual_input_tokens is None or actual_output_tokens is None:
            return
        actual_cny = self.cost(actual_input_tokens, actual_output_tokens)
        self.input_tokens = self.input_tokens - reservation.input_tokens + actual_input_tokens
        self.output_tokens = self.output_tokens - reservation.output_tokens + actual_output_tokens
        self.used_cny = max(0.0, self.used_cny - reservation.cny + actual_cny)


@dataclass
class CollectorConfig:
    api_key: str
    api_url: str
    model: str
    llm_temperature: float
    keywords: List[str]
    max_daily_api_budget_cny: float
    input_price_cny_per_1m: float
    output_price_cny_per_1m: float
    llm_max_output_tokens: int
    search_max_results_per_keyword: int
    max_pages_to_fetch: int
    max_cases_per_day: int
    page_text_max_chars: int
    request_timeout_seconds: int
    output_dir: Path
    schedule_time: str

    @classmethod
    def from_env(cls, output_dir_override: Optional[str] = None) -> "CollectorConfig":
        keywords = split_list(os.getenv("SEARCH_KEYWORDS", ""))
        if not keywords:
            raise ValueError("请在 .env 中配置 SEARCH_KEYWORDS，多个关键词用英文分号 ; 分隔。")

        output_dir = Path(output_dir_override or os.getenv("OUTPUT_DIR", "reports")).expanduser()
        return cls(
            api_key=os.getenv("LLM_API_KEY", "").strip(),
            api_url=os.getenv("OPENAI_COMPATIBLE_API_URL", "https://api.moonshot.cn/v1/chat/completions").strip(),
            model=os.getenv("LLM_MODEL", "kimi-k2.6").strip(),
            llm_temperature=get_float_env("LLM_TEMPERATURE", 0.0),
            keywords=keywords,
            max_daily_api_budget_cny=get_float_env("MAX_DAILY_API_BUDGET_CNY", 0.1),
            input_price_cny_per_1m=get_float_env("INPUT_TOKEN_PRICE_CNY_PER_1M", 2.0),
            output_price_cny_per_1m=get_float_env("OUTPUT_TOKEN_PRICE_CNY_PER_1M", 8.0),
            llm_max_output_tokens=get_int_env("LLM_MAX_OUTPUT_TOKENS", 2500),
            search_max_results_per_keyword=get_int_env("SEARCH_MAX_RESULTS_PER_KEYWORD", 5),
            max_pages_to_fetch=get_int_env("MAX_PAGES_TO_FETCH", 12),
            max_cases_per_day=get_int_env("MAX_CASES_PER_DAY", 8),
            page_text_max_chars=get_int_env("PAGE_TEXT_MAX_CHARS", 6000),
            request_timeout_seconds=get_int_env("REQUEST_TIMEOUT_SECONDS", 20),
            output_dir=output_dir,
            schedule_time=os.getenv("SCHEDULE_TIME", "02:00").strip(),
        )

    def budget_ledger(self) -> BudgetLedger:
        return BudgetLedger(
            max_cny=self.max_daily_api_budget_cny,
            input_price_cny_per_1m=self.input_price_cny_per_1m,
            output_price_cny_per_1m=self.output_price_cny_per_1m,
        )


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: List[Tuple[str, str]] = []
        self._href: Optional[str] = None
        self._text_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if href:
            self._href = href
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            title = normalize_space(" ".join(self._text_parts))
            self.links.append((title, self._href))
            self._href = None
            self._text_parts = []


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag.lower() in {"script", "style", "svg", "noscript"}:
            self._skip_depth += 1
        if tag.lower() in {"p", "br", "div", "li", "h1", "h2", "h3", "article", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "svg", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "article", "section"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            cleaned = normalize_space(data)
            if cleaned:
                self.parts.append(cleaned)

    def text(self) -> str:
        return normalize_multiline(" ".join(self.parts))


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def split_list(raw_value: str) -> List[str]:
    value = raw_value.strip()
    if not value:
        return []
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
    return [item.strip() for item in re.split(r"[;\n|]+", value) if item.strip()]


def get_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def get_float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_multiline(value: str) -> str:
    lines = [normalize_space(line) for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def http_get(url: str, timeout: int, max_bytes: int = 1_500_000) -> str:
    req = request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with request.urlopen(req, timeout=timeout) as response:
        raw = response.read(max_bytes)
        content_type = response.headers.get("Content-Type", "")
    charset_match = re.search(r"charset=([\w.-]+)", content_type, flags=re.I)
    charset = charset_match.group(1) if charset_match else "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def normalize_search_url(href: str) -> Optional[str]:
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("/"):
        parsed = parse.urlparse(href)
        query = parse.parse_qs(parsed.query)
        if "uddg" in query:
            href = query["uddg"][0]
        else:
            return None
    parsed = parse.urlparse(href)
    if parsed.netloc.lower().endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        query = parse.parse_qs(parsed.query)
        if "uddg" not in query:
            return None
        href = query["uddg"][0]
        parsed = parse.urlparse(href)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    host = parsed.netloc.lower()
    blocked_hosts = ("duckduckgo.com", "google.com", "bing.com", "baidu.com")
    if any(host == blocked or host.endswith("." + blocked) for blocked in blocked_hosts):
        return None
    return href


def search_duckduckgo(keyword: str, limit: int, timeout: int) -> List[Tuple[str, str]]:
    query = parse.urlencode({"q": keyword})
    html_text = http_get(f"https://duckduckgo.com/html/?{query}", timeout=timeout)
    parser = LinkExtractor()
    parser.feed(html_text)
    results: List[Tuple[str, str]] = []
    seen = set()
    for title, href in parser.links:
        url = normalize_search_url(href)
        if not url or url in seen:
            continue
        seen.add(url)
        results.append((title or url, url))
        if len(results) >= limit:
            break
    return results


def fetch_page_text(url: str, timeout: int, max_chars: int) -> str:
    html_text = http_get(url, timeout=timeout)
    extractor = TextExtractor()
    extractor.feed(html_text)
    text = extractor.text()
    return text[:max_chars]


def collect_source_pages(config: CollectorConfig) -> List[SourcePage]:
    pages: List[SourcePage] = []
    seen_urls = set()
    for keyword in config.keywords:
        if len(pages) >= config.max_pages_to_fetch:
            break
        try:
            results = search_duckduckgo(
                keyword=keyword,
                limit=config.search_max_results_per_keyword,
                timeout=config.request_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to console for beginners
            print(f"[搜索跳过] {keyword}: {exc}")
            continue

        for title, url in results:
            if len(pages) >= config.max_pages_to_fetch:
                break
            if url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                text = fetch_page_text(
                    url=url,
                    timeout=config.request_timeout_seconds,
                    max_chars=config.page_text_max_chars,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[页面跳过] {url}: {exc}")
                continue
            if len(text) < 200:
                continue
            pages.append(SourcePage(keyword=keyword, title=title, url=url, text=text))
            print(f"[已抓取] {len(pages)}/{config.max_pages_to_fetch} {title[:60]} -> {url}")
    return pages


def build_llm_prompt(pages: Sequence[SourcePage], max_cases: int) -> str:
    field_lines = "\n".join(f"- {field_name}" for field_name in FIELD_NAMES)
    context_blocks = []
    for index, page in enumerate(pages, 1):
        context_blocks.append(
            "\n".join(
                [
                    f"资料{index}",
                    f"关键词：{page.keyword}",
                    f"标题：{page.title}",
                    f"链接：{page.url}",
                    "正文摘录：",
                    page.text,
                ]
            )
        )
    contexts = "\n\n---\n\n".join(context_blocks)
    return f"""
你是严谨的公开资料采集助手。请只从下列网页摘录中提取“Vibe Coding 个人/小团队 AI 工具创业真实落地案例”。

硬规则：
1. 不要虚构案例；没有公开链接和产品名的项目不要输出。
2. 纯概念、教程文章、没有真实产品落地信息的内容不要输出。
3. 任意字段无公开资料，必须填“{UNDISCLOSED}”。
4. 同一字段出现多个冲突值，写“存疑出现多个：值1；值2；...”。
5. “月收入”统一换算为人民币，同时保留原始货币；没有收入数据填“{UNDISCLOSED}”。
6. “编程背景”只能是：有、无、自学、{UNDISCLOSED}。
7. “产品类型”只能是：SaaS订阅工具、本地客户端、网页插件、API服务、免费开源工具、{UNDISCLOSED}。
8. “解决痛点”最多3条，必须使用①②③序号。
9. “风险点”必须包含：合规风险、平台依赖风险、市场风险竞争、长期运营风险；无资料填“未披露”。
10. “机会点”必须包含：横向延伸场景、纵向功能衔接、B端企业转型、细分生态位卡位；无资料填“未披露”。
11. 最多输出 {max_cases} 个案例。

必须完整包含这些字段：
{field_lines}

请只返回 JSON，不要写解释。格式：
{{
  "cases": [
    {{
      "案例编号": "1",
      "产品名称": "...",
      "创始人姓名+背景": "...",
      "编程背景": "有/无/自学/未披露",
      "产品类型": "...",
      "产品用途": "...",
      "目标人群": "...",
      "解决痛点": "①...②...③...",
      "收入模式": "...",
      "月收入": "...",
      "使用的AI工具": "...",
      "开发时间": "...",
      "数据来源+链接": "...",
      "数据可信度": "★推测/★★创始人自报/★★★媒体报道/★★★★官方公告",
      "是否单人项目": "是（单人）/否（小团队）/未披露",
      "风险点": {{"合规风险": "...", "平台依赖风险": "...", "市场风险竞争": "...", "长期运营风险": "..."}},
      "机会点": {{"横向延伸场景": "...", "纵向功能衔接": "...", "B端企业转型": "...", "细分生态位卡位": "..."}}
    }}
  ]
}}

网页摘录：
{contexts}
""".strip()


def call_openai_compatible_api(
    config: CollectorConfig,
    prompt: str,
    ledger: BudgetLedger,
) -> Dict[str, Any]:
    reservation = ledger.reserve(prompt, config.llm_max_output_tokens)
    if reservation is None:
        raise RuntimeError(
            f"API预算不足：已占用约 {ledger.used_cny:.4f} 元，"
            f"上限 {ledger.max_cny:.4f} 元，已停止后续检索。"
        )

    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": "你只做公开资料结构化抽取，必须输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": config.llm_temperature,
        "max_tokens": config.llm_max_output_tokens,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        config.api_url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        },
    )
    try:
        with request.urlopen(req, timeout=config.request_timeout_seconds) as response:
            response_text = response.read().decode("utf-8", errors="replace")
    except Exception:
        ledger.release(reservation)
        raise

    data = json.loads(response_text)
    usage = data.get("usage") or {}
    ledger.replace_with_actual(
        reservation=reservation,
        actual_input_tokens=usage.get("prompt_tokens"),
        actual_output_tokens=usage.get("completion_tokens"),
    )
    return data


def parse_llm_cases(api_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    choices = api_response.get("choices") or []
    if not choices:
        return []
    message = choices[0].get("message") or {}
    content = str(message.get("content") or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content, flags=re.I).strip()
        content = re.sub(r"```$", "", content).strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return []
        parsed = json.loads(content[start : end + 1])
    cases = parsed.get("cases") if isinstance(parsed, dict) else parsed
    if not isinstance(cases, list):
        return []
    return [case for case in cases if isinstance(case, dict)]


def extract_cases(config: CollectorConfig, pages: Sequence[SourcePage], ledger: BudgetLedger) -> List[Dict[str, str]]:
    if not pages:
        return []
    if not config.api_key or config.api_key == "请在这里粘贴你的API密钥":
        print("[提示] 未配置 LLM_API_KEY：为避免编造，脚本只生成空报告。")
        return []
    prompt = build_llm_prompt(pages, config.max_cases_per_day)
    response = call_openai_compatible_api(config, prompt, ledger)
    raw_cases = parse_llm_cases(response)
    normalized = []
    for raw_case in raw_cases:
        case = normalize_case(raw_case, len(normalized) + 1)
        if is_case_publishable(case):
            normalized.append(case)
        if len(normalized) >= config.max_cases_per_day:
            break
    return dedupe_cases(normalized)


def clean_value(value: Any) -> str:
    if value is None:
        return UNDISCLOSED
    if isinstance(value, list):
        cleaned_items = [clean_value(item) for item in value if clean_value(item) != UNDISCLOSED]
        if not cleaned_items:
            return UNDISCLOSED
        if len(set(cleaned_items)) > 1:
            return "存疑出现多个：" + "；".join(cleaned_items)
        return cleaned_items[0]
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            item_text = clean_value(item)
            parts.append(f"{key}：{item_text}")
        return "\n".join(parts) if parts else UNDISCLOSED
    text = normalize_multiline(str(value))
    if not text or text.lower() in {"none", "null", "n/a", "na", "unknown"}:
        return UNDISCLOSED
    return text


def normalize_choice(value: Any, allowed_values: set) -> str:
    text = clean_value(value)
    if text in allowed_values:
        return text
    for allowed in allowed_values:
        if allowed != UNDISCLOSED and allowed in text:
            return allowed
    return UNDISCLOSED


def normalize_pain_points(value: Any) -> str:
    text = clean_value(value)
    if text == UNDISCLOSED:
        return UNDISCLOSED
    if isinstance(value, dict):
        items = [clean_value(item) for item in value.values()]
    elif isinstance(value, list):
        items = [clean_value(item) for item in value]
    elif any(marker in text for marker in PAIN_MARKERS):
        chunks = re.split(r"[①②③④⑤⑥⑦⑧⑨]", text)
        items = [chunk.strip(" ；;，,。") for chunk in chunks if chunk.strip(" ；;，,。")]
    else:
        items = [item.strip() for item in re.split(r"[;；\n]+", text) if item.strip()]
    valid_items = [item for item in items if item and item != UNDISCLOSED][:3]
    if not valid_items:
        return UNDISCLOSED
    return "".join(f"{PAIN_MARKERS[index]}{item}" for index, item in enumerate(valid_items))


def normalize_four_category_field(value: Any, required_keys: Sequence[str]) -> str:
    if isinstance(value, dict):
        return "\n".join(f"{key}：{clean_value(value.get(key, UNDISCLOSED))}" for key in required_keys)
    text = clean_value(value)
    if text == UNDISCLOSED:
        return "\n".join(f"{key}：{UNDISCLOSED}" for key in required_keys)
    lines = []
    for key in required_keys:
        pattern = re.compile(re.escape(key) + r"[：:]\s*([^；;\n]+)")
        match = pattern.search(text)
        lines.append(f"{key}：{match.group(1).strip() if match else UNDISCLOSED}")
    return "\n".join(lines)


def normalize_credibility(value: Any) -> str:
    text = clean_value(value).replace(" ", "")
    if text in CREDIBILITY_OPTIONS:
        return text
    if "官方" in text or "★★★★" in text:
        return "★★★★官方公告"
    if "媒体" in text or "★★★" in text:
        return "★★★媒体报道"
    if "创始人" in text or "自报" in text or "★★" in text:
        return "★★创始人自报"
    if "推测" in text or "★" in text:
        return "★推测"
    return UNDISCLOSED


def normalize_solo_status(value: Any) -> str:
    text = clean_value(value)
    if text == UNDISCLOSED:
        return UNDISCLOSED
    if text.startswith("是") or "单人" in text or "一人" in text:
        return text if "（" in text or "(" in text else f"是（{text}）"
    if text.startswith("否") or "团队" in text or "多人" in text:
        return text if "（" in text or "(" in text else f"否（{text}）"
    return UNDISCLOSED


def normalize_case(raw_case: Dict[str, Any], index: int) -> Dict[str, str]:
    case: Dict[str, str] = {}
    for field_name in FIELD_NAMES:
        case[field_name] = clean_value(raw_case.get(field_name, UNDISCLOSED))
    case["案例编号"] = str(index)
    case["编程背景"] = normalize_choice(raw_case.get("编程背景", UNDISCLOSED), PROGRAMMING_BACKGROUNDS)
    case["产品类型"] = normalize_choice(raw_case.get("产品类型", UNDISCLOSED), PRODUCT_TYPES)
    case["收入模式"] = normalize_choice(raw_case.get("收入模式", UNDISCLOSED), REVENUE_MODE_OPTIONS)
    case["解决痛点"] = normalize_pain_points(raw_case.get("解决痛点", UNDISCLOSED))
    case["数据可信度"] = normalize_credibility(raw_case.get("数据可信度", UNDISCLOSED))
    case["是否单人项目"] = normalize_solo_status(raw_case.get("是否单人项目", UNDISCLOSED))
    case["风险点"] = normalize_four_category_field(raw_case.get("风险点", UNDISCLOSED), RISK_KEYS)
    case["机会点"] = normalize_four_category_field(raw_case.get("机会点", UNDISCLOSED), OPPORTUNITY_KEYS)
    return case


def is_case_publishable(case: Dict[str, str]) -> bool:
    product_name = case.get("产品名称", UNDISCLOSED)
    source = case.get("数据来源+链接", "")
    if product_name == UNDISCLOSED:
        return False
    return bool(re.search(r"https?://", source))


def dedupe_cases(cases: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    deduped: List[Dict[str, str]] = []
    seen = set()
    for case in cases:
        product_key = normalize_space(case.get("产品名称", "")).lower()
        if not product_key or product_key in seen:
            continue
        seen.add(product_key)
        case = dict(case)
        case["案例编号"] = str(len(deduped) + 1)
        deduped.append(case)
    return deduped


def render_case(case: Dict[str, str]) -> str:
    lines = []
    for index, (field_name, display_name) in enumerate(FIELD_SPECS, 1):
        value = case.get(field_name, UNDISCLOSED)
        if "\n" in value:
            value = "\n   " + value.replace("\n", "\n   ")
        lines.append(f"{index}. {display_name}：{value}")
    return "\n".join(lines)


def render_report(
    cases: Sequence[Dict[str, str]],
    config: CollectorConfig,
    ledger: BudgetLedger,
    source_pages: Sequence[SourcePage],
) -> str:
    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = [
        "Vibe Coding独立创业案例每日采集报告",
        f"生成时间：{generated_at}",
        f"检索关键词：{'；'.join(config.keywords)}",
        f"已抓取公开页面：{len(source_pages)} 个",
        f"API预算上限：{config.max_daily_api_budget_cny:.4f} 元人民币",
        f"API预算占用：{ledger.used_cny:.4f} 元人民币（输入约 {ledger.input_tokens} tokens，输出预留/实际约 {ledger.output_tokens} tokens）",
        f"预算触发停止：{'是' if ledger.stopped_by_budget else '否'}",
        "",
        "说明：仅输出有公开链接且通过字段校验的案例；字段无公开资料统一填“未披露”。",
        "",
    ]
    if not cases:
        header.append("未检索到通过公开来源校验的案例。")
        return "\n".join(header)
    body = []
    for case in cases:
        body.append(render_case(case))
        body.append("")
    return "\n".join(header + body).rstrip() + "\n"


def write_outputs(report_text: str, output_dir: Path) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.date.today().strftime("%Y-%m-%d")
    txt_path = output_dir / f"vibe_coding_cases_{stamp}.txt"
    doc_path = output_dir / f"vibe_coding_cases_{stamp}.doc"
    txt_path.write_text(report_text, encoding="utf-8")

    escaped = html.escape(report_text).replace("\n", "<br>\n")
    doc_html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Vibe Coding Case Report</title>
  <style>
    body {{ font-family: "Microsoft YaHei", Arial, sans-serif; line-height: 1.6; }}
  </style>
</head>
<body>{escaped}</body>
</html>
"""
    doc_path.write_text(doc_html, encoding="utf-8")
    return txt_path, doc_path


def run_once(config: CollectorConfig) -> Tuple[Path, Path]:
    ledger = config.budget_ledger()
    pages = collect_source_pages(config)
    try:
        cases = extract_cases(config, pages, ledger)
    except error.HTTPError as exc:
        print(f"[API错误] HTTP {exc.code}: 请检查 API 地址、模型名、密钥或余额。")
        cases = []
    except Exception as exc:  # noqa: BLE001
        print(f"[API跳过] {exc}")
        cases = []
    report = render_report(cases, config, ledger, pages)
    txt_path, doc_path = write_outputs(report, config.output_dir)
    print(f"[完成] TXT: {txt_path}")
    print(f"[完成] DOC: {doc_path}")
    return txt_path, doc_path


def parse_schedule_time(value: str) -> Tuple[int, int]:
    match = re.match(r"^(\d{1,2}):(\d{2})$", value.strip())
    if not match:
        raise ValueError("SCHEDULE_TIME 格式应为 HH:MM，例如 02:00")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("SCHEDULE_TIME 小时必须为 0-23，分钟必须为 0-59")
    return hour, minute


def seconds_until_next_run(schedule_time: str, now: Optional[dt.datetime] = None) -> int:
    now = now or dt.datetime.now()
    hour, minute = parse_schedule_time(schedule_time)
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run += dt.timedelta(days=1)
    return max(1, int((next_run - now).total_seconds()))


def run_daemon(config: CollectorConfig) -> None:
    print(f"[常驻定时] 每天 {config.schedule_time} 运行。保持本窗口和电脑在线。")
    while True:
        wait_seconds = seconds_until_next_run(config.schedule_time)
        next_time = dt.datetime.now() + dt.timedelta(seconds=wait_seconds)
        print(f"[等待] 下一次运行时间：{next_time.strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(wait_seconds)
        run_once(config)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Vibe Coding 独立创业案例自动采集器")
    parser.add_argument("--env-file", default=".env", help="配置文件路径，默认 .env")
    parser.add_argument("--output-dir", default=None, help="覆盖 OUTPUT_DIR 输出目录")
    parser.add_argument("--once", action="store_true", help="只运行一次（默认行为）")
    parser.add_argument("--daemon", action="store_true", help="常驻定时运行，按 SCHEDULE_TIME 每天执行")
    parser.add_argument("--max-pages", type=int, default=None, help="本次运行最多抓取页面数")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    load_env(Path(args.env_file))
    try:
        config = CollectorConfig.from_env(output_dir_override=args.output_dir)
    except ValueError as exc:
        print(f"[配置错误] {exc}")
        return 2
    if args.max_pages is not None:
        config.max_pages_to_fetch = args.max_pages
    if args.daemon:
        run_daemon(config)
    else:
        run_once(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
