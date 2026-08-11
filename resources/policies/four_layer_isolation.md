# 四层证据隔离

**规则**：预测证据分四层，物理隔离，各有 `data_source`：
| 层 | data_source | 用途 | 禁忌 |
|---|---|---|---|
| 官方指引/实际 | `company_filing` `announcement` | 预测边界、管理层锚点 | **绝不进卖方一致预期** |
| 券商共识 | `broker_report` | 一致预期基准 | 单样本须写"单一卖方基准" |
| 专家纪要 | `acecamp_expert_column` | 只做增量修正 | 不进共识、不单独预测 |
| AlphaSonar 修正 | （生成物）| 最终预测 | 越界须举证，见 [[forecast_guardrails]] |

**为什么**：把官方 deck 当券商研报算进共识 = 用公司自述污染"独立第三方预期"，一致预期失真。专家纪要是弱证据，混进共识会放大噪声。

**在哪执行**：
- `src/skills/skill5_focused.py`：`RESEARCH_DATA_SOURCES`/`OFFICIAL_DATA_SOURCES`/`SUPPLEMENTAL_DATA_SOURCES` 三集合分流。
- 分类器：`_classify_report`（文件名判官方vs券商）。
- 弱证据只调 Bull/Bear 概率、不改点预测——见 [[methodology]]。

关联 [[data_lineage]]（分错 data_source 就等于污染这层隔离）。
