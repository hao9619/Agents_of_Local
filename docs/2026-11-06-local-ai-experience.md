# 🧠 从本地 GPU 到 NPU：Ollama、Continue 与 Lemonade 的部署排障经验

记录日期：2026-11-06。本文是本项目截至该日的阶段性经验帖，保存部署过程、有效尝试、失败现象和结论边界，不代表后续所有软件版本的行为。

我们希望模型在自己的笔记本上运行，通过 Cursor 中的 Continue 读写项目文件，并用“SVG 鹈鹕骑自行车动画”检验编码、绘图和工具调用能力。随后在另一台 AMD 笔记本上尝试 NPU＋集显混合推理，以及纯 NPU 推理。

证据分为三类：本项目保留的本机测试及产物；用户从 AMD 电脑贴回的终端输出与使用反馈；官方文档说明。AMD 电脑未由本会话直接控制，用户反馈成功不等于进行了独立的硬件性能复测。

## 📍 当前做到哪里

| 路线 | 环境与模型 | 截至本文的结果 |
| --- | --- | --- |
| RTX 4060 Laptop，8GB 显存 | Windows、Ollama 0.40.14、Continue 2.0.0、Qwen3.5 4B Q4 | 本机 API、GPU 推理及工具链有测试记录；用户后续确认新建、改写文件正常；保留了鹈鹕优化最佳结果 |
| Ryzen AI 9 365，32GB 内存 | Radeon 880M 集显＋XDNA2 NPU；Lemonade 2026.45.3；RyzenAI Server v1.7.0；Qwen3-4B-Hybrid | 用户观察到 NPU 先工作、GPU 随后生成；长度参数对齐后，用户确认一次鹈鹕任务成功写文件并停止 |
| 同一 AMD 电脑，纯 NPU | Lemonade＋FLM 1.0.7；候选 qwen3.5-4b-FLM | FLM 后端安装成功、模型列表可见；已提供下载、加载及 Continue 配置步骤，尚未收到模型成功下载、加载和工具测试反馈 |

Hybrid 使用 **Qwen3 4B**，FLM 候选使用 **Qwen3.5 4B**。不能把两者差异全部归因于 GPU/NPU，也没有完成同模型、同量化、同输入的速度或功耗对照。

## 1. 先分清谁负责什么

```text
Cursor 项目目录
    ↕ 读文件、编辑、终端等工具
Continue：会话、提示词、工具执行与批准策略
    ↕ 本机 HTTP API
Ollama / Lemonade：模型服务
    ↕ 推理后端与模型权重
GPU / NPU / CPU
```

我们写的是启动脚本、模型配置、规则和实验材料。文件工具主要由 Continue 提供，模型负责提出调用请求。模型“说要创建文件”不等于插件执行成功；必须检查工具返回和实际文件。

Lemonade 自带聊天界面不妨碍 Continue 接入。继续使用 Cursor 的方式是让 Continue 连接 Lemonade 的本地 API；这与 Cursor 自带的其他 AI 面板需要区分。

外挂知识库暂未实施。后续可研究 Continue 的 MCP/检索接口，不能把会话历史、项目文件读取和完整知识库当成同一件事。

## 2. RTX 4060：先把基础链路跑通

项目使用独立 Ollama 运行环境，API 为 `http://127.0.0.1:11435`，模型别名为 `local-coder-4060`。另一套用户安装的 Ollama 可能监听默认的 `11434`，两套程序和模型目录不要混淆。

- 项目独立运行环境及权重在 `.local/`，不纳入 Git。
- Windows Ollama 默认模型目录通常是 `%USERPROFILE%\.ollama\models`；设置了 `OLLAMA_MODELS` 后以该变量为准。下载位置不必等于程序安装位置。
- Continue 实际使用的用户配置为 `%USERPROFILE%\.continue\config.yaml`。仓库的 `continue/config.yaml` 是可共享模板，不会因为放进项目就自动替换用户配置。
- 项目规则可放在 `.continue/rules/`；活动文件工具规则见 [.continue/rules/tool-use.md](../.continue/rules/tool-use.md)，复用模板见 [continue/rules/tool-use.md](../continue/rules/tool-use.md)。

32K API 测试曾确认 GPU 加速，模型占用约 4.1GB；这不是整机总显存，也不是所有请求的固定占用。证据见 [32K 工具调用测试](evidence/2026-11-05-context-32k.json)。

### 网络与多机复现

曾遇到 Ollama 仓库域名 DNS 错误。项目保留 [备用下载脚本](../scripts/download-model.py)，按模型清单下载并校验，不把旧 IP 当永久解决办法。

换电脑不仅要复制 Git 仓库，还要安装运行环境、下载权重、配置用户目录中的 Continue 配置，并启动服务。模型权重、用户目录配置、代理状态和设备驱动不会随普通 Git 克隆自动恢复。

GitHub 公开前仍应检查配置、日志和提示词是否包含密钥、私人代码、用户名或敏感路径。本文不保存真实密钥；配置里的 `apiKey: local` 是本地服务未启用鉴权时的占位值。模型和第三方软件另受各自许可证约束，不能笼统承诺项目内所有材料均可无条件公开。

## 3. Continue 的界面与会话问题

### 找不到插件或命令

用户曾搜不到 `Continue: Focus Continue Chat`。本机 Continue 2.0.0 的命令注册存在名称/命令 ID 的细节，不能把某一篇教程里的命令标题当成所有版本均存在。可从扩展页面、Continue 图标和命令面板查实际入口；本机曾确认 `Continue: Add to Chat` 可用。

### 文件列表与 Continue 只能看一个

移动整个主侧栏会连文件列表一起移动。有效做法是移动 **Continue 这个视图** 到辅助侧栏：通过 `View: Move View` 选择 Continue，再移到新的 Secondary Side Bar；保持文件列表所在主侧栏在左边。具体菜单名称随版本可能不同。用户反馈这一布局调整成功。

### 切项目不等于新建聊天

Continue 的当前会话可能在切换目录后继续保留，即使读取的工作目录已改变。换项目、换后端或排障时应显式新建会话，在历史入口管理旧会话，不把切目录当成清空上下文。新建和删除的具体按钮以已安装版本为准；本文未保留跨版本通用的命令名。

### 思考按钮与工具过程

本机曾核对 Continue 2.0.0：思考按钮受模型名称识别与 `defaultCompletionOptions.reasoning` 影响，自定义别名未必被自动识别；显式关闭也可能隐藏按钮。找不到按钮不一定是操作遗漏。

工具卡片展示的是工具执行流程；思考内容取决于模型、后端返回及插件展示能力。只看到几句思考后长时间 GPU 满载，不能据此判定程序挂死，也不能把它当作持续正常进展的证明。

## 4. “上下文超限”和“想很久不输出”不是同一个问题

用户遇到过 `Message exceeds context limit`。系统提示词除了自写规则，还可能包含工具定义、Agent 指令、项目规则和历史消息。已经精简过通用规则，但这不会消除工具定义和上下文预算需求。

不要假定插件一定会自动压缩所有历史并继续成功执行；本项目未验证可靠的自动压缩闭环。排障时新建会话、精简无关上下文，并核对两端长度设置。

本机一次鹈鹕 API 对照中，开启思考、输出上限 2048 时返回 `done_reason=length`，HTML 不完整。改为关闭思考、8192 输出预算后，同类请求约 56 秒正常结束，输出包含 HTML 结束标签。见 [生成预算证据](evidence/2026-11-05-generation-budget.json)。

这说明预算不足可以导致失败，但不能解释每一次空白、重复或工具异常。思考、正文及工具参数都会消耗生成额度；`maxTokens` 也不是独立于上下文之外的额外空间。

## 5. 文件工具：三类错误要分别处理

| 现象 | 当时的线索 | 有效处理或下一步 |
| --- | --- | --- |
| 模型声称不会创建文件 | 臆造 `mkdir`、`write_file`，返回 Tool not found | 使用实际提供的工具名与 schema |
| 弹出批准按钮 | 工具策略为 Ask First | 用户在工具策略中决定是否自动批准；“无需确认”提示词不会覆盖策略 |
| 文件存在后不能改写 | 继续用创建工具，随后尝试不存在的写入工具 | 先读取，使用实际提供的编辑工具；用户后续确认正常 |

本机确认的新建工具为 `create_new_file(filepath, contents)`。已有文件修改可使用当次实际工具列表中的 `read_file`、`single_find_and_replace` 或 `edit_existing_file`，不能假定所有版本都同时提供这些接口。

不通过删除重建绕过编辑工具，不把权限拒绝误判为工具名错误，也不把“模型输出了代码”当成文件已经落盘。

## 6. 鹈鹕动画：提示词具体化比盲目调参数更有帮助

测试要求是单文件 HTML，使用 SVG 绘制鹈鹕骑自行车的 2D 循环动画，不依赖外部资源。早期虽能生成文件，画面结构、骑行动作和视觉效果仍明显不足。

2026-11-05 在 RTX 4060 本地模型上共进行了 11 轮调用。比较过思考开关、温度及提示词组织；没有证据说明单靠某个温度或开启思考就能稳定画好。更有用的是明确几何关系、部件标识、脚与踏板的联系，再让模型做少量精确修改。

按用户要求，现在只保留三份最佳复现材料：

- [推荐 HTML](../鹈鹕测试/index.html)
- [配置参数](../鹈鹕测试/配置.json)
- [实际提示词](../鹈鹕测试/提示词.md)

最佳结果来自第 8 轮完整生成，加第 9 轮模型提出的三处精确修订，不是单次生成。完整生成参数为 16K 上下文、8192 输出、温度 0.6、seed 42、关闭思考；局部修订为 4096 输出、温度 0.2。其余测试作品和过程截图已按要求清理，不重新创建。

结果 SHA256：`00c3c1ead62baaa5c7910fbc5a4f8d227bdaa621d7f71a0332d4cf94198147d7`。

整理时核对：当前 HTML 文件名为 `index.html`，哈希与上述最佳结果一致；配置 JSON 中仍保存实验当时的文件名“推荐结果.html”，读取时以当前链接为准。本轮未修改作品与实验参数。

作品仍是简洁插画，细节与生物结构不等于专业动画。成功生成代码、能播放动画、动作协调和审美质量，是不同的验收维度。我们没有人工绘制一份作品冒充本地模型生成。

## 7. AMD 为什么最初只用 GPU，不用 NPU

Ollama 使用的推理后端不会因为芯片配有 50 TOPS NPU 就自动调度 NPU。需要支持该 NPU 的软件栈与模型格式。硬件宣传中的 TOPS 也不能直接换算为大模型每秒输出 token 数。

我们实际选择了两条路线：

| 路线 | 后端 | 模型 |
| --- | --- | --- |
| NPU＋集显混合 | RyzenAI Server / ONNX Runtime GenAI，经 Lemonade 提供 API | `Qwen3-4B-Hybrid`，另行下载 AMD ONNX 优化模型 |
| 纯 NPU | FastFlowLM，经 Lemonade 提供 API | `qwen3.5-4b-FLM`，另行下载 FLM 模型 |

普通 Ollama GGUF 权重不能仅改一行配置就变成上述 Hybrid 模型。模型格式、运行后端和驱动都必须匹配。

Hybrid 的预期分工是 NPU 处理输入（prefill），集显逐 token 生成（decode）。用户观察到 NPU 运行一会儿后主要由 GPU 工作，符合这种分工。短输入、长 HTML 输出任务仍可能大部分时间用 GPU；没有要求两者一直同时满载，也没有证实混合模式必然更快或更省电。[Lemonade FAQ](https://lemonade-server.ai/docs/guide/faq/)

## 8. Lemonade 混合部署：版本、下载与本地后端

用户提供的版本是 `2026.45.3`，服务端口 `13305`。采用当前 `lemonade` 命令，不照搬旧版 `lemonade-server serve` 和端口 `8000`。旧 `oga-hybrid` 等 recipe 已合并到 `ryzenai-llm`，由模型配置决定执行模式；后端名称中的 `:npu` 不代表只能纯 NPU。[迁移说明](https://github.com/lemonade-sdk/lemonade/wiki/Migration)

初始检查：

```powershell
lemonade --version
lemonade status
lemonade backends
lemonade list | Select-String 'Hybrid'
```

### 后端下载 504、超时

执行 `lemonade backends install ryzenai-llm:npu` 时下载失败，关键原文：

```text
Failed to download ryzenai-server.exe from:
https://github.com/lemonade-sdk/ryzenai-server/releases/download/v1.7.0/ryzenai-server.zip
Download failed after 6 attempts.
HTTP error 504
Partial size: 0.0 MB
```

再次尝试出现 `Timeout was reached (CURL code: 28)`。这是下载阶段错误，不能据此判定 NPU 不兼容；0 MB 的残片也没有实际可续传进度。

采用的办法：浏览器下载相同版本的 [官方 ZIP](https://github.com/lemonade-sdk/ryzenai-server/releases/tag/v1.7.0)，完整解压，保留配套文件，再指向实际包含 EXE 的目录。下面路径是 AMD 电脑当时的示例：

```powershell
lemonade config set ryzenai.server_bin="D:/SoftWare_Data/Lemonade/ryzenai-backend"
```

用户收到 Configuration updated。路径保存成功只证明设置成功，运行时还需检查程序、依赖与驱动。[本地后端目录配置](https://lemonade-server.ai/docs/guide/configuration/#backend-binary-selection)

### 模型下载 SSL 失败

`lemonade pull Qwen3-4B-Hybrid` 返回 `CURL error: SSL connect error`。对照检测：

```powershell
curl.exe --noproxy "*" --max-time 15 -i "http://127.0.0.1:13305/api/v1/health"
```

本地服务返回 200、status ok；访问 Hugging Face 时却 `Recv failure: Connection was reset`，说明当时本地服务可用，外网 TLS 连接失败。

讨论过代理、TUN/虚拟网卡和进程间网络路径差异。随后用户的 curl 收到了 Hugging Face 的 404，表明那次 HTTPS 请求已通，但不是模型文件下载成功。此前给的测试 URL 使用了不存在的 `config.json`，这是指导中的错误；仓库实际文件为 `genai_config.json`。`EntryNotFound` 不是证书错误，也不应靠关闭证书校验解决。

用户随后重试下载并反馈成功。没有保留足以认定具体代理设置就是唯一修复因素的证据，也不能由浏览器/curl 可访问推断长期运行的服务必然走同一代理。

### 加载与卸载

```powershell
lemonade pull Qwen3-4B-Hybrid
lemonade run Qwen3-4B-Hybrid --ctx-size 8192
```

`run` 打开聊天入口。重新加载参数前，从内存卸载模型，不删除下载文件：

```powershell
lemonade unload Qwen3-4B-Hybrid
lemonade load Qwen3-4B-Hybrid --ctx-size 8192
```

## 9. Continue 接入：一次长度不匹配引出的反复排障

Continue 使用 `provider: openai` 和本机 `apiBase` 表示 OpenAI 兼容协议，不意味着请求发往云端。默认未开启鉴权时的 `local` 是占位值，不是真实云 API 密钥。[Continue 配置说明](https://docs.continue.dev/customize/model-providers/top-level/openai)

排障中出现过这些现象：

1. `Tool tool_call not found`：把 `tool_call` 当成工具名称。
2. `filepath argument is required and must not be empty or whitespace-only`：工具名正确，但缺少有效路径。
3. 小任务成功创建 `npu-tool-test.html`，内容为 `<!doctype html><html><body>NPU tool test</body></html>`。
4. 长任务后半段重复生成 `10 10 10`，属于异常生成；没有证据能直接断定模型损坏或 NPU 硬件问题。
5. 文件存在时先创建失败，随后覆写成功，却反复覆写相同内容。
6. 加入停止规则后有时只输出代码，没有真正调用文件工具；进一步要求保存也未稳定解决。

尝试过显式设置 `capabilities: [tool_use]`、新建 Agent 会话、明确文件名、规定成功后停止，以及“先生成再保存”的两步任务。这些尝试有局部成功，也有失败，不能作为稳定修复保证；持续加长提示词不是充分诊断。

### 三次直接 API 对照

我们让用户跳过 Continue，在 PowerShell 请求 `http://127.0.0.1:13305/api/v1/chat/completions`。模型、温度分别为 `Qwen3-4B-Hybrid`、0.2，最小请求提供 `create_new_file` 的 JSON schema，要求 `filepath`、`contents` 两个字符串参数；提示词包含 `/no_think`。

| 测试 | 用户贴回的结果 | 能证明什么 |
| --- | --- | --- |
| 非流式，max_tokens=2048 | `tool_calls` 中名称正确，参数为 api-probe.html 与 `<html>test</html>`；finish_reason=stop | 一次简单非流式调用可返回正确结构；未实际写文件 |
| 流式，同一请求 | `delta.tool_calls` 名称与参数正确，ID 为 `-`；正文样式的工具文本也出现在 reasoning_content；最后 usage 和 DONE，未见非空 finish_reason | 流式并非完全不支持工具；ID 与结束信号存在兼容性疑点，但未证明是 Continue 异常根因 |
| 非流式追加模拟 tool 成功结果，max_tokens=1024 | 简短确认创建完成，无新 tool_calls | 在该最小模拟对话里，模型能在成功后停止；不等于复杂 Agent 循环已通过 |

JSON 里的 `\u003c` 是 `<` 的正常转义，不是乱码。第一次请求曾无法连接，第二次成功，仅能说明当时短暂不可达，原因未确定。

这些 API 测试不会执行文件工具，不能把模拟成功消息当成真实文件创建证据。它们也没有完整复现 Continue 的长提示词、工具集合及较长 HTML。

### 最后发现的明确配置不匹配

用户贴出的实际 Continue 配置中，Hybrid 条目为：

```yaml
contextLength: 98304
maxTokens: 16384
temperature: 0.2
```

但此前 Lemonade 按 8192 加载。Continue 声明 96K 不会自动扩展后端容量；单次输出预算也已大于当时声明的整个运行窗口。

我们将 Hybrid 两端统一到 8K，Continue 输出预算调到 4096，保留温度 0.2，新建 Agent 会话，并用新文件名避开旧文件编辑流程。完整条目：

```yaml
  - name: Ryzen NPU+GPU
    provider: openai
    model: Qwen3-4B-Hybrid
    apiBase: http://127.0.0.1:13305/api/v1
    apiKey: local
    roles: [chat, edit, apply]
    capabilities: [tool_use]
    defaultCompletionOptions:
      contextLength: 8192
      maxTokens: 4096
      temperature: 0.2
```

这是加在用户配置现有 `models:` 下的条目，不是另建第二个 `models:`。保存后执行 `Developer: Reload Window`，新建 Agent 会话并选对模型。

随后用户确认鹈鹕任务成功。**这是当前可用基线，但不是证明长度不匹配解释了所有错误的受控实验**：重建会话、调整提示词和换文件名也发生过变化。旧流式实现的兼容性疑点仍未独立验证修复；复杂编辑和多轮工具调用没有系统性回归测试。

### 本轮成功任务的提示词

```text
请在当前项目根目录创建 pelican-bike-v2.html，用单文件 HTML、
SVG 和 CSS 实现鹈鹕骑自行车的二维循环动画。

鹈鹕应有明显的长嘴和喉囊，车轮旋转，双脚跟随踏板运动。
不使用外部资源，代码尽量简洁。

使用实际可用的文件工具保存完整 HTML，不要只展示代码。
文件写入成功后，只回复“已完成”，立即结束，不再修改。
无需测试或确认。
```

该 AMD 产物未复制回本仓库，本文不把 4060 的推荐 HTML 当作 AMD 生成结果。

## 10. 纯 NPU：FLM 后端安装成功，模型验证待继续

用户已执行并贴回成功结果：

```powershell
lemonade unload Qwen3-4B-Hybrid
lemonade backends install flm:npu
lemonade list | Select-String 'FLM'
```

安装包为 `fastflowlm_1.0.7_windows_amd64.zip`。列表包含 `qwen3.5-4b-FLM`，约 5.00GB，Downloaded 为 No；还包括其他 Qwen、Gemma、Llama 等条目。

FLM 官方 Windows 文档要求 XDNA2 NPU、Windows 11，推荐 32GB RAM，NPU 驱动不低于 `32.0.203.311`。本会话没有收到该机驱动版本截图或实际版本输出，不能把安装成功当成驱动完整验收。[安装要求](https://fastflowlm.com/docs/install_win/)

下一步已提供、尚待用户反馈：

```powershell
lemonade pull qwen3.5-4b-FLM
lemonade run qwen3.5-4b-FLM --ctx-size 8192
```

普通对话成功后，再在 Continue 的 `models:` 下增加独立条目：

```yaml
  - name: Ryzen 纯 NPU
    provider: openai
    model: qwen3.5-4b-FLM
    apiBase: http://127.0.0.1:13305/api/v1
    apiKey: local
    roles: [chat, edit, apply]
    capabilities: [tool_use]
    defaultCompletionOptions:
      contextLength: 8192
      maxTokens: 4096
      temperature: 0.2
```

先验证对话，再测小文件创建、已有文件改写、成功后停止，最后再做鹈鹕长任务。FLM 是另一条后端，不能沿用 Hybrid 的通过结论。纯 NPU 指模型主要推理路线，不要求 Windows 桌面或其他程序的 GPU 总占用绝对为零。

## 11. 最大上下文：宣传上限、模型声明与实机值分开看

| 模型 | 官方声明 | 本项目采用或拟采用 | 注意事项 |
| --- | --- | --- | --- |
| Qwen3-4B-Hybrid | ONNX 配置 context_length=40960、max_length=40960 | 已通过一次任务的 8192 | 同一配置还有 hybrid_opt_max_seq_length=4096，不能仅凭顶层声明保证 Hybrid 路径稳定跑满 40K |
| qwen3.5-4b-FLM | 当前 FLM 文档标注最大 256K、默认 32K | 部署步骤先指定 8192，待验证 | 文档声明不等于 FLM 1.0.7＋本机32GB内存已实测跑满；扩窗需核对该版本、内存与速度 |

来源：[Hybrid genai_config.json](https://huggingface.co/amd/Qwen3-4B-awq-quant-onnx-ryzenai-1.7-hybrid/blob/main/genai_config.json)、[FLM Qwen 模型说明](https://fastflowlm.com/docs/models/qwen/)。

上下文包含系统提示、工具定义、历史消息、文件内容、思考和生成输出，不是全部可用于输入文件。较长上下文的可加载、可生成、长距离检索准确率和交互速度也不是一回事。建议逐级尝试 8K、16K、32K，每次同时对齐后端与 Continue，不直接从 8K 跳到宣传上限。

## 12. 留给后续部署者的排障顺序

1. **看具体阶段。** DNS、504、TLS、文件404是下载问题；不能当作硬件推理失败。
2. **先核对实际配置。** 模型名称、API地址、上下文、输出预算都以生效配置为准，不假定用户仍使用示例。
3. **先短后长。** 普通聊天 → 结构化工具调用 → 小文件 → 改写 → 成功后停止 → 长代码。
4. **区分普通文本与工具调用。** HTML出现在聊天中不是创建成功，tool_calls出现也不是工具已执行。
5. **分开测试流式与非流式。** 单次成功不覆盖另一条代码路径；多轮工具结果回传也要单测。
6. **一次修改一个主要因素。** 不把换模型、扩上下文、改温度和重写提示词一起进行后宣称找到了唯一根因。
7. **记录可用基线与边界。** 允许保留未解决的兼容性疑点，不把一次通过包装成长期稳定。

后续待办：完成 FLM 模型下载与运行；验证纯 NPU 的工具链；收集 AMD 产物和必要日志；再做尽可能控制模型与参数的速度、内存和功耗对比。本文及索引已落盘，未由 Agent 暂存、提交或推送。
