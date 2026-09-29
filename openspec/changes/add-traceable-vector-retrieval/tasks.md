# Tasks

## 1. 切片模型与数据库索引

- [ ] 1.1 扩展 SQLite schema，增加 `knowledge_chunks`、索引状态字段和 FTS5 结构，并验证 `scripts/init_db.py` 在旧数据库上可重复运行且不破坏现有材料。
- [ ] 1.2 实现 `auto`、`custom`、`hierarchy` 三种确定性切分策略，返回切片正文、序号、偏移、策略和 `offset_basis`；用中文、Markdown 标题、重叠和边界样例运行单元测试。
- [ ] 1.3 实现切片哈希、稳定 chunk ID、正文变更检测和失败状态记录；验证相同材料/策略重建不产生重复切片，嵌入失败仍保留正文且状态可识别。

## 2. 向量服务与索引生命周期

- [ ] 2.1 增加 Qdrant Compose 服务、`campusclaw_chunks` collection 初始化和持久卷配置；验证 Qdrant 不映射宿主机端口且应用可通过内部网络访问。
- [ ] 2.2 实现服务端 embedding provider、余弦向量写入/删除和 payload 校验，点 ID 与 `knowledge_chunks.id` 一致且 payload 不包含正文；用 fake provider 单测覆盖成功、超时和维度错误。
- [ ] 2.3 实现幂等 `scripts/rebuild_knowledge_index.py`，支持全量/按班级/按材料和策略参数；运行两次后验证旧切片、旧向量清理且新索引可用。
- [ ] 2.4 接入上传、删除和应用启动 reconcile：上传后生成切片并索引，删除后清理向量，重启只处理缺失/变更/failed；验证原文事务失败时没有孤立切片或文件。

## 3. 三种检索模式与班级隔离

- [ ] 3.1 实现 keyword 检索，只查询当前会话班级且仅使用 ready 切片的全文索引；在 Qdrant 停止时验证关键词查询仍能返回正确摘录。
- [ ] 3.2 实现 vector 检索，按会话班级过滤 Qdrant、丢弃余弦低于 0.35 的候选并回 SQLite 取正文；用 fake embedding 验证相似查询、阈值和 503 故障行为。
- [ ] 3.3 实现 hybrid 检索和 RRF(k=60)，缺席路径不贡献分数并对重叠切片去重；验证默认模式、命中双路径优先和有界 top-k。
- [ ] 3.4 新增 `GET /api/knowledge/search`，实现 mode、limit、空查询、无命中固定文案、来源字段和安全文本契约；HTTP 测试覆盖未登录 401、伪造 class_id、A/B 班无泄露和旧材料标题搜索兼容。

## 4. 可追溯问答

- [ ] 4.1 实现 `POST /api/ask` 的请求解析、会话班级读取、历史消息筛选和客户端 system 丢弃；验证问题只用最新一条发起检索且最多取 4 个切片。
- [ ] 4.2 实现服务端 answer provider 与引用校验；仅在有命中时调用 provider，将标题/序号/正文传入并返回与 citations 顺序一致的 `[1]` 标注，禁止向 provider 传递向量或他班数据。
- [ ] 4.3 覆盖无命中不调用 provider、命中回答、provider 超时/错误和引用越界等测试；无命中必须返回固定文案及空 citations。

## 5. 前端工作区

- [ ] 5.1 在材料工作区增加问题输入、keyword/vector/hybrid 模式选择、结果列表、切片出处和预览/下载入口；用 `textContent` 安全展示正文，不直连 Qdrant 或模型网关。
- [ ] 5.2 增加回答区和加载、无依据、向量 503、回答失败状态；前端测试验证学生仍无上传权限、结果来源按会话班级展示且 `[n]` 引用可对应出处。

## 6. Compose 验收与文档

- [ ] 6.1 更新 Dockerfile、启动脚本和环境变量说明，确保数据库初始化、Qdrant 可用性检查和轻量 reconcile 顺序正确；运行 `docker compose config`、构建和健康检查。
- [ ] 6.2 扩展 `scripts/verify_compose.sh` 覆盖三种检索、RRF/阈值、A/B 班隔离、无命中问答、来源入口和 down/up 后索引持久性；在本地 Compose 环境运行并确认全部断言通过。
- [ ] 6.3 更新 README 记录接口、模式、切分参数、网关配置、Qdrant 持久化、重建命令和故障降级；运行完整 `pytest`、Compose 验收及 `openspec validate add-traceable-vector-retrieval --strict`。
