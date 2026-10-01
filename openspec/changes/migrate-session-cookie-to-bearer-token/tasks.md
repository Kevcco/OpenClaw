# Tasks

## 1. Token 数据模型与配置

- [x] 1.1 新增幂等的 `auth_tokens` 表，保存 Token 摘要、`user_id`、签发/过期/撤销时间并建立查询索引；运行初始化两次并验证既有 users、materials、knowledge_entries、knowledge_chunks 和向量索引不受影响。
- [x] 1.2 增加 `TOKEN_HASH_SECRET` 与 `ACCESS_TOKEN_TTL_SECONDS` 配置，要求缺少 Token 摘要密钥时应用明确启动失败；更新 `.env.example` 并验证真实密钥不进入镜像或版本文件。
- [x] 1.3 实现随机不透明 Token 的生成、HMAC 摘要、有效期判断和按用户回表；单元测试验证数据库中没有原始 Token，重复登录生成不同 Token 且默认有效期为 8 小时。

## 2. 服务端认证迁移

- [x] 2.1 将 JSON 登录交换接口改为返回 `access_token`、`token_type=Bearer`、`expires_in` 和用户摘要，并验证成功响应不设置认证 Cookie、错误密码不签发 Token。
- [x] 2.2 重写统一认证入口，只接受格式正确的 `Authorization: Bearer <token>`，拒绝 Cookie、查询参数、JSON 正文和其他请求头中的 Token；验证缺失、格式错误、未知 Token 均返回 HTTP 401 和统一错误语义。
- [x] 2.3 实现 Token 过期和撤销逻辑，登出撤销当前 Token，撤销/过期后的 Token 不能访问 `/api/me`、材料、检索或问答接口；验证认证错误不泄露 Token 是否存在。
- [x] 2.4 将角色授权和班级隔离接入 Token 关联用户，继续保持学生上传 403、跨班材料 404、检索跨班空结果和客户端 `class_id` 不生效；验证旧签名 Cookie 单独请求不能认证。

## 3. 网页端 Token 工作区

- [x] 3.1 改造登录页为 JSON 登录交换，将 Token 保存到命名的 `sessionStorage` 键；验证页面源码、URL、Cookie 和普通表单字段中不出现 Token，角色显示仍来自 `/api/me`。
- [x] 3.2 更新 `workspace.js` 的统一请求封装，为所有本站 API 主动添加 Authorization 头且不依赖 `credentials: same-origin`；验证材料、上传、下载、检索、问答和预览请求均携带同一 Token。
- [x] 3.3 将 `/materials` 改为不注入业务数据的页面壳，页面加载后用 Token 调用 `/api/me` 和材料 API；无 Token 或 API 401 时清理 sessionStorage 并跳转登录页，验证学生仍不显示上传入口。
- [x] 3.4 改造退出流程，使用当前 Bearer Token 调用登出接口后清除 sessionStorage；验证旧 Token 立即失效、刷新页面不会恢复旧登录态。

## 4. 迁移兼容与文档

- [x] 4.1 更新启动初始化和迁移流程，使 `auth_tokens` 结构可在已有 `data/app.db` 上安全创建；验证旧用户、材料、知识库、切片和 Qdrant 数据无需重新导入即可在重新登录后使用。
- [x] 4.2 更新 Dockerfile、Compose、`.env.example` 和 README，记录 Token 密钥、TTL、登录/登出请求头、旧 Cookie 失效、sessionStorage 行为和 HTTPS 要求；运行 `docker compose config` 并确认 Qdrant、数据库和上传持久化不变。
- [x] 4.3 更新 API 错误和健康检查说明，确保 `/health` 继续无需 Token 返回 200，其他受保护 API 401/403/404 语义与第 3、4 课契约一致；人工核对文档与接口实现。

## 5. 回归与验收

- [x] 5.1 增加认证单元测试，覆盖 Token 签发、摘要存储、过期、撤销、重复登录、错误凭据、Authorization 解析和旧 Cookie/URL/正文 Token 拒绝。
- [x] 5.2 更新并运行完整 pytest，覆盖教师/学生登录、材料上传与下载、班级隔离、知识库三种检索、`/api/ask` 引用和前端 401 重定向；验证所有业务数据仍按 Token 用户班级过滤。
- [x] 5.3 扩展 `scripts/verify_compose.sh`，检查登录取得 Token、三名用户用 Bearer 访问、学生 403、A/B 隔离、登出失效、旧 Cookie 401、检索/问答和 down/up 后 Token 表及业务数据持久化。
- [x] 5.4 在 Docker Compose 环境运行构建、healthcheck 和验收脚本，确认浏览器/脚本无法访问 Qdrant、Token 不写入 Cookie/URL；记录所有断言输出。
- [x] 5.5 运行 `openspec validate migrate-session-cookie-to-bearer-token --strict`，复核 proposal、design、spec 与 tasks 一致后再允许归档。
