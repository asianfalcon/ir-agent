"""策略 Agent — 估值建模和业绩预测。"""
from src.utils.prompts import load

_SYSTEM = load("agent_strategy.md")


def run(company_name: str, ticker: str, researcher_output: str, llm_caller) -> str:
    user = f"""
以下是研究员对 {company_name}（{ticker}）的事实清单：

{researcher_output}

请基于上述数据进行估值分析和业绩预测。
"""
    return llm_caller(_SYSTEM, user)
