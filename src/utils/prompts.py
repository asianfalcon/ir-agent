from pathlib import Path

_DIR = Path(__file__).parent.parent.parent / "config" / "prompts"

def load(name: str) -> str:
    return (_DIR / name).read_text(encoding="utf-8")
