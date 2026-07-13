"""
Text processing pipeline: PDF → clean Markdown, HTML → clean text, then chunk + embed metadata.
Called by watchdog_monitor for manual inputs and by refresh scripts for processed artifacts.
"""

import hashlib
import json
import re
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


def _extract_pdf(path: Path) -> str:
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


def _infer_metadata(path: Path, text: str, ticker_override: str | None = None) -> dict[str, Any]:
    ticker = ticker_override or _normalize_ticker(text) or _normalize_ticker(path.stem)

    # walk up to find the evidence category dir (reports / announcements / news)
    source_map = {"reports": "broker_report", "announcements": "announcement", "news": "web_news"}
    data_source = "web_news"
    for parent in path.parents:
        if parent.name in source_map:
            data_source = source_map[parent.name]
            break

    # extract pub_date from filename prefix like 20260701-
    import re as _re
    from datetime import date as _date

    def _valid_yyyymmdd(s: str) -> bool:
        try:
            _date(int(s[:4]), int(s[4:6]), int(s[6:8]))
            return True
        except ValueError:
            return False

    m = _re.match(r"(\d{8})", path.stem)
    if m and _valid_yyyymmdd(m.group(1)):
        pub_date = m.group(1)
    else:
        # ponytail: no valid date in filename (e.g. SEC accession-number PDFs like
        # "0000050863-25-000052.pdf" — the leading 8 digits parse as \d{8} but aren't
        # a real date) — fall back to file mtime formatted as YYYYMMDD, not a raw
        # epoch string. Still not the true publish date, but at least a valid/
        # sortable/comparable date string instead of a garbage number.
        pub_date = _date.fromtimestamp(path.stat().st_mtime).strftime("%Y%m%d")

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
