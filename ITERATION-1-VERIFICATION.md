# 迭代一验收记录

范围：第 3 课步骤 1–8，变更 `add-auth-rbac-class-knowledge`。

## 自动化与规约

| 项目 | 命令/证据 | 结果 |
| --- | --- | --- |
| 完整测试 | `C:\Users\long\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest -q` | 通过，19 passed |
| OpenSpec 严格校验 | `openspec validate add-auth-rbac-class-knowledge --strict` | 通过：`Change 'add-auth-rbac-class-knowledge' is valid` |
| Compose 配置校验 | Ubuntu VMware 首次 `docker compose up --build -d` 成功创建并启动服务；验收脚本随后成功执行 `docker compose down` / `up -d` | 通过：Compose 配置可解析，服务可以构建和重建 |
| 幂等初始化 | 空临时目录连续运行 `scripts/init_db.py` 两次，SQLite 计数为 `[users, materials, knowledge_entries] = [3, 2, 2]` | 通过 |
| 前端工作区 | `tests/test_frontend.py`：静态资源、`/api/me`、材料 API、教师上传入口和学生 403 回归 | 通过 |
| Compose 全链路脚本 | `bash scripts/verify_compose.sh`：健康检查、三账号登录、隔离、上传、403/404、down/up 持久化 | 通过：脚本输出 `Compose verification completed successfully.` |

## 关键 Scenario

| Scenario | 验证方式 | 结果 |
| --- | --- | --- |
| 未登录页面/API | `tests/test_auth.py`：页面 302、API 401，响应不含材料 | 通过 |
| 学生上传被拒绝 | `tests/test_upload.py`：学生上传返回 403，数据库和目录不变 | 通过 |
| 跨班按 ID 访问 | `tests/test_isolation.py`：A 班访问 B 班材料返回 404 且不泄露内容 | 通过 |
| 教师上传后入库 | `tests/test_upload.py`：返回 201，材料和知识库记录同班且文件存在 | 通过 |
| 上传失败清理 | `tests/test_upload.py`：非法格式、空文件、解析/数据库/移动失败均清理 | 通过 |
| 教师上传后本班可见 | `tests/test_upload.py`：教师和学生 A1 可见，学生 B1 不可见 | 通过 |
| 健康检查无需登录 | `tests/test_health.py`：无 Cookie 返回 200 和 `{"status":"ok"}` | 通过 |
| Compose 持久化 | `tests/test_persistence.py` 在应用重建并重跑初始化后验证预置用户可登录、上传材料可见；实际容器 `up -> down -> up` 仍需 Docker 复核 | 本地数据层回归通过，Compose 待 Docker 环境执行 |

用户已在 Ubuntu VMware 虚拟机完成首次 Compose 启动。首次日志发现容器入口缺少 Python 模块搜索路径，已在 `docker-entrypoint.sh` 和 `Dockerfile` 中固定 `PYTHONPATH=/app`。随后 `bash scripts/verify_compose.sh` 全部通过：`/health` 为 200；教师 A、学生 A1、学生 B1 均登录成功；A/B 班列表隔离通过；教师上传成功；学生上传返回 403；跨班 ID 访问返回 404；执行 `docker compose down` 后再次 `up -d`，教师仍能登录且上传材料仍在列表中。脚本留下了一条标题为 `Compose验收-时间戳` 的 A 班验收材料。

## 实现核对

- Compose 仅定义单一 `app` 服务，暴露宿主 `8080`，不暴露数据库端口。
- `./data` 和 `./uploads` 分别挂载到容器内持久化路径。
- `docker-entrypoint.sh` 启动时执行幂等的 `scripts/init_db.py`，然后启动 gunicorn。
- `.env.example` 只包含占位 `SECRET_KEY` 和 `WEB_PORT`，未提交真实密钥。
- 跨班资源统一按 `404` 处理，学生上传由服务端返回 `403`。
