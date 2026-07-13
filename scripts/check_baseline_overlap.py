#!/usr/bin/env python3
"""纪要修正因子的机械前置检查——原则10"防重复计算"的落地工具。

判断依据仅看研报文本是否包含该细节，不按发布时间过滤（原则10明确禁止用
"纪要早于/晚于研报发布时间"作为是否已被市场知晓的代理）。

两级检索：
1. is_baseline() —— 关键词子串匹配，抓"原话/同一实体名"命中，最快最准但换个
   说法就漏（比如纪要写"客户主动要求提前锁价"，研报写"价格趋势向好"，关键词
   对不上，语义却是同一件事）。
2. is_baseline_semantic() —— 上面漏掉时兜底，用现有 embedder.py 对纪要因子的
   完整描述做向量相似度检索，抓"意思一样、措辞不同"的吸收证据。不新增依赖，
   复用 LanceDB 已有的 chunks 向量索引。
"""
from __future__ import annotations

import sys
from pathlib import Path

import lancedb

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ponytail: L2距离阈值，未做大规模标注校准，只是"cosine相似度约0.6"的粗略换算
# （embedder.py 输出归一化向量时 L2² = 2 - 2*cos_sim）。当作可调旋钮，见下方
# is_baseline_semantic 的 max_distance 参数；真出现明显漏判/误判再调。
_DEFAULT_MAX_DISTANCE = 0.9


def is_baseline(ticker: str, keyword: str) -> list[dict]:
    """在该ticker全部broker_report切片文本中检索keyword（子串匹配）。

    命中（非空列表）→ 该纪要因子已被至少一篇研报吸收，纪要修正因子表标"是"，
    只能作为验证/强化标注，不得计入Delta。
    未命中（空列表）→ 换 is_baseline_semantic() 做语义兜底检索，仍未命中才
    交给LLM判断是否为真实增量，且需引用具体证据。
    """
    db = lancedb.connect(str(ROOT / "data/storage/lancedb_root"))
    tbl = db.open_table("chunks")
    safe_ticker = ticker.replace("'", "''")
    safe_keyword = keyword.replace("'", "''")
    rows = (
        tbl.search()
        .where(f"ticker = '{safe_ticker}' AND data_source = 'broker_report' AND text LIKE '%{safe_keyword}%'")
        .select(["pub_date", "source_file", "chunk_id"])
        .to_list()
    )
    return rows


def is_baseline_semantic(
    ticker: str, factor_text: str, top_k: int = 5, max_distance: float = _DEFAULT_MAX_DISTANCE
) -> list[dict]:
    """关键词检索(is_baseline)未命中时的语义兜底检索。

    factor_text 传纪要因子的完整描述句（不是单个关键词），例如
    "大客户7月正式下发提价通知，OEM渠道库存处于过去5年12%分位"。
    返回该ticker broker_report切片里，与factor_text向量距离 <= max_distance
    的命中（按距离升序）；命中即视为"语义已被吸收"，附distance供人工复核
    （距离越小越像同一件事，不能免去人工确认是否真对应同一事实）。
    """
    from src.db.embedder import embed_one

    db = lancedb.connect(str(ROOT / "data/storage/lancedb_root"))
    tbl = db.open_table("chunks")
    safe_ticker = ticker.replace("'", "''")
    vec = embed_one(factor_text)
    rows = (
        tbl.search(vec)
        .where(f"ticker = '{safe_ticker}' AND data_source = 'broker_report'")
        .limit(top_k)
        .select(["pub_date", "source_file", "chunk_id", "text"])
        .to_list()
    )
    return [r for r in rows if r.get("_distance", 999) <= max_distance]


if __name__ == "__main__":
    # ponytail: 用真实数据做冒烟自检，不建mock/fixture
    demo = is_baseline("INTC.US", "Google")
    assert isinstance(demo, list)
    print(f"is_baseline('INTC.US', 'Google') → {len(demo)} hit(s)")
    for row in demo:
        print(" ", row["pub_date"], row["source_file"])

    demo2 = is_baseline_semantic("INTC.US", "英特尔与谷歌在AI芯片领域的合作")
    assert isinstance(demo2, list)
    print(f"is_baseline_semantic('INTC.US', '英特尔与谷歌在AI芯片领域的合作') → {len(demo2)} hit(s)")
    for row in demo2:
        print(" ", round(row["_distance"], 4), row["source_file"])

