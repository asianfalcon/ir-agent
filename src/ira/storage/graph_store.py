"""
Kùzu embedded graph store — initialises schema and provides helpers for
querying upstream product-company relationships (Skill 3).
"""

from typing import Any

import kuzu

from ira.settings import get_settings

KUZU_PATH = get_settings().kuzu_path


def _get_db() -> kuzu.Database:
    KUZU_PATH.parent.mkdir(parents=True, exist_ok=True)
    return kuzu.Database(str(KUZU_PATH))


def init_schema() -> None:
    db = _get_db()
    conn = kuzu.Connection(db)
    stmts = [
        "CREATE NODE TABLE IF NOT EXISTS Company(ticker STRING, name STRING, PRIMARY KEY(ticker))",
        "CREATE NODE TABLE IF NOT EXISTS Product(name STRING, PRIMARY KEY(name))",
        "CREATE REL TABLE IF NOT EXISTS PRODUCES(FROM Company TO Product)",
        "CREATE REL TABLE IF NOT EXISTS UPSTREAM_OF(FROM Product TO Product, transmission_coefficient FLOAT)",
    ]
    for s in stmts:
        try:
            conn.execute(s)
        except Exception as e:
            # Table already exists — safe to ignore
            if "already exists" not in str(e).lower():
                raise
    print("[graph_store] Kùzu schema ready")


def upsert_company(ticker: str, name: str) -> None:
    db = _get_db()
    conn = kuzu.Connection(db)
    conn.execute(
        "MERGE (c:Company {ticker: $ticker}) SET c.name = $name",
        {"ticker": ticker, "name": name},
    )


def upsert_product(name: str) -> None:
    db = _get_db()
    conn = kuzu.Connection(db)
    conn.execute("MERGE (p:Product {name: $name})", {"name": name})


def link_produces(ticker: str, product_name: str) -> None:
    db = _get_db()
    conn = kuzu.Connection(db)
    conn.execute(
        """
        MATCH (c:Company {ticker: $ticker}), (p:Product {name: $product})
        MERGE (c)-[:PRODUCES]->(p)
        """,
        {"ticker": ticker, "product": product_name},
    )


def link_upstream(upstream: str, downstream: str, coef: float = 1.0) -> None:
    db = _get_db()
    conn = kuzu.Connection(db)
    conn.execute(
        """
        MATCH (p1:Product {name: $up}), (p2:Product {name: $down})
        MERGE (p1)-[r:UPSTREAM_OF]->(p2)
        SET r.transmission_coefficient = $coef
        """,
        {"up": upstream, "down": downstream, "coef": coef},
    )


def get_connection() -> kuzu.Connection:
    """Return a connection to the Kùzu database."""
    db = _get_db()
    return kuzu.Connection(db)


def query_affected_companies(input_product: str) -> list[dict[str, Any]]:
    """Return companies that produce a product downstream of input_product."""
    db = _get_db()
    conn = kuzu.Connection(db)
    result = conn.execute(
        """
        MATCH (p1:Product {name: $input_product})-[r:UPSTREAM_OF]->(p2:Product)<-[:PRODUCES]-(c:Company)
        RETURN c.name AS company_name, c.ticker AS ticker, p2.name AS product
        """,
        {"input_product": input_product},
    )
    rows = []
    while result.has_next():
        rows.append(result.get_next())
    columns = ["company_name", "ticker", "product"]
    return [dict(zip(columns, row)) for row in rows]


if __name__ == "__main__":
    init_schema()
