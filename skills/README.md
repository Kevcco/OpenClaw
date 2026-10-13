# 教学技能包约定

技能由部署时随服务发布的目录提供，不接受普通 API 上传或改写。每个技能单独放在 `skills/<package>/`，包含 `skill.yaml` 和 `instructions.md`，可选 `scripts/` 仅登记为资源，本版本不导入或执行脚本。

`skill.yaml` 采用 JSON 语法（JSON 是 YAML 1.2 的子集），因此无需额外 YAML 解析器；元数据必须包含：

| 字段 | 含义 |
| --- | --- |
| `key` | 唯一稳定标识，只允许小写字母、数字和连字符 |
| `name` | 中文展示名称 |
| `version` | 包版本快照 |
| `summary` | 常驻上下文中的一句话简介 |
| `applicability` | `any_terms` / `all_terms` 匹配条件；匹配对象仅为最新问题 |
| `priority` | 命中时的优先级，数值越大越先加载 |
| `instruction_file` | 包内规范化相对路径，必须指向 UTF-8 指令文件 |
| `instruction_tokens` | 完整指令的保守成本声明，预算判断按此值进行 |

例如：

```json
{
  "key": "example-guidance",
  "name": "示例引导",
  "version": "1.0.0",
  "summary": "一句话说明适用能力。",
  "applicability": {"any_terms": ["示例", "解释"]},
  "priority": 50,
  "instruction_file": "instructions.md",
  "instruction_tokens": 200
}
```

加载器会拒绝缺字段、重复 JSON 键、重复技能标识、路径越界、无效 UTF-8 和空指令。启用技能的简介常驻；只把条件命中的完整指令按优先级和 key 顺序装入 `SKILL_INSTRUCTION_TOKEN_BUDGET`，超预算时跳过完整指令，不截断。改包时递增 `version`；对历史版本的说明以消息和审计快照为准。
