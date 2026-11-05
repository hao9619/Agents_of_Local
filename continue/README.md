# 精简 Agent 规则模板

`rules/local-agent.md` 是通用精简版，供两台电脑复用。它保留范围、授权、验证、上下文控制和交接要求；不是其他项目长篇 AGENTS.md 的逐条等价替代，不包含其专有服务器、命令、资源或验收标准。

## 在 Continue 中使用

把模板复制到目标工作区的 `.continue/rules/local-agent.md`。例如，在本项目根目录运行以下命令，仅在目标不存在时创建：

```powershell
New-Item -ItemType Directory -Force .\.continue\rules | Out-Null
if (Test-Path .\.continue\rules\local-agent.md) { throw '目标规则已存在，请先核对内容' }
Copy-Item .\continue\rules\local-agent.md .\.continue\rules\local-agent.md
```

在 Continue 输入框上方的规则入口检查是否启用，然后新建会话验证。规则格式采用 [Continue 官方 Markdown 规则格式](https://docs.continue.dev/customize/deep-dives/rules)。当前模板仅保存在仓库普通目录 `continue/`，没有自动启用，避免与现有规则重复注入。

## 如何真正减少系统提示词

**增加短规则不会自动替换或屏蔽已有 AGENTS.md。** 若目标工作区仍自动加载长规则，两份会同时占用上下文。

需要精简已有项目时，先保留原文并核对专有要求，将常驻入口缩为必要约束和详细文档索引，细节放入项目现有文档目录，相关操作发生时再读取。具体的写入边界、服务器授权、验收标准及禁止事项不能因缩短而删除。避免把同一份完整规则同时放进 AGENTS.md 和 `.continue/rules/`。

本次仅新增可复用模板与说明，没有修改另一个项目的 AGENTS.md、本项目协作入口或 Continue 用户配置。模板的实际 token 数依模型分词器而异，不能用字符数当作 token 数。
