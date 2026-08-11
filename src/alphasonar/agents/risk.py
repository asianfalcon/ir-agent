"""风控 Agent — 对抗式审查，挑矛盾、找盲区。"""
from alphasonar.utils.prompts import load

_SYSTEM = load("agent_risk.md")


def run(company_name: str, ticker: str, researcher_output: str, llm_caller) -> str:
    user = f"""
以下是研究员对 {company_name}（{ticker}）的事实清单：

{researcher_output}

请以风控合规官身份，找出数据矛盾、信息缺口和潜在风险。
"""
    return llm_caller(_SYSTEM, user)
