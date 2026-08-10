from ira.settings import get_settings

_DIR = get_settings().prompt_root

def load(name: str) -> str:
    return (_DIR / name).read_text(encoding="utf-8")
