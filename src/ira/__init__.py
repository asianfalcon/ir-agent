"""Compatibility import for the former ``ira`` package name.

New code must import ``alphasonar``. Keeping the package search path pointed at
AlphaSonar lets existing integrations continue importing modules such as
``ira.settings`` during the migration window.
"""

from __future__ import annotations

import importlib
import sys

import alphasonar as _alphasonar

__version__ = _alphasonar.__version__
__path__ = _alphasonar.__path__

# Settings owns a process-wide cache, so the former import path must resolve to
# the exact same module object instead of loading a second copy under ``ira``.
settings = importlib.import_module("alphasonar.settings")
sys.modules[f"{__name__}.settings"] = settings
