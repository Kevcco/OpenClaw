# Design

## Context

参见 `proposal.md` 和 `specs/traceable-vector-retrieval/spec.md`。当前代码是单体 Flask 应用，使用 SQLite 保存用户、材料和 `knowledge_entries.body_text`，并通过 Compose 运行单个 Gunicorn worker。第 3 课已有会话班级隔离、教师上传、材料预览和下载授权，但没有切片、全文索引、向量服务或问答接口。

讲义以 Go + MySQL 为示例，本仓库已有稳定的 Flask + SQLite 数据边界。本次保留现有应用栈，将 SQLite 作为关系库权威数据源；新增的 Qdrant 服务和服务端网关适配器承接讲义中的向量库、嵌入与回答职责。对外行为按讲义验收，内部不进行无关的 Go/MySQL 重写。

## Goals / Non-Goals

**Goals:**

- 让三种检索模式共享同一个可定位切片模型和同一个会话班级过滤边界。
- 将切片正文、偏移、索引状态放在 SQLite，把向量和有限标识放在 Qdrant `campusclaw_chunks` 集合；结果总是从 SQLite 回表取正文。
- 为上传、重建、删除、重启和依赖故障定义可恢复的索引生命周期。
- 以独立检索 API、`/api/ask` 和工作区界面提供可验收的命中、引用及无依据行为。

**Non-Goals:**

- 不重写已有 Flask 应用为 Go，不迁移整个项目到 MySQL，不引入 LangChain/LlamaIndex。
- 不让浏览器直连 Qdrant、嵌入网关或回答网关，不把网关密钥放入页面或返回向量分量。
- 不实现流式对话、长时记忆、交叉编码器重排序或跨班/跨校搜索。

## Decisions

### 1. 关系库切片表是权威，Qdrant 是可重建投影

新增 `knowledge_chunks` 表保存 `id`、`knowledge_entry_id`、`material_id`、`class_id`、`chunk_index`、`chunk_text`、`start_offset`、`end_offset`、策略、版本、正文哈希、`index_status` 和错误信息；新增 SQLite FTS5 虚拟表索引 `chunk_text`。这映射讲义的 MySQL `knowledge_chunks` 与全文索引，同时兼容当前 SQLite 部署。

Qdrant collection 固定名为 `campusclaw_chunks`，点 ID 使用 `knowledge_chunks.id`。payload 只包含 `class_id`、`material_id`、`knowledge_entry_id`、`chunk_id`、`chunk_index`，不复制 `chunk_text`。检索拿到点 ID 后必须以会话班级再次查询 SQLite。这样 Qdrant 丢失时可以从关系库重建，单侧过滤错误也不会泄露正文。

选择新增 Qdrant Compose 服务而不是 Chroma，是为了与讲义的向量服务边界、余弦距离和点主键契约一致；Qdrant 不映射宿主机端口，只加入应用内部网络并使用持久卷。

### 2. 三种切分策略共享确定性接口

- `auto`：最大 800 Unicode 字符、重叠 80，优先空行、换行、句号等断点。
- `custom`：校验长度 100-2000、重叠 0%-50%，支持按换行、空行或句号的分隔偏好以及可选 URL/邮箱移除、连续空白折叠。
- `hierarchy`：识别 Markdown `#`/`##`/`###` 标题，标题保留在所属切片；超长章节回退到 auto 窗口。

切分器返回待嵌入文本、序号和相对于切分输入的偏移；权威 `body_text` 永远不被预处理覆盖。由于讲义明确说明预处理后的偏移不等同于原文件偏移，API 同时返回 `offset_basis`（`body_text` 或 `normalized`）和切分策略，避免前端误把规范化位置当原文件下标。默认种子材料和未指定策略均使用 `auto`。

### 3. 上传/重建采用阶段状态，不做跨存储伪事务

材料文件和原文先按现有事务写入；切片写入后设为 `pending`，嵌入成功且 Qdrant 点写入后改为 `ready`。嵌入或 Qdrant 失败时保留原文和切片，状态改为 `failed` 并记录可重试错误，绝不留下半写入点。材料删除先按现有班级授权删除 SQLite 材料级联数据，再以点 ID 清理 Qdrant；清理失败通过重建/reconcile 清理，检索回表不会返回已删除来源。

提供幂等 `scripts/rebuild_knowledge_index.py`，支持材料 ID、班级、策略和全量选项。重建先删除选定材料的旧切片和 Qdrant 点，再按本次策略重建；重复执行不会遗留旧主键。应用启动只做轻量 reconcile（缺失、哈希变化或 failed），避免每次容器重启重算所有向量。

### 4. 检索编排与故障降级

- `keyword`：SQLite FTS5 按 `class_id` 和 `index_status='ready'` 过滤，返回全文相关度排序；不调用 embedding 或 Qdrant。
- `vector`：调用 embedding provider，将查询向量交给 Qdrant，过滤 `class_id`，按余弦相似度降序并丢弃 `<0.35` 的点；点 ID 回 SQLite 取得正文。
- `hybrid`：先分别执行两路过滤和排序，再使用 `1/(60+rank)` 的 RRF；缺席路径不贡献分数，最后统一 SQLite 班级复核和有界去重。

新增登录保护的 `GET /api/knowledge/search?q=&mode=&limit=`。默认 `mode=hybrid`、limit 10、上限 20；空查询 400；无命中 200 且返回固定消息和空 `hits`。新增 `POST /api/ask` 固定使用 hybrid、最多 4 个切片；无命中直接返回固定文案，命中后才调用 answer provider。两类 provider 都通过 Flask 服务端适配器注入，测试用可控 fake；未配置真实网关时 vector/hybrid/ask 返回可诊断的 503，而 keyword 继续可用。

### 5. 班级边界集中在检索编排层和回表层

路由只从 `current_user()['class_id']` 获取班级；忽略 query/body/header 中的 `class_id`。keyword SQL、Qdrant filter、SQLite 回表和 `source` 构造全部传递同一可信值。跨班检索返回空结果，不返回 403/404；材料详情/下载继续沿用第 3 课的 404 规则。前端不持有 Qdrant 地址或网关密钥，所有结果入口仍指向已有班级保护材料路由。

### 6. 回答引用采用检索顺序的稳定编号

answer provider 接收服务端构造的最新问题、最多四条 `{title, chunk_index, chunk_text}` 和经过过滤的历史 user/assistant 消息；客户端 system 消息被移除，向量分量、Qdrant payload 和其他班级数据不进入请求。provider 返回文本后，服务端校验/规范化 `[n]` 只能引用 1..N；响应 `citations` 与切片顺序一致，前端按纯文本安全展示。

### 7. 前端保持现有材料工作区的渐进增强

在现有标题筛选旁加入检索模式选择、问题输入和结果区域，保留材料列表、上传按钮和学生只读逻辑。检索结果只渲染 `textContent`，显示加载、空结果、503 和回答失败四种状态。已有 `/api/materials?q=` 不改语义，避免破坏第 3 课接口和测试。

## Risks / Trade-offs

- [Qdrant 与 SQLite 没有跨存储事务] → SQLite 原文和切片状态为权威，写点前后均可重试；回表时再次按班级、状态和材料存在性校验，失败来源不返回。
- [本地 embedding/answer 网关不可用或首次加载慢] → provider 超时和 503 可观测，keyword 可独立工作；Compose 健康检查只依赖应用，模型缓存和 Qdrant 使用持久卷。
- [当前项目不是讲义示例的 MySQL/Go 栈] → 保持 Flask/SQLite 以降低无关迁移风险，公开 API 和验收语义与讲义一致，并在 README 标注对应关系。
- [中文全文索引在 SQLite FTS5 上不如 MySQL ngram] → 使用稳定的 ngram/规范化 tokenizer 适配层和正文关键词回归样例；向量模式承担同义表达召回。
- [切分预处理会使偏移基准复杂] → 保存 `offset_basis`、策略和版本，摘录始终来自切片正文；API 不宣称规范化偏移等同原文件偏移。

## Migration Plan

1. 先备份 `data/app.db` 和 `uploads/`，升级 SQLite schema，保留现有材料与权限数据。
2. 启动 Qdrant 内网服务并创建 `campusclaw_chunks`（余弦距离、点 ID 为 chunk ID），配置 embedding/answer 网关地址和密钥，仅注入应用容器。
3. 运行全量重建脚本，为种子及历史材料生成 `auto` 切片；核对 A/B 班、偏移、payload 无正文、重复重建幂等。
4. 启用检索 API、`/api/ask` 和前端；运行关键字、向量、混合、无命中、跨班、故障降级、重启持久化验收。
5. 回滚时停用新路由和 UI、恢复上一应用镜像；保留 SQLite 原文，Qdrant 点可删除后从重建脚本恢复，不使用 `docker compose down -v`。
