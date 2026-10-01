# Design

## Context

当前 Flask 单体应用在 `app/auth.py` 中使用签名 Cookie session 保存 `user_id`、`role` 和 `class_id`；认证装饰器从 session 读取身份，网页端通过浏览器自动携带 Cookie 调用 `/api/*`。材料页面还会在服务端模板中注入初始材料列表，`workspace.js` 的请求封装使用同源 Cookie。

本 change 只改变认证传递方式，不改变第 3 课已经建立的角色、班级隔离、材料上传和持久化行为，也不改变第 4 课检索、来源和问答 API 的业务契约。用户、材料、知识条目、切片和 Qdrant 数据必须原样保留。

OpenSpec 当前仍保留第 3 课的 active change `add-auth-rbac-class-knowledge`，其 `auth-upload` 是尚未同步到主规约的 delta。本 change 可以独立 Apply；在最终 Archive 前，需先让 predecessor 的 `auth-upload` 主规约落地，随后再同步本 change 的修改型 delta，避免两个认证版本没有共同基线。

## Goals / Non-Goals

**Goals:**

- 用可撤销、可过期的随机不透明 Bearer Token 替代签名 Cookie session。
- 让所有受保护 API 在同一个认证入口解析用户、角色和班级，并拒绝 Cookie、URL 或正文中的 Token。
- 让现有网页前端通过 sessionStorage 和请求封装显式发送 Authorization 头，同时避免把业务数据渲染到无 Token 的页面壳中。
- 为 Token 生成、摘要存储、撤销、过期、旧 Cookie 失效和数据库迁移提供可验收的测试与 Compose 行为。

**Non-Goals:**

- 不实现 JWT、刷新 Token、OAuth/OIDC、SSO、第三方登录、多设备管理或密码修改。
- 不改变教师/学生角色定义、班级隔离规则、材料文件类型、知识库检索和问答协议。
- 不允许浏览器直连数据库、Qdrant 或模型网关；不把 Token 放进 URL、页面 HTML、日志或材料响应。

## Decisions

### 1. 采用随机不透明 Token，而不是 JWT

登录成功后服务端生成高熵随机字符串，只将原始值返回一次；数据库保存使用 `TOKEN_HASH_SECRET` 计算的 HMAC-SHA-256 摘要、`user_id`、签发时间、过期时间、撤销时间和必要索引。请求收到 Bearer Token 后计算摘要并查表，再从 `users` 表读取当前角色与 `class_id`。

选择不透明 Token 是因为本项目需要明确的登出撤销和过期行为，且没有跨服务无状态验证需求。JWT 虽可减少查表，但会增加撤销列表、密钥轮换和过期前权限变化的复杂度。Token 摘要而非原文入库可以降低数据库泄露后的直接冒用风险。

### 2. 保留现有登录路径作为未认证的凭据交换

保留当前登录页面和 JSON 登录入口的 URL 语义，JSON 登录成功响应改为返回 `access_token`、`token_type`、`expires_in` 以及用户摘要；该凭据交换端点是唯一不需要已有 Token 的认证入口。现有登出入口改为要求当前 Bearer Token 并撤销该 Token。`/health` 继续无认证。

所有 `/api/me`、材料、检索、问答和管理 API 统一只读取 `Authorization: Bearer <token>`。认证失败返回 401 和统一错误体，必要时带 `WWW-Authenticate: Bearer`；角色不足仍返回 403，资源跨班访问仍按已有 404 规则处理。

### 3. Token 关联用户，不把角色和班级作为客户端可信数据

Token 表只关联 `user_id`，每次请求在 Token 有效后从数据库读取用户当前角色和班级。这样角色或班级发生服务端变更时不会继续信任 Token 内的旧授权字段，也不会接受请求中的 `class_id`。所有材料、知识库和第 4 课检索回表继续使用同一个服务端 `class_id`。

### 4. 网页端使用 sessionStorage 和统一请求封装

登录页用 `fetch` 调用凭据交换接口，将 access token 放入当前标签页会话存储的命名键；不使用 localStorage、Cookie、URL 或 HTML 隐藏字段。`workspace.js` 的 `fetchJson` 为本站 API 自动加 Authorization 头，并不再设置 `credentials: same-origin` 作为认证手段。收到 401 时清除 Token 并跳转登录页；退出时先调用撤销接口，再清除本地 Token。

由于普通页面导航不能附加 Authorization 头，`GET /materials` 改为只返回不含用户、材料和检索数据的应用壳。页面脚本取得 Token 后调用 `/api/me` 和材料 API；无 Token 或验证失败时立即跳转登录页。这样不会通过公开页面壳泄露业务数据，同时保留现有工作区 URL。

### 5. 生命周期与清理

默认 access token TTL 为 8 小时，并由 `ACCESS_TOKEN_TTL_SECONDS` 配置。Token 查询使用 `expires_at > now` 且 `revoked_at IS NULL`；登出设置撤销时间而不是物理删除，以便审计和避免旧值重新生效。提供清理过期/撤销记录的维护逻辑，但不在本 change 引入后台任务；应用启动或显式脚本可执行轻量清理。

### 6. 数据库和部署迁移

初始化脚本以幂等方式新增 `auth_tokens` 表和索引，不触碰既有用户、材料、知识库、切片或向量表。Compose 注入 `TOKEN_HASH_SECRET` 与 TTL；`.env.example` 只给出占位符。升级后旧 signed-cookie session 被忽略，所有用户需重新登录；回滚应用代码前应保留 Token 表但旧版本不会信任其记录，回滚步骤必须说明重新登录的影响。

## Risks / Trade-offs

- [Token 被前端脚本读取后仍受 XSS 影响] → 使用 sessionStorage 而非长期 localStorage，禁止拼接 HTML，保留纯文本预览，并在部署文档中要求 HTTPS 和安全响应头；本 change 不实现完整 CSP 系统。
- [Token 认证每次请求需要数据库查表] → 为摘要、用户和过期状态建立索引；当前课堂规模优先保证撤销和权限即时生效，不引入缓存造成撤销延迟。
- [旧 Cookie 用户会被强制重新登录] → 在 README、登录页面和 Compose 迁移说明中明确 breaking change；业务数据不删除。
- [页面壳公开可访问] → 壳中不嵌入用户、材料、文件路径或检索数据，所有业务 API 仍由 Bearer Token 服务端保护，前端未验证身份时立即返回登录页。
- [多标签页各自持有 Token] → sessionStorage 与当前标签页生命周期一致；本 change 不承诺跨标签同步或全设备登出。

## Migration Plan

1. 备份 `data/app.db`、`uploads/` 和第 4 课 Qdrant volume；发布包含 `auth_tokens` 幂等迁移的应用镜像。
2. 在 `.env` 中生成新的 `TOKEN_HASH_SECRET`，配置 `ACCESS_TOKEN_TTL_SECONDS`，运行数据库初始化/迁移并启动 Compose healthcheck。
3. 先验证旧 Cookie 只能得到 401，再用教师、学生 A1/B1 重新登录，确认 Token、角色权限、A/B 班隔离、材料上传、检索和问答均正常。
4. 运行完整 pytest 与 Compose 验收，额外检查响应不设置认证 Cookie、Token 不出现在 URL/日志/页面源代码中，登出后的 Token 立即失效。
5. 回滚时保留业务数据和 Token 表，恢复旧镜像并按旧版本登录流程重新建立 Cookie；不得把新 Token 当作旧 session 使用，也不得删除材料、切片或向量数据。
