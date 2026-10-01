# CampusClaw

- **价值主张**：面向中小学教研场景，把分散的教学材料沉淀为受身份、角色和班级边界保护的知识库基础。
- **核心场景**：教师和学生登录后查看本班材料，教师可上传教学材料并完成解析入库，学生保持只读。
- **当前课程范围**：材料上传、班级隔离、可追溯知识库检索和带出处问答。
- **暂不实现**：技能运行时、作业提交与批改、注册与找回密码、SSO、多校多租户及生产级高可用。

## 本地开发

```powershell
$env:TOKEN_HASH_SECRET = "local-token-hash-secret"
$env:ACCESS_TOKEN_TTL_SECONDS = "28800"
$env:DATABASE_PATH = "data/app.db"
$env:UPLOAD_DIR = "uploads"
python scripts/init_db.py
python run.py
```

打开 `http://127.0.0.1:8080/login`。预置账号为 `teacher_a / teacher_a_pass`、`student_a1 / student_a1_pass` 和 `student_b1 / student_b1_pass`。

登录是 JSON 凭据交换：成功响应返回随机不透明 `access_token`、`token_type=Bearer` 和 `expires_in`。除 `/health` 与 `/login` 外的 API 均必须携带 `Authorization: Bearer <access_token>`；登出使用同一请求头调用 `POST /logout`，服务端会立即撤销该 Token。网页端只把 Token 保存到当前标签页的 `sessionStorage`，不会写入 Cookie 或 URL；旧版 signed-session Cookie 不再有效。

示例（仅演示请求头，不要把真实 Token 写入脚本或日志）：

```bash
token="$(curl -fsS http://127.0.0.1:8080/login \
  -H 'Content-Type: application/json' \
  --data '{"username":"student_a1","password":"student_a1_pass"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
curl -H "Authorization: Bearer $token" http://127.0.0.1:8080/api/me
curl -X POST -H "Authorization: Bearer $token" http://127.0.0.1:8080/logout
```

`TOKEN_HASH_SECRET` 只用于服务端 HMAC 摘要，数据库不会保存原始 Token；生产环境必须使用随机高熵值并通过环境变量/密钥管理器注入。默认有效期为 8 小时，可用 `ACCESS_TOKEN_TTL_SECONDS` 调整。生产部署应使用 HTTPS，避免 Token 在传输中泄露。

## 第 4 课：可追溯知识库检索

登录后，教师和学生都可以在 `/materials` 的“知识库检索”区域查询当前班级材料。`/materials` 本身只返回不含业务数据的页面壳，页面脚本取得 Token 后再调用受保护 API。服务端提供：

- `GET /api/knowledge/search?q=&mode=&limit=`：`keyword`、`vector`、`hybrid` 三种模式，默认 `hybrid`，上限 20 条。
- `POST /api/ask`：使用本班混合检索的最多 4 个切片生成简短回答，并返回与 `[1]`、`[2]` 对应的 `citations`。

检索结果始终从 SQLite 的 `knowledge_chunks` 回表取得正文，包含材料标题、切片序号、字符区间、摘录以及受保护的预览/下载地址。班级范围只取 Bearer Token 关联的服务端用户，客户端提交的 `class_id` 不会改变检索范围。没有命中时返回“资料中未找到相关内容”，不会调用回答 provider。浏览器不访问 Qdrant、嵌入服务或回答网关。

### 切片与索引

上传和重建默认使用 `auto`：最多约 800 个字符、重叠 80 个字符，并优先在自然断点切分。维护流程还支持 `custom`（长度 100-2000、重叠 0%-50%）和 `hierarchy`（按 Markdown 标题分章，过长章节回退窗口）。权威材料正文不被预处理覆盖；`offset_basis` 会标明偏移基准。

全量或局部重建命令（在应用环境中运行）：

```bash
python scripts/rebuild_knowledge_index.py
python scripts/rebuild_knowledge_index.py --class-id 1 --strategy hierarchy
python scripts/rebuild_knowledge_index.py --material-id 5 --strategy custom --max-chars 600 --overlap-chars 60
```

切片正文和状态保存在 SQLite，向量保存在 Qdrant `campusclaw_chunks` 集合；向量 payload 只包含班级、材料和切片标识，不含正文。重复重建会清理旧切片和向量后重新生成。嵌入失败会保留原文和 `failed` 状态，关键词模式仍可用，恢复依赖后可再次执行重建。

### 网关配置与故障降级

Compose 默认使用确定性的 `EMBEDDING_MODE=hash` 和本地 extractive answer provider，适合课程验收。接入真实嵌入网关时，将 `EMBEDDING_MODE=http`、`EMBEDDING_API_URL`、`EMBEDDING_API_KEY` 写入 `.env`。接入 OpenAI-compatible Chat Completions（例如 DeepSeek 兼容接口）时，设置 `ANSWER_MODE=openai-compatible`、`ANSWER_API_BASE_URL`（例如 `https://api.deepseek.com`；程序会追加 `/chat/completions`）、`ANSWER_MODEL`、`ANSWER_API_KEY`，可选设置 `ANSWER_TIMEOUT`；模型名由你的服务账号实际提供的模型决定，不要把真实密钥提交到仓库或发送到浏览器。旧版项目自定义回答网关仍可使用 `ANSWER_MODE=http`、`ANSWER_API_URL`、`ANSWER_API_KEY`。这些密钥只注入应用容器。向量服务或嵌入网关不可用时，`vector`/`hybrid`/`/api/ask` 返回 HTTP 503 并显示可理解状态，`keyword` 不依赖向量服务。

材料工作区将“知识库检索”和“知识问答”分成两个独立面板：检索按钮只调用 `/api/knowledge/search` 并展示切片出处；问答按钮独立调用 `/api/ask` 并展示回答及 citations，不需要先执行检索。两者均只使用当前 Bearer Token 对应班级的数据。

## Docker Compose

### Ubuntu / VMware Linux

在已安装 Docker Engine 与 Compose 插件的 Ubuntu 虚拟机中，建议从 Ubuntu 本地工作副本运行（VMware HGFS 共享目录权限可能影响 Docker 构建）：

```bash
cd ~/projects/OpenClaw
if [ ! -f .env ]; then cp .env.example .env; fi
token_secret="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
if grep -q '^TOKEN_HASH_SECRET=' .env; then
  sed -i "s/^TOKEN_HASH_SECRET=.*/TOKEN_HASH_SECRET=${token_secret}/" .env
else
  printf '\nTOKEN_HASH_SECRET=%s\n' "$token_secret" >> .env
fi
if grep -q '^ACCESS_TOKEN_TTL_SECONDS=' .env; then
  sed -i 's/^ACCESS_TOKEN_TTL_SECONDS=.*/ACCESS_TOKEN_TTL_SECONDS=28800/' .env
else
  printf 'ACCESS_TOKEN_TTL_SECONDS=28800\n' >> .env
fi
docker compose config
docker compose up --build -d
docker compose ps
curl http://localhost:8080/health
```

健康检查应返回 `{"status":"ok"}`。若 `docker` 命令报 `/var/run/docker.sock: permission denied`，将当前用户加入 `docker` 组后注销并重新登录：

```bash
sudo usermod -aG docker "$USER"
```

### Windows 准备

1. 安装并启动 Docker Desktop。设置中启用 **Use the WSL 2 based engine**，等待 Docker Desktop 显示 Engine running。
2. 在新的 PowerShell 窗口进入项目目录，确认两个命令可用：

```powershell
docker version
docker compose version
```

### 配置与启动

```powershell
cd D:\long\2\grade5\Internet-Software\OpenClaw
$tokenSecret = py -c "import secrets; print(secrets.token_hex(32))"
$envLines = if (Test-Path .env) { Get-Content .env } else { Get-Content .env.example }
$envLines = @($envLines | Where-Object { $_ -notmatch '^(TOKEN_HASH_SECRET|ACCESS_TOKEN_TTL_SECONDS)=' })
$envLines += "TOKEN_HASH_SECRET=$tokenSecret", "ACCESS_TOKEN_TTL_SECONDS=28800"
$envLines | Set-Content -Encoding ascii .env
docker compose config
docker compose up --build -d
docker compose ps
```

打开 `http://localhost:8080/login`；健康检查地址是 `http://localhost:8080/health`，应返回 `{"status":"ok"}`。教师账号为 `teacher_a / teacher_a_pass`，学生账号为 `student_a1 / student_a1_pass` 与 `student_b1 / student_b1_pass`。Compose 未配置 `TOKEN_HASH_SECRET` 时会拒绝启动，且该密钥不会写入镜像。

Compose 运行 Flask 应用和内网 Qdrant 服务。SQLite 位于 `./data/app.db`，上传文件位于 `./uploads/`，Qdrant 位于命名卷 `openclaw_qdrant_data`；这些数据都不会因普通 `docker compose down` 删除。Qdrant 只加入 Compose 内网，不映射宿主机端口。应用入口会先初始化数据库，再等待 Qdrant（最多 `QDRANT_WAIT_SECONDS` 秒），随后由应用启动时 reconcile 缺失或失败索引。首次启动会自动创建数据库并写入演示种子。`.env` 中的 `TOKEN_HASH_SECRET` 只注入容器环境，不进入镜像构建上下文或 Git；不要提交或分享 `.env`。

查看启动日志：`docker compose logs -f app`。停止应用但保留数据：

```powershell
docker compose down
```

再次执行 `docker compose up -d` 后，预置账号和已上传材料应仍然存在。不要运行 `docker compose down -v`；不要删除 `data/` 或 `uploads/`，否则会删除持久化数据。若 `8080` 已被占用，将 `.env` 的 `WEB_PORT` 改为 `8081`，地址相应改为 `http://localhost:8081/login`。

权限与隔离约定：`/materials` 未登录时仍可返回不含业务数据的页面壳，页面随后因 `/api/me` 的 `401` 清除会话 Token 并跳转 `/login`；未登录或过期/撤销 Token 的 API 返回 `401`（带 `WWW-Authenticate: Bearer`）；角色不足返回 `403`；跨班材料 ID 访问统一返回 `404`，响应不包含他班标题、正文或存储路径。

### Compose 验收

在 Ubuntu 虚拟机中可运行下面的脚本，自动检查健康检查、三名预置用户 Bearer 登录、无认证 Cookie、双班列表隔离、三种检索模式、向量阈值、带出处问答、无依据回答、教师上传、学生 `403`、跨班 `404`、登出撤销、旧 Cookie `401`、页面壳不泄露 Token、Qdrant 不暴露宿主端口以及 `down` 后重新 `up` 的 Token 表、索引和材料持久化。脚本会在本班留下一个标题为 `Compose验收-时间戳` 的测试材料：

```bash
cd ~/projects/OpenClaw
dos2unix scripts/verify_compose.sh 2>/dev/null || true
bash scripts/verify_compose.sh
```

脚本只执行 `docker compose down`，不会使用 `-v`，不会删除 `data/` 或 `uploads/`。
