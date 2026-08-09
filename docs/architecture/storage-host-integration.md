# 宿主系统文件存储集成指南

paper-diff 的核心项目能力不再依赖本地目录。宿主只需实现同步 `FileStore` 协议，并在创建 FastAPI 应用时注入 `AppContainer`。项目、工作树、比较区、归档、快照、元数据和比较读取都会使用同一个存储实例与 namespace。

## 最小固定 namespace 集成

```python
from app.composition.container import AppContainer
from app.core.config import Settings
from app.main import create_app
from app.storage.factory import ProjectStorageFactory

store = MyHostFileStore(...)  # 实现 app.storage.ports.FileStore
factory = ProjectStorageFactory(store, namespace="tenant-42")
container = AppContainer(settings=Settings(), storage=factory)
app = create_app(container)
```

注入后，`Settings.workspace_root` 不参与核心项目文件访问。默认 namespace 为 `default`，继续使用既有 `{project_id}/...` 磁盘布局；非默认 namespace 使用 `{namespace}/{project_id}/...`，同名 project id 不会碰撞。

## 按请求选择 tenant

宿主可以从已经完成鉴权的请求上下文中解析 namespace。不要直接信任未经校验的用户输入；namespace 只允许单个安全路径段。

```python
from app.composition.container import AppContainer
from app.main import create_app
from app.storage.factory import ProjectStorageFactory

containers = {}

def resolve_container(request):
    tenant_id = request.state.authenticated_tenant_id
    if tenant_id not in containers:
        containers[tenant_id] = AppContainer(
            settings=settings,
            storage=ProjectStorageFactory(shared_store, namespace=tenant_id),
        )
    return containers[tenant_id]

app = create_app(container_resolver=resolve_container)
```

使用 request-scoped resolver 时，paper-diff 不会执行启动清理；namespace 生命周期由宿主管理。

## FileStore 必须提供的语义

协议定义在 `app.storage.ports.FileStore`。适配器至少需要实现：

- `stat/list/open_read/read_bytes`；
- `write_stream/write_bytes`，包括 `expected` 版本令牌；
- `ensure_prefix/delete/copy/move`；
- `replace_prefix(target, staged)`，发布完整的新树，失败时旧树仍可读；
- 稳定、规范化的 `StorageKey` 行为，不接受绝对路径、`..`、NUL 或越界 key；
- 并发安全的条件写，以支持 project meta CAS 重试。

先让新适配器运行 `tests/test_storage_contract.py`。`MemoryFileStore` 是最小参考实现，`LocalFileStore` 展示了原子本地写、符号链接拒绝和整树替换。

## 能力矩阵

| 能力 | 仅 FileStore | LocalFileStore 默认实现 | 宿主自定义实现 |
|---|---:|---:|---:|
| project/work/zone CRUD | 是 | 是 | 是 |
| ZIP/TAR 导入、ZIP 导出 | 是 | 是 | 是 |
| compare、raw/meta/slice | 是 | 是 | 是 |
| CAS 元数据、快照、undo | 是 | 是 | 是 |
| Git | 否 | `GitCliBackend` | 注入 `GitBackend` |
| LaTeX 编译 | 否 | `LocalCompileExecutor` | 注入 `CompileExecutor` |

当 provider 的 `StorageCapabilities.materialization=False` 且宿主没有注入 Git/编译实现时，相应 API 明确返回 `STORAGE_CAPABILITY_UNAVAILABLE`（HTTP 501），核心文件 API 仍正常工作。自定义 backend/executor 不受本地物化标志限制。

```python
container = AppContainer(
    settings=settings,
    storage=factory,
    git_backend=my_git_backend,
    compile_executor=my_compile_executor,
)
```

接口定义在 `app.integrations.ports`。宿主实现可以调用远端 Git/编译服务，不必暴露本地路径。编译产物仍应通过 `ProjectStorage.write_artifact/write_job_*` 写回；不要直接修改 work tree。

## 错误与生命周期

存储适配器应抛出 `app.storage.errors` 中的规范错误：`StorageNotFound`、`StorageConflict`、`StorageQuotaExceeded`、`StorageUnavailable`、`StorageCapabilityUnavailable` 或 `InvalidStorageKey`。API 会映射为稳定的 4xx/5xx 错误码。

当前 SPI 是同步接口，会被 HTTP 线程和 compare 后台线程并发调用。共享 adapter 必须线程安全；远程 provider 应自行配置连接池、超时、重试和熔断。不要在日志中记录论文正文、Git 凭据或宿主绝对路径。

## 上线检查

1. 对新 adapter 运行 local/memory 同款契约测试。
2. 用两个 namespace 和同一个 project id 验证隔离。
3. 注入 FastAPI 后跑 project/work/zone/compare 主路径。
4. 模拟 CAS 冲突、配额、provider 超时和 staging 中途失败。
5. 未提供 Git/compile 时确认 501 降级；提供自定义能力时确认请求由宿主接管。
6. 验证启动清理只作用于明确授权的 namespace。

完整设计与剩余加固项见 [文件访问层抽象实施计划](../superpowers/plans/2026-07-19-file-access-layer-abstraction.md)。
