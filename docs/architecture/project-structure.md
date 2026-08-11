# AlphaSonar项目结构与依赖边界

## 分层原则

仓库是一个单体代码库，但不是一个无边界的大目录。当前阶段不拆多个仓库，先用明确的包边界降低耦合：

```text
interfaces -> agents/capabilities -> pipelines/connectors -> storage
                         \              /
                          settings/resources
```

- `interfaces`只负责协议适配，不保存业务数据。
- `agents`负责编排，`capabilities`负责可复用研究能力；二者不拼接机器本地路径。
- `connectors`取得外部原始数据，`pipelines`把原始数据转成标准证据。
- `storage`封装SQLite、LanceDB和Kùzu。以后换PostgreSQL或对象存储时，上层不应重写。
- 所有可变路径只从`alphasonar.settings`读取；业务模块不得自行推导仓库路径。
- Prompt、研究政策、Schema和字典属于版本化方法论，统一放在`resources/`。

## 版本化与非版本化资产

| 资产 | 位置 | Git | 可否重建 |
|---|---|---:|---:|
| Python核心代码 | `src/alphasonar/` | 是 | — |
| Prompt/政策/Schema/字典 | `resources/` | 是 | — |
| 非敏感默认配置 | `config/` | 是 | — |
| 密钥、Cookie、本机配置 | 环境变量/Secret Manager | 否 | 否 |
| 手工原件、外部原始响应 | `$ALPHASONAR_RUNTIME_ROOT/sources/` | 否 | 部分不可重建 |
| 清洗和切片结果 | `$ALPHASONAR_RUNTIME_ROOT/derived/` | 否 | 是 |
| 数据库和索引 | `$ALPHASONAR_RUNTIME_ROOT/stores/` | 否 | 部分不可重建 |
| 研报、PDF、工作簿 | `$ALPHASONAR_RUNTIME_ROOT/artifacts/` | 否 | 通常可重建 |

预测事件、人工反馈和血缘状态虽然位于数据库中，但不是普通缓存，必须纳入备份。

## 服务器部署边界

- 镜像只包含代码、版本化资源和非敏感默认配置。
- `/srv/alphasonar`作为持久卷挂载，升级镜像不得覆盖它。
- API Key由部署平台注入，不写进镜像或Compose文件。
- 同一SQLite/LanceDB/Kùzu实例只允许一个写入Worker；查询进程以只读为主。
- 数据量或并发继续上升时，优先把SQLite迁到PostgreSQL，再考虑把原始对象迁到对象存储；Agent和Prompt无需随之拆仓库。

## 迁移与发布

1. 在旧目录上运行全部测试。
2. 用`migrate_runtime_layout.py`预演并复制，旧文件保留。
3. 校验文件数、哈希、数据库行数和索引记录数。
4. 设置`ALPHASONAR_RUNTIME_ROOT`后再次运行测试及一次只读查询。
5. 备份不可重建状态，再切换写入任务。
6. 报告输出和运行数据退出Git索引；历史敏感信息单独审计和清理。

目录变更本身不应和数据库Schema升级混在同一发布中。Schema升级必须有独立迁移版本和回滚说明。
