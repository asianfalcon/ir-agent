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

from ira.settings import get_settings

_SETTINGS = get_settings()
ROOT = _SETTINGS.project_root
VOCAB_PATH = _SETTINGS.vocab_path
VAR_SCHEMA_PATH = _SETTINGS.variable_schema_path

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
    # 兜底：小写官方特征词 + 年报缩写 AR（券商 YYYYMMDD- 命名已在前面 return，不会误伤）。
    # 修 2023-Intel-AR.pdf / intel-q3-2023-financial-and-business-report 等被误判 broker。
    fn_low = file_name.lower()
    if any(t in fn_low for t in ("annual report", "10-k", "10-q", "financial-and-business",
                                 "financial report", "financial-report", "annual-report")):
        return "company_filing"
    if _re.search(r"[-_ ]ar([-_. ]|$)", fn_low):  # "2023-Intel-AR"、"Intel AR_WR"
        return "company_filing"
    return "broker_report"


def _ticker_from_broker_name(file_name: str) -> str | None:
    """从券商研报命名 "YYYYMMDD-机构-公司-<TICKER>-标题" 抽显式标的代码。
    只认强信号：A股 6 位数字(688141) 或 XXX.US；且必须匹配 vocab 里存在的 ticker，
    避免把标题里的随机数字/代码误当 ticker。抽不到返回 None（回落目录/正文）。"""
    import re as _re
    known = {e.get("ticker") for e in _load_vocab() if e.get("entity_type") == "Company"}
    # A股 6 位：-688141- → 688141.SH / .SZ（用 vocab 里已知的带后缀形式匹配）
    for m in _re.findall(r"(?<!\d)(\d{6})(?!\d)", file_name):
        for suf in (".SH", ".SZ"):
            if m + suf in known:
                return m + suf
    # 美股：-AMD.US- / -INTC.US-
    for m in _re.findall(r"\b([A-Z]{1,5}\.US)\b", file_name):
        if m in known:
            return m
    return None


def _infer_metadata(path: Path, text: str, ticker_override: str | None = None) -> dict[str, Any]:
    # ticker 优先级：显式 override > 文件名显式代码 > 所在公司目录 > 正文 > 文件名词典。
    # 目录权威：reports/AMD/、reports/英特尔/ 等以公司命名的目录，其下文件的归属由
    # 目录决定，绝不让正文里对竞品的提及把 AMD 财报推成 INTC（曾导致 AMD 2023 文件
    # 混入 Intel 召回池）。目录名映射不出 ticker（如"美股""TMT"）时才回落到正文推断。
    dir_ticker = None
    for parent in path.parents:
        if parent.name in ("reports", "announcements", "news", "expert_minutes"):
            break
        cand = _normalize_ticker(parent.name)
        if cand:
            dir_ticker = cand
            break
    # 文件名里的显式 ticker 优先于目录权威：券商研报命名 "YYYYMMDD-机构-公司-<TICKER>-标题"
    # 会直接写明标的代码（-杰华特-688141-、-AMD.US-）。混装目录（如 reports/寒武纪/ 同时
    # 放了杰华特和寒武纪研报）只靠目录名会把两家都标成寒武纪，此时文件名的显式代码才是真相。
    name_ticker = _ticker_from_broker_name(path.name)
    ticker = ticker_override or name_ticker or dir_ticker or _normalize_ticker(text) or _normalize_ticker(path.stem)

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
        # SEC EDGAR 流水号文件名(0000050863-25-000109)绝无真实日期：其尾部 -25-000109
        # 会被下面的 yymmdd 规则误读成 20000109。直接放弃文件名日期，交给正文/财季兜底。
        if _re.match(r"^\d{10}-\d{2}-\d{6}", stem):
            return None
        m = _re.match(r"(\d{8})", stem)
        if m and _valid_yyyymmdd(m.group(1)):
            return m.group(1), "prefix"
        # 尾部 8 位日期：新闻/分析命名 "标题-YYYYMMDD"（如 ...-20260716）。日期是新闻
        # 时效性与"越新越可信"的关键，不能因放尾部而漏掉退回空值。
        m = _re.search(r"[-_](\d{8})(?:\D|$)", stem)
        if m and _valid_yyyymmdd(m.group(1)):
            return m.group(1), "suffix8"
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

    def _date_from_news_text(body: str) -> tuple[str, str] | None:
        """从新闻正文头部提取中文发布日期，只在文件名无可靠日期时启用。"""
        head = body[:3000]
        match = _re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", head)
        if not match:
            return None
        cand = f"{int(match.group(1)):04d}{int(match.group(2)):02d}{int(match.group(3)):02d}"
        return (cand, "news-text") if _valid_yyyymmdd(cand) else None

    def _date_from_fiscal_period(stem: str) -> tuple[str, str] | None:
        """末位兜底：从文件名的财季/财年推一个用于排序的代理日期（季度末/年末）。
        只求跨季度单调可比、能让真正近期的官方文件排在前，不追求真实披露日。
        命中返回 (yyyymmdd, 'fiscal-proxy')。覆盖本语料常见写法：
          Q1'26 / Q1'2026 / Q1 2024 / 1Q24 / 3Q25 / 4Q23 / 2Q2025 / FY2023 / Full Year 2023。"""
        qend = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}

        def _yr(yy: str) -> int:
            return int(yy) if len(yy) == 4 else 2000 + int(yy)

        m = (_re.search(r"[Qq]([1-4])['\s\-_]*((?:20)?\d{2})(?!\d)", stem)
             or _re.search(r"([1-4])[Qq]['\s\-_]*((?:20)?\d{2})(?!\d)", stem))
        if m:
            cand = f"{_yr(m.group(2)):04d}{qend[int(m.group(1))]}"
            if _valid_yyyymmdd(cand):
                return cand, "fiscal-proxy"
        m = _re.search(r"(?:FY|Full[\s_]*Year[\s_]*)((?:20)?\d{2})(?!\d)", stem, _re.IGNORECASE)
        if m:
            cand = f"{_yr(m.group(1)):04d}1231"
            if _valid_yyyymmdd(cand):
                return cand, "fiscal-proxy"
        return None

    hit = _date_from_name(path.stem)
    if not hit and data_source == "company_filing":
        hit = _date_from_official_text(text)
    if not hit and data_source == "web_news":
        hit = _date_from_news_text(text)
    if not hit:
        hit = _date_from_fiscal_period(path.stem)
    if hit:
        pub_date, _date_src = hit
        if _date_src != "prefix":
            print(f"[metadata] pub_date {pub_date} from {_date_src} (非标准前缀): {path.name}", flush=True)
    else:
        # 绝不退回 mtime：mtime=入库/下载日是纯噪声，会让历史文件以假的"今天"抢占
        # "越新越可信"权重（曾让 2023 年 AMD 电话会成为 INTC 的"最新官方指引"）。
        # 留空更安全：空日期在排序中视为最旧，不会劫持"最新"，只是不加分。
        pub_date = ""
        print(f"[metadata] pub_date 留空（文件名/正文/财季均无可靠日期，不退回mtime）: {path.name}", flush=True)

    source_file = _SETTINGS.locator(path)

    badges: list[str] = []
    source_weight = 1.0
    if data_source == "web_news":
        # 新闻可作事件/经营证据，但不能与公司官方文件同权。标题明确含传闻措辞时
        # 再降一级，供 Skill 层执行“只调情景概率、不改 Base 金额”的纪律。
        source_weight = 0.7
        if any(marker in path.stem for marker in ("据传", "传闻", "网传")):
            source_weight = 0.5
            badges.append("传闻待确认")

    return {
        "ticker": ticker or "UNKNOWN",
        "pub_date": pub_date,
        "period": "",
        "data_source": data_source,
        "source_file": source_file,
        "badges": badges,
        "source_weight": source_weight,
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
    extensionless_news = suffix == "" and "news" in path.parts
    # 只处理可抽文本的格式。.zip(XBRL)/.xlsx/.DS_Store 等二进制若走 read_text 兜底会被
    # 当乱码切片污染向量库（rescan glob '*' 会把它们也排进来）。无解析器直接跳过。
    # news/ 下偶有导出的无扩展名纯文本；只对该目录开放兜底，避免放宽到任意二进制。
    if suffix not in (".pdf", ".html", ".htm", ".md", ".txt") and not extensionless_news:
        print(f"[processor] skip 非文本文件（无解析器）: {path.name}")
        return []
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
            "badges":      c["metadata"].get("badges", []),
            "source_weight": c["metadata"].get("source_weight", 1.0),
        }
        flat_chunks.append(flat)

    # write to LanceDB — two-phase commit to avoid data loss window:
    # 1. compute embeddings and prepare new chunks (may fail)
    # 2. only after success, atomically replace old chunks
    from ira.storage.vector_store import upsert_chunks, delete_by_source_file

    try:
        # Phase 1: prepare new chunks (this validates data and computes embeddings)
        upsert_chunks(flat_chunks)

        # Phase 2: only after successful upsert, delete old chunks
        # (LanceDB upsert by chunk_id means new versions replace old, but we still
        #  need explicit delete to remove chunks that disappeared in this revision)
        delete_by_source_file(metadata["source_file"])

        # Re-insert to ensure clean state
        upsert_chunks(flat_chunks)
    except Exception as e:
        print(f"[processor] {path.name}: vector store update failed, old data preserved: {e}")
        raise

    # also save JSON for debugging / reproducible re-indexing
    out_dir = _SETTINGS.derived_root
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{path.stem}_chunks.json"
    out_path.write_text(json.dumps(flat_chunks, ensure_ascii=False, indent=2))
    print(f"[processor] {path.name}: {len(flat_chunks)} chunks → LanceDB + {out_path.name}")
    return flat_chunks
