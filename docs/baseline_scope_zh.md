# 基线范围

HarnessForge 的最小基线用于受控比较。

## 固定变量

- 每次实验显式选择一个模型 / 后端，可以是脚本化测试后端，也可以是一个已配置的 `LLMProvider`；
- 一个带版本的系统提示词；
- 每个任务声明一组工具；
- 一个覆盖步骤数、模型调用次数、工具调用次数、墙钟时间，以及可选 Provider token/成本限制的 `BudgetConfig`；
- 不使用记忆或检索；
- 不使用 Debug 工作流或 pytest 自动修复循环；
- 不使用动态技能；
- 不使用用户配置或持久化对话会话；
- 不使用跨任务状态；
- 每个任务使用一个独立工作区。

`harness_success` 表示智能体在没有框架故障的情况下到达了非空最终答案。由于尚未接入官方评估器，`benchmark_success` 和 `official_score` 保持为 `None`。三者不得混为一谈。

每次运行都有独立的 run ID 和 attempt ID。除非调用方显式覆盖路径，否则结果会写入 `runs/<run_id>/` 下的 `result.json`、`trajectory.jsonl` 和 artifact 目录。

## Provider 边界

Phase 1 新增了 OpenAI Responses API Provider，随后补充了 OpenAI-compatible Chat Completions Provider。`PROVIDER_API` 必须解析为 `responses` 或 `chat_completions`；密钥从显式参数或环境变量读取，不会写入运行结果；Provider 对话状态只存在于单次智能体运行中。测试使用 fake Provider 或注入的客户端，不需要真实 API key，也不会发起网络请求。

Provider 不会改变基线提示词、启用工具集、工作区保护、命令策略或既定排除项，也不会加载基准任务或调用官方评估器。

## CLI 边界

`doctor` 和 `run` 只负责本地编排。`doctor` 不发送模型请求；`run` 构建 `ProviderConfig`、`TaskSpec`、`RunConfig` 和 `BudgetConfig`，然后交给 `HarnessRunner`。CLI 退出码只描述 harness 执行状态，绝不声称 benchmark 正确性。

## 工具边界

文件修改仍全部经过 `WorkspaceGuard`。`get_diff` 只覆盖任务作用域内 HarnessForge 文件工具产生的变更，不是通用 Git working-tree 状态。`apply_patch` 使用有界的纯 Python unified diff 解析器，并在写入前校验所有目标。宿主机 terminal policy 没有扩大，仍然拒绝任意命令。

## 指标

未来公开适配器中的主要指标应当是该基准的官方通过率或官方分数。计划中的次要指标包括供应商报告的输入 / 输出 token、成本、墙钟时间、模型调用次数、工具调用次数、重复读取次数、命令耗时和补丁大小。

`AgentRunResult` 现在会记录 Provider 协议、模型名称、模型调用次数，以及 Provider 报告的输入、输出和总 token 数。由于这些 API 不统一报告单次请求成本，成本继续保留为可选字段。

## 终端边界

默认命令策略只允许少数精确的版本报告命令。它是一个面向开发安全的基线，而不是可用于 Terminal-Bench 的实用 shell。

模型可见的 terminal stdout/stderr 保持有界；输出被截断时，完整文本可以保存到可信的 run artifact 目录。

在实现 Terminal-Bench 支持时，通用终端访问应当开放在该基准的官方容器或其他隔离执行环境中。主机侧命令执行仍应保持收窄。
