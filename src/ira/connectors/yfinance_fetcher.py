"""
YFinance fetcher — 宏观指标、商品价格、海外可比公司、汇率。
无需 API key，但受 Yahoo 访问限制。
"""
import json
import re
from datetime import date, timedelta

from ira.settings import get_settings

_SETTINGS = get_settings()
RAW_DIR = _SETTINGS.external_source_root / "yfinance"
NEWS_DIR = _SETTINGS.external_source_root / "news" / "yfinance"
FIN_DIR = _SETTINGS.external_source_root / "financials" / "yfinance"
RAW_DIR.mkdir(parents=True, exist_ok=True)
NEWS_DIR.mkdir(parents=True, exist_ok=True)
FIN_DIR.mkdir(parents=True, exist_ok=True)

_FIELD_MAP = {
    "revenue": ["Total Revenue"],
    "gross_profit": ["Gross Profit"],
    "net_profit": ["Net Income"],
    "operating_cash_flow": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
}

# 常用宏观/商品标的
MACRO_SYMBOLS = {
    "sp500":    "^GSPC",
    "nasdaq":   "^IXIC",
    "gold":     "GC=F",
    "oil_wti":  "CL=F",
    "usd_cny":  "USDCNY=X",
    "sox":      "^SOX",      # 费城半导体指数
    "smh":      "SMH",       # 半导体 ETF
}


def fetch_macro(period: str = "3mo") -> dict:
    """拉取宏观/商品指数，存 JSON，返回最新收盘价字典。"""
    import yfinance as yf
    today = date.today().isoformat()
    out = RAW_DIR / f"macro_{today}.json"
    if out.exists():
        return json.loads(out.read_text())

    result = {}
    for name, sym in MACRO_SYMBOLS.items():
        try:
            tk = yf.Ticker(sym)
            hist = tk.history(period=period)
            if hist.empty:
                continue
            latest = hist.iloc[-1]
            result[name] = {
                "symbol": sym,
                "date": str(hist.index[-1].date()),
                "close": round(float(latest["Close"]), 4),
                "pct_1m": round(
                    (float(latest["Close"]) / float(hist.iloc[-21]["Close"]) - 1) * 100, 2
                ) if len(hist) >= 21 else None,
            }
        except Exception as e:
            print(f"[yfinance] {sym} ERROR: {e}")

    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[yfinance] macro: {list(result.keys())}")
    return result


def fetch_peer(symbol: str, period: str = "3mo") -> dict:
    """拉取海外可比公司行情（如 TI、ADI、MPS 等）。symbol 为 Yahoo 代码。"""
    import yfinance as yf
    today = date.today().isoformat()
    out = RAW_DIR / f"peer_{symbol}_{today}.json"
    if out.exists():
        return json.loads(out.read_text())
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(period=period)
        info = {k: tk.info.get(k) for k in
                ("shortName", "sector", "trailingPE", "forwardPE",
                 "priceToSalesTrailing12Months", "marketCap", "revenueGrowth")}
        result = {"symbol": symbol, "info": info,
                  "latest_close": round(float(hist.iloc[-1]["Close"]), 2) if not hist.empty else None}
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"[yfinance] peer {symbol}: PE={info.get('trailingPE')}")
        return result
    except Exception as e:
        print(f"[yfinance] peer {symbol} ERROR: {e}")
        return {}


def fetch_news(ticker_symbol: str, limit: int = 10) -> list[dict]:
    """拉取 Yahoo 财经新闻（英文），用于海外市场事件感知。"""
    import yfinance as yf
    today = date.today().isoformat()
    out = NEWS_DIR / f"news_{ticker_symbol}_{today}.json"
    if out.exists():
        return json.loads(out.read_text())
    try:
        tk = yf.Ticker(ticker_symbol)
        news = tk.news[:limit]
        simplified = [{"title": n.get("content", {}).get("title", ""),
                       "pub_date": n.get("content", {}).get("pubDate", ""),
                       "url": n.get("content", {}).get("canonicalUrl", {}).get("url", "")}
                      for n in news]
        out.write_text(json.dumps(simplified, ensure_ascii=False, indent=2))
        print(f"[yfinance] news {ticker_symbol}: {len(simplified)} items")
        return simplified
    except Exception as e:
        print(f"[yfinance] news {ticker_symbol} ERROR: {e}")
        return []


def _fiscal_period(period_end) -> str:
    """将 yfinance 季度列的 Timestamp 映射为 YYYYQ1-Q4。
    Intel/AMD 财季与自然季度对齐，故直接按自然季度分桶；这是针对这两个标的的
    具体假设，不是美股市场通用事实——其余美股公司接入前需重新核实。"""
    q = (period_end.month - 1) // 3 + 1
    return f"{period_end.year}Q{q}"


def fetch_financials_us(ticker: str) -> list[dict]:
    """经 yfinance 拉季度财报/资产负债表/现金流量表，写原始 JSON，
    返回每个可用季度一条记录。"""
    import yfinance as yf
    today = date.today().isoformat().replace("-", "")
    tk = yf.Ticker(ticker.split(".")[0])  # yfinance 要裸 "INTC"，不是 "INTC.US"
    qf, qbs, qcf = tk.quarterly_financials, tk.quarterly_balance_sheet, tk.quarterly_cashflow

    raw = {
        "quarterly_financials": qf.to_json(),
        "quarterly_balance_sheet": qbs.to_json(),
        "quarterly_cashflow": qcf.to_json(),
    }
    (FIN_DIR / f"{ticker}_quarterly_{today}.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")

    records = []
    for period_end in qf.columns:
        period = _fiscal_period(period_end)

        def _get(df, names):
            for n in names:
                if n in df.index:
                    v = df.at[n, period_end]
                    return None if v != v else float(v)
            return None

        revenue = _get(qf, _FIELD_MAP["revenue"])
        gross_profit = _get(qf, _FIELD_MAP["gross_profit"])
        net_profit = _get(qf, _FIELD_MAP["net_profit"])
        op_cf = _get(qcf, _FIELD_MAP["operating_cash_flow"])
        equity = None
        for n in ("Stockholders Equity", "Common Stock Equity"):
            if period_end in qbs.columns and n in qbs.index:
                v = qbs.at[n, period_end]
                equity = None if v != v else float(v)
                break
        gross_margin = round(gross_profit / revenue * 100, 4) if gross_profit and revenue else None
        roe = round(net_profit / equity * 100, 4) if net_profit and equity else None
        records.append({
            "period": period,
            "revenue": revenue,
            "gross_margin": gross_margin,
            "net_profit": net_profit,
            "roe": roe,
            "operating_cash_flow": op_cf,
        })
    return records


def upsert_sqlite_financials_us(ticker: str, records: list[dict]) -> int:
    """yfinance 的 quarterly_* 是单一 US-GAAP、单一美元计价、永远单季度（非累计），
    不存在 A股 fetch_financials 那种口径歧义，因此直接全字段 upsert
    （不同于 A股保守的只填 gross_margin 模式，见 update_sqlite_financial_supplements）。"""
    import sqlite3
    conn = sqlite3.connect(_SETTINGS.sqlite_path)
    before = conn.total_changes
    for r in records:
        conn.execute(
            """
            INSERT INTO financial_reports
                (ticker_period, ticker, period, revenue, gross_margin, net_profit, roe, operating_cash_flow, updated_at)
            VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(ticker_period) DO UPDATE SET
                revenue=excluded.revenue, gross_margin=excluded.gross_margin,
                net_profit=excluded.net_profit, roe=excluded.roe,
                operating_cash_flow=excluded.operating_cash_flow, updated_at=CURRENT_TIMESTAMP
            """,
            (f"{ticker}_{r['period']}", ticker, r["period"], r["revenue"], r["gross_margin"],
             r["net_profit"], r["roe"], r["operating_cash_flow"]),
        )
    conn.commit()
    changed = conn.total_changes - before
    conn.close()
    return changed


def fetch_news_processed(ticker: str, company_name: str, limit: int = 10) -> dict:
    """包装 fetch_news，额外写处理后的 markdown，对齐 akshare 路径的输出形状。"""
    symbol = ticker.split(".")[0]
    records = fetch_news(symbol, limit)
    today = date.today().isoformat().replace("-", "")
    processed_dir = _SETTINGS.derived_root / "news" / "yfinance" / ticker
    processed_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, item in enumerate(records, 1):
        title = item.get("title") or f"{company_name} news"
        pub_date = str(item.get("pub_date", ""))[:10].replace("-", "") or today
        path = processed_dir / f"{pub_date}_{i:03d}_{re.sub(r'[^A-Za-z0-9]+', '_', title)[:80]}.md"
        path.write_text(
            "\n".join([
                f"# {title}", "",
                f"公司：{company_name}({ticker})",
                f"日期：{item.get('pub_date', '')}",
                f"来源：Yahoo Finance",
                f"链接：{item.get('url', '')}", "",
            ]),
            encoding="utf-8",
        )
        paths.append(path)
    return {"raw": None, "files": paths}
