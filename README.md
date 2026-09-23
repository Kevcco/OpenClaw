# CampusClaw

- **价值主张**：面向中小学教研场景，把分散的教学材料沉淀为受身份、角色和班级边界保护的知识库基础。
- **核心场景**：教师和学生登录后查看本班材料，教师可上传教学材料并完成解析入库，学生保持只读。
- **本学期不做**：检索问答、AI 对话助手、技能运行时、作业提交与批改、注册与找回密码、SSO、多校多租户及生产级高可用。

## 本地开发

```powershell
$env:SECRET_KEY = "local-development-secret"
$env:DATABASE_PATH = "data/app.db"
$env:UPLOAD_DIR = "uploads"
python scripts/init_db.py
python run.py
```

打开 `http://127.0.0.1:8080/login`。预置账号为 `teacher_a / teacher_a_pass`、`student_a1 / student_a1_pass` 和 `student_b1 / student_b1_pass`。

## Docker Compose

### Ubuntu / VMware Linux

在已安装 Docker Engine 与 Compose 插件的 Ubuntu 虚拟机中，建议从 Ubuntu 本地工作副本运行（VMware HGFS 共享目录权限可能影响 Docker 构建）：

```bash
cd ~/projects/OpenClaw
cp .env.example .env
secret="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=${secret}/" .env
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
$secret = py -c "import secrets; print(secrets.token_hex(32))"
@("SECRET_KEY=$secret", "WEB_PORT=8080") | Set-Content -Encoding ascii .env
docker compose config
docker compose up --build -d
docker compose ps
```

打开 `http://localhost:8080/login`；健康检查地址是 `http://localhost:8080/health`，应返回 `{"status":"ok"}`。教师账号为 `teacher_a / teacher_a_pass`，学生账号为 `student_a1 / student_a1_pass` 与 `student_b1 / student_b1_pass`。

Compose 以单个 Flask 应用容器运行，SQLite 位于 `./data/app.db`，上传文件位于 `./uploads/`；两个目录均绑定挂载到主机。首次启动会自动创建数据库并写入演示种子。`.env` 中的随机 `SECRET_KEY` 只注入容器环境，不进入镜像构建上下文或 Git；不要提交或分享 `.env`。

查看启动日志：`docker compose logs -f app`。停止应用但保留数据：

```powershell
docker compose down
```

再次执行 `docker compose up -d` 后，预置账号和已上传材料应仍然存在。不要运行 `docker compose down -v`；不要删除 `data/` 或 `uploads/`，否则会删除持久化数据。若 `8080` 已被占用，将 `.env` 的 `WEB_PORT` 改为 `8081`，地址相应改为 `http://localhost:8081/login`。

权限与隔离约定：未登录页面返回 `302` 到 `/login`，未登录 API 返回 `401`；学生上传返回 `403`；跨班材料 ID 访问统一返回 `404`，响应不包含他班标题、正文或存储路径。

### Compose 验收

在 Ubuntu 虚拟机中可运行下面的脚本，自动检查健康检查、三名预置用户登录、双班列表隔离、教师上传、学生 `403`、跨班 `404` 以及 `down` 后重新 `up` 的持久化。脚本会在本班留下一个标题为 `Compose验收-时间戳` 的测试材料：

```bash
cd ~/projects/OpenClaw
dos2unix scripts/verify_compose.sh 2>/dev/null || true
bash scripts/verify_compose.sh
```

脚本只执行 `docker compose down`，不会使用 `-v`，不会删除 `data/` 或 `uploads/`。
