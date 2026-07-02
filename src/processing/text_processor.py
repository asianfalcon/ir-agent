"""
Text processing pipeline: PDF → clean Markdown, HTML → clean text, then chunk + embed metadata.
Called by watchdog_monitor when a new file lands in data/inputs/.
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
    return full


def _extract_html(path: Path) -> str:
    soup = BeautifulSoup(path.read_bytes(), "lxml")
    for tag in soup(["nav", "footer", "script", "style"]):
        tag.decompose()
    # keep only meaningful elements
    parts = []
    for el in soup.find_all(["h1", "h2", "h3", "p", "table"]):
        parts.append(el.get_text(" ", strip=True))
    return "\n".join(parts)


def _infer_metadata(path: Path, text: str) -> dict[str, Any]:
    ticker = _normalize_ticker(text) or _normalize_ticker(path.stem)
    source_map = {
        "reports": "broker_report",
        "announcements": "announcement",
    }
    data_source = source_map.get(path.parent.name, "web_news")
    return {
        "ticker": ticker or "UNKNOWN",
        "pub_date": path.stat().st_mtime,  # filled properly when available in filename
        "period": "",  # enriched downstream if detectable
        "data_source": data_source,
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


def process_file(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf(path)
    elif suffix in (".html", ".htm"):
        text = _extract_html(path)
    else:
        text = path.read_text(errors="ignore")

    metadata = _infer_metadata(path, text)
    chunks = chunk_text(text, metadata)

    # Persist chunks to processed/
    out_dir = ROOT / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{path.stem}_chunks.json"
    out_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2))
    print(f"[processor] {len(chunks)} chunks → {out_path.name}")
    return chunks
