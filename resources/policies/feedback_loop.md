# AlphaLoop反馈回路 · forecast_events

**规则**：每次 AlphaSonar 预测都写进 `forecast_events`（append-only），财报后补 actual，用 `score` 裁决"修正相对一致预期加分/减分"，让四层方法可证伪。

- 四类事件：`consensus`（卖方共识）/`guidance`（公司指引）/`forecast`（AlphaSonar修正）/`actual`（财报实际）。
- 历史永不覆盖；同 as_of_date 重复插入=修订新增。
- 打分按 `metric×accounting_basis` 隔离；`as_of_date` 晚于 actual 标可能穿越（无穿越回测）。
- 同日多修订：`_latest` 用 `ROW_NUMBER() OVER (ORDER BY as_of_date DESC, created_at DESC, event_id DESC)` 确定性取一条，不靠字典随机覆盖。
- 口径护栏：net_income/eps/gross_margin 无 basis 拒写；所有 actual 必须带 source_id，Non-GAAP只能来自官方对账表；revenue 用 Reported 单行、不复制成两口径。

**落地状态**：表已进`db_initializer`；AMD 2026Q2 actual与2026Q3 guidance已按append-only方式导入，并有幂等、口径和误差评分回归测试。

**为什么**：先建能证伪自己的反馈回路，再决定哪些模型值得建。7 家公司+有限季度下，券商细粒度评分/自动调权/分部模型都易把噪声拟合成规律——暂缓，等 8+ 季度真实"预测→实际"配对且 score 证明修正稳定加分再上。

**在哪执行**：`scripts/ops/forecast_snapshot.py`（record/score，表 `$ALPHASONAR_RUNTIME_ROOT/stores/relational/alphasonar.db::forecast_events`）。测试 `tests/test_forecast_snapshot.py`。README「forecast_events」。

**暂不做**：券商×科目×周期评分、自动优化权重、完整 CCG/DCAI/Foundry 分部模型、一次性项目概率模型。

关联 [[methodology]] [[data_caliber]]。
