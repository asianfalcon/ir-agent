# 领域记忆 · MEMORY.md

本目录是**可 git 追溯的领域知识**：投研业务规则的单一事实源，原子化、每条指向代码里的执行点。

## 与其他文档的分工（勿重复）

| 载体 | 角色 | 读者 |
|---|---|---|
| `README.md` | 怎么跑、目录结构 | 人（上手） |
| `resources/prompts/instructions.md` | LLM 系统原则 | MCP 运行时注入给模型 |
| `~/.claude/.../memory/` | Claude 跨会话工作记忆 | Claude（不随 git） |
| **`memory/`（本目录）** | **领域规则的版本化事实源** | **人 + 未来可接运行时** |

约定：一条规则一个文件；正文只写"规则 + 为什么 + 在哪执行"，不复制代码逻辑。改规则先改这里，再改代码。

## 索引

- [数据口径校验](data_caliber.md) — 绝对值vs亿、单季vs全年，预测前必校
- [四层证据隔离](four_layer_isolation.md) — 官方指引/券商共识/专家纪要/IRA修正物理隔离
- [预测硬护栏](forecast_guardrails.md) — 有指引必抽取、禁止机械拆季、越界举证
- [数据血缘](data_lineage.md) — 目录权威ticker、日期不退mtime、二进制不入库、先理解再入库
- [反馈回路](feedback_loop.md) — forecast_events 让每次修正可证伪
- [分析方法论](methodology.md) — 一致预期基准+纪要修正，赚的是修正值
- [供给决定型标的](supply_bound_names.md) — capex→产能→ASP，仅对自有产能公司
- [标的映射](tickers.md) — 覆盖标的的名称→ticker
