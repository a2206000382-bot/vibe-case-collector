# vibe-case-collector

Vibe Coding 独立创业案例每日采集助手。脚本会按固定模板抓取公开网页线索，自动生成：

- TXT 纯文本报告
- Word 可打开的 `.doc` 报告

报告固定分为：

1. 正式收录案例
2. 候选案例
3. 今日线索池
4. 跳过案例清单
5. 今日搜索总结
6. 下一步建议关键词

> 安全说明：真实 API key 只放在本地 `.env` 文件中，`.env` 已被 `.gitignore` 忽略，不会提交到仓库。

## 一、文件说明

| 文件 | 作用 |
| --- | --- |
| `vibe_case_collector.py` | 主程序：搜索、抓取、字段整理、预算控制、输出 TXT/DOC |
| `.env.example` | 配置模板：API key、预算、关键词、运行时间都在这里改 |
| `.gitignore` | 防止 `.env`、本地预算状态、缓存文件被上传 |
| `reports/` | 运行后自动生成的日报目录 |

## 二、第一次运行：小白分步操作

### 1. 打开 Cursor 终端

1. 打开 Cursor。
2. 点击顶部菜单 `Terminal`。
3. 点击 `New Terminal`。
4. 终端底部出现黑色命令窗口后，确认当前位置是本项目目录。

如果不确定，输入：

```bash
pwd
```

看到类似 `/workspace` 就可以继续。

### 2. 检查 Python

在终端输入：

```bash
python3 --version
```

如果显示 `Python 3.x.x`，说明可直接运行。

如果 Windows 电脑显示找不到命令，请安装 Python：

1. 打开 <https://www.python.org/downloads/>
2. 点击黄色的 `Download Python`。
3. 安装时勾选 `Add python.exe to PATH`。
4. 安装完成后重新打开终端。

### 3. 复制配置文件

Linux / macOS / Cursor Cloud 终端输入：

```bash
cp .env.example .env
```

Windows PowerShell 输入：

```powershell
Copy-Item .env.example .env
```

### 4. 填写 API key 和预算

在 Cursor 左侧文件栏点击 `.env`，按下面方式修改：

```env
OPENAI_API_KEY=你的真实API密钥
ENABLE_LLM_ENRICHMENT=false
DAILY_API_BUDGET_CNY=0.10
```

建议新手先保持：

```env
ENABLE_LLM_ENRICHMENT=false
```

这样不会调用大模型 API，成本为 0。  
如果你确实要启用大模型字段补全，再改成：

```env
ENABLE_LLM_ENRICHMENT=true
```

脚本仍会用 `DAILY_API_BUDGET_CNY=0.10` 做单日预算封顶。

### 5. 立即运行一次

```bash
python3 vibe_case_collector.py
```

运行成功会看到：

```text
TXT报告已生成：...
DOC报告已生成：...
```

打开 `reports/当天日期/`，可以看到两个文件：

- `vibe_coding_cases_YYYY-MM-DD.txt`
- `vibe_coding_cases_YYYY-MM-DD.doc`

## 三、固定字段模板

每条案例或线索都按以下 20 个字段输出，缺失资料统一写「未披露」：

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

| 星级 | 含义 |
| --- | --- |
| ★★★★ 官方公告 | 官网、产品页、公开收入面板、GitHub README、官方博客等一手资料 |
| ★★★ 媒体报道 | 科技媒体、播客、Newsletter、行业文章等第三方公开报道 |
| ★★ 创始人自报 | X/Twitter、Indie Hackers、Reddit、访谈、个人博客等创始人本人说明 |
| ★ 匿名推测 | 论坛讨论、二手转载、无法确认来源的信息 |

## 五、如何修改关键词、运行时间、预算

所有配置都在 `.env`。

### 修改搜索关键词

找到：

```env
SEARCH_KEYWORDS=关键词1|关键词2|关键词3
```

用英文竖线 `|` 分隔关键词即可。

### 修改运行时间

找到：

```env
RUN_TIME_HHMM=08:00
```

例如改成每天晚上 9 点：

```env
RUN_TIME_HHMM=21:00
```

### 修改每日预算

找到：

```env
DAILY_API_BUDGET_CNY=0.10
```

如无特殊需要，不建议调高。脚本会把每日大模型预估成本锁定在这个数值以内。

### 修改抓取数量

```env
MAX_KEYWORDS_PER_RUN=8
MAX_RESULTS_PER_KEYWORD=5
MAX_PAGES_PER_RUN=20
```

数字越大，搜索和网页请求越多；新手建议保持默认。

## 六、两套自动定时运行方案

### 方案 A：Cursor 常驻定时

适合一直开着 Cursor 或 Cursor Cloud 机器。

1. 打开 Cursor。
2. 点击 `Terminal` -> `New Terminal`。
3. 输入：

```bash
python3 vibe_case_collector.py --watch --run-now
```

含义：

- `--watch`：让程序一直开着，到 `.env` 的 `RUN_TIME_HHMM` 自动运行。
- `--run-now`：启动后先立刻跑一次。

如果只想等到设定时间再跑，输入：

```bash
python3 vibe_case_collector.py --watch
```

停止方法：在终端按 `Ctrl + C`。

### 方案 B：Windows 任务计划程序

适合每天固定时间由 Windows 自动触发。

1. 按键盘 `Win` 键。
2. 搜索 `任务计划程序` 并打开。
3. 右侧点击 `创建基本任务...`。
4. 名称填写：`Vibe Coding 案例采集`。
5. 触发器选择：`每天`。
6. 时间填写你想运行的时间，例如 `08:00`。
7. 操作选择：`启动程序`。
8. `程序或脚本` 填：

```text
python
```

9. `添加参数` 填：

```text
vibe_case_collector.py
```

10. `起始于` 填项目文件夹路径，例如：

```text
C:\Users\你的用户名\Desktop\vibe-case-collector
```

11. 点击完成。

如果你的电脑只能识别 `python3`，第 8 步改成：

```text
python3
```

## 七、常见报错和修复

### 1. `python3: command not found`

原因：电脑没装 Python，或 Python 没加入 PATH。

修复：

- Windows：重新安装 Python，安装时勾选 `Add python.exe to PATH`。
- macOS：可以尝试 `python vibe_case_collector.py`。

### 2. 没有生成报告

检查终端是否有报错。常见原因：

- 当前目录不是项目目录。
- 没有 `.env` 文件。
- 网络无法访问搜索引擎或目标网页。

可以重新执行：

```bash
python3 vibe_case_collector.py
```

### 3. 大模型没有被调用

检查 `.env`：

```env
ENABLE_LLM_ENRICHMENT=true
OPENAI_API_KEY=你的真实API密钥
```

还要确认预算没有用完：

```env
DAILY_API_BUDGET_CNY=0.10
```

预算状态保存在 `.collector_state/`，同一天多次运行会累计预算，防止超额。

### 4. API 报错或无法连接

检查：

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

如果你使用的是 OpenAI 兼容服务，需要把 `LLM_BASE_URL` 和 `LLM_MODEL` 改成服务商提供的值。

### 5. Word 打不开 `.doc`

本项目生成的是 Word 可打开的 HTML 格式 `.doc`。如果双击打不开：

1. 先打开 Microsoft Word。
2. 点击 `文件` -> `打开`。
3. 选择生成的 `.doc` 文件。

## 八、跳过规则

脚本不会为了凑数把无关内容放进正式案例：

- 无关内容不收录。
- 纯概念文章不进入正式案例。
- 无法确认产品名称的内容不进入正式案例。
- 没有来源链接的内容不进入正式案例。
- 重复产品不重复输出。
- 被跳过的内容会放在文档末尾并写明原因。

当天正式案例可以为 0，但候选案例或今日线索池会保留可复核的公开线索。