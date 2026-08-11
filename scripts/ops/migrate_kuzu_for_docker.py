"""
Migrate Kùzu data from kuzu_root.db (file) to kuzu_explorer/ (directory).
Run: python scripts/ops/migrate_kuzu_for_docker.py
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from alphasonar.settings import get_settings

_settings = get_settings()
SRC = _settings.kuzu_path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--destination", type=Path, default=_settings.kuzu_path.parent / "kuzu_explorer")
args = parser.parse_args()
DST = args.destination.expanduser().resolve()

import kuzu

if DST.exists():
    raise SystemExit(f"destination already exists; refusing to overwrite: {DST}")

src_db = kuzu.Database(str(SRC))
src    = kuzu.Connection(src_db)

dst_db = kuzu.Database(str(DST))
dst    = kuzu.Connection(dst_db)

# --- Schema ---
dst.execute("CREATE NODE TABLE IF NOT EXISTS Company(ticker STRING, name STRING, PRIMARY KEY(ticker))")
dst.execute("CREATE NODE TABLE IF NOT EXISTS Product(name STRING, PRIMARY KEY(name))")
dst.execute("CREATE NODE TABLE IF NOT EXISTS Customer(name STRING, PRIMARY KEY(name))")
dst.execute("CREATE REL TABLE IF NOT EXISTS PRODUCES(FROM Company TO Product)")
dst.execute("CREATE REL TABLE IF NOT EXISTS UPSTREAM_OF(FROM Product TO Product, transmission_coefficient DOUBLE)")
dst.execute("CREATE REL TABLE IF NOT EXISTS COMPETES_WITH(FROM Product TO Product)")
dst.execute("CREATE REL TABLE IF NOT EXISTS BUYS_FROM(FROM Customer TO Company)")

# --- Copy nodes ---
try:
    r = src.execute("MATCH (c:Company) RETURN c.ticker, c.name")
    while r.has_next():
        ticker, name = r.get_next()
        dst.execute("MERGE (c:Company {ticker: $t}) SET c.name = $n", {"t": ticker, "n": name})
    print("Copied Company nodes")
except Exception as e:
    print(f"Company: {e}")

try:
    r = src.execute("MATCH (p:Product) RETURN p.name")
    while r.has_next():
        (name,) = r.get_next()
        dst.execute("MERGE (p:Product {name: $n})", {"n": name})
    print("Copied Product nodes")
except Exception as e:
    print(f"Product: {e}")

try:
    r = src.execute("MATCH (c:Customer) RETURN c.name")
    while r.has_next():
        (name,) = r.get_next()
        dst.execute("MERGE (c:Customer {name: $n})", {"n": name})
    print("Copied Customer nodes")
except Exception as e:
    print(f"Customer: {e}")

# --- Copy edges ---
try:
    r = src.execute("MATCH (c:Company)-[:PRODUCES]->(p:Product) RETURN c.ticker, p.name")
    while r.has_next():
        ticker, pname = r.get_next()
        dst.execute(
            "MATCH (c:Company {ticker:$t}), (p:Product {name:$n}) MERGE (c)-[:PRODUCES]->(p)",
            {"t": ticker, "n": pname}
        )
    print("Copied PRODUCES edges")
except Exception as e:
    print(f"PRODUCES: {e}")

try:
    r = src.execute("MATCH (p1:Product)-[rel:UPSTREAM_OF]->(p2:Product) RETURN p1.name, p2.name, rel.transmission_coefficient")
    while r.has_next():
        p1, p2, coef = r.get_next()
        dst.execute(
            "MATCH (a:Product {name:$a}), (b:Product {name:$b}) MERGE (a)-[:UPSTREAM_OF {transmission_coefficient:$c}]->(b)",
            {"a": p1, "b": p2, "c": coef or 0.0}
        )
    print("Copied UPSTREAM_OF edges")
except Exception as e:
    print(f"UPSTREAM_OF: {e}")

try:
    r = src.execute("MATCH (p1:Product)-[:COMPETES_WITH]->(p2:Product) RETURN p1.name, p2.name")
    while r.has_next():
        p1, p2 = r.get_next()
        dst.execute(
            "MATCH (a:Product {name:$a}), (b:Product {name:$b}) MERGE (a)-[:COMPETES_WITH]->(b)",
            {"a": p1, "b": p2}
        )
    print("Copied COMPETES_WITH edges")
except Exception as e:
    print(f"COMPETES_WITH: {e}")

try:
    r = src.execute("MATCH (cu:Customer)-[:BUYS_FROM]->(c:Company) RETURN cu.name, c.ticker")
    while r.has_next():
        cuname, ticker = r.get_next()
        dst.execute(
            "MATCH (cu:Customer {name:$n}), (c:Company {ticker:$t}) MERGE (cu)-[:BUYS_FROM]->(c)",
            {"n": cuname, "t": ticker}
        )
    print("Copied BUYS_FROM edges")
except Exception as e:
    print(f"BUYS_FROM: {e}")

print(f"\nDone. Directory DB at: {DST}")
print("Run Docker with:")
print(f'  docker rm -f kuzu-explorer')
print(f'  docker run -d --name kuzu-explorer -p 8000:8000 \\')
print(f'    -v "{DST}:/database" --env MODE=READ_ONLY kuzudb/explorer')
