# Proposal

## Why

当前 CampusClaw 使用 Flask 签名 Cookie session 保存登录用户标识，浏览器会自动把认证 Cookie 附带到所有同源请求。课程项目后续需要让 API 的认证边界显式、可测试且便于前端或其他受控客户端调用，因此将登录态迁移为服务端校验的随机不透明 Bearer Token。

## What Changes

- **BREAKING** 将受保护 API 从 Cookie session 认证迁移为 `Authorization: Bearer <token>`；API 不再接受 session Cookie、查询参数或请求体中的 Token 作为认证凭据。
- 登录成功后由服务端生成高熵随机不透明 access token；服务端仅保存不可逆 Token 摘要及用户、签发时间、过期时间和撤销状态，响应返回 Token 类型与有效期。
- 增加 Token 生命周期：过期、格式错误、未知或已撤销 Token 统一返回 HTTP 401；登出撤销当前 Token，旧 Token 不能继续访问 API。
- 保留现有教师/学生角色、会话班级边界、材料授权和第 4 课知识库检索契约，但身份与 `class_id` 均从服务端解析后的 Token 关联用户读取。
- 网页登录改为调用登录 API，前端将 Token 保存在当前浏览器会话存储中，并为所有本站 API 请求主动添加 Authorization 头；401 时清理 Token 并回到登录页。
- 网页页面只提供不含业务数据的应用壳；材料、身份、检索和问答数据均通过带 Token 的 API 加载，浏览器不再依赖认证 Cookie。
- 保留密码 bcrypt 校验；移除认证对 Flask session 签名 Cookie 的依赖，新增 Token 摘要密钥和可配置的 access token TTL。
- 为现有用户和材料提供迁移路径：数据库业务数据不变，旧 Cookie 登录态不迁移，部署后用户需重新登录获取 Token。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `auth-upload`: 将用户登录、受保护 API、工作区身份加载和安全配置从签名 Cookie session 修改为随机不透明 Bearer Token，同时保留角色权限、班级隔离、材料上传和 Compose 健康检查行为。

## Impact

- 影响 `app/auth.py`、应用认证配置、前端登录与 `workspace.js` 的请求封装、受保护页面壳、SQLite schema 和初始化/迁移脚本。
- 新增 Token 存储表和过期/撤销查询索引；用户、材料、知识库和第 4 课切片数据不迁移、不改结构边界。
- 登录接口响应、登出流程、所有受保护 API 的请求头和未认证响应发生 breaking change；README、Compose 环境变量和自动化/Compose 验收脚本需要同步更新。
- 不引入 JWT、刷新 Token、OAuth/OIDC、SSO、跨域 API、第三方身份提供商或密码修改流程。
