"""
Text processing pipeline: PDF → clean Markdown, HTML → clean text, then chunk + embed metadata.
Called by watchdog_monitor for manual inputs and by refresh scripts for processed artifacts.
"""

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter

ROOT = Path(__file__).parent.parent.parent
VOCAB_PATH = ROOT / "config" / "vocab_dictionary.json"
VAR_SCHEMA_PATH = ROOT / "config" / "variable_schema.json"

CHUNK_SIZE = 700
CHUNK_OVERLAP = 70

# Regex patterns for PDF noise removal
_HEADER_FOOTER_RE = re.compile(
    r"(请务必阅读正文之后的免责条款|Page\s+\d+|证券研究报告|\b\d{1,3}\b)",
    re.IGNORECASE,
)
_DISCLAIMER_RE = re.compile(r"(免责声明|投资评级说明)")

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
)


def _load_vocab() -> list[dict]:
    return json.loads(VOCAB_PATH.read_text()) if VOCAB_PATH.exists() else []


def _load_var_names() -> list[str]:
    if not VAR_SCHEMA_PATH.exists():
        return []
    return [v["var_name"] for v in json.loads(VAR_SCHEMA_PATH.read_text())]


def _associated_vars(text: str) -> list[str]:
    schema = json.loads(VAR_SCHEMA_PATH.read_text()) if VAR_SCHEMA_PATH.exists() else []
    hits = []
    for var in schema:
        terms = [var["var_name"]] + var.get("source_field_mapping", [])
        if any(t in text for t in terms):
            hits.append(var["var_name"])
    return hits


def _normalize_ticker(text: str) -> str | None:
    for entry in _load_vocab():
        if entry.get("entity_type") == "Company":
            if entry["standard_name"] in text or any(a in text for a in entry.get("aliases", [])):
                return entry.get("ticker")
    return None


@lru_cache(maxsize=256)
def _extract_pdf(path: Path) -> str:
    # 同一次 refresh 里，近似去重(_dedupe_near_identical)和正文入库
    # (process_local_files)会各抽一遍同一批 PDF 正文——抽取是 O(页数) 的
    # 真开销(还可能触发 OCR)。用 lru_cache 按 Path 记忆，同一路径只抽一次，
    # 两处调用共享结果。key 是 Path 对象，两处都传绝对路径，命中稳定。
    doc = fitz.open(path)
    pages: list[str] = []
    for page in doc:
        raw = page.get_text()
        lines = raw.splitlines()
        # strip header/footer lines (first and last two lines of each page)
        if len(lines) > 4:
            lines = lines[2:-2]
        cleaned = "\n".join(l for l in lines if not _HEADER_FOOTER_RE.fullmatch(l.strip()))
        pages.append(cleaned)

    full = "\n".join(pages)
    # cut at disclaimer
    m = _DISCLAIMER_RE.search(full)
    if m:
        full = full[: m.start()]

    # fallback OCR for image-only PDFs
    if len(full.strip()) < 100:
        full = _ocr_pdf(path)
    return full


def _ocr_pdf(path: Path) -> str:
    """OCR fallback for image-based PDFs using tesseract."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
        pages = convert_from_path(str(path), dpi=200)
        texts = []
        for img in pages:
            text = pytesseract.image_to_string(img, lang="chi_sim+eng")
            texts.append(text)
        return "\n".join(texts)
    except Exception as e:
        print(f"[processor] OCR failed for {path.name}: {e}")
        return ""


def _extract_html(path: Path) -> str:
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    for tag in soup(["nav", "footer", "script", "style"]):
        tag.decompose()
    # keep only meaningful elements
    parts = []
    for el in soup.find_all(["h1", "h2", "h3", "p", "table"]):
        parts.append(el.get_text(" ", strip=True))
    return "\n".join(parts)


def _classify_report(file_name: str) -> str:
    """区分 reports/ 目录里的"券商研报" vs "公司官方财报/SEC文件"。
    返回 'broker_report'（券商卖方研报，进一致预期）或 'company_filing'（公司官方
    披露，不进一致预期，仅作事实证据）。

    判别以"正向券商信号"为主判据：本项目券商研报遵循严格命名约定
    `YYYYMMDD-机构名-公司-ticker-标题.pdf`（如 20260604-华泰证券-英特尔-INTC.US-...），
    官方财报从不用这个格式。因此：文件名匹配该标准券商命名 → broker_report；
    否则命中官方财报特征（Earnings/annual/10-K/SEC 流水号/proxy/公司电话会等）
    → company_filing。两者都不命中时，保守留在 broker_report（宁可漏分类也不
    误把真研报踢出一致预期）。辅以"证券/研究所"等券商标记兜底非标准命名的券商研报。"""
    import re as _re
    # 主判据：标准券商研报命名 YYYYMMDD-机构名-...（官方财报绝不用此格式）
    if _re.match(r"^\d{8}-[^-]+-", file_name):
        return "broker_report"
    # 券商团队正向信号兜底：非标准命名但含券商机构标记
    _BROKER_MARK = ("证券", "研究所", "研报", "国际", "第一上海", "中金", "海通")
    if any(m in file_name for m in _BROKER_MARK):
        return "broker_report"
    # 公司官方财报/SEC 披露特征
    _FILING_MARK = (
        "Earnings", "earnings", "EarningsRelease", "Earnings Release",
        "annual report", "Annual Report", "10-K", "10-Q", "8-K",
        "Prepared Remarks", "Earnings Call", "Earnings Deck", "Financial Results",
        "PXY", "proxy", "Proxy", "Fiscal", "Financial", "Gaap", "GAAP", "gaap",
    )
    # SEC EDGAR accession-number 文件名，如 0000050863-25-000052
    if _re.match(r"^\d{10}-\d{2}-\d{6}", file_name):
        return "company_filing"
    # 公司官方新闻稿/电话会常见短命名：AMD 官方 "..._Reports_..._Financial_..."、
    # "AMD 1Q24call.pdf"、"amd2q2025.pdf" 这类无券商标记的公司自有材料。
    if _re.search(r"_Reports_.*(Quarter|Full_Year)", file_name):
        return "company_filing"
    if _re.search(r"\d[qQ]\d.*call|^amd\s*\d[qQ]", file_name, _re.IGNORECASE):
        return "company_filing"
    if any(m in file_name for m in _FILING_MARK):
        return "company_filing"
    return "broker_report"


def _infer_metadata(path: Path, text: str, ticker_override: str | None = None) -> dict[str, Any]:
    ticker = ticker_override or _normalize_ticker(text) or _normalize_ticker(path.stem)

    # walk up to find the evidence category dir (reports / announcements / news)
    source_map = {"reports": "broker_report", "announcements": "announcement", "news": "web_news"}
    data_source = "web_news"
    for parent in path.parents:
        if parent.name in source_map:
            data_source = source_map[parent.name]
            break

    # reports/ 目录里同时混着"券商研报"和"公司官方财报"（Earnings Release/Deck、
    # 10-K/10-Q、annual report、proxy、财报电话会、SEC 流水号文件）。目录约定会把两者
    # 一律标成 broker_report，导致 Intel 自家 deck 被当成卖方研报算进一致预期、污染
    # "最新研报"排序。这里按文件名把官方财报重分类为 company_filing（见 _classify_report），
    # 该来源不进 skill5 的 RESEARCH_DATA_SOURCES，不参与卖方一致预期。每次重分类打审计日志。
    if data_source == "broker_report":
        refined = _classify_report(path.name)
        if refined != "broker_report":
            print(f"[metadata] 官方财报重分类 broker_report→{refined}: {path.name}", flush=True)
        data_source = refined

    # extract pub_date from filename prefix like 20260701-
    import re as _re
    from datetime import date as _date

    def _valid_yyyymmdd(s: str) -> bool:
        try:
            _date(int(s[:4]), int(s[4:6]), int(s[6:8]))
            return True
        except ValueError:
            return False

    def _date_from_name(stem: str) -> tuple[str, str] | None:
        """按可信度从高到低，从文件名里抠出真实发布日期，返回 (yyyymmdd, 来源标签)。
        全抠不到返回 None（由调用方退回 mtime）。三级：
          1) 标准前缀  20240918-...            —— 最高优先级，本项目命名约定
          2) ISO 日期  ..._2026-02-03_...       —— AMD 官方新闻稿命名
          3) -/_ 分隔的 6 位 YYMMDD  ...-240803  —— 券商研报把日期放尾部时（补 20 世纪前缀）
        每级都过 _valid_yyyymmdd 校验，挡掉 SEC 流水号(0000050863-25-000052)、
        "Q4 2025" 这类假日期，让它们正确退回 mtime。"""
        m = _re.match(r"(\d{8})", stem)
        if m and _valid_yyyymmdd(m.group(1)):
            return m.group(1), "prefix"
        m = _re.search(r"(\d{4})-(\d{2})-(\d{2})", stem)
        if m:
            cand = m.group(1) + m.group(2) + m.group(3)
            if _valid_yyyymmdd(cand):
                return cand, "iso"
        m = _re.search(r"[-_](\d{2})(\d{2})(\d{2})(?:\D|$)", stem)
        if m:
            cand = "20" + m.group(1) + m.group(2) + m.group(3)
            if _valid_yyyymmdd(cand):
                return cand, "yymmdd-suffix"
        return None

    def _date_from_official_text(body: str) -> tuple[str, str] | None:
        """从官方材料正文头部提取真实披露日，避免把重新下载日当发布日期。

        只使用高置信度发布语境或 SEC filed date；不匹配普通报表期末日，避免把
        `Mar 28, 2026` 误当成新闻稿发布日期。
        """
        head = body[:12000]
        sec = _re.search(r"FILED AS OF DATE\s*[:：]\s*(\d{8})", head, _re.IGNORECASE)
        if sec and _valid_yyyymmdd(sec.group(1)):
            return sec.group(1), "sec-filed-date"

        months = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }
        month_pattern = "|".join(m.title() for m in months)
        # 公司新闻稿通常以“城市, 州, Month d, yyyy – 公司今日宣布”开头。
        release = _re.search(
            rf"(?:SANTA CLARA|AUSTIN|SAN JOSE|NEW YORK|CALIF\.|CALIFORNIA)[^\n]{{0,160}}?"
            rf"({month_pattern})\s+(\d{{1,2}}),\s+(\d{{4}})",
            head,
            _re.IGNORECASE,
        )
        if release:
            month = months[release.group(1).lower()]
            cand = f"{int(release.group(3)):04d}{month:02d}{int(release.group(2)):02d}"
            if _valid_yyyymmdd(cand):
                return cand, "official-release-text"
        return None

    hit = _date_from_name(path.stem)
    if not hit and data_source == "company_filing":
        hit = _date_from_official_text(text)
    if hit:
        pub_date, _date_src = hit
        if _date_src != "prefix":
            print(f"[metadata] pub_date {pub_date} from {_date_src} (非标准前缀): {path.name}", flush=True)
    else:
        # ponytail: no valid date anywhere in filename (e.g. SEC accession-number PDFs
        # like "0000050863-25-000052.pdf", or "Q4 2025 Earnings Deck.pdf") — fall back
        # to file mtime formatted as YYYYMMDD, not a raw epoch string. Still not the true
        # publish date, but at least a valid/sortable/comparable date string. mtime can be
        # wildly wrong (re-download stamps a future date) — log it so it's auditable, and
        # for 券商研报 the right fix is to rename to the 20240803- convention, not trust this.
        pub_date = _date.fromtimestamp(path.stat().st_mtime).strftime("%Y%m%d")
        print(f"[metadata] pub_date {pub_date} from FILE MTIME (文件名无有效日期，可能不准): {path.name}", flush=True)

    try:
        source_file = str(path.relative_to(ROOT))
    except ValueError:
        source_file = str(path)

    return {
        "ticker": ticker or "UNKNOWN",
        "pub_date": pub_date,
        "period": "",
        "data_source": data_source,
        "source_file": source_file,
    }


def chunk_text(text: str, metadata: dict) -> list[dict]:
    chunks = _splitter.split_text(text)
    result = []
    for c in chunks:
        result.append({
            "chunk_id": hashlib.md5(c.encode()).hexdigest(),
            "text": c,
            "metadata": {
                **metadata,
                "associated_vars": _associated_vars(c),
            },
        })
    return result


def process_file(path: Path, ticker_override: str | None = None) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf(path)
    elif suffix in (".html", ".htm"):
        text = _extract_html(path)
    else:
        text = path.read_text(errors="ignore")

    metadata = _infer_metadata(path, text, ticker_override)
    chunks = chunk_text(text, metadata)

    # flatten metadata into top-level fields for LanceDB (no nested dicts)
    flat_chunks = []
    for c in chunks:
        source_file = c["metadata"].get("source_file", path.name)
        flat = {
            "chunk_id":    hashlib.md5(f"{source_file}:{c['chunk_id']}".encode()).hexdigest(),
            "text":        c["text"],
            "ticker":      c["metadata"]["ticker"],
            "pub_date":    c["metadata"]["pub_date"],
            "period":      c["metadata"]["period"],
            "data_source": c["metadata"]["data_source"],
            "source_file": source_file,
        }
        flat_chunks.append(flat)

    # write to LanceDB — delete old chunks from this file first (content may have
    # changed, so chunk_id/md5 won't match and stale chunks would linger otherwise)
    from src.db.vector_store import upsert_chunks, delete_by_source_file
    delete_by_source_file(metadata["source_file"])
    upsert_chunks(flat_chunks)

    # also save JSON for debugging
    out_dir = ROOT / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{path.stem}_chunks.json"
    out_path.write_text(json.dumps(flat_chunks, ensure_ascii=False, indent=2))
    print(f"[processor] {path.name}: {len(flat_chunks)} chunks → LanceDB + {out_path.name}")
    return flat_chunks
