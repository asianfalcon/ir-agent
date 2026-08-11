"""锁住数据血缘修复：目录ticker权威、SEC流水号不产垃圾日期、财季代理、绝不退mtime。"""
from pathlib import Path

from alphasonar.pipelines.text_processor import _infer_metadata


def _m(rel, text=""):
    return _infer_metadata(Path(rel), text, None)


def test_directory_ticker_authority():
    # AMD 目录下的文件，即使正文提及 Intel，也必须归 AMD.US（防跨公司污染）
    m = _m("data/inputs/reports/AMD/AMD 4Q23call.pdf", "Intel Corporation competes with AMD")
    assert m["ticker"] == "AMD.US", m
    m = _m("data/inputs/reports/英特尔/Q1 2024 Earnings Deck.pdf", "AMD mentioned")
    assert m["ticker"] == "INTC.US", m


def test_sec_accession_no_garbage_date():
    # 0000050863-25-000109 曾被读成 20000109 垃圾日期；现在应留空而非垃圾/mtime
    m = _m("data/inputs/reports/英特尔/0000050863-25-000109.pdf", "no date")
    assert m["pub_date"] == "", m


def test_fiscal_period_proxy():
    for rel, want in [
        ("data/inputs/reports/英特尔/3Q23-Earnings-Script-FINAL.pdf", "20230930"),
        ("data/inputs/reports/英特尔/2Q2025-Earnings-Call Prepared Remarks.pdf", "20250630"),
        ("data/inputs/reports/AMD/AMD Q4'23 Earnings Slides FINAL.pdf", "20231231"),
        ("data/inputs/reports/AMD/AMD Q1'26 Earnings Slides Final.pdf", "20260331"),
    ]:
        assert _m(rel)["pub_date"] == want, (rel, _m(rel)["pub_date"])


def test_never_falls_back_to_mtime():
    # 无任何可靠日期线索 → 空，绝不用 mtime（入库日会劫持"最新"权重）
    m = _m("data/inputs/reports/英特尔/2024+ARS+Form+10-K.pdf", "annual report body")
    assert m["pub_date"] == "", m


if __name__ == "__main__":
    for fn in (test_directory_ticker_authority, test_sec_accession_no_garbage_date,
               test_fiscal_period_proxy, test_never_falls_back_to_mtime):
        fn()
    print("ok")
