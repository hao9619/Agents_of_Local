---
name: background-subagent
description: Use when the user explicitly requests background execution or asks to inspect, stop, or resume an existing background task.
---

# 后台任务

在 Claude Code 中，共用规则里的 Codex 指当前执行助手；监督选择同样适用。模型、推理强度、工具和后台生命周期以当前 Claude Code 实际能力为准，不要调用 Codex 专用工具或照搬其模型名、fork_turns 等参数。未确认后台持续执行能力时，不承诺回复结束后仍会运行。

执行前读取[共用后台任务规范](../../../.agents/skills/background-subagent/SKILL.md)，并按该文件所在目录解析其配套文档链接。普通前台任务耗时较长不触发后台执行。
