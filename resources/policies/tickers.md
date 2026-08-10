# 标的映射

覆盖标的的 名称→ticker（权威源：`resources/dictionaries/vocab_dictionary.json` 的 `entity_type=Company` 条目；此表为快照，改动以词典为准）。

| ticker | 标准名 | 别名(节选) |
|---|---|---|
| INTC.US | 英特尔 | Intel, Intel Corporation, INTC |
| AMD.US | AMD | 超威半导体, Advanced Micro Devices |
| 688256.SH | 寒武纪 | Cambricon, 寒武纪-U, 寒武纪科技 |
| 688141.SH | 杰华特 | 杰华特微电子, Joulwatt |
| 300308.SZ | 中际旭创 | 旭创科技 |
| 002136.SZ | 安纳达 | 安纳达钛业 |

**规则**：
- 词典缺条目 → `_normalize_ticker` 返回 None → 文件标 UNKNOWN。新增标的先补词典再入库（否则目录权威也救不了，除非文件在该公司命名目录下）。
- 行业周报/金股组合无单一标的 → UNKNOWN 是**正确**状态，不要强行按"正文含某公司名"匹配（"空天的寒武纪"是比喻）。

**在哪执行**：`src/processing/text_processor.py` `_normalize_ticker` + `_infer_metadata` 目录权威。

关联 [[data_lineage]]。
