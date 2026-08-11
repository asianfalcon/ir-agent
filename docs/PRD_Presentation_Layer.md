# 🎯 AlphaSonar 系统：表现生成层 (Presentation Layer) 研发说明书

## 1. 模块定位与工程目标
本模块负责整个 AlphaSonar 系统的“最后一公里”。要求编写 Python 后端脚本（如 `report_generator.py`），将底层多模态数据库（SQLite、LanceDB、Kùzu）中清洗并对齐后的数据，注入到标准化的 Markdown 模板中，生成最终的【AlphaSonar 辩证投研报告】。

**⚠️ 核心红线约束：**
* 绝对禁止 LLM 进行任何数值计算。
* 严格遵循数据的物理来源，保持“视图与数据解耦”。

---

## 2. 目标输出模板 (Target Report Template)

系统最终输出的 Markdown 报告必须严格遵循以下模板结构（`$...` 为需要动态注入的变量）：

```markdown
# 📊 【AlphaSonar 辩证投研报告】$COMPANY_NAME ($TICKER) 基本面深度穿透

---

## 核心辩证结论
> ⚡ **风险/机会评级：** $RISK_OPPORTUNITY_RATING
> **一句话定调：** $ONE_SENTENCE_SUMMARY

---

## ⚖️ 多源对抗互证天平 (Multi-Source Verification)

| 维度 | 数据源提供方 | 核心立场/关键数据 | 冲突与矛盾捕捉 (AlphaSonar 警告) |
| :--- | :--- | :--- | :--- |
| **官方自述** | 公司财报 & 最新公告 | $OFFICIAL_STANCE_TEXT | $CONFLICT_WARNING_HTML |
| **卖方评价** | 券商研究所研报切片 | $ANALYST_CONSENSUS_TEXT |
| **客观现实** | 垂直网站爬虫数据汇总 | $REALITY_DATA_TEXT |

---

## 🔢 确定性财务看板 (Python 硬编码计算)
| 指标名称 | $PERIOD_T_MINUS_2 | $PERIOD_T_MINUS_1 | $PERIOD_T_CURRENT (最新) | 同比变动 (YoY) | 环比变动 (QoQ) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **销售毛利率 (gross_margin)** | $GM_T2% | $GM_T1% | $GM_CURRENT% | $GM_YOY% | $GM_QOQ% |
| **净利润 (net_profit)** | $NP_T2 | $NP_T1 | $NP_CURRENT | $NP_YOY% | $NP_QOQ% |

*(注：以上定量看板数字 100% 提取自 SQLite 本地关系库，未经 LLM 逻辑重组，确保绝对准确)*

---

## 🌐 产业链传导因果链条 (图拓扑推演)
根据本地 Kùzu 图数据库产业链推演路径：
`$GRAPH_PATH_VISUALIZATION`
* **AlphaSonar 链式逻辑提示：** $GRAPH_LOGICAL_DEDUCTION