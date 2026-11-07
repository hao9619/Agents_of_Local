# 从源码接入 Cursor 的 Continue

这份教程适用于 Windows。完成后，你可以在 Cursor 的 Continue Agent 会话中调用仓库里的 Python 工具 `generate_html_file`。Continue 启动本地 MCP 进程，Python 调用 Ollama，再把生成结果保存到项目的 `.local/artifacts/`。

## 1. 准备源码和编辑器

克隆仓库或解压源码，用 Cursor 的 **File → Open Folder** 打开含 `README.md` 和 `local_artifacts.py` 的项目根目录。安装 **Continue** 扩展，扩展 ID 为 `Continue.continue`。安装 Python 3.11 或更新版本，并在项目根目录的 PowerShell 中确认 `python --version` 可用。

下面的 PowerShell 命令都从项目根目录执行。下载运行包、模型和 Python 依赖需要网络，之后的文件生成请求发送到本机。

## 2. 启动 Ollama 并准备模型

工具访问 `http://127.0.0.1:11435`。如果该端口已经运行 Ollama，先检查模型列表：

```powershell
Invoke-RestMethod 'http://127.0.0.1:11435/api/tags' | Select-Object -ExpandProperty models | Select-Object name
```

首次部署、且使用项目独立运行包时，按 [README 快速开始](../README.md#quick-start) 安装运行环境。RTX 4060 路线的命令如下：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-runtime.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

保持启动服务的终端开启。项目脚本把模型存放在 `.local/models`，模型列表以 **当前监听 11435 的服务**为准。已经在其他 Ollama 服务下载过的模型，可能在另一个模型库里。AMD 的 Ollama 安装与驱动准备见 [Ryzen 部署指南](ryzen-deployment.md)。

在另一个 PowerShell 窗口准备 **4B**，作为新机器的起步选项：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

该脚本创建 `local-coder-4060`。如果使用已经下载的 9B 或自己的模型，记下 11435 模型列表中显示的模型名，后续填入两处配置。

## 3. 让 Continue 能调用本地模型

打开用户目录的 Continue 配置：

```powershell
notepad "$env:USERPROFILE\.continue\config.yaml"
```

空配置可使用下面的完整示例。已有配置时，将模型条目合并到现有 `models:` 列表。

```yaml
name: Local Coding
version: 0.0.1
schema: v1
models:
  - name: Local Coder
    provider: ollama
    model: local-coder-4060
    apiBase: http://127.0.0.1:11435
    roles: [chat, edit, apply]
    capabilities: [tool_use]
    defaultCompletionOptions:
      contextLength: 8192
      maxTokens: 4096
      temperature: 0.2
      reasoning: false
```

使用 9B 时，将 `model` 改为对应的已安装模型，例如 `local-coder-4060-9b`。仓库中的 [配置模板](../continue/config.yaml) 也可作为参考。

## 4. 注册项目的 Python MCP 工具

```powershell
python -m venv .local/continue-mcp
& ./.local/continue-mcp/Scripts/python.exe -m pip install -r requirements-mcp.txt
& ./.local/continue-mcp/Scripts/python.exe local_artifacts.py --configure
```

最后一条命令生成 `.continue/mcpServers/local-artifacts.local.json`。其中 `command` 指向虚拟环境的 Python，`args` 指向仓库的 `local_artifacts.py`。这两个值包含当前电脑的绝对路径，所以每台电脑分别生成配置。换目录后重新生成，并重新应用自定义 `env`。

**关键一步：工具自己的生成模型需要单独配置。** 当前工具默认用 `local-coder-4060-9b`，而上面的 4B 安装流程创建的是 `local-coder-4060`。使用 4B 时，打开生成的 JSON，在 `mcpServers` → `local-artifacts` 下、与 `command` 和 `args` 平级添加：

```json
"env": {
  "LOCAL_ARTIFACT_MODEL": "local-coder-4060"
}
```

在相邻属性间保留 JSON 的逗号，保留生成的 `command` 和 `args`。如果使用工具的默认 9B 别名，生成后的配置可直接使用。Continue 下拉菜单选择的是**负责决定何时调用工具的模型**，而此处指定的是**工具内部负责生成 HTML 的模型**。二者可以用同一个模型。

## 5. 在 Cursor 验收

1. 在命令面板执行 **Developer: Reload Window**。
2. 打开 **Continue** 面板，进入 **Tools → MCP Servers**，确认 `local-artifacts` 在线并列出 `generate_html_file`。
3. 使用 **Continue: New Session** 新建会话，选择刚配置的本地模型，切到 **Agent** 模式。
4. 发送下面的测试请求。如果出现工具批准卡片，核对工具名称后点击 **Accept**。

```text
请调用 generate_html_file，创建一个显示 LOCAL MCP READY 的单文件 HTML，
文件名为 continue-smoke-test.html。完成后报告工具返回的路径。
```

工具卡片成功且 `.local/artifacts/continue-smoke-test.html` 存在，即可确认链路打通。聊天正文有时不会复述路径，可以通过工具结果和实际文件检查。再试鹈鹕任务时，使用新文件名，例如 `pelican-local.html`。

工具还接受可选的 `references` 字符串列表。将最重要的资料片段放在前面，工具会在给输出留足预算后选入可容纳的片段。`context.included_references` 和 `context.omitted_references` 按传入顺序从 1 编号。

## 6. 使用本地知识库

在项目根目录建立 `.local/knowledge/`，将资料保存为 UTF-8 的 `.md` 或 `.txt`。工具查询时会扫描该目录及子目录。首版使用词项匹配，单文件最多 128 KiB，每次返回最多三个片段。查询中带上文档中的专用名词通常更容易命中。

如要用其他目录，在生成的 `.continue/mcpServers/local-artifacts.local.json` 中，给 `local-artifacts` 对象的 `env` 添加 `"LOCAL_KNOWLEDGE_DIR": "D:/my-knowledge"`，再重载 Cursor。相对路径从项目根目录解析。

在 Continue Agent 中先试检索，再试带资料生成：

> 请调用 search_knowledge，查询“鹈鹕 发布标识”，并给出文件名与行号。

> 请调用 generate_html_file，文件名用 release-page.html，knowledge_query 用“鹈鹕 发布标识”。生成一个显示资料中发布标识的 HTML 页面。

带资料生成的工具结果会列出 `knowledge_sources`，每项包含文件、行号及是否进入本轮上下文。没有检索命中时返回 `knowledge_no_match`。有命中但预算不足时，`included` 会标为 `false`，可以据此调整查询或缩短资料。若本次复用已有产物，`included` 为 `null`，因为没有重新生成。

## 7. 跨会话继续任务

在 Continue 的 Agent 模式中，先用 `start_task` 保存原始要求和按顺序排列的步骤，记下返回的 `task_id`：

> 请用 start_task 建立任务。原始要求是生成单文件 HTML，画出有明显长嘴和喉囊的鹈鹕骑自行车。步骤为「拟定 SVG 结构」「生成并保存动画」。

完成一个步骤后，调用 `complete_task_step`，传入 `task_id`、从 1 开始的 `step_number` 和简短 `note`。工具返回 `next_step` 指向第一个未完成步骤。生成 HTML 时把 `task_id` 一起传给 `generate_html_file`，Python 会把保存的原要求加入本次上下文，并记录这次实际成功或失败的返回。生成结果和步骤完成是两个操作，确认任务要求满足后再标记步骤完成。

新建 Continue 会话后，可以这样恢复：

> 请调用 resume_task，读取任务 ID 为「这里填实际 ID」的任务，先告诉我原始要求、已有文件结果和下一步，再从未完成的步骤继续。

如果忘了 ID，可以先调用不带参数的 `resume_task`，查看最近十条任务。带 ID 的结果会返回原始要求、各步骤、最近六条文件工具结果和结果总数。数据库保存在仓库的 `.local/task-state.sqlite3`。这套状态可跨本机 MCP 重启和 Continue 会话，当前由用户或 Agent 显式建立和恢复任务。

## 常见问题

| 现象 | 检查 |
| --- | --- |
| Tools 列表没有服务 | 确认打开的是仓库根目录，生成文件位于该目录下的 `.continue/mcpServers/`，再重载 Cursor |
| MCP 服务离线 | 检查 JSON 里的 Python 和脚本路径，在对应虚拟环境执行 `python -m pip show mcp` 确认 SDK 已安装 |
| 工具报告连接失败或找不到模型 | 查询 11435 的 `/api/tags`，核对工具的 `LOCAL_ARTIFACT_MODEL`；Continue 模型选对并不会替工具切换模型 |
| 模型只输出 HTML | 核对 Agent 模式、工具可见性和批准卡片。可在请求中明确写出 `generate_html_file` |
| 返回 `truncated` 或 `degeneration` | 前者触及输出限制，后者在一次自动重试后仍出现复读。展开工具结果的 `attempts` 可查看各轮原因。先用更短的任务验证 |
| 返回 `context_overflow` | 任务正文超出保守估算的输入预算，尚未发起推理。缩短任务，或把可省略的资料放进 `references` |
| 返回 `reused` 或 `conflict` | 同一请求已保存则复用，目标已有不同结果则保留原文件。新实验用新文件名 |

## 接入自己的下一项能力

在 [local_artifacts.py](../local_artifacts.py) 找到 `@server.tool()`。这个装饰器把普通 Python 函数暴露给 Continue，函数的参数类型和说明形成模型可见的工具描述。新增能力后，重载窗口，在 Tools 页面确认工具，再用一个最小任务验证。Continue 的配置方式见 [MCP 文档](https://docs.continue.dev/customize/deep-dives/mcp)。

仓库保存工具源码、依赖清单与验证记录。虚拟环境、权重、实验产物和带绝对路径的本机 MCP 配置由安装者本地生成。已有测试记录见 [Cursor 接入验证](evidence/2026-11-07-continue-mcp-verification.json) 和 [退化检测验证](evidence/2026-11-07-generation-guard-verification.json)。
