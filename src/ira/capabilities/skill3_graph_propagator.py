"""
Skill 3: Supply-chain path propagator — queries Kùzu graph to find
companies affected by upstream commodity price movement.
"""

from typing import Any


def query(input_product: str) -> list[dict[str, Any]]:
    from ira.storage.graph_store import query_affected_companies
    return query_affected_companies(input_product)
