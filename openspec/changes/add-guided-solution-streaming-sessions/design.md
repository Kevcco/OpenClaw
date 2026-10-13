# Design

## Context

See proposal.md for motivation. 当前服务已具备 SQLite 用户/班级、Bearer Token、材料切片、Qdrant/关键词检索和非流式 `/api/ask`；现有 schema 只有占位的 `assistants`/`skills` 表，尚无教师配置内容、会话消息或 OpenAPI/接口测试目录。回答 provider 已能接收有限历史和最多四个证据块，工作区也已通过服务端 API 展示检索与单次问答。

## Goals / Non-Goals

**Goals:**

- 在不破坏第 4 课 API 的前提下建立班级级提示词、一个解题引导技能、用户级会话和消息持久化。
- 让每轮回答拥有单一、可审计的服务端链路，并通过 SSE 将同一最终答案分段发送。
- 为新接口提供可执行的 OpenAPI 文档和数据库一致性测试。

**Non-Goals:**

- 不引入 MCP、模型自主工具调用、子代理、异步任务队列或第二个回答模型协议。
- 不把本课的技能扩展为作业批改、错题讲解或关怀式对话。
- 不允许浏览器直接接触 Qdrant、嵌入网关或回答网关，也不改变现有 Bearer Token 生命周期。

## Decisions

1. **以班级配置表区分提示词、技能和开关。** 增加一个班级助手配置记录（提示词、版本、更新时间）及技能记录（稳定名称、说明、启用状态、版本），以 `class_id` 唯一约束。教师管理路由只接受当前 Token 的班级，学生统一 403；提示词版本在消息创建时快照到消息或运行记录，避免之后编辑配置改写历史。

2. **会话归属使用创建者与班级双重边界。** 会话记录保存 `owner_user_id`、`class_id`、标题和时间；消息记录保存会话、发送者角色、问题/回答文本、状态、引用 JSON、使用的提示词/技能版本和时间。所有读取、追加和删除查询同时带会话 ID、owner 用户 ID 与 class ID，跨边界统一按不可见资源处理。

3. **复用检索与 provider，新增一个会话编排服务。** 编排服务先解析认证用户和会话，再读取班级配置，调用既有 `retrieval.search(..., mode="hybrid", limit=4)`，将已清洗的历史和证据传给 answer provider，最后复用 `normalize_citations` 生成来源。客户端提供的系统消息、班级号、技能文本和向量元数据在编排层丢弃。

4. **SSE 在应用层分段而非让 provider 暴露上游协议。** 会话消息路由以 `text/event-stream` 返回固定事件名（`start`、`delta`、`citation`/`done`、`error`），先写入 pending 消息；provider 返回完整文本后按安全的 Unicode 文本片段切成多个 `delta`，完成事件携带最终 answer、message_id 和 citations。这样当前非流式 provider 仍可用，未来可替换真正流式 provider 而不改变客户端事件契约。断连通过生成器清理并更新状态，不缓存密钥或内部诊断。

5. **解题引导规则在服务端形成不可覆盖的系统约束。** 启用时，provider 的系统消息明确要求给思路/步骤、引用材料位置且不直接给最终答案；停用时不注入这段规则。服务端仍校验引用编号和本班来源，提示词内容不由学生请求传入。

6. **OpenAPI 文档作为静态契约与实际路由同步维护。** 在应用中提供 `/openapi.json` 和 Swagger UI（可使用静态资源或轻量文档页），为 SSE 响应标注 `text/event-stream` 及事件格式。文档只描述 Bearer Token，不放 `.env` 值。`apitest/run_all.py` 用标准库 HTTP/SQLite 检查可部署地址，按 `cases/<path>/<METHOD>.py` 发现脚本并输出本地 HTML；报告目录加入 `.gitignore`。

7. **兼容与迁移采用幂等 schema 初始化。** 新表、索引和默认“解题引导”技能由现有初始化流程以 `CREATE TABLE IF NOT EXISTS`/幂等种子完成；旧数据库首次启动补齐结构，不删除任何材料、Token、切片或历史 `/api/ask` 数据。回滚时停用新路由/前端入口即可，新增表保留不影响旧功能。

## Risks / Trade-offs

- **完整 provider 非流式导致首字等待仍存在** → 先持久化 pending 状态并快速发送 `start`，再分片转发；未来可在同一事件协议下替换上游流式实现。
- **提示词或技能文本可能诱导模型越权** → 仅教师可写，服务端固定 grounding 约束和证据白名单，且回答后再做引用归一化。
- **长会话增加上下文和 SQLite 体积** → 每轮只取受限数量的最近 user/assistant 消息，限制问题、标题和配置文本长度，并保留完整消息但不把全部历史发送给模型。
- **SSE 连接中断留下未完成消息** → 记录 `streaming`/`failed` 状态和错误原因摘要，重连时允许查看失败轮次但不重复伪造完成事件。
- **文档与实现漂移** → 在 `apitest` 中从 OpenAPI 路径清单抽查响应状态和 Content-Type，并将报告生成物排除出 Git。

## Migration Plan

1. 先合并幂等数据库 schema、默认技能和服务端路由，再发布 OpenAPI/Swagger 与接口测试。
2. 更新工作区以 Token 调用会话 SSE；保留原材料检索面板和 `/api/ask` 兼容调用。
3. 在 `.env` 配置真实回答服务后运行接口测试；未配置时使用现有 extractive provider，命中/引用/持久化链路仍可验收。
4. 回滚时关闭新工作区入口并恢复旧路由注册；不删除新增表，避免影响既有数据。

## Open Questions

无。模型供应商和模型名继续作为部署配置，不改变本规约中的外部行为。
