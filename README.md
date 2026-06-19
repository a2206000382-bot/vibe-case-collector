# vibe-case-collector

Vibe Coding 独立创业案例每日自动采集器。它会按固定字段模板检索公开网页，保守输出“正式案例 / 候选案例 / 今日线索”，并在本地生成两份报告：

- `TXT` 纯文本报告
- `DOC` 文档报告（Word 可直接打开）

脚本默认不需要第三方 Python 包；如需更强的结构化提取，可在 `.env` 中开启 OpenAI 兼容 API，并受单日 `0.10` 元人民币预算硬限制保护。

## 1. 文件说明

| 文件 | 用途 |
| --- | --- |
| `vibe_case_collector.py` | 主采集脚本 |
| `.env.example` | 配置模板，复制成 `.env` 后填写密钥、关键词、预算、时间 |
| `.gitignore` | 防止 `.env` 和本地报告被提交 |
| `reports/YYYY-MM-DD/` | 每天运行后生成的本地报告目录 |

## 2. 固定输出字段

所有“正式案例 / 候选案例 / 今日线索”都使用同一套 20 个字段：

1. 案例编号
2. 收录级别
3. 产品名称
4. 创始人+编程背景
5. 产品类型
6. 产品用途
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

报告结构固定为：

一、正式收录案例  
二、候选案例  
三、今日线索池  
四、跳过案例清单  
五、今日搜索总结  
六、下一步建议关键词

## 3. 数据可信度标准

- `★★★★ 官方公告`：官网、产品页、公开收入面板、GitHub README、官方博客等一手资料。
- `★★★ 媒体报道`：科技媒体、播客、Newsletter、行业文章等第三方公开报道。
- `★★ 创始人自报`：X/Twitter、Indie Hackers、Reddit、访谈、个人博客等创始人本人说明。
- `★ 匿名推测`：论坛讨论、二手转载、无法确认来源的信息。

脚本会自动降级证据不足的内容：没有产品名、用途、来源链接或可信度的内容不会进入“正式案例”。

## 4. 小白安装步骤（Windows / macOS / Linux 通用）

### 第一步：安装 Python

1. 打开浏览器，访问 <https://www.python.org/downloads/>。
2. 点击黄色按钮下载 Python。
3. Windows 安装时，务必勾选 `Add python.exe to PATH`。
4. 安装完成后，打开命令行：
   - Windows：按 `Win + R`，输入 `cmd`，按回车。
   - macOS：打开“终端”。
   - Linux：打开 Terminal。
5. 输入下面命令检查安装是否成功：

```bash
python --version
```

如果显示 `Python 3.x.x`，说明安装成功。

### 第二步：准备配置文件

1. 在项目文件夹里找到 `.env.example`。
2. 复制一份，改名为 `.env`。
3. 用记事本或 Cursor 打开 `.env`。
4. 把你的 API 密钥填在这一行后面：

```dotenv
API_KEY=这里粘贴你的密钥
```

注意：

- 不要把密钥写进 `vibe_case_collector.py`。
- 不要截图公开展示 `.env`。
- 默认 `ENABLE_LLM_ENRICHMENT=false`，不会调用 API，也不会扣费。
- 如果要让 AI 帮你做结构化提取，把它改成：

```dotenv
ENABLE_LLM_ENRICHMENT=true
```

### 第三步：运行一次

在项目文件夹打开命令行，输入：

```bash
python vibe_case_collector.py
```

运行结束后，会看到类似提示：

```text
已生成 TXT：reports/2026-06-19/vibe_coding_cases_2026-06-19.txt
已生成 DOC：reports/2026-06-19/vibe_coding_cases_2026-06-19.doc
```

打开 `reports` 文件夹，再打开当天日期文件夹，即可看到报告。

## 5. 在 Cursor 里点击运行

1. 用 Cursor 打开本项目文件夹。
2. 左侧文件栏点击 `vibe_case_collector.py`。
3. 按快捷键打开终端：
   - Windows / Linux：`Ctrl + \``
   - macOS：`Control + \`` 或菜单 `Terminal -> New Terminal`
4. 终端底部出现后，输入：

```bash
python vibe_case_collector.py
```

5. 回车运行。
6. 运行完后，在左侧文件栏展开 `reports` 文件夹查看报告。

## 6. 两套自动定时运行方案

### 方案 A：Cursor 常驻定时

适合电脑长期打开 Cursor 的情况。

1. 打开 Cursor。
2. 打开本项目文件夹。
3. 点击底部终端，或按：
   - Windows / Linux：`Ctrl + \``
   - macOS：`Control + \``
4. 输入下面命令，让它每 24 小时运行一次：

Windows PowerShell：

```powershell
while ($true) { python vibe_case_collector.py; Start-Sleep -Seconds 86400 }
```

macOS / Linux：

```bash
while true; do python vibe_case_collector.py; sleep 86400; done
```

说明：这个方式要求 Cursor 和电脑保持运行。关闭电脑或退出 Cursor 后，定时会停止。

### 方案 B：Windows 任务计划程序系统定时

适合让 Windows 每天自动运行，不需要一直盯着 Cursor。

1. 按 `Win` 键。
2. 搜索 `任务计划程序`，打开它。
3. 右侧点击 `创建基本任务...`。
4. 名称填写：`Vibe Coding 案例采集`。
5. 点击 `下一步`。
6. 触发器选择 `每天`。
7. 时间填写你想运行的时间，例如 `08:00`。
8. 操作选择 `启动程序`。
9. `程序或脚本` 填：

```text
python
```

10. `添加参数` 填：

```text
vibe_case_collector.py
```

11. `起始于` 填项目文件夹路径，例如：

```text
C:\Users\你的用户名\Desktop\vibe-case-collector
```

12. 点击 `完成`。
13. 在任务列表里右键这个任务，点击 `运行`，先测试一次。

## 7. 修改关键词 / 运行时间 / 预算

### 修改关键词

打开 `.env`，找到：

```dotenv
SEARCH_KEYWORDS=...
```

多个关键词用英文竖线 `|` 分隔，例如：

```dotenv
SEARCH_KEYWORDS=Cursor AI SaaS revenue|vibe coded SaaS MRR|Claude Code indie hacker
```

### 修改每天抓多少内容

```dotenv
MAX_KEYWORDS_PER_RUN=12
MAX_RESULTS_PER_KEYWORD=5
MAX_PAGES_TO_FETCH=12
```

数字越大，抓取越多，运行越慢。

### 修改 API 预算

默认严格限制为每天 0.10 元人民币：

```dotenv
DAILY_API_BUDGET_CNY=0.10
```

达到预算后，脚本会停止后续 AI 结构化提取，但仍会生成报告。

### 修改自动运行时间

`.env` 里这两项主要用于记录你的计划：

```dotenv
CURSOR_CRON_TIME=08:00
WINDOWS_TASK_TIME=08:00
```

真正生效的时间需要在 Cursor 常驻命令或 Windows 任务计划程序里设置。

## 8. 常见报错修复

### 报错：`python 不是内部或外部命令`

原因：Python 没有加入系统 PATH。

修复：

1. 重新安装 Python。
2. 安装页面勾选 `Add python.exe to PATH`。
3. 关闭命令行窗口，重新打开。

### 报错：`No such file or directory`

原因：当前命令行不在项目文件夹里。

修复：

1. 在 Cursor 左侧确认项目文件夹已打开。
2. 用 Cursor 底部终端运行。
3. 或先输入 `cd 项目文件夹路径` 再运行脚本。

### 报错：`LLM 调用失败`

可能原因：

- `.env` 里的 `API_KEY` 没填或填错。
- `API_BASE_URL` 不是 OpenAI 兼容接口。
- 网络无法访问接口。
- 当天预算已用完。

修复：

1. 检查 `.env`。
2. 先把 `ENABLE_LLM_ENRICHMENT=false`，确认基础搜索能运行。
3. 再开启 `ENABLE_LLM_ENRICHMENT=true`。

### 报告里“正式案例”为 0

这是正常情况。脚本按“宁缺毋滥”处理：当天没有足够公开佐证时，正式案例可以为 0，但候选案例或今日线索会保留可复核线索。

### 搜索结果太少

可以在 `.env` 里增加英文关键词，例如：

```dotenv
SEARCH_KEYWORDS=site:indiehackers.com Cursor AI SaaS MRR|site:x.com "built with Cursor" "MRR"|Claude Code indie hacker revenue
```

## 9. 运行逻辑摘要

1. 读取 `.env` 配置。
2. 按关键词搜索公开网页。
3. 抓取网页标题、摘要和正文片段。
4. 规则判断是否与 Vibe Coding / AI Coding / 独立开发 / AI SaaS 相关。
5. 可选调用 LLM 做结构化提取。
6. 按预算估算 Token 费用，超过 0.10 元人民币则停止 API 调用。
7. 校验 20 个字段，缺失统一填 `未披露`。
8. 生成 TXT 和 DOC 两份本地报告。

## 10. 安全提醒

- `.env` 已被 `.gitignore` 忽略，不会提交。
- 不要把真实 API 密钥发到公开仓库、截图或文档中。
- 如果怀疑密钥泄露，请立刻去 API 平台重置密钥。