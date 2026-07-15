# 反馈回路 · forecast_events

**规则**：每次 IRA 预测都写进 `forecast_events`（append-only），财报后补 actual，用 `score` 裁决"修正相对一致预期加分/减分"，让四层方法可证伪。

- 四类事件：`consensus`（卖方共识）/`guidance`（公司指引）/`forecast`（IRA修正）/`actual`（财报实际）。
- 历史永不覆盖；同 as_of_date 重复插入=修订新增。
- 打分按 `metric×accounting_basis` 隔离；`as_of_date` 晚于 actual 标可能穿越（无穿越回测）。

**为什么**：先建能证伪自己的反馈回路，再决定哪些模型值得建。7 家公司+有限季度下，券商细粒度评分/自动调权/分部模型都易把噪声拟合成规律——暂缓，等 8+ 季度真实"预测→实际"配对且 score 证明修正稳定加分再上。

**在哪执行**：`scripts/forecast_snapshot.py`（record/score，表 `databases/ira.db::forecast_events`）。测试 `tests/test_forecast_snapshot.py`。README「forecast_events」。

**暂不做**：券商×科目×周期评分、自动优化权重、完整 CCG/DCAI/Foundry 分部模型、一次性项目概率模型。

关联 [[methodology]] [[data_caliber]]。
