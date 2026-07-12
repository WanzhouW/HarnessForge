# HarnessForge TodoList

本文档用于指导 HarnessForge 从当前的 **clean baseline skeleton** 迭代为可以运行公开 benchmark 的 **benchmark-ready baseline agent**。

当前项目定位：

- HarnessForge 是独立于 CyberClaw 的 benchmark-facing terminal agent harness baseline。
- 当前 baseline 默认不包含 Debug workflow、自动 pytest repair、用户画像、持久 session、M5 memory、conversation summarization、dynamic skills 和跨任务状态。
- 当前项目已有基础 agent loop、tool registry、workspace guard、文件工具、窄 terminal、trajectory logging 和 Terminal-Bench/SWE-bench adapter stub。
- 当前项目还不能直接作为公开 benchmark 实验 baseline，因为还缺真实 LLM provider、公开 benchmark adapter、容器生命周期、official evaluator、token/cost 指标和可复现实验 manifest。

---

## 全局配置与数据格式约定

为避免同一种配置同时维护 JSON 和 YAML 两套入口，后续阶段统一遵循：

- **YAML**：只用于人编写和版本控制的 Provider、benchmark、baseline 与
  experiment 配置；
- **JSONL**：用于按条追加、流式读取和断点恢复的 trajectory、benchmark
  predictions 与逐实例结果；
- **JSON**：用于一个 run 的结构化结果、manifest 或 summary；
- **Markdown**：用于给人阅读的汇总报告和说明文档。

官方 benchmark 已规定输入输出格式时，以官方格式为准。例如 SWE-bench 的
prediction 使用官方 JSONL schema，不得为了和 HarnessForge 配置统一而改写成
YAML。

配置加载层应当保持单一：Phase 2.5 只支持命令行参数和 `.env`；Phase 4 首次
引入 benchmark YAML 解析后，Phase 6 和 Phase 7 必须复用、扩展同一个 YAML
配置加载与校验层，不得另建语义重叠的 JSON 配置系统。

---

## Phase 0：工程状态确认与 baseline skeleton 冻结

### 目标

确认当前 HarnessForge 是一个干净、可回滚、没有 CyberClaw 主线污染的 baseline skeleton。

### 需要完成

- 运行全部单元测试。
- 检查代码中是否直接 import CyberClaw。
- 检查是否误引入 Debug、Memory、Profile、Session、dynamic skills。
- 记录当前状态，作为 Phase 0 基线。
- 补充一份 `docs/phase0_status.md`，说明当前 baseline 支持什么、不支持什么。

### 验收标准

- 所有测试通过。
- `src/` 和 `tests/` 中没有 `cyberclaw` import。
- baseline 默认路径不包含 Debug、Memory、Profile、Session、dynamic skills。
- 当前版本可以被标记为 `phase0-clean-skeleton`。

### 给 Codex 的 Prompt

```text
你是一个严谨的 AI Coding 项目验收助手。

当前项目是 HarnessForge，路径为：

D:\vsc\HarnessForge

目标：对当前 Phase 0 baseline skeleton 做交付自检，不要开发新功能，只做检查、必要的小修复和文档记录。

请完成以下任务：

1. 在项目根目录运行测试：

   $env:PYTHONPATH = "src"
   python -m unittest discover -s tests -v

2. 搜索代码中是否存在 CyberClaw 直接依赖：

   Select-String -Path .\src\**\*.py,.\tests\**\*.py -Pattern "cyberclaw" -CaseSensitive:$false

3. 检查 baseline 默认路径是否误引入以下内容：
   - Debug workflow
   - automatic pytest repair
   - ProfileStore
   - SessionStore
   - M5 memory
   - conversation summarization
   - dynamic skills
   - workspace/skills loading
   - cross-task state

4. 如果测试失败，只允许做最小修复，不允许新增大功能。

5. 新增文档：

   docs/phase0_status.md

   文档需要包含：
   - 当前支持能力
   - 当前明确不支持能力
   - 测试结果
   - CyberClaw 依赖检查结果
   - 禁止模块检查结果
   - 当前是否可以作为 clean baseline skeleton

禁止事项：

- 不要修改 CyberClaw 原项目。
- 不要引入真实模型 API。
- 不要实现 Terminal-Bench。
- 不要实现 SWE-bench。
- 不要加入 memory、debug、profile、session、dynamic skills。
- 不要扩大 terminal command policy。

完成后输出：
- 测试结果
- 修改文件列表
- 是否存在 CyberClaw import
- 是否存在禁止模块
- Phase 0 是否验收通过
```

---

## Phase 1：接入真实 LLM Provider

### 目标

把 HarnessForge 从 scripted-model test backend 升级为真正可以调用 LLM API 的 agent baseline。

### 需要完成

新增模块：

```text
src/harness_forge/providers/
  __init__.py
  base.py
  openai_compatible.py
  openai_chat_completions.py
```

需要实现：

- `ProviderConfig`
- `ModelMessage`
- `ModelResponse`
- `ToolCall`
- `LLMProvider`
- `OpenAICompatibleProvider`
- `OpenAIChatCompletionsProvider`
- `PROVIDER_API=responses|chat_completions` 协议选择
- usage 统计字段预留
- timeout / retry 基础机制
- temperature / max_tokens / model_name 配置

### 保留要求

- scripted model 继续保留，用于单元测试。
- 真实 provider 不应该影响 smoke test。
- provider 不应该引入 memory、summary、profile。
- provider 不应该改变 baseline 工具集。

### 验收标准

- 可以用 fake provider 跑通测试。
- 可以通过环境变量配置 OpenAI-compatible API，并明确区分 Responses 与
  Chat Completions；DeepSeek 等只兼容 `/chat/completions` 的服务不得误走
  `/responses`。
- Agent loop 能从真实 provider 获取 tool call 或 final answer。
- `AgentRunResult` 中能记录 model name、model calls 和 usage 字段，即使部分 provider 暂时返回空 usage。

### 给 Codex 的 Prompt

```text
你是一个资深 AI Coding 工程助手。

当前项目是 HarnessForge，路径为：

D:\vsc\HarnessForge

现在进入 Phase 1：接入真实 LLM Provider。

目标：在不破坏当前 scripted model 测试后端的前提下，为 HarnessForge 增加 OpenAI-compatible provider，使 agent loop 后续可以调用真实模型 API。

请完成以下任务：

1. 新增 provider 模块：

   src/harness_forge/providers/
     __init__.py
     base.py
     openai_compatible.py

2. 在 base.py 中定义：
   - ProviderConfig
   - ModelMessage
   - ToolCall
   - ModelResponse
   - LLMProvider 抽象接口

3. 在 openai_compatible.py 中实现 OpenAICompatibleProvider。

   要求：
   - 使用 Python 标准库优先；如果当前 pyproject 没有依赖，不要随意新增依赖。
   - 支持 OPENAI_API_KEY / OPENAI_BASE_URL / MODEL_NAME 等环境变量或显式 config。
   - 支持 temperature、max_tokens、timeout。
   - 支持基础 retry。
   - 返回 ModelResponse。
   - 预留 input_tokens、output_tokens、total_tokens、cost 字段。
   - 不要硬编码任何真实密钥。

4. 修改 agent loop，使它可以同时支持：
   - scripted/fake model backend
   - LLMProvider backend

5. 保持现有测试通过，并新增 provider 相关测试：
   - fake provider 测试
   - provider config 测试
   - 不需要真实 API key 的单元测试

6. 更新文档：
   - README.md
   - docs/architecture.md
   - docs/baseline_scope.md

   说明当前已经支持 provider abstraction，但真实 benchmark 仍未接入。

禁止事项：

- 不要实现 Terminal-Bench。
- 不要实现 SWE-bench。
- 不要加入 memory。
- 不要加入 Debug workflow。
- 不要加入 dynamic skills。
- 不要修改 CyberClaw。
- 不要把真实 API key 写进代码或文档。
- 不要让单元测试依赖真实网络请求。

完成后运行：

$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v

最终输出：
- 新增/修改文件列表
- 测试结果
- provider 如何配置
- 当前是否仍保持 clean baseline
```

---

## Phase 2：完善 Runner、Result Schema 与 BudgetManager

### 目标

让 HarnessForge 可以稳定运行一个本地 task，并生成完整、可分析、可复现的运行结果。

### 需要完成

重点完善：

```text
src/harness_forge/harness/runner.py
src/harness_forge/harness/result_schema.py
src/harness_forge/harness/budgets.py
src/harness_forge/logging/trajectory.py
```

新增或完善字段：

- `run_id`
- `task_id`
- `attempt_id`
- `model_config`
- `prompt_version`
- `enabled_tools`
- `max_steps`
- `max_tool_calls`
- `wall_time_limit`
- `model_call_count`
- `tool_call_count`
- `stop_reason`
- `harness_success`
- `benchmark_success`
- `official_score`
- `trajectory_path`
- `artifact_path`
- `errors`

### 验收标准

- 任意 toy task 可以完整运行。
- 每次运行生成结构化 `AgentRunResult`。
- 每次运行生成 JSONL trajectory。
- 超过 max_steps / max_tool_calls / wall_time 时能正常停止，并记录 stop reason。
- `success` 不再和 benchmark score 混淆。

### 给 Codex 的 Prompt

```text
你是一个资深 AI Coding 工程助手。

当前项目是 HarnessForge，路径为：

D:\vsc\HarnessForge

现在进入 Phase 2：完善 Runner、Result Schema 与 BudgetManager。

目标：让 HarnessForge 能稳定运行一个本地 toy task，并输出完整 AgentRunResult 和 JSONL trajectory，为后续公开 benchmark adapter 做准备。

请完成以下任务：

1. 完善以下文件：

   src/harness_forge/harness/runner.py
   src/harness_forge/harness/result_schema.py
   src/harness_forge/harness/budgets.py
   src/harness_forge/logging/trajectory.py

2. 明确区分：

   - harness_success：agent loop 是否正常完成
   - benchmark_success：官方 benchmark evaluator 是否通过，当前阶段可以为 None
   - official_score：官方 benchmark 分数，当前阶段可以为 None

3. AgentRunResult 至少包含：

   - run_id
   - task_id
   - attempt_id
   - instruction
   - workspace_root
   - model_config
   - prompt_version
   - enabled_tools
   - max_steps
   - max_tool_calls
   - wall_time_limit
   - model_call_count
   - tool_call_count
   - stop_reason
   - harness_success
   - benchmark_success
   - official_score
   - final_answer
   - trajectory
   - trajectory_path
   - artifact_path
   - errors

4. BudgetConfig 至少支持：

   - max_steps
   - max_tool_calls
   - wall_time_seconds
   - max_model_calls
   - 预留 max_input_tokens / max_output_tokens / max_cost

5. Runner 需要做到：

   - 每个 task 生成独立 run_id
   - 每次运行有 attempt_id
   - 记录 stop_reason
   - 预算耗尽时正常停止
   - 写 JSONL trajectory
   - 不调用官方 evaluator

6. 新增或更新测试：

   - 正常完成 toy task
   - max_steps 触发停止
   - max_tool_calls 触发停止
   - trajectory 文件存在且非空
   - benchmark_success 当前为 None

7. 更新文档：

   - docs/architecture.md
   - docs/baseline_scope.md

禁止事项：

- 不要接 Terminal-Bench。
- 不要接 SWE-bench。
- 不要加入 Debug workflow。
- 不要加入 memory。
- 不要扩大 terminal command policy。
- 不要修改 CyberClaw。

完成后运行：

$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v

最终输出：
- 修改文件列表
- 测试结果
- Runner 当前能力
- 当前还不能代表 official benchmark score 的说明
```

---

## Phase 2.5：实现主程序入口与本地任务 CLI

### 目标

在 Phase 2 已经稳定 Runner、Result Schema 和 BudgetManager 之后，为
HarnessForge 增加一个薄的主程序入口，让用户无需自己编写 Python 调用脚本，
即可检查环境并运行一个本地 task。

主程序入口只负责解析配置、构建现有对象、调用 Runner 和展示结果，不得复制
agent loop、预算、工具或 benchmark adapter 的业务逻辑。

### 需要完成

新增或修改：

```text
src/harness_forge/cli.py
src/harness_forge/__main__.py
pyproject.toml
```

提供两种等价入口：

```powershell
python -m harness_forge ...
harnessforge ...
```

最小命令集：

```text
harnessforge doctor
harnessforge run
```

`doctor` 需要检查：

- Python 版本是否满足项目要求；
- `openai` 和 `python-dotenv` 是否可用；
- `.env` 是否存在；
- `MODEL_NAME`、`OPENAI_BASE_URL` 和 API key 配置状态；
- Provider 是否可以在不发送网络请求的情况下完成初始化；
- 不得输出 API key 原文。

`run` 至少支持：

- `--task-id`
- `--instruction`
- `--workspace`
- `--tools`
- `--model`
- `--base-url`
- `--temperature`
- `--max-tokens`
- `--max-steps`
- `--max-model-calls`
- `--max-tool-calls`
- `--wall-time`
- `--trajectory-path`
- `--result-path`

配置优先级固定为：

```text
命令行参数 > 进程环境变量 / .env > 代码默认值
```

Phase 2.5 只实现命令行参数和 `.env` 配置，不新增 task JSON 配置系统，也不在
此阶段提前建立完整 YAML 实验配置系统。Phase 4、Phase 6 和 Phase 7 需要的
benchmark / experiment YAML 应复用后续统一的配置加载层，避免维护两套相互
重叠的 JSON/YAML 配置入口。

建议使用 Python 标准库 `argparse`，不引入 Click 或 Typer。控制台命令通过
`pyproject.toml` 注册：

```toml
[project.scripts]
harnessforge = "harness_forge.cli:main"
```

### 退出码

```text
0 = harness 正常完成
1 = agent / harness 运行失败
2 = 命令参数或配置错误
3 = Provider 初始化或 API 调用错误
```

退出码只表示 harness 运行状态，不得伪装成 official benchmark pass/fail。

### 验收标准

- `python -m harness_forge --help` 可以运行；
- 安装项目后 `harnessforge --help` 可以运行；
- `doctor` 可以给出清晰且不泄漏密钥的本地环境检查结果；
- `run` 可以通过命令行参数运行一个本地 toy task；
- CLI 可以生成 Phase 2 定义的 result JSON 和 JSONL trajectory；
- CLI 只调用 `HarnessRunner`，不重复实现 agent loop 或预算逻辑；
- CLI 测试使用 fake provider，不需要真实 API key 或网络；
- 当前仍不声称支持 official Terminal-Bench 或 SWE-bench。

### 给 Codex 的 Prompt

```text
你是一个资深 Python CLI 与 AI Coding 工程助手。

当前项目是 HarnessForge，路径为：

D:\vsc\HarnessForge

现在进入 Phase 2.5：实现主程序入口与本地任务 CLI。

前置条件：Phase 2 的 Runner、AgentRunResult、BudgetConfig 和 trajectory 接口已经
稳定。如果这些接口尚未完成，不要在 CLI 中自行补一套临时实现。

目标：让用户可以通过 `python -m harness_forge` 或安装后的 `harnessforge`
命令检查环境并运行一个本地 toy task。

请完成以下任务：

1. 新增：

   src/harness_forge/cli.py
   src/harness_forge/__main__.py

2. 在 pyproject.toml 中注册：

   [project.scripts]
   harnessforge = "harness_forge.cli:main"

3. 使用标准库 argparse 实现：

   - harnessforge doctor
   - harnessforge run

4. doctor 只做本地检查，默认不得发送模型请求或消耗 token。检查 Python 版本、
   依赖、.env、模型配置和 Provider 初始化状态，不得打印 API key。

5. run 从命令行参数和 .env 构建：

   - ProviderConfig
   - 由 `PROVIDER_API` 选择的 Responses 或 Chat Completions Provider
   - TaskSpec
   - RunConfig
   - BudgetConfig

   然后只调用 HarnessRunner，不要在 CLI 中复制 agent loop、工具或预算逻辑。

6. run 至少支持 task id、instruction、workspace、enabled tools、模型参数、预算、
   trajectory path 和 result path。

7. 配置优先级：

   命令行参数 > 进程环境变量 / .env > 代码默认值

8. 当前阶段不要新增 task JSON loader，也不要提前建立完整 YAML 配置系统。
   Phase 4/6/7 的 YAML 配置由后续统一配置加载层负责。

9. 定义稳定退出码：

   - 0：harness 正常完成
   - 1：agent / harness 运行失败
   - 2：参数或配置错误
   - 3：Provider 错误

   不得把 harness 正常完成解释为 official benchmark pass。

10. 新增测试：

   - --help 可运行
   - doctor 配置完整/缺失场景
   - API key 不泄漏
   - fake provider 可以通过 CLI 跑完 toy task
   - 参数错误有清晰信息和退出码
   - result JSON 与 trajectory 文件生成
   - 测试不需要网络

11. 更新 README.md、README_zh.md 和 architecture 文档，说明安装、doctor、run、
    参数、退出码和当前限制。

禁止事项：

- 不要在 CLI 中复制 Runner 或 agent loop。
- 不要调用 official evaluator。
- 不要实现 Terminal-Bench 或 SWE-bench。
- 不要加入 Debug workflow、memory、profile、session 或 dynamic skills。
- 不要扩大 terminal command policy。
- 不要引入 JSON/YAML 双重配置系统。
- 不要让测试访问真实网络或要求真实 API key。

完成后运行：

$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v

最终输出：
- 新增/修改文件列表
- CLI 命令与参数说明
- 退出码说明
- 测试结果
- 当前仍不代表 official benchmark score 的说明
```

---

## Phase 3：增强基础工具集

### 目标

让 baseline agent 具备完成真实 coding/terminal task 的最低工具能力，但仍保持 baseline 干净。

### 需要完成

新增或增强工具：

```text
src/harness_forge/tools/diff.py
src/harness_forge/tools/patch.py
```

增强现有：

```text
src/harness_forge/tools/filesystem.py
src/harness_forge/tools/search.py
src/harness_forge/tools/edit.py
src/harness_forge/tools/terminal.py
```

建议工具能力：

- `get_diff`
- `write_file`
- `apply_patch`
- `read_file` 分块读取
- `search_text` 支持 glob / regex / case-sensitive
- `list_dir` 支持更清晰的截断信息
- terminal 输出写 artifact 文件
- stdout/stderr 截断但保留完整版本到 artifact

### 验收标准

- 可以修改已有文件。
- 可以新建文件。
- 可以生成 diff。
- 可以应用 patch。
- 大文件读取不会爆上下文。
- terminal 输出可追踪。
- 所有工具仍经过 WorkspaceGuard。

### 给 Codex 的 Prompt

```text
你是一个资深 AI Coding 工程助手。

当前项目是 HarnessForge，路径为：

D:\vsc\HarnessForge

现在进入 Phase 3：增强基础工具集。

目标：让 baseline agent 具备完成真实 coding/terminal task 的最低工具能力，但仍保持 baseline 干净，不引入 Debug workflow 或 memory。

请完成以下任务：

1. 新增工具文件：

   src/harness_forge/tools/diff.py
   src/harness_forge/tools/patch.py

2. 实现或增强以下工具：

   - get_diff：查看 workspace 当前文件改动
   - write_file：新建或覆盖文件，需要 WorkspaceGuard
   - apply_patch：应用 unified diff patch，需要 WorkspaceGuard 和错误处理
   - read_file：支持 offset/limit 或 line range
   - search_text：支持 glob、regex、case_sensitive 参数
   - list_dir：输出明确截断信息
   - run_command：stdout/stderr 保留截断结果，并可把完整输出写入 artifact

3. 所有工具必须返回统一 ToolResult。

4. 所有文件路径必须经过 WorkspaceGuard。

5. 不要把工具输出设计成只有自然语言，要保留结构化字段。

6. 新增或更新测试：

   - write_file 能创建新文件
   - get_diff 能看到修改
   - apply_patch 能成功应用简单 patch
   - apply_patch 遇到非法路径要拒绝
   - read_file 分块读取正确
   - search_text regex/glob 可用
   - terminal 输出 artifact 可记录

7. 更新文档：

   - README.md
   - docs/architecture.md
   - docs/baseline_scope.md

禁止事项：

- 不要加入 Debug workflow。
- 不要自动 pytest repair。
- 不要加入 memory/profile/session。
- 不要加载 dynamic skills。
- 不要开放宿主机任意 shell。
- 不要实现 Terminal-Bench。
- 不要实现 SWE-bench。
- 不要修改 CyberClaw。

完成后运行：

$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v

最终输出：
- 新增/修改文件列表
- 工具能力变化
- 测试结果
- 是否仍保持 baseline 干净
```

---

## Phase 4：实现 Terminal-Bench 最小 Adapter

### 目标

优先接入 Terminal-Bench，让 HarnessForge 能跑通至少一个公开 benchmark task，并拿到官方 pass/fail。

### 需要完成

重点文件：

```text
src/harness_forge/benchmark_adapters/terminal_bench.py
src/harness_forge/benchmark_adapters/base.py
src/harness_forge/harness/runner.py
```

最小闭环：

```text
读取 Terminal-Bench task
→ 准备任务 workspace / container
→ 转成 TaskSpec
→ 调用 Runner
→ 调用官方 evaluator
→ 写 AgentRunResult
→ 写 official pass/fail
```

### 验收标准

- 可以跑通 1 个 Terminal-Bench task。
- 可以拿到 official evaluator 的 pass/fail。
- `benchmark_success` 不再总是 None。
- trajectory、artifact、official result 都能保存。
- 不伪造官方结果。
- 人工编写的 adapter 配置使用 YAML；trajectory 和逐任务机器记录继续使用
  JSONL，单次 official result 使用 JSON 或官方规定格式。

### 给 Codex 的 Prompt

```text
你是一个资深 AI Coding 工程助手。

当前项目是 HarnessForge，路径为：

D:\vsc\HarnessForge

现在进入 Phase 4：实现 Terminal-Bench 最小 Adapter。

目标：接入 Terminal-Bench 的最小闭环，让 HarnessForge 能跑通至少 1 个 Terminal-Bench task，并调用官方 evaluator 得到 pass/fail。

重要原则：

- 不要伪造已经支持完整 Terminal-Bench。
- 先跑通最小闭环，再考虑批量任务。
- 所有 official score 必须来自官方 evaluator 或官方任务验证逻辑。
- 如果本地没有 Terminal-Bench 数据或命令，请先实现 adapter 接口和清晰错误提示，不要写假结果。

请完成以下任务：

1. 完善：

   src/harness_forge/benchmark_adapters/base.py
   src/harness_forge/benchmark_adapters/terminal_bench.py

2. TerminalBenchAdapter 至少需要提供：

   - load_task(task_id or task_path)
   - prepare_workspace()
   - to_task_spec()
   - run_evaluator()
   - collect_result()
   - cleanup()

3. 与 Runner 对接：

   - adapter 负责准备 task
   - runner 负责运行 agent
   - adapter 负责调用 official evaluator
   - result_schema 负责保存 official result

4. 如果需要容器，请先做接口与文档说明；不要随意在宿主机开放任意 shell。

5. 新增配置示例：

   configs/benchmarks/terminal_bench.example.yaml

   这是后续 benchmark / experiment 共用 YAML 配置加载层的起点。配置解析、
   校验和错误格式需要设计为可被 Phase 6、Phase 7 复用，不要另建 JSON 配置
   入口。

6. 新增文档：

   docs/terminal_bench_adapter.md

   文档需要说明：
   - 如何配置 Terminal-Bench 路径
   - 如何运行单任务
   - 当前支持范围
   - 当前不支持范围
   - official evaluator 如何接入
   - terminal policy 如何处理

7. 新增测试：

   - adapter config 解析测试
   - 缺少 Terminal-Bench 数据时给出清晰错误
   - mock evaluator 返回 pass/fail 时能写入 AgentRunResult
   - 不需要真实下载 benchmark 的单元测试

禁止事项：

- 不要伪造 official pass/fail。
- 不要下载 benchmark。
- 不要把 mock evaluator 结果当成真实 benchmark 结果。
- 不要加入 Debug workflow。
- 不要加入 memory。
- 不要修改 CyberClaw。
- 不要开放宿主机任意 shell。

完成后运行：

$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v

最终输出：
- 新增/修改文件列表
- Terminal-Bench adapter 当前支持范围
- 如何运行单任务
- 测试结果
- 还缺什么才能跑完整 Terminal-Bench suite
```

---

## Phase 5：容器内 Terminal Policy 与任务生命周期

### 目标

把 terminal 能力从“宿主机窄命令”升级为“隔离环境中的通用 terminal”，为 Terminal-Bench 任务提供真实执行能力。

### 需要完成

新增或完善：

```text
src/harness_forge/safety/command_policy.py
src/harness_forge/harness/lifecycle.py
src/harness_forge/tools/terminal.py
```

区分：

```text
HostCommandPolicy
ContainerCommandPolicy
```

容器内可以逐步允许：

```text
ls
cat
grep
find
python
python -m pytest
pytest
pip
bash -lc
git diff
```

但必须支持：

- timeout
- cwd 限制
- stdout/stderr 截断
- 完整输出 artifact 保存
- 进程树清理
- 命令日志
- container lifecycle
- cleanup

### 验收标准

- Host 侧仍然窄。
- Container 侧可以为 benchmark 开放更通用命令。
- 所有命令可记录 trajectory。
- 命令超时可正常终止。
- 不会误把宿主机 shell 当成 benchmark shell。

### 给 Codex 的 Prompt

```text
你是一个资深 AI Coding 工程助手。

当前项目是 HarnessForge，路径为：

D:\vsc\HarnessForge

现在进入 Phase 5：实现容器内 Terminal Policy 与任务生命周期。

目标：区分宿主机安全策略和 benchmark 隔离环境策略。Host 侧继续保持窄命令，Container 侧为 Terminal-Bench 这类任务预留更通用 terminal 能力。

请完成以下任务：

1. 完善命令策略：

   src/harness_forge/safety/command_policy.py

   定义：
   - BaseCommandPolicy
   - HostCommandPolicy
   - ContainerCommandPolicy

2. HostCommandPolicy：
   - 继续只允许少量安全命令
   - 不允许任意 shell
   - 用于开发和单元测试

3. ContainerCommandPolicy：
   - 允许 benchmark 容器内常见命令
   - 例如 ls、cat、grep、find、python、pytest、pip、bash -lc、git diff
   - 必须支持显式 allowlist
   - 必须记录被拒绝命令

4. 新增 lifecycle 模块：

   src/harness_forge/harness/lifecycle.py

   设计接口：
   - setup()
   - workspace_root
   - run_command()
   - collect_artifacts()
   - cleanup()

   当前如果不实际控制 Docker，可以先实现 LocalIsolatedLifecycle / MockContainerLifecycle，但接口必须清晰。

5. 修改 terminal tool：
   - terminal tool 不直接决定所有命令策略
   - 由 lifecycle 或 command policy 注入
   - 命令结果写入 trajectory
   - stdout/stderr 截断，但完整输出可以保存 artifact

6. 新增测试：
   - Host policy 拒绝 bash -lc
   - Container policy 可允许 bash -lc
   - timeout 能停止
   - 被拒绝命令有明确错误
   - lifecycle cleanup 被调用

7. 更新文档：
   - docs/architecture.md
   - docs/baseline_scope.md
   - docs/terminal_bench_adapter.md

禁止事项：

- 不要在宿主机开放任意 shell。
- 不要默认允许危险命令。
- 不要实现 memory。
- 不要实现 Debug workflow。
- 不要修改 CyberClaw。
- 不要伪造官方 benchmark 结果。

完成后运行：

$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v

最终输出：
- 新增/修改文件列表
- HostCommandPolicy 与 ContainerCommandPolicy 差异
- 生命周期接口说明
- 测试结果
```

---

## Phase 6：实现 Metrics 与可复现实验 Manifest

### 目标

让每次实验都有可复现配置和完整指标，便于之后写论文或组会汇报。

### 需要完成

新增目录：

```text
configs/
  baseline.yaml
  providers/
  benchmarks/

experiments/
  manifests/
  results/
```

格式职责固定为：

- `configs/**/*.yaml`：人工编写的实验配置；
- `experiments/manifests/*.json`：单次运行 manifest；
- `experiments/results/*.json`：单次或聚合 summary；
- `experiments/results/*.jsonl`：逐任务、逐实例的可追加记录；
- `experiments/results/*.md`：面向人的汇总报告。

Phase 6 必须复用 Phase 4 建立的 YAML 配置加载与校验层，并将其扩展到 provider、
baseline 和 benchmark 配置；不要再实现语义重叠的 JSON 配置 loader。

新增或完善：

```text
src/harness_forge/harness/metrics.py
src/harness_forge/harness/manifest.py
```

记录内容：

- git commit
- dirty status
- model name
- provider config
- temperature
- max_tokens
- max_steps
- max_tool_calls
- tool schema hash
- prompt hash
- benchmark version
- task subset
- container image
- start/end time
- official score
- harness metrics

### 指标

主指标：

```text
official_pass_rate
official_score
```

补充指标：

```text
model_calls
input_tokens
output_tokens
cost
tool_calls
terminal_calls
read_file_calls
repeated_reads
wall_time
command_time
patch_size
stop_reason
```

### 验收标准

- 每个 run 都有 manifest。
- 每个 task 都有 metrics。
- 可以生成 summary JSON / Markdown。
- 能区分 official metric 和 harness diagnostic metric。

### 给 Codex 的 Prompt

```text
你是一个资深 AI Coding 工程助手。

当前项目是 HarnessForge，路径为：

D:\vsc\HarnessForge

现在进入 Phase 6：实现 Metrics 与可复现实验 Manifest。

目标：让每次实验都能保存可复现配置、运行环境、模型配置、prompt/tool hash、official score 和 harness diagnostic metrics。

请完成以下任务：

1. 新增目录：

   configs/
     baseline.yaml
     providers/
     benchmarks/

   experiments/
     manifests/
     results/

   YAML 只承载人工配置；manifest 和 summary 使用 JSON，逐任务记录使用
   JSONL，面向人的报告使用 Markdown。

2. 新增模块：

   src/harness_forge/harness/metrics.py
   src/harness_forge/harness/manifest.py

3. Manifest 至少记录：

   - run_id
   - timestamp
   - git_commit
   - dirty_status
   - model_name
   - provider_name
   - temperature
   - max_tokens
   - max_steps
   - max_tool_calls
   - prompt_hash
   - tool_schema_hash
   - benchmark_name
   - benchmark_version
   - task_subset
   - container_image
   - config_path

4. Metrics 至少支持：

   主指标：
   - official_pass_rate
   - official_score

   诊断指标：
   - model_calls
   - input_tokens
   - output_tokens
   - cost
   - tool_calls
   - terminal_calls
   - read_file_calls
   - repeated_reads
   - wall_time
   - command_time
   - patch_size
   - stop_reason

5. 修改 AgentRunResult，使其可以携带 metrics 和 manifest path。

6. 新增 summary 脚本或函数：
   - 输入多个 task result
   - 输出 summary JSON
   - 输出 summary Markdown

7. 新增测试：
   - manifest 可生成
   - prompt/tool hash 稳定
   - metrics 可聚合
   - official metric 和 diagnostic metric 不混淆

8. 更新文档：
   - docs/baseline_scope.md
   - docs/architecture.md
   - README.md

禁止事项：

- 不要接入新的复杂 benchmark。
- 不要加入 memory。
- 不要加入 Debug workflow。
- 不要修改 CyberClaw。
- 不要把 harness_success 当作 official_pass_rate。

完成后运行：

$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v

最终输出：
- 新增/修改文件列表
- manifest 字段说明
- metrics 字段说明
- 测试结果
```

---

## Phase 7：建立正式实验对照组

### 目标

把 HarnessForge 的实验设计固定下来，为后续 harness 改进论文做对照。

### 对照组设计

#### Baseline A：Minimal Terminal Agent

```text
真实 LLM provider
+ explicit ReAct loop
+ 基础工具
+ 无 memory
+ 无 debug
+ 无 summary
+ 无 dynamic skills
```

#### Baseline B：Safety Harness Agent

```text
Baseline A
+ WorkspaceGuard
+ CommandPolicy
+ structured trajectory
+ BudgetManager
```

#### Method C：Improved Harness Agent

后续逐项加入：

```text
context governance
tool-call suppression
repeated-read reduction
verifier feedback structuring
failure recovery policy
```

### 需要完成

- 新增 `configs/experiments/`。
- 固定 baseline prompt。
- 固定工具集。
- 固定预算。
- 固定模型参数。
- 输出实验对照说明文档。

### 验收标准

- 每组实验的差异是明确的。
- 不会把多个改动混在一起。
- 每个实验组都有 config。
- 可以用同一批任务重复运行。

### 给 Codex 的 Prompt

```text
你是一个资深 AI Coding 实验设计助手。

当前项目是 HarnessForge，路径为：

D:\vsc\HarnessForge

现在进入 Phase 7：建立正式实验对照组。

目标：把 HarnessForge 后续论文/组会实验中的 baseline 和 method 组固定下来，避免控制变量混乱。

请完成以下任务：

1. 新增配置目录：

   configs/experiments/

2. 新增配置文件：

   configs/experiments/baseline_a_minimal.yaml
   configs/experiments/baseline_b_safety_harness.yaml
   configs/experiments/method_c_improved_harness.yaml

3. 三组定义如下：

   Baseline A：Minimal Terminal Agent
   - 真实 LLM provider
   - explicit ReAct loop
   - 基础工具
   - 无 memory
   - 无 debug
   - 无 summary
   - 无 dynamic skills

   Baseline B：Safety Harness Agent
   - Baseline A
   - WorkspaceGuard
   - CommandPolicy
   - structured trajectory
   - BudgetManager

   Method C：Improved Harness Agent
   - Baseline B
   - 后续逐项加入 context governance、tool-call suppression、repeated-read reduction、verifier feedback structuring、failure recovery policy

4. 新增文档：

   docs/experiment_groups.md

   文档需要说明：
   - 每组包含什么
   - 每组不包含什么
   - 每组之间唯一差异是什么
   - 为什么不能把 memory/debug/profile 放入 baseline
   - 如何保证模型、工具、prompt、预算固定

5. 修改 manifest，使其能记录 experiment_group。

6. 新增测试：
   - 三个 config 可以被加载
   - experiment_group 能写入 manifest
   - baseline A/B/C 的关键开关符合预期

禁止事项：

- 不要实现 Method C 的具体优化策略。
- 不要加入 memory。
- 不要加入 Debug workflow。
- 不要加入 profile/session。
- 不要修改 CyberClaw。
- 不要改变默认 baseline 行为。

完成后运行：

$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v

最终输出：
- 新增/修改文件列表
- 三组实验定义
- 测试结果
- 后续哪一组可以先跑 Terminal-Bench
```

---

## Phase 8：SWE-bench Adapter 预研与最小接口

### 目标

在 Terminal-Bench 基本跑通后，再预研 SWE-bench。不要在早期把复杂度拉满。

### 需要完成

完善：

```text
src/harness_forge/benchmark_adapters/swe_bench.py
docs/swe_bench_adapter.md
configs/benchmarks/swe_bench.example.yaml
```

SWE-bench 需要能力：

- instance loader
- repo checkout
- base commit 校验
- patch export
- official evaluator
- fail-to-pass tests
- pass-to-pass tests
- 依赖构建
- 环境隔离
- 官方 SWE-bench prediction JSONL 导出
- official result JSON / instance result JSONL 收集

格式边界：HarnessForge 的 SWE-bench 运行参数使用 YAML；官方 dataset instance
保持官方字段结构；提交给 evaluator 的 prediction 必须使用官方 JSONL schema，
至少保留 `instance_id`、`model_name_or_path` 和 `model_patch`。不得把 instance、
prediction 或逐实例 evaluator 结果改造成 HarnessForge 自定义 YAML。

### 验收标准

- 有清晰 adapter 接口。
- 有清晰文档。
- 不伪造支持完整 SWE-bench。
- 可以用 mock instance 测试 patch export 流程。
- 可以把 mock patch 导出为官方 schema 兼容的 prediction JSONL。
- 真正运行 SWE-bench 放到后续阶段。

### 给 Codex 的 Prompt

```text
你是一个资深 AI Coding 工程助手。

当前项目是 HarnessForge，路径为：

D:\vsc\HarnessForge

现在进入 Phase 8：SWE-bench Adapter 预研与最小接口。

注意：只有在 Terminal-Bench 最小闭环基本完成后，才应该进入这个阶段。

目标：为 SWE-bench 支持设计最小 adapter 接口和文档，不要伪造已经完整支持 SWE-bench。

请完成以下任务：

1. 完善：

   src/harness_forge/benchmark_adapters/swe_bench.py

   并新增人工配置示例：

   configs/benchmarks/swe_bench.example.yaml

2. 设计 SWEBenchAdapter 接口：

   - load_instance()
   - checkout_repo()
   - validate_base_commit()
   - to_task_spec()
   - export_patch()
   - run_official_evaluator()
   - collect_result()
   - cleanup()

   Adapter 需要能导出官方 SWE-bench prediction JSONL。每行至少包含：

   - instance_id
   - model_name_or_path
   - model_patch

   人工运行参数使用 YAML；官方 prediction、逐实例结果和 trajectory 使用 JSONL；
   单次汇总结果使用 JSON。不要建立表达同一配置的 JSON/YAML 双入口。

3. 新增文档：

   docs/swe_bench_adapter.md

   文档需要说明：
   - SWE-bench 与 Terminal-Bench 的差异
   - 需要 repo checkout
   - 需要 patch export
   - 需要 official evaluator
   - 需要 fail-to-pass / pass-to-pass tests
   - 当前阶段只做接口，不声称完整支持

4. 新增测试：
   - mock SWE-bench instance 可以加载
   - patch export 可以从 toy repo 生成
   - prediction JSONL 符合官方字段结构且可以逐行解析
   - 缺少真实 SWE-bench 数据时给出清晰错误
   - mock evaluator 可以把结果写入 AgentRunResult

禁止事项：

- 不要下载 SWE-bench。
- 不要运行真实 SWE-bench evaluator。
- 不要伪造 official score。
- 不要加入 Debug workflow。
- 不要加入 memory。
- 不要修改 CyberClaw。
- 不要让 SWE-bench 复杂度影响 Terminal-Bench 主线。

完成后运行：

$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v

最终输出：
- 新增/修改文件列表
- SWE-bench adapter 当前支持范围
- 当前明确不支持范围
- 测试结果
- 后续真正接 SWE-bench 还缺什么
```

---

# 总优先级总结

## 当前最重要的路线

```text
Phase 0：确认 skeleton 干净
→ Phase 1：接真实 LLM provider
→ Phase 2：完善 runner/result/budget
→ Phase 2.5：实现主程序入口与本地任务 CLI
→ Phase 3：增强基础工具
→ Phase 4：接 Terminal-Bench 最小 adapter
→ Phase 5：容器内 terminal policy
→ Phase 6：metrics + manifest
→ Phase 7：实验对照组
→ Phase 8：SWE-bench 预研
```

## 不要过早做的事情

- 不要一开始做 Self-Harness 自动优化。
- 不要一开始加 memory。
- 不要一开始加 Debug workflow。
- 不要一开始做复杂 SWE-bench。
- 不要把多个 harness 改进一起塞进 baseline。
- 不要让 baseline 变成“已经有很多策略加成的 method”。

## 当前项目定位

当前 HarnessForge 应该被描述为：

```text
一个干净、独立、可复现的 benchmark-facing terminal agent harness skeleton。
```

下一阶段目标是把它升级为：

```text
一个可以接真实 LLM、运行 Terminal-Bench 单任务、调用官方 evaluator 的 benchmark-ready baseline agent。
```
