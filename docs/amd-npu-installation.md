# AMD 纯 NPU：把本项目的工具接进 Continue

适用于已有 Windows 11、Ryzen AI NPU、Lemonade 和 FastFlowLM 的电脑。下面以 `qwen3.5-9b-FLM` 为例。若当前用 4B，将所有模型名替换为 `qwen3.5-4b-FLM`。

Continue 用 Lemonade 的 OpenAI 兼容接口聊天，自研工具用同一个 Lemonade 服务的 Ollama 兼容流式接口生成文件。两个入口都指向本机，纯 NPU 由 FLM 模型及后端决定。本文的接入已用兼容响应测试，AMD 实机仍需按下文完成验收。 [Lemonade 的 Ollama 兼容接口](https://lemonade-server.ai/docs/api/ollama/)

## 1. 检查 AMD 电脑上的模型

在 AMD 电脑打开 PowerShell，先检查 Lemonade 和模型列表：

```powershell
lemonade status
lemonade list | Select-String 'qwen3.5-(4b|9b)-FLM'
```

如果缺少 FLM 后端或模型，按需执行：

```powershell
lemonade backends install flm:npu
lemonade pull qwen3.5-9b-FLM
```

以 8K 上下文加载。如果当前同一个模型用其他上下文加载过，先执行 `lemonade unload qwen3.5-9b-FLM` 再加载：

```powershell
lemonade load qwen3.5-9b-FLM --ctx-size 8192
```

用短请求确认 **自研工具要调用的接口**可用：

```powershell
$probe = @{
    model = 'qwen3.5-9b-FLM'
    stream = $false
    messages = @(@{ role = 'user'; content = 'Reply with READY.' })
    options = @{ num_predict = 128 }
} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Uri 'http://127.0.0.1:13305/api/chat' -Method Post -ContentType 'application/json' -Body $probe
```

成功时会返回包含 `message` 的 JSON。若此接口返回 404 而 Continue 的聊天能用，先核对 Lemonade 版本是否提供 `/api/chat`，更新后再试。

## 2. 注册仓库工具

用 Cursor 打开新克隆或更新后的项目根目录。确认 Python 3.11+ 和 Continue 扩展已安装，在该目录执行：

```powershell
python -m venv .local/continue-mcp
& ./.local/continue-mcp/Scripts/python.exe -m pip install -r requirements-mcp.txt
& ./.local/continue-mcp/Scripts/python.exe local_artifacts.py --configure --api-base http://127.0.0.1:13305 --model qwen3.5-9b-FLM
```

第三条命令生成本机的 `.continue/mcpServers/local-artifacts.local.yaml`，将工具内部的地址和模型绑定到 Lemonade。以前已装过依赖时可直接执行第三条。

## 3. 选择 Continue 的纯 NPU 模型

如果 Continue 里已能选到正确的 FLM 模型，可直接使用。需要新增时，把下面的条目合并进 `%USERPROFILE%\.continue\config.yaml` 中已有的 `models:` 列表：

```yaml
  - name: Ryzen 纯 NPU 9B
    provider: openai
    model: qwen3.5-9b-FLM
    apiBase: http://127.0.0.1:13305/api/v1
    apiKey: local
    roles: [chat, edit, apply]
    capabilities: [tool_use]
    defaultCompletionOptions:
      contextLength: 8192
      maxTokens: 4096
      temperature: 0.2
```

`apiKey: local` 适用于未启用鉴权的本机 Lemonade。这个条目决定 Continue 聊天使用的模型，上一节的命令决定 Python 工具内部使用的模型。

## 4. 验收

1. 在 Cursor 执行 **Developer: Reload Window**。
2. 打开 **Continue → Tools → MCP Servers**，确认 `local-artifacts` 在线。
3. 新建 Continue Agent 会话，选中 FLM 模型，发送下面的请求。若有工具卡片，核对名称后批准。

```text
请调用 generate_html_file，生成显示 AMD MCP READY 的简单 HTML。
文件名使用 amd-mcp-check.html，返回工具结果。
```

以工具返回 `saved` 且 `.local/artifacts/amd-mcp-check.html` 存在为通过。若 Continue 能聊天但工具报连接或模型错误，先检查第 1 节的短请求，再核对第 2 节生成的配置。

资料、任务进度和实验文件都存放在各自电脑的 `.local/` 下。换机时按需复制 Markdown/TXT 资料。知识库和多轮状态的使用见 [Continue 工具教程](continue-installation.md#6-使用本地知识库)。

## 5. 排查 MCP 请求超时

如果生成 HTML 时提示 `MCP error -32001: Request timed out`，尤其是约一分钟就报错，先更新项目源码，再在项目根目录重新注册工具。已有 AMD 地址、模型和知识库配置时，直接运行以下命令即可保留这些设置。

```powershell
& ./.local/continue-mcp/Scripts/python.exe local_artifacts.py --configure
```

执行 **Developer: Reload Window**，确认 `local-artifacts` 在线。新配置让 Continue 等待工具最多 15 分钟。先按上一节跑简短的 HTML，再用新文件名重试长任务。如果简短测试仍失败，核对 `lemonade status`、第 1 节的 `/api/chat` 探测结果和 Continue 扩展版本。
