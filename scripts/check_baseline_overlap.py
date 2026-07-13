#!/usr/bin/env python3
"""纪要修正因子的机械前置检查——原则10"防重复计算"的落地工具。

判断依据仅看研报文本是否包含该细节，不按发布时间过滤（原则10明确禁止用
"纪要早于/晚于研报发布时间"作为是否已被市场知晓的代理）。
"""
from __future__ import annotations

from pathlib import Path

import lancedb

ROOT = Path(__file__).resolve().parent.parent


def is_baseline(ticker: str, keyword: str) -> list[dict]:
    """在该ticker全部broker_report切片文本中检索keyword。

    命中（非空列表）→ 该纪要因子已被至少一篇研报吸收，纪要修正因子表标"是"，
    只能作为验证/强化标注，不得计入Delta。
    未命中（空列表）→ 交给LLM判断是否为真实增量，且需引用具体证据。
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


if __name__ == "__main__":
    # ponytail: 用真实数据做冒烟自检，不建mock/fixture
    demo = is_baseline("INTC.US", "Google")
    assert isinstance(demo, list)
    print(f"is_baseline('INTC.US', 'Google') → {len(demo)} hit(s)")
    for row in demo:
        print(" ", row["pub_date"], row["source_file"])
