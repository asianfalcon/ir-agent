# AlphaSonar — 投研智能体

基于 MCP 的私有买方投研系统。接入本地私有知识库（财务数据库 + 研报向量库 + 产业链图谱），通过多 Agent 协作给出有据可查、观点鲜明的投资判断。

> **Ping the market. Read the echoes. Capture the alpha.**

**AlphaSonar** 是品牌名；对外命令统一使用短前缀 `alpha-`，Python 包和环境变量仍使用明确的 `alphasonar` / `ALPHASONAR_*`，避免与其他项目冲突。

产品语言沿用声呐从发射到回波判读的过程：

| 术语 | 含义 | 当前系统映射 |
|---|---|---|
| **Ping** | 主动搜索公告、研报、纪要和新闻 | Connectors、定时采集、单公司更新 |
| **Echo** | 汇集不同来源对同一事实的反馈 | 多源检索、对抗式互证 |
| **Noise Filter** | 过滤重复、传闻和低质量信息 | 去重、来源分级、口径与时效校验 |
| **Signal** | 提取可量化的业绩变化 | 财务计算、预测修正、边际变化 |
| **Contact** | 发现值得研究的潜在 Alpha 目标 | 事件催化、产业链传播、机会筛选 |
| **Track** | 持续跟踪预测与关键验证点 | 文件监控、watchlist、预测快照 |
| **Depth** | 表示证据深度与可信度 | 来源层级、交叉验证、`source_id` 血缘 |
| **AlphaLoop** | 用实际财报复盘并修正模型 | `forecast_events`、误差评分与反馈策略 |

首次阅读项目请先看 [`docs/PROJECT_DESIGN.md`](docs/PROJECT_DESIGN.md)，文档索引见 [`docs/README.md`](docs/README.md)。

## 架构概览

```
Claude Desktop / Codex
        ↕ MCP (stdio)
   interfaces/mcp/server.py ← 11 个 MCP 工具
        ↕
   Skills 1–6             ← 单工具查询层
   Agents (5 岗位)        ← 多 Agent 编排层
        ↕
   SQLite / LanceDB / Kùzu ← 本地数据层
```

本地客户端使用 `alpha-mcp`（stdio）；服务器部署使用 `alpha-server`（Streamable HTTP）。Compose默认把`/mcp`只发布到宿主机`127.0.0.1:8000`，并要求`ALPHASONAR_MCP_TOKEN`或`ALPHASONAR_MCP_TOKEN_FILE`鉴权。

### 数据层

| 存储 | 内容 | 路径 |
|---|---|---|
| SQLite | 财务报表、历史股价 | `$ALPHASONAR_RUNTIME_ROOT/stores/relational/alphasonar.db` |
| LanceDB | 研报/公告向量切片 | `$ALPHASONAR_RUNTIME_ROOT/stores/vector/lancedb_root/` |
| Kùzu | 产业链图谱（公司↔产品↔上下游） | `$ALPHASONAR_RUNTIME_ROOT/stores/graph/kuzu_root.db` |

> 旧目录仅用于迁移兼容；生产环境的路径一律由 `alphasonar.settings` 和环境变量决定。
> 若本机仍只有 `databases/ira.db`，AlphaSonar会原地兼容读取；运行目录迁移脚本会把它复制为新布局中的`alphasonar.db`，不会删除旧库。

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

### MCP 工具（11 个）

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

定义在 `resources/prompts/instructions.md`，运行时注入 MCP server：

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
13. **完整研报骨架** — 固定为“业绩预测、估值、机会与风险”三大模块；业绩预测先做核心业务与业绩拆解，再依次展示官方锚点、券商基准、纪要修正和最终预测
14. **预测硬护栏** — 本地有官方指引必抽取（否则 `GUIDANCE_EXTRACTION_FAILED`，禁止静默降级）；禁止机械拆季（全年÷4／固定比例）；AlphaSonar 越界指引区间必须举证，缺证据才缩回

### 财务预测三步校验

任何营收、净利润、毛利率、现金流、估值或未来业绩预测，必须先完成：

1. **字段口径校验**：确认 `financial_reports.period` 对应单季度、累计报告期还是全年口径；无法确认时，禁止把 `Q1-Q4` 相加为全年。
2. **全年数交叉验证**：用 `Q4/年报口径`、券商研报历史值、公司公告摘要至少两类本地来源核对全年收入和利润；冲突时保留差异并说明采用口径。
3. **预测倍率 sanity check**：预测中枢必须和历史全年收入、最近季度收入年化、卖方预测区间比较；若预测中枢相对历史基数跃升超过 2 倍，必须列出订单、产能、价格、客户四类证据中的至少两类，否则只能放入乐观情景，不得作为基准预测。

输出研报时必须单列“口径校验”或“预测校验”，并区分“已验证事实”“外推假设”“情景预测”。

### 预测硬护栏

`earnings_forecast`（skill5）与研报生成必须遵守，防止漏读指引和机械外推：

1. **有指引必抽取**：本地存在 `company_filing`/`announcement` 时，必须成功抽取目标期指引进上下文；抽取为空则抛 `GUIDANCE_EXTRACTION_FAILED`，**禁止静默降级为全年拆季**。本地本就无官方文件时正常放行。
2. **禁止机械拆季**：严禁全年÷4、剩余收入×固定比例、仅凭“季节性”套 30/33/37%。拆季必须有公司季度指引／明确季度一致预期／券商季度预测表／已披露季度订单出货其一，否则输出“季度数据不足，无法可靠拆分”。
3. **越界举证不撤回**：AlphaSonar 点预测可落在指引区间外（修正值来源），但必须挂显式理由＋证据来源(source_id)＋Δ；缺可量化证据才降回区间内或标为 Bull/Bear case。

### 研报格式骨架

完整研报骨架沉淀在：

```text
resources/prompts/report_skeleton.md
resources/prompts/instructions.md
```

固定顺序：

1. **业绩预测**
   - 核心业务判断与业绩拆解：按真正重要的分部/产品拆收入，并建立毛利率→费用→净利润/EPS桥；不做机械指标清单。
   - 预测校验与公司官方指引：历史实际值用于基数校验，公司指引作为未来锚点。
   - 券商业绩预测表：逐篇列出券商预测，最后一行为“卖方基准”。
   - 纪要修正因子表：列出纪要因子、来源、类型、影响指标、方向、幅度。
   - 修正后业绩表：唯一最终数字表，历史实际值只作为锚点行，未来按短/中/长期列出一致预期、纪要修正后预测和修正值。
2. **估值**
   - 判断纪要修正值是否已被 price in。
3. **机会与风险**
   - Bull/Base/Bear case、概率、触发条件、投资动作和催化剂时间线。

修正值必须显式计算并加粗，格式如 `**+4.5 亿 🔼12.8%**`、`**-1.2 亿 🔽8.0%**`。

### Markdown 转 PDF

通用脚本：

```bash
/path/to/python scripts/ops/render_markdown_report_pdf.py \
  --src "$ALPHASONAR_RUNTIME_ROOT/artifacts/reports/<report>.md" \
  --out "$ALPHASONAR_RUNTIME_ROOT/artifacts/pdf/<report>.pdf"
```

PDF 生成规则已固化在脚本中：

- 使用 ReportLab 直接渲染中文，避免 LibreOffice/浏览器中文丢字。
- 不强制在“估值”“机会与风险”前分页，减少大面积空白。
- 自动收紧表格字号、行距和页边距，避免孤行分页。
- Markdown 中保留 `🔼/🔽`；PDF 中可渲染为兼容性更好的 `▲/▼`。

## 数据口径与入库规则

### 数据目录原则

- `sources/manual/`：人工放入、手动下载、官方导出的原始文件。不要放程序自动生成的 Markdown。
- `sources/external/`：程序通过 API、公开接口或官方工具自动拉取的原始响应，尽量保持原貌。
- `derived/`：清洗、转换、切片后的可重建中间产物。

分类顺序统一为“数据形态 → 来源平台/方式 → 标的”，例如
`sources/external/announcements/akshare/`、`derived/news/akshare/688141.SH/`、
`sources/manual/expert_minutes/acecamp/export/`。

### SQLite 财务库

- 主库路径：`$ALPHASONAR_RUNTIME_ROOT/stores/relational/alphasonar.db`
- 表：`financial_reports`、`historical_prices`、`companies`、`spider_crawl_log`、`forecast_events`
- 初始化只创建 schema，不会自动补财务数据：

```bash
python -m alphasonar.storage.db_initializer
```

#### forecast_events — 预测事件表（反馈回路）

append-only，让四层方法的每次修正都能被实际业绩证伪。同一张表存 `consensus`/`guidance`/`forecast`(=AlphaSonar)/`actual` 四类事件；历史永不覆盖，同 `as_of_date` 重复插入视为修订新增。`score` 按 `metric×accounting_basis` 隔离比对（GAAP 不与 Non-GAAP 混），裁决 AlphaSonar 修正相对一致预期加分/减分，`as_of_date` 晚于 actual 则标可能穿越。

```bash
# 记一条预测（财报后补 actual，再 score）
python -m scripts.ops.forecast_snapshot record --ticker AMD --as-of-date 2026-07-15 \
  --target-period 2026Q2 --event-type forecast --metric revenue --mid 11300000000 \
  --basis Non-GAAP --source-type alphasonar --source-id amd_report_20260714
python -m scripts.ops.forecast_snapshot score --ticker AMD
```

> 口径：`value_*` 用绝对值（对齐 `financial_reports.revenue`，如 13,577,000,000），不要填“亿美元”，否则误差全废。

### LanceDB 研报/专家专栏库

- 主路径：`$ALPHASONAR_RUNTIME_ROOT/stores/vector/lancedb_root/`
- 表：`chunks`
- 入库规则：先完整生成并合并新切片，成功后才清理同来源陈旧切片，避免重建失败导致数据丢失。
- 证据链字段：AceCamp 专家专栏会写入 `source_file = acecamp://article/{id}`，用于报告引用和追溯。
- 数据源字段：AceCamp 专家专栏写入 `data_source = acecamp_expert_column`，券商研报仍为 `broker_report`。
- 专家专栏权重字段：`release_time` 记录原始访谈发布时间，`badges` 保留 AceCamp 标签，`is_hot` 标记热度纪要，`source_weight` 用于后续排序/引用权重。

手动下载的 AceCamp 专家专栏导出 JSON 放入：

```text
$ALPHASONAR_RUNTIME_ROOT/sources/manual/expert_minutes/acecamp/export/
```

然后运行：

```bash
python -m alphasonar.connectors.acecamp.expert_processor
```

### 研报 PDF 入库

券商研报 PDF 放入对应目录，例如：

```text
$ALPHASONAR_RUNTIME_ROOT/sources/manual/reports/杰华特/
```

然后运行 PDF 解析与切片：

```bash
python -m alphasonar.pipelines.text_processor
```

## 目录结构

```text
alphasonar/                       # 只保存可版本化资产
├── src/alphasonar/
│   ├── agents/                  # 多 Agent 编排
│   ├── capabilities/            # 单项研究能力
│   ├── connectors/              # 外部数据连接器
│   ├── pipelines/               # 清洗、解析、切片
│   ├── storage/                 # SQLite/LanceDB/Kùzu 适配
│   ├── interfaces/mcp/          # MCP 入口
│   └── settings.py              # 唯一运行路径配置入口
├── resources/
│   ├── prompts/                 # 提示词与报告骨架
│   ├── policies/                # 研究规则、口径、反馈方法
│   ├── schemas/                 # 字段定义
│   └── dictionaries/            # 公司/产品词典
├── config/                      # 非敏感运行配置与示例
├── scripts/
│   ├── ops/                     # 数据更新、迁移、预测复盘
│   ├── dev/                     # 诊断与可视化
│   └── oneoff/                  # 一次性交付脚本（逐步归档）
├── deploy/                      # Docker/Compose及独立服务
├── docs/                        # 架构和运维文档
└── tests/

$ALPHASONAR_RUNTIME_ROOT/               # 不进入 Git，服务器挂持久卷
├── sources/{manual,external}/
├── derived/
├── stores/{relational,vector,graph}/
├── artifacts/
└── cache/
```

完整分层规则见 `docs/architecture/project-structure.md`，路径与迁移步骤见
`docs/architecture/runtime-layout.md`。不设置
`ALPHASONAR_RUNTIME_ROOT` 时仍读取旧目录，只用于平滑迁移。

## 快速开始

### 1. 环境

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
export ALPHASONAR_RUNTIME_ROOT="$HOME/alphasonar-runtime"
```

### 2. 配置 Claude Desktop

将以下内容写入 `~/Library/Application Support/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "alpha": {
      "command": "/path/to/alphasonar/.venv/bin/alpha-mcp",
      "args": [],
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
python -m alphasonar.storage.db_initializer
```

### 4. 摄入研报 PDF

手动下载的 PDF 放入 `$ALPHASONAR_RUNTIME_ROOT/sources/manual/reports/<公司或主题>/`，然后：

```bash
python -m alphasonar.pipelines.text_processor
```

### 5. 摄入 AceCamp 专家专栏

手动下载的专家专栏导出 JSON 放入 `$ALPHASONAR_RUNTIME_ROOT/sources/manual/expert_minutes/acecamp/export/`，然后：

```bash
python -m alphasonar.connectors.acecamp.expert_processor
```

AceCamp 在线查询只使用官方 skill：

```bash
python3 data/tmp/acecamp-research/scripts/acecamp_client.py ask "问题" --mode deep
python3 data/tmp/acecamp-research/scripts/acecamp_client.py search --query "关键词" --original_query "原始问题"
```

`alphasonar.connectors.acecamp.spider` 仅保留为官方 Personal API 的辅助封装，不进入自动调度；其 `ask_and_store` 默认不写入 LanceDB，显式入库时会标记为 `acecamp_ai_answer`，不能当作券商研报或专家纪要证据。

### 6. 一键更新单个股票

推荐统一走总入口，避免漏掉财报、公告、新闻、研报、专家纪要中的某一类：

```bash
python scripts/ops/refresh_company_data.py --ticker 688141.SH --company 杰华特
```

持续追踪手工证据目录可运行 `alpha-track`。原 `alpha-hound`、`alphasonar-watch` 仍作为兼容别名，但新文档和部署不再使用。

长期更新策略：

- 财报/公告/新闻：自动拉取到 `sources/external/`，再转换到 `derived/` 并入 LanceDB/SQLite。
- 研报 PDF：手动放入 `sources/manual/reports/<公司名>/`，总入口会统一处理。
- 专家纪要：只处理 `sources/manual/expert_minutes/acecamp/export/` 下的官方/手动导出 JSON。
- AceCamp 在线 ask/search：只作为临时研究辅助，不自动入证据库。

### 7. 拉取行情和研报（定时）

```bash
python -m alphasonar.connectors.api_scheduler
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
