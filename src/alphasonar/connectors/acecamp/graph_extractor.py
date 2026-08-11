"""
从 AceCamp 专家专栏导出 JSON 中提取实体关系并写入 Kùzu 图谱。

用法：
    python -m alphasonar.connectors.acecamp.graph_extractor
"""
import json
import re
from pathlib import Path

from alphasonar.settings import get_settings

_SETTINGS = get_settings()
EXPERT_EXPORT_DIR = _SETTINGS.manual_source_root / "expert_minutes" / "acecamp" / "export"
LEGACY_MINUTES_DIR = _SETTINGS.manual_source_root / "minutes"


def extract_entities(article: dict) -> dict:
    """
    从 article_info JSON 提取实体。
    返回 {companies: [...], products: [...], relations: [...]}
    """
    companies = []
    products = []
    relations = []

    # 从 corporations 字段提取公司
    for corp in article.get("corporations", []):
        companies.append({
            "name": corp.get("name"),
            "ticker": corp.get("ticker"),
        })

    # 从 hashtags 提取产品/技术标签
    for tag in article.get("hashtags", []):
        products.append({"name": tag})

    # 从 content/summary 提取关系（简单规则：提到公司名+产品名）
    title = article.get("title", "")
    summary = article.get("summary", "")
    content_html = article.get("content", "")
    content = re.sub(r'<[^>]+>', '', content_html)
    text = f"{title} {summary} {content}"

    for company in companies:
        for product in products:
            if company["name"] in text and product["name"] in text:
                relations.append({
                    "company": company["name"],
                    "ticker": company.get("ticker", ""),
                    "product": product["name"],
                    "type": "produces",
                })

    return {"companies": companies, "products": products, "relations": relations}


def upsert_to_kuzu(entities: dict) -> int:
    """写入 Kùzu 图数据库，返回插入的关系数。"""
    from alphasonar.storage.graph_store import get_connection

    conn = get_connection()
    count = 0

    for rel in entities["relations"]:
        company_name = rel["company"]
        ticker = rel.get("ticker", "")
        product = rel["product"]

        # 跳过没有 ticker 的公司（Kùzu Company 节点主键是 ticker）
        if not ticker:
            continue

        # 创建 Company 节点（如不存在）
        conn.execute(
            "MERGE (c:Company {ticker: $ticker}) ON CREATE SET c.name = $name",
            {"ticker": ticker, "name": company_name}
        )

        # 创建 Product 节点（如不存在）
        conn.execute(
            "MERGE (p:Product {name: $name})",
            {"name": product}
        )

        # 创建 PRODUCES 关系
        conn.execute(
            """
            MATCH (c:Company {ticker: $ticker})
            MATCH (p:Product {name: $product})
            MERGE (c)-[:PRODUCES]->(p)
            """,
            {"ticker": ticker, "product": product}
        )
        count += 1

    return count


def process_article(json_path: Path) -> int:
    """处理单个 JSON 并提取到图谱，返回关系数。"""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    article = data.get("data") or data

    article_id = article.get("id")
    title = article.get("title", str(article_id))[:30]

    entities = extract_entities(article)
    if not entities["relations"]:
        print(f"[graph] {article_id} '{title}': 未提取到关系")
        return 0

    count = upsert_to_kuzu(entities)
    print(f"[graph] {article_id} '{title}': {count} 条关系")
    return count


def _input_dir() -> Path:
    """Prefer the new AceCamp expert export directory, with old minutes path as fallback."""
    if any(EXPERT_EXPORT_DIR.glob("*.json")):
        return EXPERT_EXPORT_DIR
    return LEGACY_MINUTES_DIR


def batch_process() -> int:
    """批量处理 data/inputs/expert_minutes/acecamp/export/ 下所有 JSON。"""
    input_dir = _input_dir()
    if not input_dir.exists():
        print(f"[graph] 目录不存在: {input_dir}")
        return 0

    files = sorted(input_dir.glob("*.json"))
    if not files:
        print(f"[graph] 无 JSON 文件")
        return 0

    print(f"[graph] 从 {input_dir} 找到 {len(files)} 个 JSON")
    total = 0
    for f in files:
        try:
            n = process_article(f)
            total += n
        except Exception as e:
            print(f"[graph] {f.name} ERROR: {e}")
    return total


if __name__ == "__main__":
    n = batch_process()
    print(f"\n完成：共写入 {n} 条关系到图谱")
