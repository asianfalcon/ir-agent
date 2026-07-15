# 数据血缘

入库元数据（ticker/pub_date/data_source）错一个，就污染召回。四条硬规则：

1. **先理解再入库**：批量入库前先抽样核对 ticker/日期/口径符合文件真实内容，别盲跑 watchdog。
2. **目录权威 ticker**：文件在 `reports/AMD/`、`reports/英特尔/` 等公司目录下，归属由目录定，正文提及竞品不得覆盖。目录映射不出 ticker（美股/TMT/行业报告）才回落正文→UNKNOWN 是合理状态。
3. **日期绝不退 mtime**：mtime=入库日是噪声，会让历史文件以假的"今天"抢占"越新越可信"权重（曾让 2023 年 AMD 电话会成为 INTC"最新指引"）。推不出用财季代理（Q末/年末），再不行留空（空=最旧，安全）。
4. **二进制不入库**：`.zip`(XBRL)/`.xlsx`/`.DS_Store` 无解析器，走 read_text 会被当乱码切片，直接跳过。

**为什么**：2026-07-15 入库 Intel/AMD 历史 PDF 踩了 ticker 污染（424 AMD chunk 混入 INTC）+ 日期劫持（击穿指引护栏）。修复后 INTC 池 AMD chunk=0、最新官方文件回到真实 Q1'26 Release。

**在哪执行**：`src/processing/text_processor.py` `_infer_metadata`（目录ticker/财季代理/不退mtime）+ `process_file`（二进制跳过）+ `_classify_report`。回归测试 `tests/test_metadata_lineage.py`。

关联 [[four_layer_isolation]] [[tickers]]。
