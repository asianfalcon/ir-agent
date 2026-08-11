"""
Skill 6: Event-driven catalyst analysis.
拉取热门事件（新闻 + 宏观），分析对 watchlist 公司的催化或压制影响。
"""
import json

from alphasonar.settings import get_settings

_SETTINGS = get_settings()
WATCHLIST_PATH = _SETTINGS.config_root / "watchlist.json"
VOCAB_PATH = _SETTINGS.vocab_path


def _load_system() -> str:
    p = _SETTINGS.prompt_root / "skill6_event_catalyst.md"
    return p.read_text(encoding="utf-8")


def run(event_query: str, llm_caller) -> str:
    """
    event_query: 事件描述，如"英伟达 Blackwell 供应链砍单"
    返回 Markdown 格式的事件驱动分析报告。
    """
    vocab = json.loads(VOCAB_PATH.read_text()) if VOCAB_PATH.exists() else []
    watchlist = json.loads(WATCHLIST_PATH.read_text()) if WATCHLIST_PATH.exists() else []

    companies = [e for e in vocab if e.get("entity_type") == "Company"
                 and e.get("ticker") in watchlist]
    company_list = "\n".join(
        f"- {e['standard_name']}（{e['ticker']}）主营：{e.get('product','未知')}"
        for e in companies
    ) or "（暂无 watchlist 公司信息）"

    # 拉宏观数据
    macro_text = "（宏观数据获取失败）"
    try:
        from alphasonar.connectors.yfinance_fetcher import fetch_macro
        macro = fetch_macro()
        macro_text = "\n".join(
            f"  {k}: {v['close']} ({v.get('pct_1m',0):+.1f}% 近1月) [{v['date']}]"
            for k, v in macro.items()
        )
    except Exception as e:
        macro_text = f"（yfinance 获取失败: {e}）"

    # 拉 tushare 新闻（若有 token）
    news_text = "（新闻数据未配置）"
    try:
        from alphasonar.connectors.tushare_fetcher import fetch_news
        keywords = event_query.split()[:4]
        news = fetch_news(keywords, limit=10)
        if news:
            news_text = "\n".join(
                f"  [{n.get('pub_date','?')[:10]}] {n.get('title','')}"
                for n in news[:8]
            )
    except Exception:
        pass

    user = f"""
【事件】{event_query}

【当前宏观/商品指标】(来源: YFinance)
{macro_text}

【相关新闻标题】(来源: Tushare/新浪/东财)
{news_text}

【watchlist 公司】(来源: config/watchlist.json)
{company_list}

请分析该事件对上述各公司的催化/压制影响。
"""
    return llm_caller(_load_system(), user)
