# 预测硬护栏

`earnings_forecast` 与研报生成必须遵守，防漏指引和机械外推：

1. **有指引必抽取**：本地存在 `company_filing`/`announcement` 时，必须抽到目标期指引；抽取为空 → 抛 `GUIDANCE_EXTRACTION_FAILED`，禁止静默降级为全年拆季。本地无官方文件才放行。
2. **禁止机械拆季**：严禁全年÷4、剩余收入×固定比例、仅凭"季节性"套 30/33/37%。拆季须有公司季度指引/明确季度共识/券商季度表/已披露订单出货其一，否则输出"季度数据不足"。
3. **越界举证不撤回**：IRA 点预测可落在指引区间外（修正值来源），但须挂理由+证据(source_id)+Δ；缺可量化证据才降回区间内或标 Bull/Bear。

**为什么**：AMD 本地有 109-115 亿指引却被 MCP 漏读、生成违反指引结果——这是正确性 bug，不是缺功能。护栏之外都是先建反馈回路再建模型（见 [[feedback_loop]]），不在数据不足时给噪声拟合参数。

**在哪执行**：`src/skills/skill5_focused.py` `earnings_forecast`（guidance 空+有官方chunk→raise；prompt 内拆季/越界规则）。README「预测硬护栏」。

关联 [[four_layer_isolation]] [[data_caliber]]。
