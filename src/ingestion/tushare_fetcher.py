"""
Tushare fetcher — 财务数据、日线行情、新闻公告。
需在 config/api_keys.json 填入 tushare_token。
"""
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
_KEYS_PATH = ROOT / "config" / "api_keys.json"
RAW_DIR = ROOT / "data" / "raw" / "tushare"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def _pro():
    import tushare as ts
    token = json.loads(_KEYS_PATH.read_text()).get("tushare_token", "")
    if not token:
        raise RuntimeError("tushare_token 未配置，请在 config/api_keys.json 填入")
    ts.set_token(token)
    return ts.pro_api()


def fetch_daily(ts_code: str) -> int:
    """拉取近 90 天日线行情，存 JSON，返回行数。ts_code 格式：688141.SH"""
    today = date.today().isoformat().replace("-", "")
    start = (date.today() - timedelta(days=90)).isoformat().replace("-", "")
    out = RAW_DIR / f"{ts_code}_daily_{today}.json"
    if out.exists():
        return 0
    try:
        pro = _pro()
        df = pro.daily(ts_code=ts_code, start_date=start, end_date=today)
        out.write_text(df.to_json(orient="records", force_ascii=False))
        print(f"[tushare] daily {ts_code}: {len(df)} rows")
        return len(df)
    except Exception as e:
        print(f"[tushare] daily ERROR {ts_code}: {e}")
        return 0


def fetch_financials(ts_code: str) -> int:
    """拉取最新财务摘要（income + balancesheet），存 JSON。"""
    today = date.today().isoformat().replace("-", "")
    out = RAW_DIR / f"{ts_code}_fin_{today}.json"
    if out.exists():
        return 0
    try:
        pro = _pro()
        inc = pro.income(ts_code=ts_code, limit=8)
        bal = pro.balancesheet(ts_code=ts_code, limit=8)
        data = {"income": inc.to_dict(orient="records"),
                "balancesheet": bal.to_dict(orient="records")}
        out.write_text(json.dumps(data, ensure_ascii=False))
        print(f"[tushare] financials {ts_code}: {len(inc)} periods")
        return len(inc)
    except Exception as e:
        print(f"[tushare] financials ERROR {ts_code}: {e}")
        return 0


def fetch_news(keywords: list[str], limit: int = 20) -> list[dict]:
    """拉取涉及关键词的最新新闻，返回列表并存 JSON。"""
    today = date.today().isoformat()
    out = RAW_DIR / f"news_{today}.json"
    if out.exists():
        return json.loads(out.read_text())
    try:
        pro = _pro()
        start_dt = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        df = pro.news(src="sina,eastmoney", start_date=start_dt, limit=200)
        kw_lower = [k.lower() for k in keywords]
        filtered = [r for r in df.to_dict(orient="records")
                    if any(k in (r.get("title", "") + r.get("content", "")).lower()
                           for k in kw_lower)][:limit]
        out.write_text(json.dumps(filtered, ensure_ascii=False, indent=2))
        print(f"[tushare] news: {len(filtered)} items matching {keywords}")
        return filtered
    except Exception as e:
        print(f"[tushare] news ERROR: {e}")
        return []
