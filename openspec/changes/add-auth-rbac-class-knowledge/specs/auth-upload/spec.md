# Spec Delta

## Purpose

本能力让教师和学生以各自角色登录 CampusClaw，以班级作为不可绕过的数据边界隔离教学材料，并使教师上传的内容可靠地进入知识库、供本班成员查看，同时明确安全、部署和持久化的验收行为。

## ADDED Requirements

### Requirement: 用户登录

系统 MUST 提供教师（teacher）和学生（student）两类角色的账号密码登录；登录成功后 MUST 建立有效会话；未登录用户访问受保护页面或 API 时 MUST 被拒绝，且 MUST NOT 泄露业务数据。

#### Scenario: 教师与学生登录成功

- **WHEN** 教师 A、学生 A1 或学生 B1 使用各自有效账号和密码登录
- **THEN** 登录 MUST 成功并建立有效会话
- **AND** 会话 MUST 关联该用户的标识、角色与所属班级

#### Scenario: 错误密码登录失败

- **WHEN** 用户使用存在的用户名和错误密码登录
- **THEN** 登录 MUST 失败且 MUST NOT 建立有效会话
- **AND** 响应 MUST NOT 返回密码哈希或其他认证秘密

#### Scenario: 未登录访问受保护资源

- **WHEN** 未携带有效会话的用户请求材料列表页面或受保护 API
- **THEN** 页面请求 MUST 重定向到登录页
- **AND** API 请求 MUST 返回 HTTP 401
- **AND** 响应 MUST NOT 包含任何班级的材料标题、正文、文件路径或存储键

### Requirement: 角色权限

系统 MUST 按有效会话中的角色授权；教师可上传和管理本班材料，学生对本班材料只读；学生调用上传或管理接口 MUST 被服务端拒绝。

#### Scenario: 学生上传被拒绝

- **WHEN** 学生 A1 使用有效会话向材料上传接口提交文件
- **THEN** 系统 MUST 返回 HTTP 403
- **AND** 材料与知识库数据 MUST 无新增或变更
- **AND** 上传目录 MUST 无因该请求产生的新文件

#### Scenario: 教师上传被允许

- **WHEN** 教师 A 使用有效会话提交受支持的材料文件
- **THEN** 系统 MUST 接受请求并执行材料上传与知识库入库流程
- **AND** 成功响应 MUST 返回 HTTP 201 和新材料标识

#### Scenario: 学生只读本班列表

- **WHEN** 学生 A1 登录后访问本班材料列表
- **THEN** 系统 MUST 展示其有权读取的本班材料
- **AND** 学生 MUST NOT 能通过页面或 API 上传、修改或删除材料

### Requirement: 班级隔离

班级 MUST 作为数据边界。所有材料、知识库及相关业务查询 MUST 在服务端按有效会话中的班级标识过滤；A 班用户 MUST NOT 读取、修改或删除 B 班材料；前端隐藏按钮 MUST NOT 作为满足本要求的手段。

#### Scenario: 跨班按 ID 访问材料被拒绝

- **WHEN** 班级 A 的用户通过 URL、API 路径参数或请求体指定班级 B 的材料 ID 发起访问
- **THEN** 系统 MUST 返回 HTTP 404
- **AND** 响应 MUST NOT 返回该材料的标题、正文片段、文件路径、存储键或班级归属

#### Scenario: 列表不得泄露其他班级材料

- **WHEN** 学生 A1 请求材料列表并提供任意合法的分页或搜索参数
- **THEN** 返回集合中的每一条记录 MUST 归属于班级 A
- **AND** 返回内容 MUST NOT 包含班级 B 预置材料的可区分标题

#### Scenario: 客户端班级参数不能覆盖会话

- **WHEN** 班级 A 用户在查询参数、路径或请求体中伪造班级 B 的标识
- **THEN** 系统 MUST 忽略或拒绝该客户端班级标识
- **AND** 用户 MUST 仍只能读取或写入会话所关联的班级 A 数据

### Requirement: 材料上传与知识库入库

教师上传受支持的教学材料后，系统 MUST 保存文件、解析文本并写入知识库记录；材料与知识库条目 MUST 关联教师会话所属班级；本班材料列表 MUST 从数据库查询展示，上传成功后刷新列表 MUST 可见新记录。

#### Scenario: 上传后知识库与列表可查

- **WHEN** 教师 A 上传合法的 `.md` 或 `.txt` 文件且解析成功
- **THEN** 知识库中 MUST 新增与该材料对应且关联班级 A 的记录
- **AND** 材料集合 MUST 新增一条关联班级 A、标题可辨的记录
- **AND** 教师 A 刷新本班材料列表时 MUST 看到该材料

#### Scenario: 上传后本班学生可见但只读

- **WHEN** 教师 A 成功上传新材料后学生 A1 刷新本班材料列表
- **THEN** 学生 A1 MUST 能看到该材料
- **AND** 学生 A1 MUST NOT 能修改、删除或再次上传覆盖该材料

#### Scenario: 上传失败不产生脏数据

- **WHEN** 上传因不支持的格式、空文件或解析失败而终止
- **THEN** 系统 MUST 返回 HTTP 400 和明确的错误语义
- **AND** 材料与知识库中 MUST NOT 留下不完整记录
- **AND** 上传目录中 MUST NOT 留下孤立文件

### Requirement: 材料工作区前端

系统 MUST 提供可用的登录和材料工作区界面。工作区刷新后 MUST 通过 `/api/me` 获取当前身份，不得从浏览器存储读取角色作为授权依据；材料集合 MUST 从受会话保护的 API 加载；教师 MUST 能从界面上传 `.txt`/`.md`，学生 MUST 看不到上传入口且保持只读。材料内容预览 MUST 以不执行 HTML/脚本的方式呈现，搜索结果仍由服务端按当前会话班级过滤。

#### Scenario: 工作区依据服务端身份显示操作

- **WHEN** 教师或学生打开或刷新材料工作区
- **THEN** 界面 MUST 通过 `/api/me` 确认身份，并从材料 API 加载集合
- **AND** 教师 MUST 看到上传入口，学生 MUST NOT 看到上传入口
- **AND** 学生即使绕过界面仍 MUST 由上传 API 拒绝

#### Scenario: 材料预览不会执行上传内容

- **WHEN** 用户打开含有 HTML 或脚本标记的 Markdown 材料
- **THEN** 内容 MUST 以安全文本呈现
- **AND** 浏览器 MUST NOT 执行材料中的脚本

### Requirement: 预置核心数据

系统 MUST 建立班级、用户、讲义、作业、助手和技能六类核心数据结构，并预置可验收的样本数据，以支持登录、班级隔离和上传验收。

#### Scenario: 种子数据包含双班和用户

- **WHEN** 首次执行数据库初始化或种子流程
- **THEN** 数据库 MUST 包含班级 A 和班级 B
- **AND** 数据库 MUST 包含归属班级 A 的教师 A 与学生 A1，以及归属班级 B 的学生 B1
- **AND** 每个预置用户 MUST 具有可登录用户名和密码哈希

#### Scenario: 两班材料可区分且核心结构完整

- **WHEN** 种子流程执行完成
- **THEN** 数据库 MUST 至少包含一条标题可识别为班级 A 的材料和一条标题可识别为班级 B 的材料
- **AND** 讲义、作业、助手和技能的数据结构 MUST 已建立

### Requirement: 密码哈希与会话密钥

系统 MUST 使用单向密码哈希算法存储和校验密码，禁止存储明文密码；会话签名密钥 MUST 仅通过服务端环境变量或 Compose 注入，MUST NOT 硬编码在源码或提交到版本库。

#### Scenario: 数据库中不存在明文密码

- **WHEN** 检查预置用户的密码字段
- **THEN** 字段值 MUST NOT 等于任何预置账号的明文密码
- **AND** 字段值 MUST 符合所选密码哈希算法的可识别格式

#### Scenario: 登录使用哈希校验

- **WHEN** 用户先后使用正确密码与错误密码登录
- **THEN** 正确密码 MUST 通过哈希校验并建立会话
- **AND** 错误密码 MUST 校验失败且不建立会话

#### Scenario: 缺少会话密钥时启动失败

- **WHEN** 应用启动环境未提供必需的会话签名密钥
- **THEN** 应用 MUST 拒绝启动且 MUST NOT 静默使用不安全默认值
- **AND** `.env.example` MUST 列出该环境变量名但 MUST NOT 包含真实密钥

### Requirement: Docker Compose 部署与健康检查

系统 MUST 以 Docker Compose 作为标准启动方式，提供无需认证的 `GET /health`，并通过 volume 持久化数据库文件和上传目录，使容器重建后数据保持可用。

#### Scenario: Compose 启动后应用可访问

- **WHEN** 操作者按 README 配置环境并执行 `docker compose up --build` 直至 healthcheck 通过
- **THEN** 浏览器 MUST 能访问登录页
- **AND** `GET /health` MUST 返回 HTTP 200 和表示服务可用的 JSON 响应

#### Scenario: 健康检查不依赖登录态

- **WHEN** 未携带会话 cookie 的请求访问 `GET /health`
- **THEN** 接口 MUST 返回 HTTP 200
- **AND** 接口 MUST NOT 重定向到登录页

#### Scenario: 重建容器后数据仍然存在

- **WHEN** 系统已有预置数据和教师上传的数据，并在不删除 volume 的情况下执行 `docker compose down` 后再次启动
- **THEN** 预置用户 MUST 仍可登录
- **AND** 已上传材料及对应知识库记录 MUST 仍可由本班列表或数据库查询获得
