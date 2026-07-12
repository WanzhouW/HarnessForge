# Phase 0 状态

状态日期：2026-07-11

## 结论

HarnessForge 满足 Phase 0 的验收标准，可以作为干净的基线骨架。当前状态适合
在开始真实模型 Provider 工作前标记为 `phase0-clean-skeleton` 里程碑。

## 当前支持能力

- 显式的“模型动作 / 工具观察”智能体循环；
- 用于测试的确定性脚本化模型后端；
- 任务、预算、轨迹、工具调用和运行结果结构；
- 任务作用域内的工具注册，以及结构化 `ToolResult`；
- 受工作区保护的目录列表、UTF-8 文件读取、字面量搜索和精确替换；
- 有意收窄能力范围并设置 `shell=False` 的终端接口；
- 同步 JSONL 轨迹日志；
- 仅包含接口的 Terminal-Bench 和 SWE-bench 适配器桩。

## 当前明确不支持能力

- 真实 LLM Provider 或在线模型 API 调用；
- Terminal-Bench 或 SWE-bench 的官方任务加载与评估；
- 基准容器创建或生命周期管理；
- 通用的基准任务终端策略；
- Debug 工作流或 pytest 自动修复循环；
- 用户配置、持久化会话、M5 记忆、检索或对话摘要；
- 动态技能发现或 `workspace/skills` 加载；
- 跨任务状态。

## 测试结果

以下命令执行成功：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

结果：共运行 13 项测试，13 项全部通过。

## CyberClaw 依赖检查

对 `src/` 和 `tests/` 下的 Python 源码进行不区分大小写的搜索，没有发现
`from cyberclaw ...`、`import cyberclaw` 或 `cyberclaw.*` 依赖。项目文档中
仅可为了记录来源和有意排除的内容而提及 CyberClaw。

## 禁止模块检查

默认源码和测试路径中不存在 Debug 工作流、pytest 自动修复、`ProfileStore`、
`SessionStore`、M5 记忆、对话摘要、动态技能、`workspace/skills` 或跨任务状态的
实现与加载路径。基线系统提示词明确要求模型不要假定 Debug 工作流、持久记忆
或跨任务状态；这段文字是约束，不是这些功能的实现。

## Phase 0 判定

Phase 0 验收通过。Phase 1 可以在继续保持本文所列排除项和任务隔离的前提下，
增加 Provider 抽象。
