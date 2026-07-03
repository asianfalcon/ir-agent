"""PM Agent — 综合四方报告，给出最终投资决策。"""
from src.utils.prompts import load

_SYSTEM = load("agent_pm.md")


def run(
    company_name: str,
    ticker: str,
    researcher_output: str,
    risk_output: str,
    strategy_output: str,
    trader_output: str,
    llm_caller,
) -> str:
    user = f"""
目标公司：{company_name}（{ticker}）

## 研究员报告
{researcher_output}

## 风控报告
{risk_output}

## 策略报告
{strategy_output}

## 交易员报告
{trader_output}

请综合以上四份报告，给出最终投资决策。
"""
    return llm_caller(_SYSTEM, user)
