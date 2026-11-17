<!-- BEGIN local-agent-guides -->
## 本项目通用协作规则

以下路径相对于本入口文件所在目录。用户明确要求及本项目具体约定优先于引用文档中的默认建议。

- 开始或恢复工作时，读取 [文档与目录规范](.agents/skills/background-subagent/documentation.md) 中的多层项目安装与会话交接规则，再读本目录现有状态入口，核对用户指定的会话角色、职责、活动任务及文件负责人。未被用户指定时不得自称主会话；缺少交接信息时不编造。文档和目录维护也遵循该规范。
- 在通过 GitHub 多机接续的项目首次接入或规则变化时，读取 [Git 与多机接续规范](.agents/skills/background-subagent/git-multicomputer-workflow.md)，后续复用并按需查阅。将代码、必要证据和当前进展在工作过程中写入根仓库可收录的位置，结束前核查本轮增量；不等用户要求再整理，不把干净状态当作已经同步。沿用一个主分支，Git 暂存、提交和推送默认由用户执行。
- 创建任何辅助会话前，读取 [子代理模型与交接规则](.agents/skills/background-subagent/codex-subagent-model-selection.md)，向用户说明任务和监管建议，等待用户选择自己监管或 Codex 监管；已明确的同一任务选择无需重复询问。
- 根目录已授权按需配置子目录时，在实际进入子目录工作或准备交接前检查其入口。使用 [安装工具](.agents/skills/background-subagent/install_agent_docs.py) 的 --workspace 根目录 --project 目标子目录，先 --dry-run 再执行。只处理本轮可写范围，保留已有约定；不递归安装、不自动使用 --overwrite、不创建会话。规则入口未准备好的独立目录，应由已有规则的会话先配置，再由用户开启主会话。
- 用户明确要求后台执行，或查询、停止、恢复已有后台任务时，使用 [background-subagent 技能](.agents/skills/background-subagent/SKILL.md)，并核对当前环境的执行能力与权限。普通任务耗时较长不自动触发后台执行。
<!-- END local-agent-guides -->
