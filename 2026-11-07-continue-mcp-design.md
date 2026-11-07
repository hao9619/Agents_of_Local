# Continue 本地工具接入设计

状态：设计已确认，首版已实现。实测记录见 [MCP 验证证据](docs/evidence/2026-11-07-continue-mcp-verification.json)。

## 从编辑器调用我们自己的代码

在项目根目录的 `.continue/mcpServers/` 添加项目级配置。Continue 在 Agent 模式下通过 stdio 启动本地 Python MCP 服务，读取工具描述，并在收到工具调用时把参数交给 Python。Python 返回执行结果，Continue 将其带回会话。项目已有的 Ollama 模型配置继续负责对话模型选择。

```text
Cursor → Continue Agent → MCP 工具 generate_html_file
                                  ↓
                         Python 文件交付执行器
                                  ↓
                       Ollama API → 保存与运行记录
```

第一版只提供 `generate_html_file`，接收任务描述和目标 HTML 文件名。外层 Agent 只需提交简短参数。Python 调用现有 Ollama 接口生成完整 HTML，并接收后端结束原因。这样可以在代码里控制生成预算、是否保存及何时返回成功。外层模型若没有发出调用，Continue 中会缺少这次工具执行记录，可与工具执行失败区分。

Continue 的普通 MCP 工具只在被调用时运行。生成限制和截断处理适用于这个工具发出的请求。监听 Continue 的所有生成流需要另外接入模型请求路径。

## 文件交付和失败处理

- 第一版将产物限制在指定的实验输出目录，接受简单的 `.html` 文件名。
- 生成成功并取得非空内容后，由程序负责写入一次，并返回实际路径。相同任务描述和目标文件名再次提交时，核对磁盘产物与已保存的完成记录，一致则返回已有结果，省去再次推理。已有文件与记录不符，或不同任务使用同名文件时，报告冲突。
- 遇到长度截断、请求失败或无有效内容时返回明确失败原因。截断结果不写为最终产物。
- 记录结束原因、生成 token 数、耗时与写入状态。工具日志走 stderr，stdout 用于 MCP 消息。
- 暂不对动画效果和语义质量评分。复读检测、上下文状态与知识库检索可在同一执行器中分阶段加入。

## 验收

1. 在 Cursor 打开项目根目录，Continue 的 Agent 工具列表可见自研工具。发一条小 HTML 任务后能看到工具返回，磁盘上能找到文件。
2. 将生成额度临时调低触发截断，检查工具返回的原因和最终文件是否存在。
3. 重复提交相同任务，检查没有再次生成和写入。用不同任务提交同名文件，检查冲突处理。
4. 使用现有 4060 模型运行鹈鹕任务，保留工具执行结果和耗时。与既有 Continue 路径对照时保持模型和任务一致，单独记录外层 Agent 有没有选择自研工具。

参考：[Continue MCP 配置](https://docs.continue.dev/customize/deep-dives/mcp) · [Continue YAML 属性](https://docs.continue.dev/reference) · [MCP 服务端开发](https://modelcontextprotocol.io/docs/develop/build-server)
