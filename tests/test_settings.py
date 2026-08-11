from alphasonar.settings import Settings

_ENV_KEYS = (
    "ALPHASONAR_RUNTIME_ROOT",
    "ALPHASONAR_MANUAL_SOURCE_ROOT",
    "ALPHASONAR_EXTERNAL_SOURCE_ROOT",
    "ALPHASONAR_DERIVED_ROOT",
    "ALPHASONAR_STORE_ROOT",
    "ALPHASONAR_ARTIFACT_ROOT",
    "ALPHASONAR_CACHE_ROOT",
    "ALPHASONAR_SQLITE_PATH",
    "ALPHASONAR_LANCE_PATH",
    "ALPHASONAR_KUZU_PATH",
    "ALPHASONAR_CONFIG_ROOT",
    "ALPHASONAR_RESOURCE_ROOT",
    "ALPHASONAR_PROMPT_ROOT",
    "IRA_RUNTIME_ROOT",
    "IRA_MANUAL_SOURCE_ROOT",
    "IRA_EXTERNAL_SOURCE_ROOT",
    "IRA_DERIVED_ROOT",
    "IRA_STORE_ROOT",
    "IRA_ARTIFACT_ROOT",
    "IRA_CACHE_ROOT",
    "IRA_SQLITE_PATH",
    "IRA_LANCE_PATH",
    "IRA_KUZU_PATH",
    "IRA_CONFIG_ROOT",
    "IRA_RESOURCE_ROOT",
    "IRA_PROMPT_ROOT",
)


def _clear(monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_legacy_layout_is_backward_compatible(monkeypatch):
    _clear(monkeypatch)
    settings = Settings.from_env()
    assert settings.uses_legacy_layout
    assert settings.resource_root == settings.project_root / "resources"
    current = settings.project_root / "databases" / "alphasonar.db"
    legacy = settings.project_root / "databases" / "ira.db"
    assert settings.sqlite_path == (legacy if legacy.exists() and not current.exists() else current)
    assert settings.lance_path == settings.project_root / "data" / "storage" / "lancedb_root"
    source = settings.project_root / "data" / "inputs" / "reports" / "AMD" / "q2.pdf"
    assert settings.locator(source) == "data/inputs/reports/AMD/q2.pdf"


def test_runtime_root_separates_mutable_state(monkeypatch, tmp_path):
    _clear(monkeypatch)
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("ALPHASONAR_RUNTIME_ROOT", str(runtime))
    settings = Settings.from_env()
    assert not settings.uses_legacy_layout
    assert settings.manual_source_root == runtime / "sources" / "manual"
    assert settings.external_source_root == runtime / "sources" / "external"
    assert settings.derived_root == runtime / "derived"
    assert settings.sqlite_path == runtime / "stores" / "relational" / "alphasonar.db"
    assert settings.lance_path == runtime / "stores" / "vector" / "lancedb_root"
    assert settings.kuzu_path == runtime / "stores" / "graph" / "kuzu_root.db"
    assert settings.artifact_root == runtime / "artifacts"
    assert settings.locator(runtime / "sources" / "manual" / "reports" / "a.pdf") == "manual://reports/a.pdf"


def test_individual_path_override_wins(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("ALPHASONAR_RUNTIME_ROOT", str(tmp_path / "runtime"))
    custom_db = tmp_path / "database" / "custom.db"
    monkeypatch.setenv("ALPHASONAR_SQLITE_PATH", str(custom_db))
    settings = Settings.from_env()
    assert settings.sqlite_path == custom_db


def test_former_ira_environment_is_compatible(monkeypatch, tmp_path):
    _clear(monkeypatch)
    former_runtime = tmp_path / "former-runtime"
    monkeypatch.setenv("IRA_RUNTIME_ROOT", str(former_runtime))
    settings = Settings.from_env()
    assert settings.runtime_root == former_runtime
    assert settings.sqlite_path == former_runtime / "stores" / "relational" / "alphasonar.db"


def test_alphasonar_environment_wins_over_former_name(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("IRA_RUNTIME_ROOT", str(tmp_path / "former"))
    current_runtime = tmp_path / "current"
    monkeypatch.setenv("ALPHASONAR_RUNTIME_ROOT", str(current_runtime))
    assert Settings.from_env().runtime_root == current_runtime


def test_ensure_runtime_dirs_is_explicit(monkeypatch, tmp_path):
    _clear(monkeypatch)
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("ALPHASONAR_RUNTIME_ROOT", str(runtime))
    settings = Settings.from_env()
    assert not runtime.exists()
    settings.ensure_runtime_dirs()
    assert settings.sqlite_path.parent.is_dir()
    assert settings.lance_path.parent.is_dir()
    assert settings.artifact_root.is_dir()
