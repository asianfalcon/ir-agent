# IRA代码与运行数据解耦

## 目标

代码仓库只保存可版本化的核心逻辑；原始数据、派生数据、数据库、索引和报告输出存放在独立运行目录。开发机和服务器使用同一套代码，通过环境变量切换运行目录。

## 运行目录

设置：

```bash
export IRA_RUNTIME_ROOT=/srv/ira
```

系统自动使用：

```text
/srv/ira/
├── sources/
│   ├── manual/          # 手工上传及官方导出
│   └── external/        # 外部接口原始响应
├── derived/             # 清洗、转换和切片结果
├── stores/
│   ├── relational/      # SQLite；后续可替换PostgreSQL
│   ├── vector/          # LanceDB
│   └── graph/           # Kùzu
├── artifacts/           # Markdown/PDF/Excel等输出
└── cache/               # 临时缓存
```

未设置`IRA_RUNTIME_ROOT`时，系统保持现有目录行为，不移动数据：

- `data/inputs/`
- `data/raw/`
- `data/processed/`
- `data/storage/`
- `databases/ira.db`
- `output/`

这只是迁移兼容模式，不建议服务器继续使用。

## 配置优先级

单项环境变量高于`IRA_RUNTIME_ROOT`派生值：

1. `IRA_SQLITE_PATH`等具体路径；
2. `IRA_RUNTIME_ROOT`派生路径；
3. 旧项目内目录。

运行配置从`config/`读取；提示词、政策、Schema和字典从`resources/`读取。
可分别用`IRA_CONFIG_ROOT`、`IRA_RESOURCE_ROOT`和`IRA_PROMPT_ROOT`覆盖。

## 数据规则

1. `sources/manual`和`sources/external`中的原始对象只追加，不原地覆盖。
2. `derived`及向量/图索引必须可以从原始对象重建。
3. 预测快照、人工反馈和血缘信息属于不可重建控制状态，必须单独备份。
4. 数据库和索引不进入Docker镜像，不进入Git，通过持久卷挂载。
5. 服务器上的写入任务应由单一Worker串行执行；MCP/API进程以读取为主。

## 迁移流程

完成代码路径迁移并通过测试后，再执行：

1. 停止本地采集任务；
2. 备份现有原始数据和数据库；
3. 先预演：`python scripts/ops/migrate_runtime_layout.py --runtime-root /srv/ira`；
4. 确认目标后复制：在同一命令后添加`--execute`；该工具不删除旧文件，也不覆盖冲突文件；
5. 设置`IRA_RUNTIME_ROOT`；
6. 对SQLite行数、LanceDB chunks数和Kùzu节点数做迁移前后核对；
7. 验证后再将旧运行文件退出Git索引。Git历史清理和密钥轮换必须单独执行。
