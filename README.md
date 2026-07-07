# IRA — 投研智能体

基于 MCP 的私有买方投研系统。接入本地私有知识库（财务数据库 + 研报向量库 + 产业链图谱），通过多 Agent 协作给出有据可查、观点鲜明的投资判断。

## 架构概览

```
Claude Desktop / Codex
        ↕ MCP (stdio)
   mcp_server.py          ← 10 个 MCP 工具
        ↕
   Skills 1–5             ← 单工具查询层
   Agents (5 岗位)        ← 多 Agent 编排层
        ↕
   SQLite / LanceDB / Kùzu ← 本地数据层
```

### 数据层

| 存储 | 内容 | 路径 |
|---|---|---|
| SQLite | 财务报表、历史股价 | `databases/ira.db` |
| LanceDB | 研报/公告向量切片 | `data/storage/lancedb_root/` |
| Kùzu | 产业链图谱（公司↔产品↔上下游） | `data/storage/kuzu_root.db` |

> 注意：`databases/ira.db` 是唯一 SQLite 主库。不要使用 `data/financial.db` 作为财务库；若该文件存在且为 0 字节，它只是误建的影子文件，不代表财务数据丢失。

### Skills（单工具层）

| Skill | 文件 | 功能 |
|---|---|---|
| 1 | `skill1_text2sql.py` | 自然语言 → SQL → SQLite |
| 2 | `skill2_calculator.py` | 财务指标同比/环比计算（纯 Python）|
| 3 | `skill3_graph_propagator.py` | Kùzu 图谱：上游商品 → 受影响公司 |
| 4 | `skill4_verifier.py` | 多源对抗审查报告 |
| 5 | `skill5_focused.py` | 5 个快捷分析（业绩/股价/边际/图谱/风险）|
| 6 | `skill6_event_catalyst.py` | 事件驱动催化分析（YFinance 宏观 + Tushare 新闻）|

### Agents（多 Agent 层）

按基金公司岗位职责划分，顺序编排：

```
研究员 → 风控 + 策略 + 交易员 → PM
```

| Agent | 职责 |
|---|---|
| 研究员 | 整理原始数据，输出结构化事实清单，不作判断 |
| 风控 | 对抗式审查，挑矛盾、找盲区，悲观视角 |
| 策略 | 估值建模（PE/PS/PB）、业绩区间预测 |
| 交易员 | 边际变化、催化剂、入场时机 |
| PM | 综合四方报告，给出买/卖/持有结论和仓位建议 |

### MCP 工具（10 个）

| 工具 | 层级 | 说明 |
|---|---|---|
| `text2sql` | Skill 1 | 自然语言查财务数据库 |
| `financial_dashboard` | Skill 2 | 财务看板（无 LLM）|
| `graph_propagation` | Skill 3 | 产业链传导查询 |
| `adversarial_report` | Skill 4 | 对抗式投研报告 |
| `earnings_forecast` | Skill 5 | 预测业绩 |
| `price_target` | Skill 5 | 预测股价 |
| `marginal_change` | Skill 5 | 边际改变 |
| `relationship_graph` | Skill 5 | 关系图谱 |
| `opportunity_risk` | Skill 5 | 机会与风险 |
| `full_analysis` | Agents | 完整多 Agent 投研决策报告 |
| `event_catalyst` | Skill 6 | 热门事件驱动分析（宏观+新闻+传导路径）|

## 系统原则

定义在 `config/prompts/instructions.md`，运行时注入 MCP server：

1. **符合第一性原则** — 从数据本身推断，不用训练记忆
2. **对抗式审查** — 多源交叉验证，保留矛盾而非平滑
3. **拒绝杜撰数据** — 工具返回空则如实告知，禁止补充推断
4. **完整的推理链** — 数据→推论→结论，每步可验证
5. **完整的证据链** — 每个数字行内标注 `[来源: 工具名/表名/切片ID]`
6. **观点鲜明** — 必须给出明确判断，不允许无结论表述
7. **深挖隐含信息与合理线性外推** — 挖掘管理层措辞、财务结构、研报语气等边际变化，并标注外推假设和失效边界
8. **财务预测前置三步校验** — 字段口径、全年数交叉验证、预测倍率 sanity check 通过后，才能做业绩外推
9. **研报作为一致预期基准** — 多篇研报交叉佐证、去伪存真后的结论，作为对比基准
10. **纪要修正预测** — 离散的访谈纪要不单独预测业绩，只用于修正研报外推得到的预测
11. **短中长三维度分级** — 修正后预测按 0–6 月/6 月–1 年/1–2 年对比一致预期，短中长全超 → 大牛股；仅长期超 → 潜力股
12. **数据质量四要求** — 准确性（逐字核对）、时效性（标原始时间戳，越新权重越高，超 6 月提示过时）、连贯性（能与前后期衔接）、多样性（覆盖多种独立信源）

### 财务预测三步校验

任何营收、净利润、毛利率、现金流、估值或未来业绩预测，必须先完成：

1. **字段口径校验**：确认 `financial_reports.period` 对应单季度、累计报告期还是全年口径；无法确认时，禁止把 `Q1-Q4` 相加为全年。
2. **全年数交叉验证**：用 `Q4/年报口径`、券商研报历史值、公司公告摘要至少两类本地来源核对全年收入和利润；冲突时保留差异并说明采用口径。
3. **预测倍率 sanity check**：预测中枢必须和历史全年收入、最近季度收入年化、卖方预测区间比较；若预测中枢相对历史基数跃升超过 2 倍，必须列出订单、产能、价格、客户四类证据中的至少两类，否则只能放入乐观情景，不得作为基准预测。

输出研报时必须单列“口径校验”或“预测校验”，并区分“已验证事实”“外推假设”“情景预测”。

## 数据口径与入库规则

### 数据目录原则

- `data/inputs/`：人工放入、手动下载、官方导出的原始文件。这里代表“我信任它是原始输入”，不要放程序自动生成的 markdown。
- `data/raw/`：程序通过 API、公开接口或官方工具自动拉取的原始响应，尽量保持 JSON 原貌，便于追溯和重新加工。
- `data/processed/`：清洗、转换、切片后的中间产物，例如公告/新闻转出的 markdown、调试用 chunks JSON。

分类顺序统一为“数据形态 → 来源平台/方式 → 标的”，例如 `data/raw/announcements/akshare/`、`data/processed/news/akshare/688141.SH/`、`data/inputs/expert_minutes/acecamp/export/`。这样查询时先按投研证据类型找，再区分来源质量和获取方式。

### SQLite 财务库

- 主库路径：`databases/ira.db`
- 表：`financial_reports`、`historical_prices`、`companies`、`spider_crawl_log`
- 初始化只创建 schema，不会自动补财务数据：

```bash
python -m src.db.db_initializer
```

### LanceDB 研报/专家专栏库

- 主路径：`data/storage/lancedb_root/`
- 表：`chunks`
- 入库规则：按 `chunk_id` 先删后写，避免重复运行导致重复 chunks。
- 证据链字段：AceCamp 专家专栏会写入 `source_file = acecamp://article/{id}`，用于报告引用和追溯。
- 数据源字段：AceCamp 专家专栏写入 `data_source = acecamp_expert_column`，券商研报仍为 `broker_report`。
- 专家专栏权重字段：`release_time` 记录原始访谈发布时间，`badges` 保留 AceCamp 标签，`is_hot` 标记热度纪要，`source_weight` 用于后续排序/引用权重。

手动下载的 AceCamp 专家专栏导出 JSON 放入：

```text
data/inputs/expert_minutes/acecamp/export/
```

然后运行：

```bash
python -m src.ingestion.acecamp.expert_processor
```

### 研报 PDF 入库

券商研报 PDF 放入对应目录，例如：

```text
data/inputs/reports/杰华特/
```

然后运行 PDF 解析与切片：

```bash
python -m src.processing.text_processor
```

## 目录结构

```
ir-agent/
├── config/
│   ├── prompts/              ← 所有 prompt 独立文件（改 prompt 不动代码）
│   │   ├── instructions.md   ← MCP server 系统原则
│   │   ├── agent_*.md        ← 5 个岗位 Agent 的 system prompt
│   │   ├── skill4_*.md       ← Skill 4 审查 prompt + 报告模板
│   │   └── skill5_grounding_rule.md
│   ├── vocab_dictionary.json ← 公司/产品别名词典
│   ├── variable_schema.json  ← SQLite 字段映射
│   └── watchlist.json        ← 关注标的列表
├── src/
│   ├── agents/               ← 多 Agent 层
│   │   ├── orchestrator.py   ← 编排入口
│   │   ├── researcher.py / risk.py / strategy.py / trader.py / pm.py
│   ├── skills/               ← 单工具层（Skills 1–5）
│   ├── db/                   ← SQLite / LanceDB / Kùzu 封装
│   ├── ingestion/            ← 官方接口/公共接口定时拉取
│   ├── processing/           ← PDF 解析、OCR、分块
│   ├── utils/prompts.py      ← prompt 文件 loader
│   └── mcp_server.py         ← MCP 入口，注册 11 个工具
├── databases/ira.db          ← SQLite 主库
├── data/
│   ├── inputs/                ← 手动上传/官方导出原件（不放自动生成文件）
│   │   ├── reports/           ← 卖方研报 PDF
│   │   ├── announcements/     ← 手动下载的公司公告
│   │   ├── news/              ← 手动保存的重要新闻
│   │   └── expert_minutes/    ← 专家访谈纪要（如 acecamp/export）
│   ├── raw/                   ← 程序自动拉取的原始响应
│   │   ├── financials/{tushare,akshare}/
│   │   ├── announcements/{tushare,akshare}/
│   │   ├── news/{tushare,akshare,yfinance}/
│   │   ├── market/{tushare,akshare,yfinance}/
│   │   └── acecamp_official/  ← AceCamp 官方 Personal API 原始响应（临时研究）
│   ├── processed/             ← 程序清洗/转换/切片后的中间产物
│   │   ├── announcements/{akshare}/<ticker>/
│   │   ├── news/{akshare,web}/<ticker>/
│   │   └── *_chunks.json
│   └── storage/              ← LanceDB + Kùzu
└── docs/                     ← 设计文档（PRD、架构图）
```

## 快速开始

### 1. 环境

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置 Claude Desktop

将以下内容写入 `~/Library/Application Support/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "ira": {
      "command": "/path/to/ir-agent/.venv/bin/python",
      "args": ["/path/to/ir-agent/src/mcp_server.py"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

> 推荐用 `launchctl setenv ANTHROPIC_API_KEY "..."` 注入环境变量，避免 key 明文写入文件。

### 3. 初始化数据库

```bash
python -m src.db.db_initializer
```

### 4. 摄入研报 PDF

手动下载的 PDF 放入 `data/inputs/reports/<公司或主题>/`，然后：

```bash
python -m src.processing.text_processor
```

### 5. 摄入 AceCamp 专家专栏

手动下载的专家专栏导出 JSON 放入 `data/inputs/expert_minutes/acecamp/export/`，然后：

```bash
python -m src.ingestion.acecamp.expert_processor
```

AceCamp 在线查询只使用官方 skill：

```bash
python3 data/tmp/acecamp-research/scripts/acecamp_client.py ask "问题" --mode deep
python3 data/tmp/acecamp-research/scripts/acecamp_client.py search --query "关键词" --original_query "原始问题"
```

`src.ingestion.acecamp.spider` 仅保留为官方 Personal API 的辅助封装，不进入自动调度；其 `ask_and_store` 默认不写入 LanceDB，显式入库时会标记为 `acecamp_ai_answer`，不能当作券商研报或专家纪要证据。

### 6. 一键更新单个股票

推荐统一走总入口，避免漏掉财报、公告、新闻、研报、专家纪要中的某一类：

```bash
python scripts/refresh_company_data.py --ticker 688141.SH --company 杰华特
```

长期更新策略：

- 财报/公告/新闻：自动拉取到 `data/raw/`，再转换到 `data/processed/` 并入 LanceDB/SQLite。
- 研报 PDF：手动放入 `data/inputs/reports/<公司名>/`，总入口会统一处理。
- 专家纪要：只处理 `data/inputs/expert_minutes/acecamp/export/` 下的官方/手动导出 JSON，保留 `release_time`、`badges`、`is_hot`、`source_weight`。
- AceCamp 在线 ask/search：只作为临时研究辅助，不自动入证据库。

### 7. 拉取行情和研报（定时）

```bash
python -m src.ingestion.api_scheduler
```

## 数据源

| 来源 | 内容 | 方式 |
|---|---|---|
| AkShare | 历史股价、财务摘要 | API，定时拉取（15:35 收盘后）|
| Tushare | 日线行情、财务报表、新闻公告 | API（需 token，填入 `config/api_keys.json`）|
| YFinance | 宏观指标、商品价格、海外可比公司、汇率 | API，免费无需 key（有限速，每日缓存）|
| AceCamp | 专家纪要导出、深度问答 | 官方 skill/Personal API（需账号，不用爬虫）|
| 手动下载 | 券商研报 PDF | 放入指定目录后批量处理 |
| 公司公告 | 财报、公告 | AkShare + 手动 |

### YFinance 宏观标的

`^GSPC`（标普500）· `^IXIC`（纳斯达克）· `GC=F`（黄金）· `CL=F`（WTI原油）· `USDCNY=X`（美元/人民币）· `^SOX`（费城半导体）· `SMH`（半导体ETF）

### Tushare 配置

在 `config/api_keys.json` 填入 token（[申请地址](https://tushare.pro/register)）：

```json
{
  "tushare_token": "your_token_here"
}
```

## 关注标的

当前 `config/watchlist.json`：`002136.SZ`（安纳达）· `300308.SZ`（中际旭创）· `688256.SH`（寒武纪）· `688141.SH`（杰华特）
