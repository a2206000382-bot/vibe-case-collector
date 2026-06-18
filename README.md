# vibe-case-collector

Vibe Coding 独立创业案例每日采集器。脚本会按配置关键词搜索公开网页，保守分级为“正式案例 / 候选案例 / 今日线索”，并生成 TXT 与 Word 可打开的 DOC 报告。

## 快速开始

```bash
cp .env.example .env
python3 vibe_case_collector.py
```

生成文件位于：

```text
reports/YYYY-MM-DD/vibe_cases_YYYY-MM-DD.txt
reports/YYYY-MM-DD/vibe_cases_YYYY-MM-DD.doc
```

## 主要文件

- `vibe_case_collector.py`：主采集脚本。
- `.env.example`：配置样例，真实密钥请复制到 `.env`。
- `prompts/case_extract_prompt.txt`：可选 API 精读提示词。
- `scripts/run_daily_cursor.py`：Cursor 常驻定时运行脚本。
- `scripts/run_collector_windows.bat`：Windows 任务计划程序可调用的批处理。
- `docs/BEGINNER_GUIDE.md`：零基础分步操作教程、定时方案和报错修复。

## 预算保护

默认不开启大模型精读：

```text
ENABLE_LLM_ENRICHMENT=false
MAX_DAILY_BUDGET_CNY=0.10
```

如改为 `ENABLE_LLM_ENRICHMENT=true`，脚本会在每日 0.1 元人民币预算内调用 OpenAI 兼容接口，超过预算前自动停止后续 API 调用。

## 采集原则

- 不虚构案例，不用模型猜测填字段。
- 缺失公开资料统一填写「未披露」。
- 正式案例可以为 0，避免把概念文章或无关内容凑入正式案例。
- 候选案例和今日线索用于后续人工复核。