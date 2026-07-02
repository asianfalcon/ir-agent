"""
Export Kùzu graph to interactive HTML via pyvis.
Run: python scripts/visualize_graph.py [ticker]
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import kuzu
from pyvis.network import Network

KUZU_PATH = ROOT / "data" / "storage" / "kuzu_root.db"
FILTER_TICKER = sys.argv[1] if len(sys.argv) > 1 else None

db = kuzu.Database(str(KUZU_PATH))
conn = kuzu.Connection(db)

net = Network(height="750px", width="100%", bgcolor="#0d1117", font_color="white",
              notebook=False, directed=True)
net.set_options("""
{
  "physics": { "solver": "forceAtlas2Based",
               "forceAtlas2Based": { "gravitationalConstant": -80, "springLength": 120 },
               "stabilization": { "iterations": 200 } },
  "edges": { "arrows": "to", "width": 2, "smooth": { "type": "curvedCW", "roundness": 0.2 } },
  "nodes": { "borderWidth": 2, "shadow": true, "font": { "size": 13 } }
}
""")

added_nodes = set()

def add_node(nid, label, color, shape, size, title):
    if nid not in added_nodes:
        net.add_node(nid, label=label, color=color, shape=shape, size=size, title=title)
        added_nodes.add(nid)

# ── Company nodes ──────────────────────────────────────────────
res = conn.execute("MATCH (c:Company) RETURN c.ticker, c.name")
while res.has_next():
    ticker, name = res.get_next()
    if FILTER_TICKER and ticker != FILTER_TICKER and name not in ('寒武纪',):
        pass  # still add but smaller
    color = "#e94560" if ticker == FILTER_TICKER or name == "寒武纪" else "#888"
    size  = 35 if ticker == FILTER_TICKER or name == "寒武纪" else 20
    add_node(f"C:{ticker}", f"{name}\n({ticker})", color, "dot", size, f"公司: {name}\n{ticker}")

# ── Product nodes ──────────────────────────────────────────────
res = conn.execute("MATCH (p:Product) RETURN p.name")
while res.has_next():
    (name,) = res.get_next()
    is_own = name.startswith("MLU")
    color = "#f5a623" if is_own else "#4a9eff"
    add_node(f"P:{name}", name, color, "diamond", 20 if is_own else 15, f"产品: {name}")

# ── Customer nodes ─────────────────────────────────────────────
try:
    res = conn.execute("MATCH (c:Customer) RETURN c.name")
    while res.has_next():
        (name,) = res.get_next()
        add_node(f"CU:{name}", name, "#2ecc71", "triangle", 18, f"客户: {name}")
except Exception:
    pass

# ── PRODUCES ──────────────────────────────────────────────────
res = conn.execute("MATCH (c:Company)-[:PRODUCES]->(p:Product) RETURN c.ticker, p.name")
while res.has_next():
    ticker, pname = res.get_next()
    if f"C:{ticker}" in added_nodes and f"P:{pname}" in added_nodes:
        net.add_edge(f"C:{ticker}", f"P:{pname}", label="生产", color="#f5a623", width=3)

# ── UPSTREAM_OF ───────────────────────────────────────────────
res = conn.execute("MATCH (p1:Product)-[r:UPSTREAM_OF]->(p2:Product) RETURN p1.name, p2.name, r.transmission_coefficient")
while res.has_next():
    p1, p2, coef = res.get_next()
    if f"P:{p1}" in added_nodes and f"P:{p2}" in added_nodes:
        net.add_edge(f"P:{p1}", f"P:{p2}", label=f"上游 {coef}", color="#9b59b6", dashes=True)

# ── COMPETES_WITH ─────────────────────────────────────────────
try:
    res = conn.execute("MATCH (p1:Product)-[:COMPETES_WITH]->(p2:Product) RETURN p1.name, p2.name")
    while res.has_next():
        p1, p2 = res.get_next()
        if f"P:{p1}" in added_nodes and f"P:{p2}" in added_nodes:
            net.add_edge(f"P:{p1}", f"P:{p2}", label="竞争", color="#e74c3c", dashes=True, width=1)
except Exception:
    pass

# ── BUYS_FROM ─────────────────────────────────────────────────
try:
    res = conn.execute("MATCH (cu:Customer)-[:BUYS_FROM]->(c:Company) RETURN cu.name, c.ticker")
    while res.has_next():
        cuname, ticker = res.get_next()
        if f"CU:{cuname}" in added_nodes and f"C:{ticker}" in added_nodes:
            net.add_edge(f"CU:{cuname}", f"C:{ticker}", label="采购", color="#2ecc71", width=2)
except Exception:
    pass

# ── Legend (static nodes in corner) ───────────────────────────
legend = [
    ("legend_company",  "公司",  "#e94560", "dot",      10),
    ("legend_own_prod", "自研产品", "#f5a623", "diamond",  10),
    ("legend_comp_prod","竞品",  "#4a9eff", "diamond",  10),
    ("legend_customer", "客户",  "#2ecc71", "triangle", 10),
]
for nid, lbl, col, shape, sz in legend:
    net.add_node(nid, label=lbl, color=col, shape=shape, size=sz,
                 x=-600, y=-300 + legend.index((nid,lbl,col,shape,sz))*50,
                 physics=False, font={"size": 11})

suffix = f"_{FILTER_TICKER}" if FILTER_TICKER else ""
out = ROOT / "data" / f"graph_viz{suffix}.html"
net.save_graph(str(out))
print(f"saved → {out}")

import subprocess
subprocess.run(["open", str(out)])
