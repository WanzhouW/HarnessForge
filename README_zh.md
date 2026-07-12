# HarnessForge

HarnessForge 是一个面向基准测试的极简终端智能体框架基线。它将
CyberClaw 中的通用设计理念提取到一个独立项目中，既不修改也不导入
CyberClaw 的主运行时。

当前基线提供：

- 一个小型、显式的智能体循环，同时支持用于测试的脚本化模型后端和
  `LLMProvider` 抽象；
- 基于官方 Python SDK 的 Responses API 与 Chat Completions API Provider，后者
  可连接 DeepSeek 等兼容服务；
- 可复现的 run/attempt ID、结构化结果、JSONL 轨迹，以及步骤、模型调用、工具
  调用、墙钟时间、token 和成本预算；
- 工作区边界保护机制；
- 结构化的 `list_dir`、分块 `read_file`、正则/glob `search_text`、`edit_file`、
  `write_file`、`get_diff` 和纯 Python `apply_patch` 工具；
- 一个刻意收窄能力范围并设置 `shell=False` 的终端接口；
- 截断的终端显示输出，以及保存完整输出的 JSON artifact；
- `doctor` 和本地任务 `run` CLI 命令；
- 为未来 Terminal-Bench 和 SWE-bench 适配器预留的纯接口桩。

本基线有意排除了 Debug 工作流、pytest 自动修复、用户配置、持久化会话、
M5 记忆、对话摘要、动态技能以及跨任务状态。

目前，它**尚未**提供完整的 Terminal-Bench 或 SWE-bench 集成。具体而言，
它不会下载基准测试、创建官方基准测试容器、调用官方评估器，也不声称其默认
终端策略足以应对公开基准测试任务。

## 项目结构

```text
.
├── README.md
├── README_zh.md
├── .env.example
├── pyproject.toml
├── docs/
│   ├── architecture.md
│   ├── architecture_zh.md
│   ├── baseline_scope.md
│   ├── baseline_scope_zh.md
│   ├── extraction_notes.md
│   ├── extraction_notes_zh.md
│   ├── phase0_status.md
│   ├── phase0_status_zh.md
│   ├── testing_phase2_phase3.md
│   └── testing_phase2_phase3_zh.md
├── src/harness_forge/
│   ├── cli.py              # doctor 与本地任务运行命令
│   ├── agent/              # 智能体循环、提示词与状态
│   ├── benchmark_adapters/ # 未来基准适配器的接口桩
│   ├── harness/            # 任务规格、预算、运行器与结果结构
│   ├── logging/            # 轨迹事件记录与 JSONL 日志
│   ├── providers/          # Provider 契约、Responses 与 Chat Completions 后端
│   ├── safety/             # 工作区与命令策略边界
│   └── tools/              # 文件系统、搜索、编辑、终端与注册表工具
└── tests/                  # 单元测试与冒烟测试
```

## 开发

本包采用 `src/` 目录布局。运行时依赖为官方 `openai` Python 包和
`python-dotenv`；脚本化测试不会发起网络请求。

```powershell
python -m pip install -e .
```

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

## 命令行入口

以下两种入口共用同一个 `argparse` 实现：

```powershell
python -m harness_forge --help
harnessforge --help
```

检查 Python、依赖、`.env` 和 Provider 初始化状态，且不发送模型请求：

```powershell
harnessforge doctor
```

运行一个本地任务：

```powershell
harnessforge run `
  --task-id local-demo `
  --instruction "Read notes.txt and summarize it." `
  --workspace .\demo_workspace `
  --tools list_dir,read_file
```

每次运行默认在 `runs/<run_id>/` 下生成 `result.json`、`trajectory.jsonl` 和
`artifacts/`。CLI 退出码只描述 harness 执行状态：0 为正常完成，1 为 harness
失败，2 为配置错误，3 为 Provider 错误；它们不代表官方 benchmark 是否通过。

## 模型 Provider 配置

HarnessForge 同时支持 `responses` 和 `chat_completions` 两种 API 协议。可以通过
显式参数、进程环境变量，或者启动 HarnessForge 时所在目录中的 `.env` 文件进行
配置。按当前仓库的运行方式，文件应放在 `D:\vsc\HarnessForge\.env`。

OpenAI Responses API 配置示例：

```dotenv
PROVIDER_API=responses
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=your-model-name
```

DeepSeek Chat Completions 配置示例：

```dotenv
PROVIDER_API=chat_completions
OPENAI_API_KEY=你的DeepSeek密钥
OPENAI_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-flash
```

这里沿用 `OPENAI_API_KEY` 变量名，是因为 DeepSeek 通过 OpenAI-compatible SDK
接入。`PROVIDER_API` 决定请求 `/responses` 还是 `/chat/completions`；“兼容
OpenAI”并不代表同时支持这两种协议。命令行参数
`--provider-api responses|chat_completions` 可以覆盖环境变量。

`ProviderConfig.from_env()` 会自动调用 `load_dotenv()`。进程中已经存在的环境
变量优先于 `.env` 中的值。也可以通过
`ProviderConfig.from_env(dotenv_path=...)` 显式指定其他文件。

等价的 PowerShell 配置如下：

```powershell
$env:OPENAI_API_KEY = "..."
$env:OPENAI_BASE_URL = "https://api.openai.com/v1"
$env:MODEL_NAME = "your-model-name"
$env:PROVIDER_API = "responses"
```

```python
from harness_forge.providers import ProviderConfig, create_provider

provider = create_provider(
    ProviderConfig.from_env(
        temperature=0.0,
        max_tokens=4096,
        timeout_seconds=60,
        max_retries=2,
    )
)
```

将 `provider` 作为 `RunConfig.model` 传入。Provider 调用保持同步；Responses
后端关闭 API 存储和并行工具调用，Chat Completions 后端使用兼容性更广的标准
消息和函数工具格式。若兼容服务仍在一次响应中返回多个工具调用，Agent Loop
会将它们排队并按“一步一个工具”顺序执行，全部结果返回后才再次请求模型。
两者的超时和重试都由官方 SDK 负责。`AgentRunResult` 会
在 `model_config.provider_api` 中记录所选协议，并记录实际服务模型名称、模型调用次数和
Provider 报告的 token 用量。除非兼容 Provider 返回成本数据，否则 `cost` 保持
为 `None`。

接入真实 Provider 本身并不意味着 HarnessForge 已经可以运行公开基准。公开
基准适配器、官方评估器和容器生命周期仍未实现。

另请参阅：

- `docs/architecture_zh.md`：组件边界；
- `docs/baseline_scope_zh.md`：受控变量；
- `docs/extraction_notes_zh.md`：来源说明与有意排除的内容；
- `docs/phase0_status_zh.md`：干净基线骨架的验收记录；
- `docs/testing_phase2_phase3_zh.md`：测试输入、方法和预期输出。
