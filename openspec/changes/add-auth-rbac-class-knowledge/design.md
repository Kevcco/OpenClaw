# Design

## Context

当前仓库只有 OpenSpec 配置、课程材料和本 change 的规划文档，没有业务应用代码或既有数据需要迁移。动机见 `proposal.md`，可验收行为见 `specs/auth-upload/spec.md`。本设计约束后续 Apply 阶段的 CampusClaw 最小可运行实现。

## Goals / Non-Goals

**Goals:**

- 建立包含 `user_id`、`role` 和 `class_id` 的登录会话，并让页面与 API 采用一致的认证入口。
- 在服务端统一落实角色授权和班级过滤，任何客户端参数都不能扩大当前会话的权限。
- 完成“文件保存、文本解析、材料与知识库入库、本班列表可见”的可回滚上传链路。
- 用 Docker Compose 提供单命令启动、持久化数据目录和无需认证的健康检查。
- 让初始化脚本生成可直接用于跨班、角色和登录验收的双班种子数据。

**Non-Goals:**

- 不设计检索、向量索引、问答、Agent、作业流程或企业身份集成；详见 `proposal.md` 的 Non-goals。
- 不为当前课堂规模引入独立数据库服务、对象存储、任务队列或微服务拆分。
- 不在本 change 中实现系统管理员跨班操作。

## Decisions

### 1. 使用 Flask SSR 与 SQLite 构成单体应用

- Web 层采用 Flask 3.x，同一进程提供登录页、材料列表、上传 API 和健康检查；页面使用服务端模板渲染。
- 数据层采用 SQLite 单文件 `data/app.db`，通过参数化 SQL 和集中式数据库 helper 访问。
- 容器内使用 gunicorn 绑定 `0.0.0.0:8080`；本地调试可使用 Flask 开发服务器。
- 选择理由：当前是从零开始的单班级规模教学项目，Flask 与 SQLite 依赖少、行为容易通过 HTTP 和 SQL 直接验收。
- 备选方案：Node + Express + better-sqlite3 行为上可行，但会使课件给出的 Python 验证命令和任务清单失效；独立 PostgreSQL 对本阶段过重。

建议模块边界：

```text
app/
  __init__.py      # 应用工厂、SECRET_KEY 校验
  auth.py          # 登录、登出、认证装饰器
  materials.py     # 列表、按 ID 访问、上传入口
  knowledge.py     # 文件解析与知识库写入
  db.py            # 连接与强制 class_id 的查询 helper
  templates/       # 登录页与材料列表
scripts/init_db.py # 建表与种子数据
```

### 2. 使用签名 Cookie 会话与 bcrypt 密码哈希

- Flask signed-cookie session 至少保存 `user_id`、`role` 和 `class_id`；Cookie 设置 `HttpOnly` 与 `SameSite=Lax`，生产 HTTPS 环境再启用 `Secure`。
- `SECRET_KEY` 必须从环境变量读取；缺失时应用启动失败。Compose 通过 `.env` 注入，仓库只提交不含真实值的 `.env.example`。
- 用户表仅保存 `password_hash`，使用 bcrypt 生成和校验；登录错误统一返回，不暴露用户是否存在或哈希内容。
- 页面无会话时返回 `302` 到 `/login`；受保护 API 无会话时返回 `401` JSON。登出清除 session。
- 选择理由：签名 Cookie 满足单体课堂应用的状态需求，无需额外会话存储；bcrypt 是成熟的自适应密码哈希算法。
- 备选方案：JWT 会增加撤销和安全存储复杂度；明文或通用快速哈希不满足密码存储要求。

### 3. 在查询和写入边界统一执行班级隔离

- 列表与集合查询必须使用会话中的 `class_id`，形如 `WHERE class_id = :session_class_id`；路由不得使用 query、path 或 body 中的班级值替代会话值。
- 按 ID 读取、修改或删除材料时，查询同时约束资源 ID 与会话 `class_id`。不存在或跨班均返回 `404`，响应不泄露资源是否存在。
- 新材料和知识库条目的 `class_id` 只取自会话；客户端若提交班级字段则忽略或拒绝。
- 学生上传和其他写操作在文件保存或事务开始前返回 `403`。前端可按角色隐藏控件，但这只改善界面，不承担安全职责。
- 选择理由：在服务端查询边界约束租户键，可覆盖页面、API、直接 ID 访问和参数篡改；统一返回 `404` 可降低资源枚举风险。
- 备选方案：先按 ID 查询再返回 `403` 更便于调试，但会确认他班资源存在；仅在前端隐藏按钮无法满足隔离要求。

### 4. 使用显式数据模型与可重复的种子初始化

SQLite 至少包含以下结构：

| 实体 | 关键字段与关系 |
| --- | --- |
| classes | `id`, `name` |
| users | `id`, `username`, `password_hash`, `role`, `class_id` |
| lectures / assignments / assistants / skills | 主键及必要的 `class_id` 或归属关系，用于六类核心结构验收 |
| materials | `id`, `title`, `class_id`, `file_path`, `uploaded_by`, 时间戳 |
| knowledge_entries | `id`, `material_id`, `class_id`, `body_text`, 时间戳 |

- 外键保持材料、知识库条目、上传者和班级之间的一致性，并为 `class_id` 和常用查询字段建立索引。
- `scripts/init_db.py` 可重复执行且不重复插入种子：班级 A/B、教师 A、学生 A1/B1、两班各一条标题可区分的材料；所有用户密码在写库前 bcrypt 哈希。
- 选择理由：显式关系便于用 SQL 验收隔离和入库结果，并为后续能力留下清晰边界。
- 备选方案：把所有域对象塞入 JSON 会削弱约束和查询可验证性，因此不采用。

### 5. 上传采用暂存、解析、事务入库和失败清理

```text
teacher multipart request
  -> authenticate and require role=teacher
  -> validate extension and non-empty size (.txt/.md)
  -> save to a class-scoped temporary path
  -> parse UTF-8 text
  -> BEGIN
       insert material using session.class_id
       insert knowledge entry linked to material and same class_id
     COMMIT
  -> atomically move/rename to final class-scoped path
  -> return 201 with material_id
```

- 保存路径为 `uploads/{class_id}/{uuid}_{safe_filename}`，不直接信任原始文件名。
- 解析或数据库操作失败时回滚事务并清理暂存文件；最终移动失败时删除已插入记录或执行等价补偿，确保不留下孤立文件或不完整记录。
- 材料标题来自经过清理的表单标题或文件名；列表始终从数据库查询，不扫描上传目录。
- 选择理由：在角色检查后才触碰磁盘，并把双表写入放在一个事务中，可让失败场景具有明确的不变量。
- 备选方案：异步解析更适合大文件，但会引入任务状态和队列；本阶段只接收小型 txt/md，同步处理更易验收。

### 6. Docker Compose 负责配置、持久化和探活

- `Dockerfile` 安装依赖并以 gunicorn 启动应用。
- `docker-compose.yml` 定义 `app` 服务和 `8080:8080` 端口，挂载 `./data:/app/data` 与 `./uploads:/app/uploads`，通过 `.env` 注入 `SECRET_KEY`。
- 容器启动时仅在数据库不存在或尚未初始化时执行 `scripts/init_db.py`，随后启动 Web 服务。
- `GET /health` 无需登录，正常时返回 `200 application/json` 与 `{"status":"ok"}`；Compose healthcheck 调用该端点。
- README 的 Apply 阶段内容将固定步骤：从 `.env.example` 创建 `.env`、设置 `SECRET_KEY`、运行 `docker compose up --build`、访问 `http://localhost:8080/login` 和 `/health`。
- 选择理由：绑定挂载便于课堂直接检查文件持久性，健康端点能区分“容器进程存在”和“应用已就绪”。
- 备选方案：命名 volume 隔离性更好，但课堂直接查看数据库与上传结果不够方便。

## Risks / Trade-offs

- [SQLite 并发写入能力有限] → 保持事务短小；当前课堂规模可接受，后续规模扩大时再迁移独立数据库。
- [上传文件与数据库无法天然形成同一事务] → 使用暂存文件、原子移动和失败补偿，并用测试覆盖每个失败点。
- [签名 Cookie 中的数据客户端可见但不可篡改] → 不在 session 中保存秘密或材料内容，只保存最小身份与授权字段。
- [首版不支持 PDF 等复杂格式] → 只允许 txt/md，明确返回 400 且清理所有副作用。
- [绑定挂载依赖宿主目录权限] → Compose 启动文档明确创建和授权 `data/`、`uploads/`，健康检查暴露启动失败。

## Migration Plan

这是全新应用，无旧数据迁移。Apply 阶段按“应用骨架 → 数据结构与种子 → 登录会话 → 班级隔离 → 上传入库 → Compose 与健康检查”的顺序实现。若部署失败，可停止 Compose 并回退应用镜像；不删除 `data/` 和 `uploads/`，以保留可恢复数据。
