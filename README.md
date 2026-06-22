# Vibe Coding 独立创业案例采集器

这是一个面向零基础小白的每日自动采集脚本，用来检索公开可查证的 Vibe Coding / AI Coding / 独立开发 / AI SaaS 相关创业案例，并按固定字段输出 TXT 和 Word 可打开的 `.doc` 文档。

脚本特点：

- 只使用 Python 标准库，不需要安装第三方包。
- API 密钥、关键词、预算、运行时间全部写在 `.env`，不写进代码。
- 每日 API 预算默认硬上限为 `0.10` 元人民币；达到阈值会停止后续 LLM 调用。
- 每条记录统一使用 20 个固定字段，缺失信息统一填写「未披露」。
- 每日报告固定分为：正式收录案例、候选案例、今日线索池、跳过案例清单、今日搜索总结、下一步建议关键词。
- 同时生成 TXT 纯文本和 Word 可打开的 DOC 文件。

> 安全提醒：不要把真实 API Key 发到公开仓库。`.gitignore` 已经忽略 `.env`，只提交 `.env.example`。

## 一、文件说明

```text
vibe_case_collector.py   主程序
.env.example             配置模板，复制成 .env 后填写
.gitignore               忽略真实密钥和缓存文件
reports/                 每天运行后自动生成的报告目录
```

## 二、第一次运行：小白分步教程

### 1. 打开 Cursor 里的终端

1. 打开 Cursor。
2. 左侧点 `Explorer/资源管理器`，确认能看到本项目文件。
3. 顶部菜单点 `Terminal`。
4. 点 `New Terminal`。
5. 终端底部出现命令输入区后，确认路径是项目目录。如果不是，输入：

```bash
cd /workspace
```

### 2. 检查 Python

在终端输入：

```bash
python3 --version
```

如果显示 `Python 3.x.x`，说明可以继续。

Windows 用户如果没有 `python3`，通常可以改用：

```bat
python --version
```

### 3. 创建 `.env` 配置文件

在 Cursor 左侧文件区找到 `.env.example`。

方法 A：界面复制

1. 右键 `.env.example`。
2. 选择 `Duplicate/复制`。
3. 把新文件改名为 `.env`。
4. 打开 `.env`，把 `LLM_API_KEY=` 后面填入你的 API Key。

方法 B：终端复制

```bash
cp .env.example .env
```

然后在 Cursor 左侧点击 `.env`，填入：

```text
LLM_API_KEY=你的真实API密钥
```

如果只想先免费跑搜索和文档生成，可以保持：

```text
ENABLE_LLM_ENRICHMENT=false
```

如需启用大模型辅助提取，再改成：

```text
ENABLE_LLM_ENRICHMENT=true
```

### 4. 立即运行一次

Linux / macOS / Cursor Cloud：

```bash
python3 vibe_case_collector.py --once
```

Windows：

```bat
python vibe_case_collector.py --once
```

运行完成后会看到类似：

```text
已生成：reports/2026-06-22/vibe_coding_cases_2026-06-22.txt
已生成：reports/2026-06-22/vibe_coding_cases_2026-06-22.doc
```

### 5. 打开结果文件

在 Cursor 左侧打开：

```text
reports/当天日期/
```

你会看到两份文件：

- `vibe_coding_cases_当天日期.txt`：纯文本，适合复制到微信、飞书、Notion。
- `vibe_coding_cases_当天日期.doc`：Word 可打开的文档。

## 三、报告固定字段

所有正式案例、候选案例、今日线索都使用同一套字段：

1. 案例编号
2. 收录级别：正式案例 / 候选案例 / 今日线索
3. 产品名称
4. 创始人+编程背景
5. 产品类型
6. 产品用途：从用户视角说明这个软件具体能帮你做什么
7. 目标人群
8. 解决痛点
9. 收入模式+MRR/ARR
10. AI工具
11. 工具-场景匹配分析
12. 开发时间
13. 来源+链接
14. 数据可信度
15. 可信度理由
16. 是否单人/小团队
17. 风险点
18. 机会点
19. 缺失字段
20. 复核建议

## 四、数据可信度标准

- `★★★★ 官方公告`：官网、产品页、公开收入面板、GitHub README、官方博客等一手资料。
- `★★★ 媒体报道`：科技媒体、播客、Newsletter、行业文章等第三方公开报道。
- `★★ 创始人自报`：X/Twitter、Indie Hackers、Reddit、访谈、个人博客等创始人本人说明。
- `★ 匿名推测`：论坛讨论、二手转载、无法确认来源的信息。

脚本会尽量自动判断，但它不会假装自己已经核实全部事实。正式使用前请打开来源链接人工复核。

## 五、两套自动定时运行方案

### 方案 A：Cursor 常驻定时

适合电脑或云端 Cursor 一直开着的情况。

1. 打开 Cursor。
2. 顶部菜单点 `Terminal`。
3. 点 `New Terminal`。
4. 输入：

```bash
cd /workspace
python3 vibe_case_collector.py --daemon
```

默认每天 `.env` 里的 `RUN_AT=08:00` 运行一次。

想改成每天 21:30，打开 `.env`，改成：

```text
RUN_AT=21:30
```

停止常驻运行：在终端按快捷键：

```text
Ctrl + C
```

### 方案 B：Windows 任务计划程序

适合每天自动运行，不需要一直打开 Cursor。

1. 按键盘 `Win` 键。
2. 搜索 `任务计划程序` 并打开。
3. 右侧点击 `创建基本任务`。
4. 名称填写：`Vibe Coding 每日采集`。
5. 触发器选择：`每天`。
6. 时间填写：例如 `08:00:00`。
7. 操作选择：`启动程序`。
8. `程序或脚本` 填写 Python 路径，例如：

```text
C:\Windows\py.exe
```

如果你知道自己的 Python 路径，也可以填类似：

```text
C:\Users\你的用户名\AppData\Local\Programs\Python\Python312\python.exe
```

9. `添加参数` 填写：

```text
vibe_case_collector.py --once
```

10. `起始于` 填写项目所在文件夹，例如：

```text
C:\Users\你的用户名\Desktop\vibe-case-collector
```

11. 点击 `完成`。

测试方式：在任务列表里右键这个任务，点 `运行`，然后检查 `reports` 文件夹是否生成了当天报告。

## 六、如何自定义关键词、时间、预算

### 修改关键词

打开 `.env`，找到：

```text
SEARCH_KEYWORDS=
SEARCH_KEYWORDS_EN=
```

在后面增加关键词，用逗号分开即可。例如：

```text
SEARCH_KEYWORDS=Vibe Coding 独立创业案例,Cursor 独立开发 收入,Claude Code 一人 SaaS
```

### 修改运行时间

打开 `.env`，修改：

```text
RUN_AT=08:00
```

例如晚上 9 点运行：

```text
RUN_AT=21:00
```

### 修改预算

打开 `.env`：

```text
DAILY_BUDGET_CNY=0.10
HARD_DAILY_BUDGET_CNY=0.10
```

本项目默认按任务要求把每日大模型调用硬上限锁定到 `0.10` 元人民币。你可以调低，例如：

```text
DAILY_BUDGET_CNY=0.05
```

如不了解 API 价格，不建议调高。

### 修改搜索深度

打开 `.env`：

```text
MAX_SEARCH_RESULTS_PER_KEYWORD=5
MAX_TOTAL_RESULTS=45
MAX_DEEP_PAGES=8
```

- 想更快：把数字调小。
- 想更多线索：把数字稍微调大。
- 启用大模型时，数字越大越可能触发预算保护。

## 七、常见报错和修复

### 报错：`请先在 .env 配置 SEARCH_KEYWORDS`

原因：没有 `.env`，或 `.env` 里关键词为空。

修复：

```bash
cp .env.example .env
```

然后重新运行。

### 报错：`python3: command not found`

原因：电脑没有安装 Python，或 Windows 命令叫 `python`。

修复：

- Windows 先试：

```bat
python vibe_case_collector.py --once
```

- 仍然不行，就去 Python 官网安装 Python 3。

### 报错：网络抓取失败

原因：搜索引擎或网页临时打不开。

修复：

1. 稍后重新运行。
2. 在 `.env` 的 `SOURCE_URLS=` 后面手动放公开来源链接。
3. 降低 `MAX_DEEP_PAGES`，减少正文抓取数量。

### 报告里「正式案例」为 0

这是正常情况。脚本从严处理：没有产品名称、用途、来源链接、可信度理由的内容不会进入正式案例。

你仍然可以查看：

- `二、候选案例`
- `三、今日线索池`
- `四、跳过案例清单`

### 大模型没有调用

检查 `.env`：

```text
ENABLE_LLM_ENRICHMENT=true
LLM_API_KEY=你的真实API密钥
```

如果预算接近上限，脚本会自动跳过后续 LLM 调用，避免超支。

## 八、手动补充公开来源

如果你已经知道某个公开来源，例如创始人访谈、GitHub README、产品官网，可以放到 `.env`：

```text
SOURCE_URLS=https://example.com/case-1,https://example.com/case-2
```

脚本会把这些链接和搜索结果一起处理。

## 九、跳过规则

以下内容不会进入正式案例：

- 无关内容。
- 纯概念文章。
- 无法确认产品名称。
- 没有来源链接。
- 重复产品。
- 无公开可查证信息的传闻。

跳过内容会放在报告的 `四、跳过案例清单`，并写明跳过原因。