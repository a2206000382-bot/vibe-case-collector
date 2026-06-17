# vibe-case-collector

Vibe Coding 独立创业案例自动采集器。脚本会按固定字段模板搜索公开网页，调用 OpenAI 兼容大模型接口做结构化抽取，并每天生成：

- `TXT` 纯文本报告
- `DOC` 文档报告（Word 可直接打开）

> 注意：用户需求里写“16 个字段”，但实际编号列出了 1-17 共 17 项。本项目按用户列出的 17 项全部输出，避免遗漏“风险点”或“机会点”。

## 1. 文件说明

| 文件 | 作用 |
| --- | --- |
| `vibe_case_collector.py` | 主采集脚本，无第三方依赖 |
| `.env.example` | 配置模板，复制为 `.env` 后填写密钥、关键词、预算、运行时间 |
| `tests/test_vibe_case_collector.py` | 基础校验测试 |
| `reports/` | 运行后自动生成的报告目录，不会提交到 Git |

## 2. 固定输出字段

每个案例都会按下面顺序输出，缺失公开资料时统一写「未披露」：

1. 案例编号
2. 产品名称
3. 创始人姓名+背景
4. 编程背景
5. 产品类型
6. 产品用途
7. 目标人群
8. 解决痛点
9. 收入模式
10. 月收入
11. 使用的AI工具
12. 开发时间
13. 数据来源+链接
14. 数据可信度（明星标准，仅限4档任选）
15. 是否单人项目
16. 风险点（四类各1条，缺一不可）
17. 机会点（四类各1条，缺一不可）

## 3. 第一次运行：零基础步骤

### 第 1 步：安装 Python

1. 打开浏览器，进入 <https://www.python.org/downloads/>
2. 点击黄色的 `Download Python` 按钮。
3. Windows 安装时一定勾选 `Add python.exe to PATH`。
4. 安装完成后，按 `Win + R`，输入 `cmd`，回车。
5. 输入下面命令检查是否安装成功：

```bash
python --version
```

能看到 `Python 3.x.x` 就可以继续。

如果提示 `python: command not found`，请把后续命令里的 `python` 改成 `python3`，例如：

```bash
python3 --version
```

### 第 2 步：用 Cursor 打开项目

1. 打开 Cursor。
2. 点击左上角 `File`。
3. 点击 `Open Folder...`。
4. 选择本项目文件夹。
5. 打开后按快捷键 ``Ctrl + ` ``，底部会出现终端窗口。

### 第 3 步：创建配置文件

在 Cursor 底部终端输入：

```bash
cp .env.example .env
```

Windows 如果 `cp` 不可用，可输入：

```cmd
copy .env.example .env
```

然后在左侧文件列表点击 `.env`，填写：

```env
LLM_API_KEY=你的真实API密钥
OPENAI_COMPATIBLE_API_URL=https://api.deepseek.com/chat/completions
LLM_MODEL=deepseek-chat
```

如果你使用的不是 DeepSeek，请把 `OPENAI_COMPATIBLE_API_URL` 和 `LLM_MODEL` 改成服务商给你的地址和模型名。

### 第 4 步：运行一次

在 Cursor 底部终端输入：

```bash
python vibe_case_collector.py --once
```

如果你的电脑提示 `python: command not found`，请改用：

```bash
python3 vibe_case_collector.py --once
```

运行完成后查看 `reports` 文件夹，会看到类似：

```text
vibe_coding_cases_2026-06-17.txt
vibe_coding_cases_2026-06-17.doc
```

## 4. 成本控制说明

`.env.example` 默认配置：

```env
MAX_DAILY_API_BUDGET_CNY=0.1
INPUT_TOKEN_PRICE_CNY_PER_1M=2
OUTPUT_TOKEN_PRICE_CNY_PER_1M=8
LLM_MAX_OUTPUT_TOKENS=2500
```

脚本在每次调用大模型前会先按“输入字符数约等于 token 数 + 最大输出 token 数”预留费用；如果预估会超过 0.1 元人民币，会立刻停止 API 抽取并输出当前报告，避免超额扣费。

如果服务商价格不同，只改这两项：

```env
INPUT_TOKEN_PRICE_CNY_PER_1M=你的输入价格
OUTPUT_TOKEN_PRICE_CNY_PER_1M=你的输出价格
```

## 5. 两套自动定时运行方案

### 方案 A：Cursor 常驻定时

适合一直开着电脑和 Cursor 的情况。

1. 打开 Cursor。
2. 打开本项目文件夹。
3. 按 ``Ctrl + ` `` 打开底部终端。
4. 确认 `.env` 里有：

```env
SCHEDULE_TIME=02:00
```

5. 输入：

```bash
python vibe_case_collector.py --daemon
```

如果 `python` 不可用，请改成：

```bash
python3 vibe_case_collector.py --daemon
```

6. 不要关闭这个终端窗口，也不要让电脑关机。脚本会每天到点自动运行。

想修改运行时间，把 `.env` 里的 `SCHEDULE_TIME=02:00` 改成你想要的时间，例如：

```env
SCHEDULE_TIME=08:30
```

### 方案 B：Windows 任务计划程序

适合不想一直开着 Cursor 的情况。

#### 图形界面做法

1. 按 `Win + R`。
2. 输入 `taskschd.msc`，回车。
3. 右侧点击 `创建基本任务...`。
4. 名称填写：`Vibe Coding 案例采集`。
5. 触发器选择：`每天`。
6. 时间填写：例如 `02:00:00`。
7. 操作选择：`启动程序`。
8. `程序或脚本` 填写 Python 路径，例如：

```text
C:\Users\你的用户名\AppData\Local\Programs\Python\Python312\python.exe
```

9. `添加参数` 填写：

```text
vibe_case_collector.py --once
```

10. `起始于` 填写本项目文件夹路径，例如：

```text
C:\Users\你的用户名\Desktop\vibe-case-collector
```

11. 点击完成。

#### 命令行做法

把下面命令里的路径改成你电脑上的真实路径：

```cmd
schtasks /Create /SC DAILY /ST 02:00 /TN "Vibe Coding 案例采集" /TR "\"C:\Users\你的用户名\AppData\Local\Programs\Python\Python312\python.exe\" \"C:\Users\你的用户名\Desktop\vibe-case-collector\vibe_case_collector.py\" --once"
```

## 6. 自定义修改

### 修改搜索关键词

打开 `.env`，找到：

```env
SEARCH_KEYWORDS=Vibe Coding独立创业案例;Vibe Coding无代码SaaS项目;个人开发者Vibe Coding变现;轻量化AI工具Vibe Coding副业;一人AI SaaS创业Vibe Coding
```

用英文分号 `;` 分隔多个关键词。

### 修改每天最多花多少钱

打开 `.env`，找到：

```env
MAX_DAILY_API_BUDGET_CNY=0.1
```

例如改成 `0.05` 就是每天最多约 5 分钱。

### 修改抓取深度

打开 `.env`，可调整：

```env
SEARCH_MAX_RESULTS_PER_KEYWORD=5
MAX_PAGES_TO_FETCH=12
MAX_CASES_PER_DAY=8
```

数字越大，搜索越深，但大模型输入也可能变多，更容易触发预算停止。

## 7. 常见报错和修复

### 报错：`[配置错误] 请在 .env 中配置 SEARCH_KEYWORDS`

说明没有创建 `.env`，或 `.env` 里没有关键词。

修复：

```bash
cp .env.example .env
```

然后检查 `.env` 里的 `SEARCH_KEYWORDS=` 不为空。

### 报错：`HTTP 401`

通常是 API 密钥错误或没有权限。

修复：

1. 打开 `.env`。
2. 检查 `LLM_API_KEY=` 后面是否粘贴了完整密钥。
3. 检查服务商后台余额和模型权限。

### 报错：`HTTP 404` 或模型不存在

通常是接口地址或模型名不对。

修复：

1. 检查 `OPENAI_COMPATIBLE_API_URL`。
2. 检查 `LLM_MODEL`。
3. 确认接口是 `chat/completions` 兼容格式。

### 提示：`API预算不足`

说明继续调用会超过 `.env` 里设置的费用上限。

修复方法：

- 想省钱：不用修，脚本已经按规则停止。
- 想多抓一点：调小 `MAX_PAGES_TO_FETCH` 或调大 `MAX_DAILY_API_BUDGET_CNY`。

### 报告里写“未检索到通过公开来源校验的案例”

说明本次搜索抓到的网页里，没有同时满足“真实产品 + 公开链接 + 字段校验”的案例。

修复：

1. 换更具体的关键词。
2. 增大 `MAX_PAGES_TO_FETCH`。
3. 确认网络能访问搜索结果和网页。

### Word 打开 DOC 提示格式不匹配

本项目生成的是 Word 可打开的 HTML 格式 `.doc` 文件。出现提示时点击“是”即可打开。若公司电脑限制严格，可优先使用同名 `.txt` 文件。

## 8. 本地测试

在项目根目录运行：

```bash
python -m unittest discover -s tests
```

如果 `python` 不可用，请运行：

```bash
python3 -m unittest discover -s tests
```

看到 `OK` 表示字段模板和预算控制基础逻辑正常。