# Vibe Coding 案例采集器小白操作教程

本教程假设你不会写代码，只按步骤点击和复制即可。

## 1. 你会得到什么

每天运行后，程序会在 `reports/日期/` 文件夹里生成两份文件：

- `vibe_cases_日期.txt`：纯文本报告。
- `vibe_cases_日期.doc`：Word 可打开的文档报告。

报告固定包含：

1. 正式收录案例
2. 候选案例
3. 今日线索池
4. 跳过案例清单
5. 今日搜索总结
6. 下一步建议关键词

所有案例统一输出 20 个字段，缺失公开资料时统一写「未披露」。

## 2. 第一次安装

### 2.1 安装 Python

1. 打开浏览器，进入 <https://www.python.org/downloads/>。
2. 点击黄色按钮下载 Python。
3. 双击安装包。
4. Windows 安装第一页一定勾选 **Add python.exe to PATH**。
5. 点击 **Install Now**。
6. 安装完成后点击 **Close**。

### 2.2 在 Cursor 打开项目

1. 打开 Cursor。
2. 左上角点击 **File**。
3. 点击 **Open Folder...**。
4. 选择本项目文件夹。
5. 点击 **Open**。

### 2.3 创建 `.env` 配置文件

1. 在 Cursor 左侧文件列表找到 `.env.example`。
2. 右键点击 `.env.example`。
3. 点击 **Duplicate** 或复制粘贴一份。
4. 把新文件改名为 `.env`。
5. 打开 `.env`。
6. 把 `API_KEY=请把你的API密钥填在这里` 后面的中文替换成你的真实 API 密钥。
7. 按 `Ctrl+S` 保存。

注意：`.env` 已被 Git 忽略，不会提交到代码仓库。

## 3. 手动运行一次

1. 在 Cursor 顶部菜单点击 **Terminal**。
2. 点击 **New Terminal**。
3. 在下方黑色窗口输入：

```bash
python vibe_case_collector.py
```

如果 Windows 提示找不到 `python`，改用：

```bash
py -3 vibe_case_collector.py
```

看到类似下面内容就成功了：

```text
采集完成
TXT：reports/2026-06-18/vibe_cases_2026-06-18.txt
DOC：reports/2026-06-18/vibe_cases_2026-06-18.doc
案例/线索数量：若干
API估算消耗：0.000000 元人民币 / 0.10 元人民币
```

## 4. API 预算保护怎么开

默认配置：

```text
ENABLE_LLM_ENRICHMENT=false
MAX_DAILY_BUDGET_CNY=0.10
```

含义：

- `false`：不开启大模型精读，只用公开搜索结果生成报告，最省钱。
- `true`：开启大模型精读，程序会在每天 0.1 元人民币预算内调用 API。
- 达到预算上限前，程序会停止后续 API 调用，避免超额。

如果要开启精读：

1. 打开 `.env`。
2. 把 `ENABLE_LLM_ENRICHMENT=false` 改成 `ENABLE_LLM_ENRICHMENT=true`。
3. 确认 `API_KEY=` 后面已经填入真实密钥。
4. 按 `Ctrl+S` 保存。
5. 重新运行 `python vibe_case_collector.py`。

## 5. 修改搜索关键词

打开 `.env`，找到：

```text
SEARCH_KEYWORDS=Vibe Coding 独立创业案例|Vibe Coding 无代码 SaaS 项目|...
```

每个关键词之间用英文竖线 `|` 分隔。

示例：

```text
SEARCH_KEYWORDS=built with Cursor revenue founder interview|site:indiehackers.com Cursor AI SaaS revenue|Lovable founder revenue case study
```

保存后重新运行即可。

## 6. 修改运行时间

如果使用 Cursor 常驻定时，在 `.env` 最后一行增加：

```text
RUN_AT_LOCAL_TIME=08:00
```

想改成晚上 9 点，就写：

```text
RUN_AT_LOCAL_TIME=21:00
```

## 7. 定时方案一：Cursor 常驻定时

适合：电脑常开、Cursor 常开的人。

1. 打开 Cursor。
2. 顶部点击 **Terminal**。
3. 点击 **New Terminal**。
4. 输入：

```bash
python scripts/run_daily_cursor.py
```

Windows 如果失败，输入：

```bash
py -3 scripts/run_daily_cursor.py
```

5. 看到“Cursor 常驻定时已启动”即可。
6. 不要关闭 Cursor，不要关闭这个终端窗口。
7. 想停止时，在终端按 `Ctrl+C`。

## 8. 定时方案二：Windows 任务计划程序

适合：不想一直打开 Cursor，但电脑每天会开机的人。

### 8.1 先确认批处理能运行

1. 打开项目文件夹。
2. 进入 `scripts` 文件夹。
3. 双击 `run_collector_windows.bat`。
4. 如果看到“运行完成。报告在 reports 文件夹中。”，说明可以继续。

### 8.2 创建 Windows 定时任务

1. 按键盘 `Win` 键。
2. 输入“任务计划程序”。
3. 点击打开 **任务计划程序**。
4. 右侧点击 **创建基本任务...**。
5. 名称填写：`Vibe Coding 案例采集`。
6. 点击 **下一步**。
7. 选择 **每天**。
8. 点击 **下一步**。
9. 设置你想运行的时间，例如 `08:00:00`。
10. 点击 **下一步**。
11. 选择 **启动程序**。
12. 点击 **下一步**。
13. “程序或脚本”点击 **浏览...**。
14. 选择项目里的 `scripts/run_collector_windows.bat`。
15. “起始于”填写项目文件夹路径，例如：

```text
C:\Users\你的用户名\Desktop\vibe-case-collector
```

16. 点击 **下一步**。
17. 点击 **完成**。

## 9. 常见报错和修复

### 9.1 `python 不是内部或外部命令`

原因：Windows 没把 Python 加到 PATH。

修复：

1. 先试试 `py -3 vibe_case_collector.py`。
2. 如果还不行，重新安装 Python。
3. 安装第一页勾选 **Add python.exe to PATH**。

### 9.2 `API 精读失败`

原因可能是密钥、接口地址或模型名不对。

修复：

1. 打开 `.env`。
2. 检查 `API_KEY=` 后面有没有多余空格。
3. 检查 `OPENAI_COMPATIBLE_BASE_URL=` 是否和你的平台文档一致。
4. 检查 `OPENAI_MODEL=` 是否是平台支持的模型名。
5. 如果只想先生成报告，把 `ENABLE_LLM_ENRICHMENT=true` 改回 `false`。

### 9.3 报告里正式案例为 0

这是正常情况。规则要求不为了凑数把无关内容放入正式案例。

你可以先看：

- 二、候选案例
- 三、今日线索池
- 四、跳过案例清单

再人工挑选可信线索复核。

### 9.4 搜索结果太少

修复：

1. 打开 `.env`。
2. 把 `MAX_RESULTS_PER_KEYWORD=6` 改成 `10`。
3. 把 `MAX_FETCH_PAGES=10` 改成 `20`。
4. 增加更精准的关键词，例如：

```text
site:x.com "built with Cursor" "MRR"
site:indiehackers.com "built with Claude" SaaS
```

### 9.5 预算不够

修复：

1. 保持 `MAX_DAILY_BUDGET_CNY=0.10` 可严格控费。
2. 减少 `MAX_FETCH_PAGES`。
3. 减少关键词数量。
4. 或关闭精读：`ENABLE_LLM_ENRICHMENT=false`。

## 10. 输出规则提醒

- 无公开资料：统一写「未披露」。
- 多个冲突数据：写「存疑出现多个」，并列全部值。
- 没有来源链接：不能进入正式案例。
- 纯概念文章：不能进入正式案例。
- 重复产品：只保留一次。
- 被跳过内容：写入文档末尾，并说明跳过原因。
