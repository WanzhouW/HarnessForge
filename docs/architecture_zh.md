# 架构

HarnessForge 将基准编排、智能体策略、工具和安全边界分离：

```text
CLI / TaskSpec
  → Runner
    → Agent Loop
      → Scripted Model / LLMProvider
        → OpenAI Responses API / OpenAI-Compatible Chat Completions API
      → Tool Registry
        → Filesystem / Search / Edit / Diff / Patch / Terminal Tools
          → WorkspaceGuard / CommandPolicy
    → runs/<run_id>/
      → Trajectory Events / AgentRunResult / Artifacts
```

## 分层职责

- **TaskSpec** 描述一个隔离任务：身份标识、指令、工作区、启用的工具和适配器元数据。
- **Runner** 验证任务边界，构建任务作用域内的注册表，应用固定运行配置，创建 run/attempt ID 和输出路径，并调用循环。它写入 JSON 结果与 JSONL 轨迹，但不负责评估公开基准。
- **Agent Loop** 是一个显式的“模型动作 / 工具观察”循环。Provider 一次返回多个工具调用时，循环将调用放入任务内队列，保持每个 step 只执行一个工具，并在队列清空后才再次调用模型。它没有 Debug 外层循环、记忆、用户配置、摘要、动态技能发现，也不依赖 LangGraph。每次运行的 Provider 消息和待执行队列只保存在循环内部，不会跨任务持久化。
- **LLMProvider** 统一模型消息、工具调用、文本响应和用量数据。`create_provider()` 根据 `ProviderConfig.provider_api` 选择 Responses 或 Chat Completions 后端。两者都使用官方 OpenAI Python SDK，并支持配置模型、基础 URL、temperature、输出 token 上限、超时和重试次数。Responses 工具 schema 是扁平结构；Chat Completions 使用嵌套的 `function` 结构，并把 `assistant.tool_calls` 与 `tool_call_id` 转换为统一内部消息。
- **Tool Registry** 负责注册、查找、基础参数校验，以及统一的 `ToolResult` 协议。它从不直接打印。
- **Tools** 暴露结构化目录列表、有界行范围读取、字面量/正则/glob 搜索、精确替换、文件创建、任务作用域 diff、纯 Python unified patch，以及一个收窄能力范围的命令运行器。
- **WorkspaceChangeTracker** 在一次运行中首次执行 HarnessForge 文件修改前保存原内容。因此 `get_diff` 无需 Git 仓库或宿主机子进程，就能报告 `edit_file`、`write_file` 和 `apply_patch` 产生的变化。
- **WorkspaceGuard** 是主机 / 任务工作区路径边界。它阻止路径逃逸和访问看起来敏感的路径。它不是 Docker 沙箱，也不是操作系统级沙箱。
- **CommandPolicy** 只允许显式列出的 argv 形式。基线策略有意设置得很窄，并不足以覆盖 Terminal-Bench。
- **Budget / Result** 记录明确的步骤、模型调用、工具调用和墙钟时间预算，预留 token/成本限制，并记录停止原因、调用次数、Provider 用量和输出路径。`harness_success` 与当前保持为空的 `benchmark_success`、`official_score` 相互独立。
- **CLI** 是一层很薄的 `argparse` 入口。`doctor` 不发送模型请求，只做本地检查；`run` 构建现有配置并调用 Runner。`PROVIDER_API` 或 `--provider-api` 只负责选择 Provider 协议，不改变 Agent Loop。
- **Terminal artifacts** 在 `ToolResult` 中保留有界 stdout/stderr；被截断的完整输出写入可信的 run artifact 目录。

## 依赖方向

CLI 和未来基准适配器依赖框架数据结构与 Runner；Runner 依赖工具和循环，循环依赖 Provider 契约，工具依赖安全原语。Provider 契约、安全模块和数据结构不依赖 Runner。没有任何模块导入 CyberClaw。
