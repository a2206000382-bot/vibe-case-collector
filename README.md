# Vibe Coding 独立创业案例采集器

这是一个面向零基础用户的 Python 自动化脚本，用来每天检索公开网页中的 **Vibe Coding / AI Coding / 独立开发 / AI SaaS** 真实落地案例，并生成两份本地文档：

- `TXT` 纯文本报告
- `DOC` 文档报告（Word/WPS 可打开）

脚本会按固定 20 个字段输出，并把结果分为：

1. 正式收录案例
2. 候选案例
3. 今日线索池
4. 跳过案例清单
5. 今日搜索总结
6. 下一步建议关键词

> 重要：API 密钥只放本地 `.env` 文件，`.env` 已被 `.gitignore` 忽略，不能上传到 GitHub。

---

## 1. 目录说明

```text
vibe_case_collector.py  主程序
.env.example            配置模板：关键词、预算、运行时间、API 配置都在这里改
requirements.txt        需要安装的 Python 组件清单
tests/                  自动检查脚本基本逻辑
reports/                每天生成的报告目录，运行后自动创建
```

---

## 2. 第一次安装：一步一步照做

### 2.1 打开 Cursor 终端

1. 用 Cursor 打开本项目文件夹。
2. 点击顶部菜单 `Terminal`。
3. 点击 `New Terminal`。
4. 也可以直接按快捷键：
   - Windows：`Ctrl + 反引号`，反引号通常在键盘左上角 `Esc` 下方。
   - macOS：`Control + 反引号`。

### 2.2 安装 Python 依赖

在 Cursor 底部终端里逐行输入：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果终端提示 `python: command not found`，把上面所有 `python` 改成 `python3`：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Windows 用户在 PowerShell 中激活虚拟环境时使用：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

如果 PowerShell 提示不能运行脚本，先执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

然后重新运行激活命令。

---

## 3. 配置 `.env`

### 3.1 复制配置模板

Linux/macOS：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

### 3.2 在 Cursor 里填写配置

1. 在左侧文件列表点击 `.env`。
2. 找到 `OPENAI_API_KEY=`。
3. 把你的 API key 粘贴在等号后面。
4. 保存文件：
   - Windows/Linux：`Ctrl + S`
   - macOS：`Command + S`

示例格式：

```text
OPENAI_API_KEY=你的key粘贴在这里
OPENAI_BASE_URL=https://api.moonshot.cn/v1
LLM_MODEL=kimi-k2.6
```

说明：Kimi 平台的模型名通常不是单独的 `kimi`，而是类似 `kimi-k2.6`、`kimi-k2.7-code`。如果不确定，可以先使用 `.env.example` 里的 `kimi-k2.6`。

### 3.3 默认是否会调用大模型？

默认会。后续每一次检索都会调用 API 做一次输出前整理复核：

```text
USE_LLM_EXTRACTION=true
REQUIRE_LLM_EXTRACTION=true
```

如果没有填写 `OPENAI_API_KEY`，程序会直接停止并提示你补 key，避免误以为已经完成 API 辅助整理。

预算仍会被程序强制锁在每天不超过：

```text
DAILY_API_BUDGET_RMB=0.10
```

即使你误填更高，程序也会自动按 0.10 元人民币封顶。

---

## 4. 手动运行一次

在终端中确认已经看到 `(.venv)`，然后运行：

```bash
python vibe_case_collector.py --env .env
```

如果你的电脑只能使用 `python3`，则运行：

```bash
python3 vibe_case_collector.py --env .env
```

运行完成后会看到类似：

```text
TXT 已生成：.../reports/vibe_cases_2026-06-17.txt
DOC 已生成：.../reports/vibe_cases_2026-06-17.doc
--- 可复制报告文本开始 ---
这里会完整打印一份可以直接复制的报告正文
--- 可复制报告文本结束 ---
```

打开左侧 `reports` 文件夹，即可查看每日报告。终端里也会同步打印完整可复制文本，方便直接复制给聊天窗口、文档或表格。

如果你只想生成文件、不想在终端打印完整报告，可以运行：

```bash
python3 vibe_case_collector.py --env .env --no-print-report
```

---

## 5. 固定输出字段

每条正式案例、候选案例、今日线索都会完整展示 20 个字段：

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

缺少公开资料的字段统一写 `未披露`。

---

## 6. 收录规则

### 6.1 正式收录案例

要求至少具备：

- 产品名称明确
- 产品用途明确
- 来源链接可访问
- 数据可信度可判断
- 和 Vibe Coding / AI Coding / 独立开发 / AI SaaS 范围匹配

脚本不会为了凑数把无关内容放进正式案例。当天正式案例可以为 0。

### 6.2 候选案例

适合放入候选的情况：

- 产品名称和用途比较明确
- 但创始人、收入、开发时间等字段缺失
- 或产品类型和聚焦范围需要人工确认

### 6.3 今日线索池

只要和以下方向相关，就可以先进入线索池：

- Vibe Coding
- AI Coding
- 独立开发
- AI SaaS
- Cursor / Claude Code / Lovable / Bolt.new / Replit Agent 等工具生态

线索池不是正式案例，需要人工复核。

### 6.4 跳过案例清单

以下内容会被跳过：

- 纯概念文章
- 没有产品名称
- 没有来源链接
- 和主题无关
- 重复产品

---

## 7. 两套自动定时运行方案

### 7.1 方案 A：Cursor 常驻定时

适合：电脑或云端 Cursor 一直开着。

步骤：

1. 打开 Cursor。
2. 打开本项目。
3. 打开终端。
4. 激活虚拟环境：

   ```bash
   source .venv/bin/activate
   ```

   Windows PowerShell：

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

5. 运行常驻模式：

   ```bash
   python vibe_case_collector.py --env .env --watch
   ```

6. 终端会显示：

   ```text
   常驻定时已启动。每天 09:00 运行；按 Ctrl+C 停止。
   ```

7. 不要关闭这个终端窗口。到时间后脚本会自动生成当天报告。

修改运行时间：

1. 打开 `.env`。
2. 找到：

   ```text
   RUN_AT_HHMM=09:00
   ```

3. 改成你想要的时间，例如晚上 8 点：

   ```text
   RUN_AT_HHMM=20:00
   ```

4. 保存后重启常驻命令。

### 7.2 方案 B：Windows 任务计划程序

适合：想让 Windows 系统每天自动触发。

步骤：

1. 点击 Windows 开始菜单。
2. 搜索 `任务计划程序`。
3. 点击右侧 `创建基本任务`。
4. 名称填写：

   ```text
   Vibe Coding 案例采集
   ```

5. 触发器选择 `每天`。
6. 时间填写你想运行的时间，例如 `09:00`。
7. 操作选择 `启动程序`。
8. `程序或脚本` 填 Python 的完整路径。

   如果你不确定 Python 在哪里，在 PowerShell 输入：

   ```powershell
   where python
   ```

9. `添加参数` 填：

   ```text
   vibe_case_collector.py --env .env
   ```

10. `起始于` 填本项目文件夹路径，例如：

    ```text
    C:\Users\你的名字\vibe-case-collector
    ```

11. 点击完成。

建议第一次设置后，右键任务，点击 `运行`，确认 `reports` 文件夹里能生成报告。

---

## 8. 修改关键词、预算、运行时间

全部在 `.env` 里修改。

### 8.1 修改中文关键词

找到：

```text
SEARCH_KEYWORDS_ZH=Vibe Coding 独立创业案例|Vibe Coding 无代码 SaaS 项目|...
```

每个关键词之间用 `|` 分隔。

### 8.2 修改英文关键词

找到：

```text
SEARCH_KEYWORDS_EN=vibe coding indie hacker|built with Cursor startup|...
```

也用 `|` 分隔。

### 8.3 修改公开种子来源

如果搜索引擎当天返回结果很少，可以在 `.env` 里维护公开来源链接：

```text
SEED_SOURCE_URLS=标题@@https://example.com/article|另一个标题@@https://example.com/another
```

规则：

- `标题` 用来帮助脚本识别产品名。
- `@@` 后面放公开可访问链接。
- 多条之间用 `|` 分隔。
- 不确定的链接可以先放进种子来源，脚本会把信息不足的内容放入候选或线索，不会强行变正式案例。

### 8.4 修改预算

找到：

```text
DAILY_API_BUDGET_RMB=0.10
```

为了防止误扣费，程序内部会强制不超过 0.10 元人民币。

### 8.5 修改搜索数量

找到：

```text
MAX_RESULTS_PER_KEYWORD=5
MAX_FETCHED_PAGES=18
```

零基础建议先不要调太大。网页检索本身不消耗 API token，但太大可能会变慢或被搜索网站限制。

### 8.6 修改是否在终端输出完整报告

默认会输出完整可复制文本，同时保留 `.txt` 和 `.doc` 文件：

```text
PRINT_REPORT_TEXT=true
```

如果只想生成文件、不想在终端显示完整报告，改成：

```text
PRINT_REPORT_TEXT=false
```

---

## 9. 常见报错和修复

### 9.1 `缺少依赖，请先运行：pip install -r requirements.txt`

原因：没有安装依赖。

修复：

```bash
pip install -r requirements.txt
```

### 9.2 `未找到搜索关键词`

原因：没有 `.env`，或 `.env` 里关键词为空。

修复：

```bash
cp .env.example .env
```

然后检查：

```text
SEARCH_KEYWORDS_ZH=...
SEARCH_KEYWORDS_EN=...
```

### 9.3 搜索失败或页面读取失败

可能原因：

- 网络暂时不可用
- 搜索引擎限制访问
- 某些网站需要登录

修复办法：

1. 重新运行一次。
2. 把 `MAX_RESULTS_PER_KEYWORD` 调小。
3. 把 `REQUEST_DELAY_SECONDS` 调大，例如：

   ```text
   REQUEST_DELAY_SECONDS=2
   ```

4. 手动把重要线索加入下一轮关键词。

### 9.4 没有正式案例

这是正常情况。脚本会严格过滤，不会为了数量把无关内容放入正式案例。

可检查：

- `二、候选案例`
- `三、今日线索池`
- `四、跳过案例清单`
- `六、下一步建议关键词`

---

## 10. 数据可信度标准

```text
★★★★ 官方公告：
官网、产品页、公开收入面板、GitHub README、官方博客等一手资料。

★★★ 媒体报道：
科技媒体、播客、Newsletter、行业文章等第三方公开报道。

★★ 创始人自报：
X/Twitter、Indie Hackers、Reddit、访谈、个人博客等创始人本人说明。

★ 匿名推测：
论坛讨论、二手转载、无法确认来源的信息。
```

---

## 11. 每次采集后的复盘

报告末尾会自动生成：

- 今日搜索总结
- 运行逻辑总结
- 结果总结
- 下一步建议关键词
- Agent Instructions 优化建议

建议你每天看这三处：

1. `缺失字段`：决定下一轮要补什么资料。
2. `复核建议`：决定是否升级为正式案例。
3. `下一步建议关键词`：复制到 `.env` 的关键词列表中继续深挖。

---

## 12. 给后续 Agent Instructions 的优化建议

如果你想让自动化越来越准，可以逐步加入这些约束：

1. 正式案例必须至少有两类来源：产品官网 + 创始人自述，或创始人自述 + 第三方报道。
2. 明确排除大型平台公司，只把 Lovable、Bolt.new、Cursor 当作生态线索。
3. 明确排除游戏、课程平台、纯内容站，除非当天主题允许。
4. 收入字段优先 MRR，其次 ARR，再其次一次性收入线索。
5. 每天最多正式收录 3 条，候选 5 条，线索 10 条，避免报告过长。
6. 对“存疑出现多个”的收入或开发周期，要求下一轮专门复核原始创始人链接。