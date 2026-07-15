# 数据口径校验

**规则**：任何营收/利润/毛利率/EPS 预测前，必须先校三项——
1. **字段口径**：`financial_reports.period` 是单季度、累计还是全年？不确定时禁止把 Q1-Q4 相加当全年。
2. **绝对值 vs 亿**：`financial_reports.revenue` 存**绝对值**（INTC 2026Q1 = 13,577,000,000），不是"亿美元"。`forecast_events` 的 `value_*` 同口径，填错误差全废。
3. **GAAP vs Non-GAAP**：对比只在同 metric + 同 basis 内进行，绝不混比。

**为什么**：口径错是最隐蔽的错——数字看着对，结论全歪。AMD 报告里把亿当绝对值就被算成 100% 误差。

**在哪执行**：
- 校验原则：`config/prompts/instructions.md` 原则8 + README「财务预测三步校验」。
- 口径隔离：`scripts/forecast_snapshot.py` score 按 `metric×accounting_basis` 分组。

关联 [[four_layer_isolation]] [[feedback_loop]]。
