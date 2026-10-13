# Proposal

## Why

第 4 课已提供受 Bearer Token 保护的本班检索、来源引用和单次问答，但尚无可连续追问且可持久化的学生会话，也没有由教师管理、参与每轮回答的提示词和技能。本课把这些现有基础连接成可演示的解题助手，并以流式反馈、接口文档和可重复的接口测试完成验收。

## What Changes

- 为每个班级增加教师管理的助手提示词和解题引导技能设置；设置从后续回答轮次生效，学生不能查看或修改这些管理项。
- 增加按登录用户和班级隔离的持久化对话与消息；学生可创建会话、查看自己的历史并连续追问。
- 每轮助手回答固定执行“读取当前班级配置、应用启用技能、按最新问题检索本班知识、基于证据生成回答”；引用须定位到材料及切片，缺少依据时明确说明且不调用回答模型。
- 为会话消息提供带 Bearer 认证的 SSE 增量回答；保留第 4 课单次问答和检索能力，并使其使用同一套提示词、技能与知识依据规则。
- 提供可浏览和试调主要接口的 OpenAPI/Swagger 文档，以及按 URL 组织的 `apitest/` 接口测试和一键 HTML 报告生成流程；报告不提交到 Git。
- 本课只交付一个教师可维护的“解题引导”技能；不引入多技能自动选择、工具调用/MCP、作业流程、异步队列或关怀式对话。

## Capabilities

### New Capabilities

- `guided-solution-sessions`: 教师管理的提示词与解题引导技能、带来源依据的本班助手流程、用户隔离的持久化会话及 SSE 消息响应。
- `api-contract-testing`: 主要 HTTP API 的 OpenAPI/Swagger 描述、交互式试调入口及核对响应和数据库状态的接口回归测试。

### Modified Capabilities

- `traceable-vector-retrieval`: 扩展现有单次问答，使其服从班级提示词与解题引导技能，同时保持 Bearer 认证、检索班级隔离、来源引用、无依据拒答及原响应兼容。

## Impact

预计影响 `app/db.py`、`app/answer.py`、`app/retrieval_routes.py`、新助手/会话路由、材料工作区模板和脚本、SQLite schema、OpenAPI/Swagger 文档、pytest 与新增 `apitest/` 测试目录、依赖/配置说明及 `.gitignore`。需要为助手设置、会话与消息增加持久化结构；现有 Bearer Token 认证和第 4 课的 SQLite/Qdrant 知识检索继续复用。真实 AI 服务仍由服务端环境变量配置，密钥不得进入浏览器、测试报告或 Git。
