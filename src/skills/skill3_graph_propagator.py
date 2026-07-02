"""
Skill 3: Supply-chain path propagator — queries Kùzu graph to find
companies affected by upstream commodity price movement.
"""

from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent.parent


def query(input_product: str) -> list[dict[str, Any]]:
    from src.db.graph_store import query_affected_companies
    return query_affected_companies(input_product)
