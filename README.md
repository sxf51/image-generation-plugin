# 图像工作室 · image-generation-plugin 2.0

插件自带前端页面、Web API 与图像工具。项目本体提供插件注册、用户鉴权、ToolExecutor、页面桥接，以及一份通用的**插件存储服务**；没有新增宿主业务接口或宿主数据库表。

页面为中英双语：静态文案写成 `data-i18n` 键，后端只回**消息码**（`prompt_required`、`task_failed` 之类），由页面按宿主桥接报告的语言渲染，读者中途切换语言会即时重绘。

## 功能

- **提示词模板**：12 个原创参数化模板，包含电商、广告、海报、人像、角色、界面、信息图、社交封面和 4 类改图；可按分类选择、应用后自由修改。提交前提示替换 `{变量}`。
- **参考图**：上传 PNG / JPEG / WebP（最多 8 MiB、2000 万像素），或从自己的作品中选择。后端重新编码为 PNG，不信任客户端文件名或 MIME。
- **连续改图**：选择产出图片继续编辑，任务记录 `parent_id` 和参考图 ID，保留每一版提示词和结果。
- **历史任务**：按状态、提示词搜索，每页 20 条；查看耗时、模型、参数、产出和来源任务，复用参数或重试。已清理图片显示为不可用，历史仍然保留。
- **统计**：任务总数、7 / 30 / 90 天使用次数、活跃用户、成功与失败、缓存命中、新产出和改图任务，以及每日使用次数折线图和明细表。
- **异步提交**：页面提交立即返回 202，每个用户最多 3 个并行任务；离开页面不会取消生成。进程异常退出的任务在过期检查后标记中断，不自动重试收费请求。
- `/draw`、`/edit` 工具调用同样记录任务。`/image-prompt`、`/image-status` 和仅规划的 `/imagine` 不计为图像生成使用。

模板分类和工作流参考 [EvoLinkAI 提示词资料库](https://github.com/EvoLinkAI/awesome-gpt-image-2-API-and-Prompts)。本插件的 `templates.json` 为原创参数化模板，没有复制远程图片或要求运行时访问该仓库。

## 存储

插件不自己拼目录、不自己建 Redis 连接、也不自己想 key 前缀。宿主在装配插件运行时上下文时注入一份已经绑定好本插件作用域的存储对象（`runtime_context["storage"]`），插件只调用它的方法，调用时**不传自己的名字**：

| 方法 | 用途 |
| --- | --- |
| `storage.dir(...)` / `storage.path(...)` | 本插件私有的目录与文件路径，父目录按需创建 |
| `storage.resolve(path)` | 校验某个路径确实属于本插件，越界或不存在返回 `None` |
| `storage.user_file(path)` | 解析"宿主替用户存下来的文件"（聊天里刚上传的图片），越界返回 `None` |
| `storage.key(...)` | 本插件私有的 Redis key |
| `storage.client()` | 共享的 Redis 客户端，已配好重试与空闲健康检查；后端不可用时返回 `None` |

由此带来的性质：

- 生成图片与 `reference-*.png` 参考图写入 `storage.dir("images")`，磁盘位置由宿主的数据根目录决定，插件配置里不再有 `output.directory`，也不再需要目录白名单。
- 任务元数据、状态、用户索引、资产索引、统计事件与带 TTL 的生成缓存都写在 `storage.key(...)` 前缀下，插件之间互不可见。
- **以图生图**接受两种来源：本插件自己的产出/参考图（`storage.resolve`），以及用户在聊天里上传的附件（`storage.user_file`）。模型看不到本地路径，所以 `image_edit_tool` 会从这次消息的 `content_parts` 里取图——DAG 路由下由 planner 铺进节点入参，ReAct 路由下由编排器通过 caller context 注入。宿主没有交出来的路径一律拒绝。
- 连接由宿主统一管理，因此空闲后被对端关闭的连接会自动重连，而不是把 `ConnectionError` 抛给正在执行的任务。
- 任务及资产元数据不设置 TTL；缓存遵循 `generation.cache_ttl_seconds`。请为 Redis 启用 AOF / RDB 持久化，并同时备份 Redis 和数据目录。存储不可用时接口返回 `storage_unavailable` 与 503，不继续提交生成任务。
- 并发限制及终态写入使用 Redis WATCH / MULTI，避免多个 worker 同时超额提交或重复计入产出。
- `output.keep_last` 仅清理生成图片，参考图不受该策略影响。任务记录保留，即使对应图片已删除。
- 本版本不迁移旧数据：此前 `data/generated-images` 下的图片与旧命名空间下的任务记录仍在磁盘/Redis 上，但新工作室不再读取它们。

## 配置与运行

请在插件详情页的“API 密钥”字段填写图像服务密钥。该字段以密码框显示并由插件配置保存；不再通过环境变量配置密钥。Redis 地址由宿主的存储服务决定，插件不再单独配置。然后安装插件 `requirements.txt`、重新加载插件，打开“图像工作室”。不需要重建宿主前端。

图像服务必须支持 OpenAI Images 兼容的 `/images/generations`。生成和编辑均支持服务返回 base64 或 URL；URL 使用插件已有的下载大小与网络地址校验。

**以图生图的两种调用方式**（`openai_images.edit_transport`）：

| 取值 | 行为 |
| --- | --- |
| `auto`（默认） | 先按 OpenAI 官方契约打 multipart `/images/edits`；该端点返回 404 / 405（说明服务商根本没有它）时自动改走 `input_references`。其它 HTTP 错误照常抛出，不会被第二次调用掩盖 |
| `images_edits` | 固定走 OpenAI 官方的 multipart `/images/edits` |
| `input_references` | 固定走统一图像端点 `POST {api_base}/images`，参考图以 `data:` URL 内联进 `input_references` |

OpenAI 官方把改图放在 `/images/edits`；OpenRouter 这类聚合服务没有该端点（直接返回 404），改图能力挂在统一图像端点上，需要走 `input_references`。默认的 `auto` 会自己探测，通常不需要手工配置。注意统一端点没有蒙版（mask）概念，因此带蒙版的请求在回退时会明确报错而不是悄悄编辑整张图。模型是否支持参考图以实际服务为准（OpenRouter 可查 `GET /api/v1/images/models` 的 `input_references`）。

前后端分离时，页面仍只通过 `window.CapstonePluginPage` 调用宿主桥接：`apiGet` / `apiPost` 传 JSON，`dataUrl` 获取预览。页面不访问 Redis、不接触密钥，也不硬编码后端 origin。沿用宿主 `VITE_API_BASE_URL` 与 CORS 配置即可。

## API

统一前缀：`/api/v1/plugins/extensions/image-generation-plugin/`，身份来自宿主鉴权。失败一律返回 `{"status": "error", "message": "<消息码>"}`，消息码是稳定的 snake_case 标识而不是某一种语言的句子。

任务失败时，记录里存的同样是消息码（`provider_edit_unsupported`、`provider_unauthorized`、`provider_timeout` 等，全集见 `studio.FAILURE_CODES`），页面据此告诉用户到底哪里出了问题。服务商返回的原始报错文本不会落库，也不会回给前端——它可能带服务端路径或密钥片段。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | templates | 模板列表 |
| POST | references | `{data: base64 或 data URL}` 上传参考图，返回资产 ID |
| POST | tasks | `{prompt, size, image_count, reference?, parent_id?, template_id?}`，返回 202 和任务 |
| GET | history | `id` 查询单个任务；或 `page / status / search` 查询当前用户历史 |
| GET | gallery | 当前用户可用产出，`limit` 为 1–200 |
| GET | thumbnail | `id` 指定当前用户的资产，返回 JPEG 预览 |
| GET | stats | `days=7 / 30 / 90`，模块汇总数据，不包含用户身份或他人提示词 |
| GET | recent | 声明式面板的当前用户最近产出 |
| POST | generate | 同步执行入口，返回经过筛选的结果和任务，不返回服务端路径或原始错误 |

统计口径：一次通过参数校验并入账的生成 / 改图计一次使用，含失败和缓存命中；总任务数为全部历史，其余指标属于所选周期。新产出数排除缓存；活跃用户按提交身份去重，不计缺失身份的 `unknown` 工具调用。图表按 UTC 自然日分桶、补齐零值。所有已认证模块访问者可看汇总统计，图片与任务始终按当前用户隔离。

## 验证

在项目根目录运行：

```powershell
.venv/Scripts/python.exe -m pytest plugins/image-generation-plugin/tests/test_studio.py -q --basetemp data/.test-image-studio
node --test plugins/image-generation-plugin/tests/studio-ui.test.mjs
.venv/Scripts/python.exe -m ruff check plugins/image-generation-plugin
```

后端测试启动独立的 `redis-server`，使用动态本地端口和临时目录，结束后关闭；不会连接或清空项目 Redis。未安装 `redis-server` 时该集成测试组跳过。UI 测试使用宿主前端已有的 jsdom 依赖。测试覆盖用户隔离、参考图校验、编辑链、历史持久化、并发限制、Redis 缓存 TTL、统计、Redis 故障和页面交互，不调用收费图像 API。
