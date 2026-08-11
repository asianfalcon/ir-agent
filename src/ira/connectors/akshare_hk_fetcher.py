"""AkShare 港股 fetcher —— EastMoney 数据源，港股代码空间。"""
from datetime import date

from ira.settings import get_settings

_SETTINGS = get_settings()


def fetch_financials_hk(ticker: str) -> list[dict]:
    """ticker 形如 '0700.HK'。用 AkShare 的港股 EastMoney 接口——
    和 cn 路径同一数据提供方（EastMoney），只是代码空间不同。"""
    import akshare as ak
    code = ticker.split(".")[0].zfill(5)  # AkShare 港股接口要 5 位零填充代码，如 "00700"
    today = date.today().isoformat().replace("-", "")
    out_dir = _SETTINGS.external_source_root / "financials" / "akshare_hk"
    out_dir.mkdir(parents=True, exist_ok=True)
    df = ak.stock_financial_hk_report_em(stock=code, symbol="资产负债表", indicator="报告期")
    df2 = ak.stock_financial_hk_analysis_indicator_em(symbol=code, indicator="报告期")
    (out_dir / f"{ticker}_hk_report_{today}.json").write_text(df.to_json(orient="records", force_ascii=False))
    (out_dir / f"{ticker}_hk_indicator_{today}.json").write_text(df2.to_json(orient="records", force_ascii=False))
    # 字段到 period/revenue/gross_margin/... 的映射留待真正接入港股标的时，
    # 用一次真实调用返回的列名核对后再补——本次沙盒环境无法发起网络请求验证列名，
    # 先返回空列表，保证 hk 分支可调用、不报错，是有意为之的延后，不是遗漏。
    return []
