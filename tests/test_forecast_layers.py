import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.mcp_server import _normalize_ticker_arg
from src.processing.text_processor import _classify_report, _infer_metadata
from src.skills.skill5_focused import (
    _evidence_chunks,
    _latest_version_per_team,
    _research_chunks,
    earnings_forecast,
)


def chunk(source_file, pub_date, data_source, text, chunk_id):
    return {
        "chunk_id": chunk_id,
        "text": text,
        "ticker": "INTC.US",
        "pub_date": pub_date,
        "period": "",
        "data_source": data_source,
        "source_file": source_file,
    }


class ForecastLayerTests(unittest.TestCase):
    def test_ticker_normalization(self):
        self.assertEqual(_normalize_ticker_arg("INTC"), "INTC.US")
        self.assertEqual(_normalize_ticker_arg("英特尔"), "INTC.US")

    def test_report_classification(self):
        self.assertEqual(_classify_report("Q1'26 Earnings Release.pdf"), "company_filing")
        self.assertEqual(
            _classify_report("20260604-华泰证券-英特尔-INTC.US-盈利预测.pdf"),
            "broker_report",
        )

    def test_official_release_date_comes_from_text(self):
        body = (
            "Intel Reports First-Quarter 2026 Financial Results\n"
            "SANTA CLARA, Calif., April 23, 2026 – Intel Corporation today reported results."
        )
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp) / "reports"
            reports.mkdir()
            path = reports / "Q1'26 Earnings Release.pdf"
            path.write_bytes(b"placeholder")
            metadata = _infer_metadata(path, body, "INTC.US")
        self.assertEqual(metadata["data_source"], "company_filing")
        self.assertEqual(metadata["pub_date"], "20260423")

    def test_news_date_and_rumor_weight_come_from_local_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            news = Path(tmp) / "news"
            news.mkdir()
            path = news / "据传公司扩产.md"
            path.write_text("2026年7月13日，公司宣布扩产。", encoding="utf-8")
            metadata = _infer_metadata(path, path.read_text(), "INTC.US")
        self.assertEqual(metadata["data_source"], "web_news")
        self.assertEqual(metadata["pub_date"], "20260713")
        self.assertEqual(metadata["source_weight"], 0.5)
        self.assertEqual(metadata["badges"], ["传闻待确认"])

    def test_consensus_and_evidence_sources_are_separate(self):
        rows = [
            chunk("broker.pdf", "20260601", "broker_report", "2026E 营业收入", "b"),
            chunk("filing.pdf", "20260423", "company_filing", "Q2 Outlook", "f"),
            chunk("announcement.pdf", "20260424", "announcement", "业绩指引", "a"),
            chunk("expert.json", "20260602", "acecamp_expert_column", "专家观点", "e"),
            chunk("news.md", "20260716", "web_news", "渠道新闻", "n"),
        ]
        self.assertEqual([r["chunk_id"] for r in _research_chunks(rows)], ["b"])
        self.assertEqual({r["chunk_id"] for r in _evidence_chunks(rows)}, {"a", "b", "e", "f", "n"})

    def test_latest_forecast_does_not_get_replaced_by_newer_thematic_note(self):
        old_forecast = chunk(
            "20260123-华泰证券-英特尔-INTC.US-盈利预测.pdf",
            "20260123",
            "broker_report",
            "2026E 2027E 2028E 营业收入 归母净利润 EPS",
            "old",
        )
        newer_thematic = chunk(
            "20260701-华泰证券-英特尔-INTC.US-管理层变动点评.pdf",
            "20260701",
            "broker_report",
            "管理层变动与战略评论，不含财务预测表",
            "theme",
        )
        selected = _latest_version_per_team([old_forecast, newer_thematic])
        self.assertEqual([r["chunk_id"] for r in selected], ["old"])

    def test_earnings_prompt_has_four_physically_separate_layers(self):
        official = chunk(
            "Q1'26 Earnings Release.pdf",
            "20260423",
            "company_filing",
            "Q2 2026 Outlook Revenue $13.8-14.8 billion Gross margin 39.0% EPS $0.20",
            "official",
        )
        broker = chunk(
            "20260604-华泰证券-英特尔-INTC.US-盈利预测.pdf",
            "20260604",
            "broker_report",
            "2026E 2027E 2028E 营业收入 归母净利润 EPS 盈利预测",
            "broker",
        )
        expert = chunk(
            "expert.json",
            "20260701",
            "acecamp_expert_column",
            "供应链专家补充观点",
            "expert",
        )
        dashboard = {
            "period": "2026Q1",
            "metrics": {
                "revenue": {"value": 13577000000, "yoy_pct": 7.2, "qoq_pct": -0.7},
                "net_profit": {"value": -3728000000, "yoy_pct": None, "qoq_pct": -530.8},
            },
        }
        with patch("src.db.vector_store.search", return_value=[]):
            prompt = earnings_forecast(
                "INTC.US",
                "英特尔",
                dashboard,
                [official, broker, expert],
                lambda _system, user: user,
            )

        official_section = prompt.split("【公司官方指引", 1)[1].split("【卖方一致预期候选", 1)[0]
        sellside_section = prompt.split("【卖方一致预期候选", 1)[1].split("【专家/纪要补充", 1)[0]
        supplemental_section = prompt.split("【专家/纪要补充", 1)[1].split("强制计算顺序", 1)[0]
        self.assertIn("Q1'26 Earnings Release.pdf", official_section)
        self.assertNotIn("Q1'26 Earnings Release.pdf", sellside_section)
        self.assertIn("华泰证券", sellside_section)
        self.assertNotIn("expert.json", sellside_section)
        self.assertIn("expert.json", supplemental_section)
        self.assertIn("【经营驱动证据", prompt)
        self.assertIn("核心业务判断与业绩拆解", prompt)
        self.assertIn("分部/产品→合并收入→毛利→营业利润→税后利润→EPS", prompt)


if __name__ == "__main__":
    unittest.main()
