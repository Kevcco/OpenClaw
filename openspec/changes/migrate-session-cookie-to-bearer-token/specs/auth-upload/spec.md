# Spec Delta

## MODIFIED Requirements

### Requirement: 用户登录

系统 MUST 提供教师（teacher）和学生（student）两类角色的账号密码登录。登录交换接口不要求已有 Token；凭据校验成功后 MUST 返回一次性展示的随机不透明 access token、`token_type=Bearer`、有效期和当前用户的标识、角色与班级。系统 MUST NOT 通过认证 Cookie 建立登录态，受保护 API 后续只接受 Authorization 头中的 Bearer Token。未登录用户访问受保护 API 时 MUST 被拒绝，且 MUST NOT 泄露业务数据。

#### Scenario: 教师与学生登录成功

- **WHEN** 教师 A、学生 A1 或学生 B1 使用各自有效账号和密码调用登录交换接口
- **THEN** 登录 MUST 成功并返回随机不透明 Bearer access token
- **AND** 响应 MUST 包含用户标识、角色、所属班级、`token_type` 和有效期
- **AND** 响应 MUST NOT 通过 `Set-Cookie` 建立认证 session

#### Scenario: 错误密码登录失败

- **WHEN** 用户使用存在的用户名和错误密码登录
- **THEN** 登录 MUST 失败且 MUST NOT 返回 access token
- **AND** 响应 MUST NOT 返回密码哈希或其他认证秘密

#### Scenario: 旧 Cookie 不能继续认证

- **WHEN** 请求只携带迁移前签发的 session Cookie 而不携带有效 Bearer Token
- **THEN** 受保护 API MUST 返回 HTTP 401
- **AND** 响应 MUST NOT 包含任何班级的材料标题、正文、文件路径或存储键

#### Scenario: 未携带 Token 访问受保护 API

- **WHEN** 用户未携带 Authorization Bearer Token 请求受保护 API
- **THEN** API MUST 返回 HTTP 401
- **AND** 响应 MUST NOT 包含任何班级的业务数据

### Requirement: 令牌认证生命周期

系统 MUST 为每次成功登录生成高熵、不可从用户信息推导的随机不透明 access token。服务端 MUST 仅保存 Token 的不可逆摘要、关联用户标识、签发时间、过期时间和撤销状态，不得保存或回显可恢复的原始 Token。Token 有效期 MUST 可通过服务端配置，默认有效期为 8 小时。所有受保护 API MUST 只接受 `Authorization: Bearer <token>`，不得从 Cookie、查询参数、JSON 正文或其他请求头读取 Token。

#### Scenario: 有效 Token 访问 API

- **WHEN** 用户使用未过期且未撤销的 Bearer Token 请求 `/api/me`、材料、检索或问答 API
- **THEN** 服务端 MUST 从 Token 关联的用户记录解析身份、角色和班级
- **AND** 请求 MUST 按现有角色与班级规则继续授权

#### Scenario: 无效或过期 Token 被拒绝

- **WHEN** 请求携带格式错误、未知、过期或已撤销的 Bearer Token
- **THEN** API MUST 返回 HTTP 401
- **AND** 响应 MUST 使用统一的认证错误语义，不泄露 Token 是否曾经存在

#### Scenario: 登出撤销当前 Token

- **WHEN** 已认证用户调用登出接口并携带当前 Bearer Token
- **THEN** 服务端 MUST 将该 Token 标记为 revoked
- **AND** 同一 Token 后续访问任何受保护 API MUST 返回 HTTP 401

#### Scenario: Token 不能通过 URL 或正文传递

- **WHEN** 客户端把 Token 放入查询参数、JSON 正文、Cookie 或非 Authorization 请求头
- **THEN** 服务端 MUST 不将其视为认证凭据
- **AND** 请求 MUST 按未认证请求处理

### Requirement: 角色权限

系统 MUST 按有效 Bearer Token 解析出的角色授权；教师可上传和管理本班材料，学生对本班材料只读；学生调用上传或管理接口 MUST 被服务端拒绝。

#### Scenario: 学生上传被拒绝

- **WHEN** 学生 A1 使用有效 Bearer Token 向材料上传接口提交文件
- **THEN** 系统 MUST 返回 HTTP 403
- **AND** 材料与知识库数据 MUST 无新增或变更
- **AND** 上传目录 MUST 无因该请求产生的新文件

#### Scenario: 教师上传被允许

- **WHEN** 教师 A 使用有效 Bearer Token 提交受支持的材料文件
- **THEN** 系统 MUST 接受请求并执行材料上传与知识库入库流程
- **AND** 成功响应 MUST 返回 HTTP 201 和新材料标识

#### Scenario: 学生只读本班列表

- **WHEN** 学生 A1 使用有效 Bearer Token 访问本班材料列表
- **THEN** 系统 MUST 展示其有权读取的本班材料
- **AND** 学生 MUST NOT 能通过页面或 API 上传、修改或删除材料

### Requirement: 班级隔离

班级 MUST 作为数据边界。所有材料、知识库及相关业务查询 MUST 在服务端按有效 Bearer Token 关联用户的班级标识过滤；A 班用户 MUST NOT 读取、修改或删除 B 班材料；前端隐藏按钮 MUST NOT 作为满足本要求的手段。客户端提交的 `class_id` MUST 被忽略或拒绝，且不得覆盖 Token 解析出的用户班级。

#### Scenario: 跨班按 ID 访问材料被拒绝

- **WHEN** 班级 A 的用户通过 URL、API 路径参数或请求体指定班级 B 的材料 ID 发起访问
- **THEN** 系统 MUST 返回 HTTP 404
- **AND** 响应 MUST NOT 返回该材料的标题、正文片段、文件路径、存储键或班级归属

#### Scenario: 列表不得泄露其他班级材料

- **WHEN** 学生 A1 使用有效 Bearer Token 请求材料列表并提供任意合法的分页或搜索参数
- **THEN** 返回集合中的每一条记录 MUST 归属于班级 A
- **AND** 返回内容 MUST NOT 包含班级 B 预置材料的可区分标题

#### Scenario: 客户端班级参数不能覆盖 Token 班级

- **WHEN** 班级 A 用户在查询参数、路径或请求体中伪造班级 B 的标识
- **THEN** 系统 MUST 忽略或拒绝该客户端班级标识
- **AND** 用户 MUST 仍只能读取或写入 Token 关联的班级 A 数据

### Requirement: 材料工作区前端

系统 MUST 提供可用的登录和材料工作区界面。登录页 MUST 通过登录交换接口取得 Bearer Token，前端 MUST 将 Token 保存在当前浏览器会话存储中，并为所有本站 API 请求主动添加 Authorization 头；前端不得把 Token 放入 URL 或普通 Cookie，也不得从浏览器存储读取角色作为授权依据。工作区页面可以返回不含业务数据的应用壳，身份、材料、检索和问答数据 MUST 从受 Token 保护的 API 加载。教师 MUST 能从界面上传 `.txt`/`.md`，学生 MUST 看不到上传入口且保持只读。材料内容预览 MUST 以不执行 HTML/脚本的方式呈现。

#### Scenario: 工作区使用 Token 校准身份

- **WHEN** 教师或学生登录后打开或刷新材料工作区
- **THEN** 界面 MUST 从会话存储取得 Token，并使用 `Authorization: Bearer` 调用 `/api/me` 和材料 API
- **AND** 教师 MUST 看到上传入口，学生 MUST NOT 看到上传入口
- **AND** 学生即使绕过界面仍 MUST 由上传 API 拒绝

#### Scenario: Token 失效时清理并重新登录

- **WHEN** 任一 API 返回 HTTP 401
- **THEN** 前端 MUST 清除当前会话存储中的 Token
- **AND** 页面 MUST 引导用户回到登录页

#### Scenario: 登出清理前端 Token

- **WHEN** 用户点击退出并且当前 Token 仍有效
- **THEN** 前端 MUST 使用该 Token 调用登出接口并清除会话存储
- **AND** 该 Token 后续不能访问受保护 API

#### Scenario: 材料预览不会执行上传内容

- **WHEN** 用户打开含有 HTML 或脚本标记的 Markdown 材料
- **THEN** 内容 MUST 以安全文本呈现
- **AND** 浏览器 MUST NOT 执行材料中的脚本

### Requirement: 密码哈希与认证密钥

系统 MUST 使用单向密码哈希算法存储和校验密码，禁止存储明文密码；原始 Bearer Token MUST NOT 持久化；Token 摘要所需的服务端密钥 MUST 仅通过环境变量或 Compose 注入，MUST NOT 硬编码在源码或提交到版本库。认证不得依赖 Flask 签名 session Cookie。

#### Scenario: 数据库中不存在明文密码或原始 Token

- **WHEN** 检查预置用户和 Token 存储表
- **THEN** 用户密码字段 MUST NOT 等于任何预置账号的明文密码
- **AND** Token 表 MUST 只包含摘要及生命周期元数据，不得包含可直接用于 Authorization 的原始 Token

#### Scenario: 登录使用哈希校验

- **WHEN** 用户先后使用正确密码与错误密码登录
- **THEN** 正确密码 MUST 通过哈希校验并签发 Bearer Token
- **AND** 错误密码 MUST 校验失败且不签发 Token

#### Scenario: 缺少 Token 摘要密钥时启动失败

- **WHEN** 应用启动环境未提供必需的 Token 摘要密钥
- **THEN** 应用 MUST 拒绝启动且 MUST NOT 静默使用不安全默认值
- **AND** `.env.example` MUST 列出该环境变量名但 MUST NOT 包含真实密钥

## ADDED Requirements

### Requirement: Token 迁移与旧登录态处理

系统 MUST 将数据库中的用户、角色、班级、材料和知识库数据原样保留，并通过新增 Token 存储结构承接新的认证生命周期。迁移后旧签名 Cookie 不得继续作为认证凭据；用户必须重新登录取得 Token。部署和回滚说明 MUST 明确该 breaking change，不得把旧 Cookie 宣称为可兼容的登录态。

#### Scenario: 迁移不改变业务数据

- **WHEN** 应用从 Cookie 认证版本升级到 Bearer Token 版本
- **THEN** 既有用户、材料、知识库条目、切片和向量索引 MUST 保持可用
- **AND** 用户重新登录后 MUST 继续按照原角色和班级访问这些数据

#### Scenario: 新版本忽略旧 Cookie

- **WHEN** 用户升级后仅携带升级前的 Cookie 访问受保护 API
- **THEN** API MUST 返回 HTTP 401 并要求 Bearer Token
- **AND** 用户完成重新登录后取得的新 Token MUST 能访问其原有授权范围
