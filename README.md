# Vibe Coding 独立创业案例自动采集脚本

这是一个面向零基础用户的自动化采集工具。它会按 `.env` 里的关键词检索公开网页，抓取页面文字，再调用你配置的 OpenAI 兼容大模型，把公开可查证的 Vibe Coding 个人/小团队 AI 工具创业案例整理成高完整度报告，并每天生成两份本地文件：

- `outputs/vibe_coding_cases_日期.txt`
- `outputs/vibe_coding_cases_日期.docx`

> 注意：需求标题写“16个字段”，但实际清单编号包含 1 到 17。脚本按用户列出的 17 项全部输出，不会省略第 17 项“机会点”。

## 1. 脚本严格遵守的采集规则

1. 只检索公开可访问网页，不内置、不伪造任何案例。
2. 没有公开资料的字段统一写：`未披露`。
3. 同一字段出现冲突数据时，要求模型以 `存疑：...` 开头并列出全部数值。
4. 开启质量增强后，脚本会围绕产品名二次检索多个公开来源，再补全和纠错。
5. 禁止把“推断/可能/猜测/似乎”写进关键字段；只能推断时仍然写 `未披露`。
6. 达不到完整度门槛的候选不会进入正式案例，会放到“信息不足候选”区。
7. 每个正式案例会输出 21 个字段：
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
   14. 数据可信度
   15. 是否单人项目
   16. 风险点
   17. 机会点
   18. 公开证据摘要
   19. 仍缺失字段
   20. 数据完整度评分
   21. 复核说明
8. 脚本会记录每天已使用的模型 API 成本，默认每日上限是 `0.1` 元人民币；达到或接近上限时，自动停止后续关键词和网页抽取。

## 2. 文件说明

| 文件 | 作用 |
| --- | --- |
| `vibe_case_collector.py` | 主程序，负责检索、抓取、抽取、校验、输出 TXT 和 DOCX |
| `.env` | 配置文件，存放 API Key、预算、关键词、运行时间等 |
| `.env.example` | 可提交的配置模板，不包含真实 API Key |
| `requirements.txt` | 需要安装的 Python 工具清单 |
| `.gitignore` | 忽略运行时生成的缓存、输出文件夹和虚拟环境 |

## 3. 第一次使用：Cursor 里一步一步操作

### 第 1 步：打开文件夹

1. 打开 Cursor。
2. 点击左上角菜单：`File`。
3. 点击：`Open Folder...`。
4. 选择本项目文件夹。
5. 点击 `Open`。

### 第 2 步：打开命令行窗口

1. 在 Cursor 顶部菜单点击：`Terminal`。
2. 点击：`New Terminal`。
3. 下方会出现一个黑色或深色的小窗口。

如果你喜欢快捷键：

- Windows：按 `Ctrl + Shift + \``
- macOS：按 `Control + Shift + \``

### 第 3 步：安装 Python

先在命令行窗口输入：

```bash
python --version
```

如果能看到类似 `Python 3.11.8`，说明已安装。

如果提示找不到 `python`，再试一次：

```bash
python3 --version
```

如果 `python3` 能显示版本号，后面教程里的 `python` 都可以替换成 `python3`。

如果提示找不到 Python：

1. 打开浏览器。
2. 访问：<https://www.python.org/downloads/>
3. 下载最新版 Python。
4. Windows 安装时一定勾选：`Add python.exe to PATH`。
5. 安装完成后，关闭 Cursor 再重新打开。

### 第 4 步：创建独立运行环境

在 Cursor 的命令行窗口逐行输入：

```bash
python -m venv .venv
```

如果你的电脑只识别 `python3`，就输入：

```bash
python3 -m venv .venv
```

Windows 用户继续输入：

```bash
.venv\Scripts\activate
```

macOS / Linux 用户输入：

```bash
source .venv/bin/activate
```

看到命令行前面出现 `(.venv)`，表示成功。

### 第 5 步：安装依赖

继续输入：

```bash
pip install -r requirements.txt
```

如果提示找不到 `pip`，使用：

```bash
python3 -m pip install -r requirements.txt
```

等它运行结束，不要中途关闭窗口。

### 第 6 步：填写 `.env`

1. 在 Cursor 左侧文件列表中点击 `.env`。
2. 找到这一行：

```env
LLM_API_KEY=
```

3. 在等号后面粘贴你的模型 API Key，例如：

```env
LLM_API_KEY=你的真实APIKey
```

4. 按 `Ctrl + S` 保存。

不要把 API Key 发给别人，也不要截图给别人。

## 4. 手动运行一次

在 Cursor 命令行窗口输入：

```bash
python vibe_case_collector.py
```

如果你的电脑只识别 `python3`，就输入：

```bash
python3 vibe_case_collector.py
```

运行结束后，打开左侧的 `outputs` 文件夹，可以看到：

- TXT 纯文本文件
- DOCX Word 文件

如果 `.env` 里没有填写 `LLM_API_KEY`，脚本不会调用付费接口，会生成一份空报告，方便你先确认安装没问题。

## 5. 固定输出模板示例

每个案例都会按下面顺序排版：

```text
1. 案例编号：1
2. 产品名称：产品完整对外名称
3. 创始人姓名+背景：创始人全名+职业/过往从业经历；无公开信息填未披露
4. 编程背景：有/无/自学/未披露
5. 产品类型：SaaS订阅工具/本地客户端/网页插件/API服务/开源免费工具/未披露
6. 产品用途：一句话说明核心功能
7. 目标人群：清晰划分使用群体
8. 解决痛点：①痛点1 ②痛点2 ③痛点3
9. 收入模式：SaaS月订阅/一次性买断/API按量收费/广告变现/企业定制服务/未披露
10. 月收入：5万元人民币（$7200美元）/存疑/未披露
11. 使用的AI工具：Cursor、Claude、DeepSeek 等；无资料填未披露
12. 开发时间：从启动开发到上线 MVP 总周期；无资料填未披露
13. 数据来源+链接：信息出处+公开链接
14. 数据可信度（星级标准，仅4档可选）：★/★★/★★★/★★★★
15. 是否单人项目：是，团队规模：1人 / 否，团队规模：... / 未披露
16. 风险点（四类各1条，缺一不可）：
   - 合规风险：...
   - 平台依赖风险：...
   - 市场竞争风险：...
   - 长期运营风险：...
17. 机会点（四类各1条，缺一不可）：
   - 横向扩展场景：...
   - 纵向功能深化：...
   - B端企业转化：...
   - 细分生态位卡位：...
```

## 6. Cursor 常驻定时运行方案

这种方式适合电脑或云机器一直开着的场景。

### 操作步骤

1. 打开 Cursor。
2. 打开本项目文件夹。
3. 打开命令行窗口：`Terminal` -> `New Terminal`。
4. 激活环境：

Windows：

```bash
.venv\Scripts\activate
```

macOS / Linux：

```bash
source .venv/bin/activate
```

5. 启动常驻定时：

```bash
python vibe_case_collector.py --loop
```

macOS / Linux 用户也可以直接输入：

```bash
bash run_cursor_loop.sh
```

6. 保持 Cursor 和这个命令行窗口不要关闭。

脚本会读取 `.env` 里的：

```env
RUN_TIME=09:00
```

意思是每天本机时间 09:00 自动运行一次。

如果想改成晚上 8 点半，把它改成：

```env
RUN_TIME=20:30
```

保存后，重新停止并启动 `--loop` 命令。

停止方式：

- 在命令行窗口按 `Ctrl + C`。

## 7. Windows 任务计划程序 Triggers 系统定时方案

这种方式适合 Windows 电脑，不需要一直盯着 Cursor。

### 第 1 步：确认项目路径

假设你的项目文件夹在：

```text
C:\Users\你的用户名\Desktop\vibe-case-collector
```

请把下面示例里的路径换成你自己的真实路径。

### 第 2 步：打开任务计划程序

1. 按键盘 `Win + S`。
2. 输入：`任务计划程序`。
3. 点击打开。

### 第 3 步：创建基本任务

1. 右侧点击：`创建基本任务...`
2. 名称填写：`Vibe Coding 案例每日采集`
3. 点击：`下一步`

### 第 4 步：设置 Triggers

1. 选择：`每天`
2. 点击：`下一步`
3. 设置开始时间，例如：`09:00:00`
4. 点击：`下一步`

### 第 5 步：设置操作

1. 选择：`启动程序`
2. 点击：`下一步`
3. `程序或脚本` 填：

```text
C:\Users\你的用户名\Desktop\vibe-case-collector\.venv\Scripts\python.exe
```

4. `添加参数` 填：

```text
vibe_case_collector.py
```

5. `起始于` 填项目文件夹路径：

```text
C:\Users\你的用户名\Desktop\vibe-case-collector
```

6. 点击：`下一步`
7. 点击：`完成`

如果你想更简单，也可以把 `程序或脚本` 直接填成项目里的批处理文件：

```text
C:\Users\你的用户名\Desktop\vibe-case-collector\run_once_windows.bat
```

这种方式不需要填写 `添加参数`，但 `起始于` 仍然建议填写项目文件夹路径。

### 第 6 步：测试任务

1. 在任务计划程序左侧点击：`任务计划程序库`
2. 找到：`Vibe Coding 案例每日采集`
3. 右键它
4. 点击：`运行`
5. 回到项目文件夹，查看 `outputs` 是否生成文件

## 8. 修改关键词、预算、运行时间

所有常用修改都在 `.env` 文件里完成。

### 修改关键词

找到：

```env
SEARCH_KEYWORDS=Vibe Coding独立创业案例|Vibe Coding无代码SaaS项目|个人开发者Vibe Coding变现|轻量化AI工具Vibe Coding副业|一人AI SaaS创业Vibe Coding
```

多个关键词之间用英文竖线 `|` 分隔。例如：

```env
SEARCH_KEYWORDS=Vibe Coding SaaS revenue|AI solo founder Cursor|个人开发者AI工具收入
```

### 修改每日预算

找到：

```env
DAILY_BUDGET_CNY=0.1
```

如果要改成 0.2 元：

```env
DAILY_BUDGET_CNY=0.2
```

### 修改数据完整度门槛

找到：

```env
MIN_COMPLETENESS_SCORE=0.72
```

含义：完整度低于 72% 的候选案例不进入正式案例。

如果你想更严格，例如只要更完整的案例：

```env
MIN_COMPLETENESS_SCORE=0.8
```

如果你想多收录一些，但允许更多“未披露”：

```env
MIN_COMPLETENESS_SCORE=0.6
```

### 开启或关闭二次补全

默认开启：

```env
ENABLE_ENRICHMENT=true
ENRICHMENT_RESULTS_PER_CASE=4
```

这会让脚本围绕每个候选产品追加检索多个来源，结果更完整，但会多消耗 API Token。

如果只想省钱快速跑：

```env
ENABLE_ENRICHMENT=false
```

### 修改运行时间

找到：

```env
RUN_TIME=09:00
```

改成你想要的时间，例如晚上 10 点：

```env
RUN_TIME=22:00
```

## 9. 常见报错和修复

### 报错：`python 不是内部或外部命令`

原因：电脑没有安装 Python，或安装时没有加入 PATH。

修复：

1. 先试试：

```bash
python3 --version
```

如果能显示版本，后续命令把 `python` 换成 `python3` 即可。

如果仍然找不到：

1. 重新安装 Python。
2. 安装时勾选 `Add python.exe to PATH`。
3. 重启 Cursor。

### 报错：`ModuleNotFoundError`

原因：依赖没有安装。

修复：

```bash
pip install -r requirements.txt
```

如果你使用了虚拟环境，请先激活 `.venv`。

### 报错：`LLM_API_KEY 为空`

原因：`.env` 没有填模型 API Key。

修复：

1. 打开 `.env`。
2. 找到 `LLM_API_KEY=`。
3. 在等号后粘贴你的 API Key。
4. 保存后重新运行。

### 报错：搜索失败或没有结果

可能原因：

- 网络暂时不稳定。
- DuckDuckGo 当前不可用。
- 关键词太窄。

修复：

1. 稍后重新运行。
2. 换一组关键词。
3. 如果你有 Serper API Key，可把 `.env` 改成：

```env
SEARCH_PROVIDER=serper
SERPER_API_KEY=你的SerperKey
```

### 报错：`已达到或接近单日预算上限`

这不是故障，说明脚本按规则停止了付费模型调用。

如果你确认要提高预算，修改：

```env
DAILY_BUDGET_CNY=0.2
```

### Word 文件打不开

可能原因：运行中被中断，文件没写完。

修复：

1. 删除当天生成的 `.docx` 文件。
2. 重新运行：

```bash
python vibe_case_collector.py
```

## 10. 数据可信度星级说明

脚本要求模型只能使用以下 4 档：

| 星级 | 含义 |
| --- | --- |
| ★ | 匿名推测，无任何公开佐证，仅网友讨论猜想 |
| ★★ | 创始人自报，来自创始人社交平台或采访亲口说明 |
| ★★★ | 媒体报道，来自科技媒体、行业专栏公开报道 |
| ★★★★ | 官方公告，来自产品官网、官方财报、公开数据后台 |

## 11. 运行后会产生哪些文件

```text
outputs/
  vibe_coding_cases_2026-06-16.txt
  vibe_coding_cases_2026-06-16.docx

.run_state/
  budget_2026-06-16.json
```

`.run_state` 里的文件用于记录当天已花费的模型 API 费用，避免重复运行时超预算。
