# Spec Delta

## Purpose

为课堂演示和回归验收提供可发现、可试调且可重复执行的 API 合约，使认证、班级隔离、提示词/技能、会话流式回答及数据库持久化都能被自动核对。

## ADDED Requirements

### Requirement: 主要 API 提供 OpenAPI 与 Swagger 入口

系统 MUST 提供机器可读的 OpenAPI 描述和浏览器可打开的 Swagger UI。描述 MUST 列出登录、Bearer 认证、提示词和技能管理、知识检索、会话、消息流式响应及错误码；每个受保护路径 MUST 明确要求 `Authorization: Bearer <token>`，请求参数、成功响应、鉴权失败、权限不足、资源不可见和服务不可用响应 MUST 可在文档中查到。Swagger UI MUST 能对主要接口发起试调而不要求把服务端 API 密钥暴露给浏览器。

#### Scenario: 浏览器打开并试调 Swagger
- **WHEN** 用户打开 Swagger 页面并加载 OpenAPI 文档
- **THEN** 页面显示主要接口、参数、响应和认证说明
- **AND** 用户可以填写 Bearer Token 后试调健康检查、登录后的检索或会话接口

#### Scenario: OpenAPI 与实际认证一致
- **WHEN** 客户端按文档调用一个标记为受保护的路径且不带 Bearer Token
- **THEN** 服务返回 HTTP 401
- **AND** 文档没有把 Cookie 或 URL Token 描述为可替代认证方式

### Requirement: 接口测试按 URL 组织且核对持久化结果

仓库 MUST 提供 `apitest/` 目录，测试脚本按 URL 和 HTTP 方法组织（例如 `cases/api/login/POST.py`），并提供 `run_all.py` 一键执行入口。测试 MUST 至少覆盖登录、知识检索、提示词/技能管理、创建会话和发送一条消息；除 HTTP 状态码外，测试 MUST 核对响应字段、引用/事件内容与 SQLite 中的用户、配置、会话或消息状态一致。测试默认使用本机可配置的服务地址和演示账号，不得把真实密钥写入仓库。

#### Scenario: 一键测试生成本地报告
- **WHEN** 运行 `python apitest/run_all.py`
- **THEN** 测试按目录发现并执行所有接口脚本，失败项返回非零退出码
- **AND** 在本机生成 HTML 报告，报告路径可配置且报告文件不被 Git 跟踪

#### Scenario: 测试验证班级隔离与流式消息
- **WHEN** 接口测试以 A 班和 B 班 Token 分别检索并创建会话，再读取 SSE 消息事件
- **THEN** 测试确认 A 班响应不含 B 班材料，并确认完成事件中的消息和引用已写入数据库
- **AND** 测试确认学生越权修改提示词/技能时得到 403
