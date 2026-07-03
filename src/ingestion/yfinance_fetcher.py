"""
YFinance fetcher — 宏观指标、商品价格、海外可比公司、汇率。
无需 API key，但受 Yahoo 访问限制。
"""
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
RAW_DIR = ROOT / "data" / "raw" / "yfinance"
RAW_DIR.mkdir(parents=True, exist_ok=True)

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
    out = RAW_DIR / f"news_{ticker_symbol}_{today}.json"
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
