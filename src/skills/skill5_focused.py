"""
Skill 5: Five focused analysis shortcuts.
Each function returns a Markdown string grounded in local data.
"""

from typing import Any


# ── shared prompt helper ──────────────────────────────────────────────────────

_GROUNDING_RULE = """
【数据来源标注规则 · 强制执行】
- 每个数字/结论后必须标注 [来源: 工具名/数据表]
- 无本地数据支撑的内容只能写"暂无本地数据"，严禁用训练记忆补充
"""


def earnings_forecast(
    ticker: str,
    company_name: str,
    dashboard: dict,
    vector_chunks: list[dict],
    llm_caller,
) -> str:
    """预测业绩：历史趋势 + 券商预测共识 → 未来2季度区间预测"""
    fin = dashboard.get("metrics", {})
    rev = fin.get("revenue", {})
    np_ = fin.get("net_profit", {})
    period = dashboard.get("period", "最新")

    fin_text = (
        f"营收: {rev.get('value')} YoY {rev.get('yoy_pct')}% QoQ {rev.get('qoq_pct')}%\n"
        f"净利润: {np_.get('value')} YoY {np_.get('yoy_pct')}% QoQ {np_.get('qoq_pct')}%"
    )

    sell_snips = [c["text"][:150] for c in vector_chunks
                  if c.get("data_source") == "broker_report"][:5]
    sell_text = "\n".join(f"- {s}" for s in sell_snips) or "暂无本地研报数据"

    prompt = f"""你是卖方分析师。请基于以下本地数据预测 {company_name}({ticker}) 未来2个季度业绩区间。

【历史财务数据 · 周期: {period}】(来源: SQLite financial_reports)
{fin_text}

【券商研报预测摘要】(来源: LanceDB broker_report)
{sell_text}

{_GROUNDING_RULE}

请输出：
## 📈 业绩预测 · {company_name}

### 基准情景（中性）
| 季度 | 营收预测 | YoY | 净利润预测 | YoY |
|:---|:---|:---|:---|:---|
| 下一季度 | ... | ... | ... | ... |
| 再下季度 | ... | ... | ... | ... |

### 预测依据（附来源标注）
（逐条列出，每条带 [来源: ...]）

### 主要预测风险
（可能导致预测偏差的因素）
"""
    return llm_caller(_GROUNDING_RULE, prompt)


def price_target(
    ticker: str,
    company_name: str,
    dashboard: dict,
    vector_chunks: list[dict],
    llm_caller,
) -> str:
    """预测股价：估值模型 + 券商目标价共识"""
    fin = dashboard.get("metrics", {})
    period = dashboard.get("period", "最新")

    fin_lines = []
    for k, v in fin.items():
        fin_lines.append(f"  {k}: {v.get('value')}")
    fin_text = "\n".join(fin_lines) or "暂无财务数据"

    # 找含目标价的切片
    target_snips = [c["text"][:200] for c in vector_chunks
                    if any(kw in c["text"] for kw in ["目标价", "目标市值", "PE", "PS", "估值", "合理价值"])][:4]
    target_text = "\n".join(f"- {s}" for s in target_snips) or "暂无本地目标价数据"

    prompt = f"""你是量化分析师。请基于以下本地数据估算 {company_name}({ticker}) 合理股价区间。

【财务指标 · 周期: {period}】(来源: SQLite financial_reports)
{fin_text}

【券商目标价/估值参考】(来源: LanceDB broker_report)
{target_text}

{_GROUNDING_RULE}

请输出：
## 💹 股价目标 · {company_name}

### 估值区间
| 估值方法 | 假设 | 隐含价格 | 来源 |
|:---|:---|:---|:---|
| PE法 | ... | ... | [来源: ...] |
| PS法 | ... | ... | [来源: ...] |

### 券商目标价共识
（列出本地数据中出现的目标价，每条带来源标注）

### 当前定价隐含的预期
（若无本地股价数据，写"暂无本地价格数据"）
"""
    return llm_caller(_GROUNDING_RULE, prompt)


def marginal_change(
    ticker: str,
    company_name: str,
    dashboard: dict,
    vector_chunks: list[dict],
    llm_caller,
) -> str:
    """边际改变：最新催化剂 + 与上期对比的增量变化"""
    fin = dashboard.get("metrics", {})
    period = dashboard.get("period", "最新")

    deltas = []
    for k, v in fin.items():
        qoq = v.get("qoq_pct")
        yoy = v.get("yoy_pct")
        if qoq is not None:
            deltas.append(f"{k}: QoQ {qoq:+.1f}% / YoY {yoy:+.1f}%")
    delta_text = "\n".join(deltas) or "暂无环比数据"

    # 按 pub_date 排序取最新研报
    recent = sorted(vector_chunks, key=lambda c: c.get("pub_date", ""), reverse=True)
    recent_snips = [c["text"][:150] for c in recent[:5]]
    recent_text = "\n".join(f"- [{c.get('pub_date','?')}] {c['text'][:120]}"
                            for c in recent[:5]) or "暂无近期研报"

    prompt = f"""你是行业跟踪分析师。请聚焦于 {company_name}({ticker}) 的边际变化，输出增量信息。

【环比/同比变化 · 周期: {period}】(来源: SQLite financial_reports)
{delta_text}

【最新研报摘要（按时间排序）】(来源: LanceDB broker_report)
{recent_text}

{_GROUNDING_RULE}

请输出：
## 🔄 边际改变 · {company_name}

### 核心变化（3条以内，最重要的排第一）
1. **[变化描述]** [来源: ...]
   - 变化前：...
   - 变化后：...
   - 影响：...

### 催化剂时间线
（列出近期重要事件，格式：日期 · 事件 · 影响方向 · [来源: ...]）

### 哪些预期尚未price in
"""
    return llm_caller(_GROUNDING_RULE, prompt)


def relationship_graph(
    ticker: str,
    company_name: str,
    product: str,
    chain_companies: list[dict],
    vector_chunks: list[dict],
    llm_caller,
) -> str:
    """关系图谱：产业链传导 + 竞争格局文字描述 + HTML路径"""
    chain_text = "\n".join(
        f"- {r['company_name']}({r['ticker']}) 生产 {r['product']}"
        for r in chain_companies
    ) or "图谱暂无传导路径"

    compete_snips = [c["text"][:150] for c in vector_chunks
                     if any(kw in c["text"] for kw in ["竞争", "市占率", "份额", "对手", "替代"])][:3]
    compete_text = "\n".join(f"- {s}" for s in compete_snips) or "暂无本地竞争数据"

    # trigger pyvis rendering
    import subprocess, sys
    from pathlib import Path
    root = Path(__file__).parent.parent.parent
    script = root / "scripts" / "visualize_graph.py"
    html_path = root / "data" / f"graph_viz_{ticker}.html"
    subprocess.Popen([sys.executable, str(script), ticker])

    prompt = f"""你是产业链研究员。请描述 {company_name}({ticker}) 的关系图谱。

【产业链传导（来自 Kùzu 图谱）】
{chain_text}
核心产品：{product}

【竞争格局研报摘要】(来源: LanceDB broker_report)
{compete_text}

{_GROUNDING_RULE}

请输出：
## 🌐 关系图谱 · {company_name}

### 产业链位置
（上游 → 本公司({company_name}) → 下游，文字描述，附 [来源: Kùzu]）

### 核心竞争对手
| 竞争对手 | 优势 | 劣势 | 来源 |
|:---|:---|:---|:---|

### 产业链传导风险
（上游涨价/下游需求变化如何影响本公司）

---
📊 **交互式图谱已生成** → 用浏览器打开: `{html_path}`
"""
    return llm_caller(_GROUNDING_RULE, prompt)


def opportunity_risk(
    ticker: str,
    company_name: str,
    dashboard: dict,
    vector_chunks: list[dict],
    chain_companies: list[dict],
    llm_caller,
) -> str:
    """机会与风险：多空双向辩证分析"""
    fin = dashboard.get("metrics", {})
    period = dashboard.get("period", "最新")
    gm = fin.get("gross_margin", {})

    fin_text = f"毛利率: {gm.get('value')} YoY {gm.get('yoy_pct')}%"

    bull_snips = [c["text"][:150] for c in vector_chunks
                  if any(kw in c["text"] for kw in ["买入", "增持", "催化", "机会", "上行", "超预期"])][:3]
    bear_snips = [c["text"][:150] for c in vector_chunks
                  if any(kw in c["text"] for kw in ["风险", "减持", "不确定", "下行", "低于预期", "竞争加剧"])][:3]

    bull_text = "\n".join(f"- {s}" for s in bull_snips) or "暂无看多研报"
    bear_text = "\n".join(f"- {s}" for s in bear_snips) or "暂无看空研报"

    chain_text = ", ".join(r["company_name"] for r in chain_companies) or "暂无图谱数据"

    prompt = f"""你是对冲基金研究员，对多空双方同样严苛。请对 {company_name}({ticker}) 做机会与风险分析。

【财务数据 · {period}】(来源: SQLite)
{fin_text}

【看多研报摘要】(来源: LanceDB broker_report)
{bull_text}

【看空/风险研报摘要】(来源: LanceDB broker_report)
{bear_text}

【产业链相关公司】(来源: Kùzu)
{chain_text}

{_GROUNDING_RULE}

请输出：
## ⚖️ 机会与风险 · {company_name}

### 🟢 核心机会（Bull Case）
| 催化剂 | 概率估计 | 潜在影响 | 来源 |
|:---|:---|:---|:---|

### 🔴 核心风险（Bear Case）
| 风险因素 | 严重程度 | 触发条件 | 来源 |
|:---|:---|:---|:---|

### 🎯 关键观测指标
（未来3个月需要跟踪的3-5个指标，用于判断多空方向）

### IRA 综合评分
- 机会强度：⭐⭐⭐（仅基于本地数据）
- 风险程度：⭐⭐⭐
- 数据完整性：（缺少哪些关键数据）
"""
    return llm_caller(_GROUNDING_RULE, prompt)
