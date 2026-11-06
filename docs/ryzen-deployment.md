# 另一台 Ryzen AI 9 365 电脑如何部署

更新时间：2026-11-06。本文主要说明 Ollama GPU 路线，保留早期部署基线。适用硬件：Windows 11、Ryzen AI 9 365、32GB 内存、无独显。Lemonade Hybrid 的用户验证结果、下载排障及纯 NPU 的当前进展，统一见 [部署排障经验帖](../2026-11-06-local-ai-experience.md)；其中纯 NPU 模型运行尚未验证。

## 建议配置

先用 Qwen3.5 4B Q4、8K 上下文进行简单对话验证，便于比较速度和工具调用；满意后再尝试 9B Q4。9B 并非确定更适合，容量允许不代表交互速度足够。

Ollama Windows 的 AMD ROCm 支持列表不能直接用 Linux 的列表代替。该机的集显能否加速需要实际驱动和后端确认。官方还提供 Vulkan 支持；不要把 Ryzen AI 的 NPU 自动视为 Ollama 推理设备。先更新电脑厂商或 AMD 提供的兼容显卡驱动。

## 1. 安装软件

安装 Cursor、Continue 扩展 `Continue.continue`，以及 [官方 Ollama Windows 安装器](https://ollama.com/download/windows)。该机先使用官方完整安装器，避免把本项目为 NVIDIA 准备的独立运行包直接当作 AMD 完整环境。

安装后新开 PowerShell：

```powershell
ollama --version
ollama pull qwen3.5:4b-q4_K_M
```

如果项目已在该机复制或克隆，在项目根目录运行：

```powershell
$env:OLLAMA_HOST = '127.0.0.1:11434'
ollama create local-coder-ryzen -f .\profiles\ryzen-ai-9\Modelfile
ollama run local-coder-ryzen
ollama ps
```

这里复用的是 4B/8K 模型配置，文件名中的 4060 不会把模型绑定到 NVIDIA。`ollama ps` 的 PROCESSOR 显示实际 CPU/GPU 分配；它显示 CPU 时仍可运行，但需要评估速度。关闭交互用 `/bye`；`ollama stop local-coder-ryzen` 卸载模型。

## 2. Continue 配置

打开 Continue 的本地配置；Windows 常用位置为 `%USERPROFILE%\.continue\config.yaml`。有原文件先备份，再合并以下模型条目，或在配置选择器加载独立配置：

```yaml
name: Local Ryzen
version: 0.0.1
schema: v1
models:
  - name: Local Coder Ryzen
    provider: ollama
    model: local-coder-ryzen
    apiBase: http://127.0.0.1:11434
    roles: [chat, edit, apply]
    capabilities: [tool_use]
    defaultCompletionOptions:
      contextLength: 8192
      maxTokens: 2048
      temperature: 0.2
```

选 **Local Coder Ryzen** 和 **Agent** 模式，使用本项目 README 的示例任务验证读写文件。两台机器的端口可以不同，因为各自连接自己的 localhost；4060 本项目采用 11435 是为了避开本机另一个已有服务。

## 3. 再尝试 9B

下载 `ollama pull qwen3.5:9b-q4_K_M`，另建 Modelfile：

```text
FROM qwen3.5:9b-q4_K_M
PARAMETER num_ctx 8192
PARAMETER num_predict 2048
PARAMETER temperature 0.2
```

用 `ollama create local-coder-ryzen-9b -f <该文件路径>` 创建独立别名，Continue 的 model 改为该别名。比较相同任务的首字等待、生成速度、内存占用和工具正确率。先保留 8K，确有需要再试 16K，同时改 Modelfile 和 Continue 配置。

## 故障定位

- 下载提示 `lookup registry.ollama.ai: no such host`：先查网络 DNS；这不是显存不足。不要关闭 TLS 校验或照搬固定 IP 作为长期配置。
- 未发现集显：检查当前版本的 [GPU 支持说明](https://docs.ollama.com/gpu) 和 `%LOCALAPPDATA%\Ollama\server.log`。需要显式启用集显时，先退出托盘 Ollama，再在新 PowerShell 中设置 `$env:OLLAMA_IGPU_ENABLE='1'` 并执行 `ollama serve`；只在该进程内实验，不保证该硬件可用。若后端不稳定，返回 CPU 基线再排查。
- 不要同时开多个 `ollama serve` 争用 11434。改环境变量后需要重启对应服务才生效。
- 整套配置是推理和 Agent 行为定制；训练或修改神经网络结构属于另一项工作。

参考：[Windows 安装与依赖](https://docs.ollama.com/windows)、[GPU 后端支持](https://docs.ollama.com/gpu)、[Continue Ollama 配置](https://docs.continue.dev/customize/model-providers/top-level/ollama)。

## Agent 上下文补充

4060 本机实测项目的 Agent 系统提示约 12.9K，已改 32K。另一台 8K 只适合作为简单对话基线；Agent 若报上下文不足，需把 Ryzen Modelfile 的 num_ctx 与 Continue contextLength 同步改为 32768，再创建模型并核对内存、延迟。不能把 CPU/集显机器的速度视为已验证。
