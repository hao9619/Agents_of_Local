
我想在本地部署大模型，要求如下：一、硬件配置：两台win11电脑，一台为AI9 H 365芯片（集显无独显）+32GB内存（8000MHz+），一台为i7 13620H（集显）+4060Laptop（8GB显存）+32GB内存（5200MHz），这两台各部署一个。二、要求：1. 部署的本地模型能够被cursor调用为agent提供模型，具体调用方式是API还是啥暂未知，需要你调研一下。2. 我能通过代码设置模型的上下文等参数或设计模型的模块，代码和模块简单易懂，方便我学习以及后续自定义。请你看看有没有方法满足以上要求  

我会先核实 Cursor 目前接入自建模型的方式和 Agent 模式限制，再按两台机器的内存、显存分别选可运行的模型与部署方案。也会给你一份便于改上下文参数、提示词和工具逻辑的简单代码结构。
```
• Searched the web for site:docs.cursor.com custom API keys OpenAI base URL agent mode local models, site:docs.cursor.com advanced models override …
• Searched the web for Cursor documentation API keys override OpenAI base URL local Ollama Agent custom model 2026, site:docs.cursor.com "Override …
```
查到一个关键限制：Cursor 的自定义模型请求仍经过 Cursor 服务器，因此它不能直接访问你电脑上的 `localhost` 或局域网地址。要用 Cursor 自带 Agent，模型 API 需要一个外部可访问的 HTTPS 地址；这也意味着整个流程不能算完全离线。我继续核对适合两台机器的模型和可控参数。
```
• Searched the web for site:qwenlm.github.io Qwen3.5 4B 9B coding tool calling context, site:huggingface.co/Qwen Qwen3.5-9B model card GGUF context…
• Searched the web for site:docs.ollama.com "Modelfile" "PARAMETER num_ctx", site:docs.ollama.com/openai OpenAI compatibility Ollama api, site:docs…
• Opened https://docs.ollama.com/modelfile
• Searched the web for site:docs.continue.dev Cursor IDE extension local ollama agent mode config yaml, site:docs.continue.dev "Cursor" "Continue" …
• Searched the web for Continue extension Cursor IDE install official documentation, site:docs.continue.dev Cursor install Continue extension, site…
• Searched the web for site:docs.cline.bot Ollama local models Cursor extension provider context window tool use, site:docs.cline.bot "Cursor" exte…
• Searched the web for site:docs.ollama.com/gpu AMD Ryzen AI 9 365 Radeon 880M Windows Vulkan, site:github.com/ollama/ollama Radeon 880M Ryzen AI 9…
```
目前有两条可行路线：一条是让 Cursor 自带 Agent 走 HTTPS 隧道调用本机模型，但兼容性要实测；另一条是在 Cursor 编辑器里用支持本地 Ollama 的 Agent 扩展，配置更直接，也更适合学习和改模块。我会把两条路线的取舍和最小配置写清楚。
```
• Searched the web for site:docs.cline.bot "Running Models Locally" Ollama, site:docs.cline.bot/provider-config/ollama, site:docs.cline.bot "Ollama…
• Searched for 'contextLength'
• Searched the web
• Searched the web for site:docs.continue.dev/guides "Run Continue Without Internet" local ollama, site:docs.continue.dev "rules:" "Agent" config.y…
• Searched the web for site:docs.continue.dev "~/.continue/config.yaml" IDE extension, site:docs.continue.dev "~/.continue/configs/config.yaml", si…
```
可以满足你的主要目标，但要区分两种“在 Cursor 里用”：

| 方式 | 能否调用本机模型 | 是否使用 Cursor 自带 Agent | 适合程度 |
|---|---|---|---|
| **在 Cursor 中安装 Continue 扩展** | 可以，直接连接本机 Ollama | 使用 Continue 的 Agent | **建议先用这条**：配置直观，方便改参数和规则 |
| Cursor 自带 Agent + 自定义 API | 原理上可以 | 是 | 需要把本机 API 经带鉴权的 HTTPS 入口提供给 Cursor；目前还有兼容性问题 |

关键原因是：Cursor 官方说明，自带 Agent 的请求会经过 Cursor 服务器组装提示词；Cursor 社区支持人员也明确表示，它不能直接连接本机 `localhost`，需要外部可访问的 HTTPS 地址。此外，Cursor 曾确认自定义地址接 Ollama 时存在 Agent 请求丢失 `model` 字段的问题。因此**不能保证仅填入一个 Ollama 地址，就能稳定驱动 Cursor 自带 Agent**。Cursor Tab 补全也不使用自带的 API 密钥。[Cursor 官方说明 (https://prod.cursor.com/help/models-and-usage/api-keys)](<https://prod.cursor.com/help/models-and-usage/api-keys>)、[本地模型连接说明 (https://forum.cursor.com/t/how-can-i-use-a-local-llm-on-my-desktop-ai-computer/152419)](<https://forum.cursor.com/t/how-can-i-use-a-local-llm-on-my-desktop-ai-computer/152419>)、[Agent 兼容性问题 (https://forum.cursor.com/t/gent-mode-with-openai-base-url-override-sends-request-without-model-model-is-required/160070/5)](<https://forum.cursor.com/t/gent-mode-with-openai-base-url-override-sends-request-without-model-model-is-required/160070/5>)

### 两台电脑怎么选模型

| 电脑 | 建议起步模型 | 理由 |
|---|---|---|
| Ryzen AI 9 365、32 GB、无独显 | `qwen3.5:9b-q4_K_M` | 模型文件约 6.6 GB，可利用系统内存；先从 **16K 上下文**试起。集显加速效果需以实际驱动和 `ollama ps` 为准。 |
| i7-13620H、RTX 4060 Laptop 8 GB、32 GB | `qwen3.5:4b-q4_K_M` | 模型文件约 3.3 GB，给上下文和运行开销留出显存。9B 文件约 6.6 GB，在 8 GB 显存下运行较长上下文容易挤出显存。 |

这两个模型都有工具调用能力。模型标称支持 256K 上下文，**不代表这两台机器适合开到 256K**；上下文越长，占用的内存或显存越多。4B 的多步骤改代码能力也可能不稳定，适合先用小任务验证。[Ollama 模型规格 (https://ollama.com/library/qwen3.5/tags)](<https://ollama.com/library/qwen3.5/tags>)、[Ollama 上下文说明 (https://docs.ollama.com/context-length)](<https://docs.ollama.com/context-length>)、[Windows 与显卡支持 (https://docs.ollama.com/windows)](<https://docs.ollama.com/windows>)

### 推荐的最小部署

两台 Windows 11 都安装 [Ollama (https://docs.ollama.com/windows)](<https://docs.ollama.com/windows>)。分别下载上述模型：

```
# Ryzen 电脑
ollama pull qwen3.5:9b-q4_K_M

# RTX 4060 电脑
ollama pull qwen3.5:4b-q4_K_M
```

每台电脑各建一个 `Modelfile`，下面以 Ryzen 电脑为例；RTX 电脑只需把第一行换成 `FROM qwen3.5:4b-q4_K_M`：

```
FROM qwen3.5:9b-q4_K_M
PARAMETER num_ctx 16384
PARAMETER temperature 0.2
```

然后在该文件所在目录运行：

```
ollama create local-coder -f .\Modelfile
ollama run local-coder
ollama ps
```

`num_ctx` 控制实际分配的上下文窗口，`temperature` 控制输出随机性。如果 RTX 电脑显存不够，先把 `num_ctx` 降到 `8192`，重新执行 `ollama create`。`ollama ps` 可以查看模型运行在 GPU 还是 CPU。[Modelfile 参数文档 (https://docs.ollama.com/modelfile)](<https://docs.ollama.com/modelfile>)、[检查模型运行位置 (https://docs.ollama.com/context-length)](<https://docs.ollama.com/context-length>)

接着在 Cursor 中安装 **Continue 扩展**，将 `%USERPROFILE%\.continue\config.yaml` 设为：

```
name: Local Coder
version: 0.0.1
schema: v1

models:
  - name: Local Coder
    provider: ollama
    model: local-coder
    apiBase: http://127.0.0.1:11434
    roles: [chat, edit, apply]
    capabilities: [tool_use]
    defaultCompletionOptions:
      contextLength: 16384
      maxTokens: 2048
      temperature: 0.2
```

在 Continue 面板选这个模型和 **Agent** 模式即可。这里的 `contextLength` 要与 `Modelfile` 中的 `num_ctx` 保持一致；`maxTokens` 是单次回答的输出上限。Continue 官方提供了 Ollama 接入、Agent 工具调用和 YAML 配置说明。[Continue 配置位置 (https://docs.continue.dev/customize/deep-dives/configuration)](<https://docs.continue.dev/customize/deep-dives/configuration>)、[Ollama 接入指南 (https://docs.continue.dev/guides/ollama-guide)](<https://docs.continue.dev/guides/ollama-guide>)、[配置字段 (https://docs.continue.dev/reference)](<https://docs.continue.dev/reference>)

### 你能自定义到什么程度

这套配置可以清楚地分成几层：

1. **模型运行层**：用 `Modelfile` 调上下文、温度、基础模型。
2. **Agent 层**：用 `config.yaml` 选模型、设置输出长度、启用工具调用。
3. **行为规则层**：在项目的 `.continue/rules/` 下写 Markdown 文件，规定代码风格、工作步骤等。
4. **工具层**：以后可通过 MCP 增加你自己写的工具或服务。[Continue 规则 (https://docs.continue.dev/customize/deep-dives/rules)](<https://docs.continue.dev/customize/deep-dives/rules>)、[Agent 自定义 (https://docs.continue.dev/ide-extensions/agent/how-to-customize)](<https://docs.continue.dev/ide-extensions/agent/how-to-customize>)

如果“设计模型的模块”指**修改神经网络层或训练模型本体**，上述配置做不到；那属于训练或微调工程。若你的意思是设计提示词、项目知识、工具和 Agent 工作流程，上面这套就合适。

\*\*建议先在两台机器分别跑通 Ollama → Continue Agent → 一个简单的读文件、改文件任务。\*\*如果你必须使用 _Cursor 自带_ Agent，再测试“带鉴权的 HTTPS 入口 + Cursor 的 OpenAI Base URL Override”；这条路线目前应按实验方案看待，且请求会经过 Cursor 服务器，不能算全程本地。
```
  Worked for 2m 22s • 6:24 AM
```
这个项目能通过git，让别人快速复现吗？  

可以。**Git 仓库能让别人快速复现部署流程**：克隆仓库后，选择对应电脑的配置、下载模型、启动 Ollama，再把 Continue 配置导入 Cursor。模型权重通常单独下载，不放进 Git。

建议仓库这样组织：

```
local-coder/
├─ profiles/
│  ├─ ryzen-ai-9/Modelfile
│  └─ rtx-4060/Modelfile
├─ continue/config.yaml
├─ scripts/
│  ├─ setup.ps1
│  └─ check.ps1
└─ README.md
```

`setup.ps1` 负责按硬件选择模型并执行 `ollama pull`、`ollama create`；`check.ps1` 验证本地 API、模型名称和工具调用。README 写清 Windows、驱动、Ollama 和 Continue 的安装步骤。为了让不同时间克隆的人得到尽量一致的结果，还应记录 **Ollama 版本、模型标签及模型摘要**，并且不要提交 API 密钥。

能自动复现的是**本地模型 + Continue Agent**。Cursor 自带 Agent 的外网 HTTPS 接入仍受其服务端路由和兼容性影响，不能承诺克隆仓库后一键可用。当前我们讨论的是方案，**还没有创建这个 Git 项目**。