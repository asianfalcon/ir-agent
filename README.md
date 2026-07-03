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

### Skills（单工具层）

| Skill | 文件 | 功能 |
|---|---|---|
| 1 | `skill1_text2sql.py` | 自然语言 → SQL → SQLite |
| 2 | `skill2_calculator.py` | 财务指标同比/环比计算（纯 Python）|
| 3 | `skill3_graph_propagator.py` | Kùzu 图谱：上游商品 → 受影响公司 |
| 4 | `skill4_verifier.py` | 多源对抗审查报告 |
| 5 | `skill5_focused.py` | 5 个快捷分析（业绩/股价/边际/图谱/风险）|

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

## 系统原则

定义在 `config/prompts/instructions.md`，运行时注入 MCP server：

1. **符合第一性原则** — 从数据本身推断，不用训练记忆
2. **对抗式审查** — 多源交叉验证，保留矛盾而非平滑
3. **拒绝杜撰数据** — 工具返回空则如实告知，禁止补充推断
4. **完整的推理链** — 数据→推论→结论，每步可验证
5. **完整的证据链** — 每个数字行内标注 `[来源: 工具名/表名/切片ID]`
6. **观点鲜明** — 必须给出明确判断，不允许无结论表述

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
│   ├── ingestion/            ← AceCamp 爬取 + AkShare 定时拉取
│   ├── processing/           ← PDF 解析、OCR、分块
│   ├── utils/prompts.py      ← prompt 文件 loader
│   └── mcp_server.py         ← MCP 入口，注册 10 个工具
├── databases/ira.db          ← SQLite 主库
├── data/
│   ├── raw/                  ← AceCamp / AkShare 原始 JSON
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

### 4. 摄入研报

手动下载的 PDF 放入 `data/raw/reports/<ticker>/`，然后：

```bash
python -m src.processing.text_processor
```

### 5. 拉取行情和研报（定时）

```bash
python -m src.ingestion.api_scheduler
```

## 数据源

| 来源 | 内容 | 方式 |
|---|---|---|
| AkShare | 历史股价、财务摘要 | API，定时拉取 |
| AceCamp | 研报、深度问答 | API（需账号）|
| 手动下载 | 券商研报 PDF | 放入指定目录后批量处理 |
| 公司公告 | 财报、公告 | AkShare + 手动 |

## 关注标的

当前 `config/watchlist.json`：`002136.SZ`（安纳达）· `300308.SZ`（中际旭创）· `688256.SH`（寒武纪）· `688141.SH`（杰华特）
