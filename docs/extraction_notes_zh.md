# 提取说明

HarnessForge 复制的是设计理念，而不是 CyberClaw 的运行时依赖。

| HarnessForge 模块 | CyberClaw 参考 | 保留 | 移除或变更 |
| --- | --- | --- | --- |
| `safety/workspace.py` | `cyberclaw/workspace.py` | 解析后的根目录边界、路径遍历拒绝、敏感路径策略 | CyberClaw 导入和产品工作区假设；新的文档字符串区分了主机边界与容器隔离 |
| `tools/registry.py` | `cyberclaw/tools.py` | 命名注册、查找、基础 schema 检查 | 打印、LangChain 转换、时间 / 计算器 / 用户配置工具、默认注册表、动态技能 |
| `tools/filesystem.py` | `cyberclaw/coding_tools.py` | 有边界的目录列表和 UTF-8 文本读取 | 纯自然语言结果和基于闭包的构造方式 |
| `tools/search.py` | `cyberclaw/coding_tools.py` | 有边界的递归字面量搜索、跳过二进制 / 大文件 | 记忆笔记副作用和产品日志 |
| `tools/edit.py` | `cyberclaw/coding_tools.py` | 精确唯一替换和统一 diff | 仓库内备份目录和恢复工作流 |
| `tools/terminal.py` | `cyberclaw/coding_tools.py` | `shell=False`、argv 解析、超时、结构化输出 | pytest 特定失败语义，以及“主机白名单就是通用基准终端”的主张 |
| `agent/loop.py` | `cyberclaw/agent.py` | 模型动作 → 工具结果 → 下一动作的控制流 | LangGraph、Debug 工作流、用户配置、会话、M5 记忆、摘要、动态技能 |
| `logging/` | `cyberclaw/logger.py` | JSONL 事件理念 | 后台线程和隐式全局 logger；写入改为同步且显式 |
| `harness/` | `cyberclaw/benchmark_runner.py` 和 `benchmark_memory.py` | 任务 / 结果分离、工具计数尝试 | `expect_contains`、共享用户配置、内部 fixtures、记忆指标，以及未实现的验证器声明 |

新项目不直接导入 CyberClaw，因为这样会让基线随 CyberClaw 的交互式运行时漂移，并重新引入隐藏变量。

Debug 工作流被排除，是因为公开终端任务并不统一都是 pytest 修复任务。自动测试 / 修复 / 重新测试的外层循环会在基线智能体循环之外增加额外模型调用和任务特定策略。

记忆、用户配置和会话组件被排除，是因为基线必须让每个任务从全新状态开始。它们会改变提示词，可能触发额外模型调用，并产生跨任务泄漏风险。它们未来可以回归，但只能作为显式声明、单独度量的实验策略。
