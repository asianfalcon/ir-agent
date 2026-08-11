"""
AlphaSonar Track — monitors evidence inputs and triggers processing.
Handles the file-lock race (2s stability check) and crash-recovery rescan on startup.
"""

import hashlib
import sqlite3
import time
from pathlib import Path
from queue import Queue
from threading import Thread

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from alphasonar.settings import get_settings

_SETTINGS = get_settings()
WATCH_DIRS = [
    _SETTINGS.manual_source_root / "reports",
    _SETTINGS.manual_source_root / "announcements",
    _SETTINGS.manual_source_root / "expert_minutes" / "acecamp" / "export",
]
DB_PATH = _SETTINGS.sqlite_path
STABILITY_DELAY = 2.0  # seconds to wait after last modify event


def _source_id(path: str) -> str:
    return hashlib.md5(path.encode()).hexdigest()


def _is_stable(path: Path) -> bool:
    """Return True when file size stops changing and can be opened exclusively."""
    try:
        size_before = path.stat().st_size
        time.sleep(STABILITY_DELAY)
        if path.stat().st_size != size_before:
            return False
        # Try exclusive open
        with open(path, "rb"):
            return True
    except (OSError, FileNotFoundError):
        return False


def _log_file(conn: sqlite3.Connection, path: Path) -> None:
    mtime = path.stat().st_mtime
    conn.execute(
        "INSERT OR REPLACE INTO sys_file_log(file_path, mtime) VALUES (?,?)",
        (str(path), mtime),
    )
    conn.execute(
        "INSERT OR IGNORE INTO sys_data_lineage(source_id, file_path) VALUES (?,?)",
        (_source_id(str(path)), str(path)),
    )
    conn.commit()


def _already_processed(conn: sqlite3.Connection, path: Path) -> bool:
    row = conn.execute("SELECT mtime FROM sys_file_log WHERE file_path=?", (str(path),)).fetchone()
    if row is None:
        return False
    return abs(row[0] - path.stat().st_mtime) < 0.01


def rescan(queue: Queue) -> None:
    """On startup: queue any file not yet in sys_file_log or with changed mtime."""
    conn = sqlite3.connect(DB_PATH)
    for watch_dir in WATCH_DIRS:
        for path in watch_dir.rglob("*"):
            if path.is_file() and not _already_processed(conn, path):
                queue.put(path)
    conn.close()


class _Handler(FileSystemEventHandler):
    def __init__(self, queue: Queue):
        self._queue = queue
        self._pending: dict[str, float] = {}

    def on_modified(self, event):
        if not event.is_directory:
            self._pending[event.src_path] = time.time()

    on_created = on_modified

    def flush_pending(self) -> None:
        now = time.time()
        ready = [p for p, t in self._pending.items() if now - t >= STABILITY_DELAY]
        for p in ready:
            del self._pending[p]
            path = Path(p)
            if path.exists():
                self._queue.put(path)


def _process_worker(queue: Queue) -> None:
    """Consumes the queue; import processing here to keep ingestion decoupled."""
    from alphasonar.connectors.acecamp.expert_processor import process_article  # lazy import
    from alphasonar.pipelines.text_processor import process_file  # lazy import

    conn = sqlite3.connect(DB_PATH)
    while True:
        path: Path = queue.get()
        if not _is_stable(path):
            queue.put(path)  # re-queue, still writing
            continue
        if _already_processed(conn, path):
            continue
        print(f"[Track] processing: {path.name}")
        try:
            if "expert_minutes" in path.parts:
                # Without an explicit batch ticker, process_article infers tickers
                # from the AceCamp corporations payload and writes one copy per ticker.
                process_article(path)
            else:
                process_file(path)
            _log_file(conn, path)
        except Exception as e:
            print(f"[Track] ERROR {path.name}: {e}")
        finally:
            queue.task_done()


def start() -> None:
    queue: Queue = Queue()
    rescan(queue)

    handler = _Handler(queue)
    observer = Observer()
    for d in WATCH_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        observer.schedule(handler, str(d), recursive=True)

    observer.start()
    Thread(target=_process_worker, args=(queue,), daemon=True).start()
    print(f"[Track] tracking {[str(d) for d in WATCH_DIRS]}")

    try:
        while True:
            handler.flush_pending()
            time.sleep(0.5)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    start()
