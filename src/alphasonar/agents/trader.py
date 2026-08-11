"""交易员 Agent — 边际变化和入场时机。"""
from alphasonar.utils.prompts import load

_SYSTEM = load("agent_trader.md")


def run(company_name: str, ticker: str, researcher_output: str, llm_caller) -> str:
    user = f"""
以下是研究员对 {company_name}（{ticker}）的事实清单：

{researcher_output}

请聚焦边际变化，判断当前入场时机。
"""
    return llm_caller(_SYSTEM, user)
