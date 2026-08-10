"""Central path and runtime configuration for IRA.

The code repository and mutable runtime state are intentionally separated.  Existing
local installations keep using the legacy in-repository directories until
``IRA_RUNTIME_ROOT`` is set, so this module can be adopted without moving data first.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _default_resource_root() -> Path:
    checkout = PROJECT_ROOT / "resources"
    return checkout if checkout.exists() else Path(sys.prefix) / "share" / "ira-agent"


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser().resolve() if value else None


@dataclass(frozen=True)
class Settings:
    project_root: Path
    runtime_root: Path | None
    manual_source_root: Path
    external_source_root: Path
    derived_root: Path
    store_root: Path
    artifact_root: Path
    cache_root: Path
    sqlite_path: Path
    lance_path: Path
    kuzu_path: Path
    config_root: Path
    resource_root: Path
    prompt_root: Path

    @classmethod
    def from_env(cls) -> "Settings":
        runtime_root = _env_path("IRA_RUNTIME_ROOT")

        if runtime_root is None:
            # Compatibility mode: do not move or duplicate existing user data.
            manual_source_root = PROJECT_ROOT / "data" / "inputs"
            external_source_root = PROJECT_ROOT / "data" / "raw"
            derived_root = PROJECT_ROOT / "data" / "processed"
            store_root = PROJECT_ROOT / "data" / "storage"
            artifact_root = PROJECT_ROOT / "output"
            cache_root = PROJECT_ROOT / "tmp"
            default_sqlite = PROJECT_ROOT / "databases" / "ira.db"
            default_lance = store_root / "lancedb_root"
            default_kuzu = store_root / "kuzu_root.db"
        else:
            manual_source_root = runtime_root / "sources" / "manual"
            external_source_root = runtime_root / "sources" / "external"
            derived_root = runtime_root / "derived"
            store_root = runtime_root / "stores"
            artifact_root = runtime_root / "artifacts"
            cache_root = runtime_root / "cache"
            default_sqlite = store_root / "relational" / "ira.db"
            default_lance = store_root / "vector" / "lancedb_root"
            default_kuzu = store_root / "graph" / "kuzu_root.db"

        config_root = _env_path("IRA_CONFIG_ROOT") or PROJECT_ROOT / "config"
        resource_root = _env_path("IRA_RESOURCE_ROOT") or _default_resource_root()
        return cls(
            project_root=PROJECT_ROOT,
            runtime_root=runtime_root,
            manual_source_root=_env_path("IRA_MANUAL_SOURCE_ROOT") or manual_source_root,
            external_source_root=_env_path("IRA_EXTERNAL_SOURCE_ROOT") or external_source_root,
            derived_root=_env_path("IRA_DERIVED_ROOT") or derived_root,
            store_root=_env_path("IRA_STORE_ROOT") or store_root,
            artifact_root=_env_path("IRA_ARTIFACT_ROOT") or artifact_root,
            cache_root=_env_path("IRA_CACHE_ROOT") or cache_root,
            sqlite_path=_env_path("IRA_SQLITE_PATH") or default_sqlite,
            lance_path=_env_path("IRA_LANCE_PATH") or default_lance,
            kuzu_path=_env_path("IRA_KUZU_PATH") or default_kuzu,
            config_root=config_root,
            resource_root=resource_root,
            prompt_root=_env_path("IRA_PROMPT_ROOT") or resource_root / "prompts",
        )

    @property
    def vocab_path(self) -> Path:
        return self.resource_root / "dictionaries" / "vocab_dictionary.json"

    @property
    def variable_schema_path(self) -> Path:
        return self.resource_root / "schemas" / "variable_schema.json"

    @property
    def uses_legacy_layout(self) -> bool:
        return self.runtime_root is None

    def ensure_runtime_dirs(self) -> None:
        """Create mutable runtime directories; never called implicitly on import."""
        directories = (
            self.manual_source_root,
            self.external_source_root,
            self.derived_root,
            self.store_root,
            self.artifact_root,
            self.cache_root,
            self.sqlite_path.parent,
            self.lance_path.parent,
            self.kuzu_path.parent,
        )
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def locator(self, path: Path) -> str:
        """Return a portable lineage locator instead of a machine-specific path."""
        resolved = path.expanduser().resolve()
        if self.uses_legacy_layout:
            try:
                return resolved.relative_to(self.project_root.resolve()).as_posix()
            except ValueError:
                return resolved.as_posix()
        roots = (
            ("manual", self.manual_source_root),
            ("external", self.external_source_root),
            ("derived", self.derived_root),
            ("artifact", self.artifact_root),
        )
        for scheme, root in roots:
            try:
                return f"{scheme}://{resolved.relative_to(root.resolve()).as_posix()}"
            except ValueError:
                continue
        return resolved.as_posix()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


def reset_settings_cache() -> None:
    """Test/helper hook for re-reading environment variables."""
    get_settings.cache_clear()
