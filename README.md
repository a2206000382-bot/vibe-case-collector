# vibe-case-collector

面向零基础小白的「Vibe Coding / AI Coding 独立创业案例」每日自动采集脚本。

脚本会按固定模板输出每日报告：

1. 一、正式收录案例
2. 二、候选案例
3. 三、今日线索池
4. 四、跳过案例清单
5. 五、今日搜索总结
6. 六、下一步建议关键词

每条案例固定 20 个字段，缺失信息统一写「未披露」，不会为了凑数把无关内容放入正式案例。

## 重要安全提醒

- 不要把 API key 写进代码。
- 不要把 `.env` 发给别人。
- 本仓库已经把 `.env` 和 `reports/` 加入 `.gitignore`，避免误提交密钥和每日报告。
- 默认 `ENABLE_LLM_ENRICHMENT=false`，不会调用付费大模型。只有你手动改成 `true` 才会使用 API key。
- 单日 API 预算由 `.env` 中 `MAX_DAILY_API_COST_CNY=0.10` 控制。脚本会按 token 预估花费，超过阈值会停止后续付费增强。

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `vibe_case_collector.py` | 主采集脚本，使用 Python 标准库，无需安装第三方包 |
| `.env.example` | 配置模板，复制成 `.env` 后填写 API key、关键词、预算、运行时间 |
| `run_collector.bat` | Windows 双击运行/任务计划程序调用入口 |
| `reports/日期/` | 每日自动生成的 TXT 和 DOC 报告目录，本地生成，不提交 |

## 第一次使用：一步一步照做

### 第 1 步：安装 Python

1. 打开浏览器，进入 `https://www.python.org/downloads/`
2. 点击黄色按钮下载 Python。
3. Windows 安装时，请勾选页面底部的 **Add python.exe to PATH**。
4. 点击 **Install Now**。
5. 安装完成后，按键盘 `Win + R`，输入 `cmd`，回车。
6. 输入：

```bash
python --version
```

能看到版本号就说明安装成功。

### 第 2 步：在 Cursor 里打开项目

1. 打开 Cursor。
2. 点击左上角 **File**。
3. 点击 **Open Folder...**。
4. 选择本项目文件夹。
5. 点击 **Open**。

### 第 3 步：复制配置文件

在 Cursor 左侧文件列表中：

1. 找到 `.env.example`。
2. 右键点击它。
3. 点击 **Copy**。
4. 在空白处右键。
5. 点击 **Paste**。
6. 把复制出来的新文件改名为 `.env`。

如果你喜欢用终端，也可以按 `Ctrl + ~` 打开 Cursor 终端，输入：

```bash
cp .env.example .env
```

### 第 4 步：填写 API key

打开 `.env`，找到这一行：

```text
LLM_API_KEY=请粘贴你的apikey
```

把等号后面的内容替换为你的 API key。

如果只是先跑通流程，可以保持：

```text
ENABLE_LLM_ENRICHMENT=false
```

这样不会扣 API 费用。

如果你确认要让大模型辅助整理摘要，再改成：

```text
ENABLE_LLM_ENRICHMENT=true
```

同时保留：

```text
MAX_DAILY_API_COST_CNY=0.10
```

### 第 5 步：运行一次

在 Cursor 里按 `Ctrl + ~` 打开终端，输入：

```bash
python vibe_case_collector.py --once
```

Linux/macOS 如果 `python` 不可用，改用：

```bash
python3 vibe_case_collector.py --once
```

运行成功后，会看到类似：

```text
采集完成：reports/2026-06-21/vibe_coding_cases_2026-06-21.txt
DOC文件：reports/2026-06-21/vibe_coding_cases_2026-06-21.doc
今日API预估花费：0.0000 元人民币
```

打开 `reports/当天日期/` 文件夹，就能看到：

- `vibe_coding_cases_日期.txt`
- `vibe_coding_cases_日期.doc`

## 固定输出字段

每条案例都会严格输出以下 20 个字段：

1. 案例编号
2. 收录级别：正式案例 / 候选案例 / 今日线索
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

## 数据可信度标准

- `★★★★ 官方公告`：官网、产品页、公开收入面板、GitHub README、官方博客等一手资料。
- `★★★ 媒体报道`：科技媒体、播客、Newsletter、行业文章等第三方公开报道。
- `★★ 创始人自报`：X/Twitter、Indie Hackers、Reddit、访谈、个人博客等创始人本人说明。
- `★ 匿名推测`：论坛讨论、二手转载、无法确认来源的信息。

## 两套自动定时运行方案

### 方案 A：Cursor 常驻定时

适合电脑长期开机、Cursor 长期开着的情况。

1. 打开 `.env`。
2. 找到：

```text
RUN_AT=08:00
```

3. 改成你想每天运行的时间，比如晚上 9 点：

```text
RUN_AT=21:00
```

4. 在 Cursor 按 `Ctrl + ~` 打开终端。
5. 输入：

```bash
python vibe_case_collector.py --daemon
```

6. 看到「已进入光标/Cursor 常驻定时模式」后，不要关闭这个终端。
7. 到时间后脚本会自动运行一次。
8. 想停止时，在终端按 `Ctrl + C`。

### 方案 B：Windows 任务计划程序

适合不用一直打开 Cursor 的情况。

1. 按 `Win` 键。
2. 搜索 **任务计划程序**。
3. 打开它。
4. 点击右侧 **创建基本任务...**。
5. 名称填写：`Vibe Coding 案例每日采集`。
6. 点击 **下一步**。
7. 触发器选择 **每天**。
8. 点击 **下一步**。
9. 设置运行时间，比如 `08:00:00`。
10. 点击 **下一步**。
11. 操作选择 **启动程序**。
12. 点击 **下一步**。
13. 「程序或脚本」选择本项目里的 `run_collector.bat`。
14. 「起始于」填写本项目文件夹路径，例如：

```text
C:\Users\你的用户名\Desktop\vibe-case-collector
```

15. 点击 **下一步**。
16. 点击 **完成**。
17. 右键刚创建的任务，点击 **运行**，先测试一次。

## 如何修改关键词

打开 `.env`，找到：

```text
SEARCH_KEYWORDS=关键词1||关键词2||关键词3
```

用 `||` 分隔每个关键词。

示例：

```text
SEARCH_KEYWORDS=Cursor 独立开发 AI 工具||Claude Code 独立开发 SaaS||vibe coding indie hacker
```

## 如何修改预算

打开 `.env`，找到：

```text
MAX_DAILY_API_COST_CNY=0.10
```

如果你希望仍然保持极低成本，不建议改大。

如果只想完全免费运行，请保持：

```text
ENABLE_LLM_ENRICHMENT=false
```

## 如何修改搜索深度

打开 `.env`：

```text
MAX_SEARCH_RESULTS_PER_KEYWORD=4
MAX_TOTAL_ITEMS=30
```

- `MAX_SEARCH_RESULTS_PER_KEYWORD`：每个关键词最多拿几个搜索结果。
- `MAX_TOTAL_ITEMS`：最终最多输出多少条。

数值越大，运行越慢，噪音也可能越多。

## 如何修改运行时间

打开 `.env`：

```text
RUN_AT=08:00
```

改成 24 小时制时间。

例如：

```text
RUN_AT=22:30
```

表示每天晚上 10 点 30 分运行。

## 常见报错和修复

### 1. `python 不是内部或外部命令`

原因：Python 没装好，或安装时没有勾选 PATH。

修复：

1. 重新打开 Python 安装包。
2. 点击 **Modify**。
3. 勾选 **Add Python to environment variables**。
4. 继续安装。
5. 关闭并重新打开终端。

### 2. `No such file or directory: .env`

原因：还没有复制配置文件。

修复：

```bash
cp .env.example .env
```

Windows 也可以手动复制 `.env.example`，然后改名为 `.env`。

### 3. 报告里很多「未披露」

这是正常现象。规则要求没有公开证据就必须写「未披露」。

修复方向：

- 增加更具体的关键词，比如产品名、创始人名。
- 在 `SEED_URLS` 添加产品官网、GitHub、Product Hunt、Indie Hackers 链接。
- 打开生成报告里的「复核建议」，人工点击来源链接补充证据。

### 4. 正式案例为 0

这是允许的。正式案例必须有产品名称、用途、来源链接、可信度等基础信息，并且要有更强的案例信号。脚本宁可输出候选案例和线索池，也不会把无关内容塞进正式案例。

### 5. API 花费超过预期

修复：

1. 打开 `.env`。
2. 改成：

```text
ENABLE_LLM_ENRICHMENT=false
```

3. 或继续使用 LLM，但保持：

```text
MAX_DAILY_API_COST_CNY=0.10
```

脚本会在 `reports/日期/api_usage.json` 记录当天估算花费。

### 6. `.doc` 打不开

本脚本生成的是 Word 可打开的 HTML 格式 `.doc`。如果双击打不开：

1. 先打开 Microsoft Word。
2. 点击 **文件**。
3. 点击 **打开**。
4. 选择生成的 `.doc` 文件。

## 跳过规则

以下内容不会进入正式案例：

- 无关内容。
- 纯概念文章。
- 无法确认产品名称的内容。
- 没有来源链接的内容。
- 重复产品。

被跳过的内容会写在报告末尾的「四、跳过案例清单」中，并标明原因。

## 推荐工作流

1. 每天自动运行。
2. 先看「正式收录案例」。
3. 再看「候选案例」。
4. 从「今日线索池」挑出值得人工复核的链接。
5. 把确认过的好来源加入 `.env` 的 `SEED_URLS`。
6. 第二天继续自动采集。