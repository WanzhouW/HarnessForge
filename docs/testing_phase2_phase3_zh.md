# Phase 2–3 测试指南

本文用于验证 Phase 2 的 Runner/Result/Budget、Phase 2.5 的 CLI，以及 Phase 3
的工具能力。以下测试都不会调用官方 benchmark evaluator。

## 环境准备

```powershell
conda activate aiagent
cd D:\vsc\HarnessForge
python --version
python -m pip install -e .
python -m pip check
```

预期：Python 为 3.11 或更高版本，`pip check` 输出
`No broken requirements found`。

## 自动化测试

运行全部测试：

```powershell
python -m unittest discover -s tests -v
```

按阶段分别运行：

```powershell
python -m unittest discover -s tests -p "test_runner_phase2.py" -v
python -m unittest discover -s tests -p "test_cli.py" -v
python -m unittest discover -s tests -p "test_providers.py" -v
python -m unittest discover -s tests -p "test_phase3_tools.py" -v
```

预期：每项测试末尾为 `ok`，命令最终输出 `OK`。

自动化测试使用的确定性输入和预期结果如下：

| 功能 | 测试输入 | 预期输出 |
| --- | --- | --- |
| 正常运行 | scripted model 返回 `done` | `harness_success=true`、`benchmark_success=null`，result 和 trajectory 文件存在 |
| 步骤预算 | `max_steps=1`，模型返回一个工具动作 | `stop_reason=max_steps` |
| 模型预算 | 两个 scripted 动作，`max_model_calls=1` | 只调用模型一次，`stop_reason=max_model_calls` |
| 工具预算 | 工具动作配合 `max_tool_calls=0` | 工具不执行，`stop_reason=max_tool_calls` |
| 墙钟预算 | 模型睡眠时间超过限制 | `stop_reason=wall_time` |
| Token 预算 | Provider 报告 11 个输入 token，上限为 10 | `stop_reason=max_input_tokens` |
| Provider 协议 | `PROVIDER_API=chat_completions` | 工厂选择 Chat Completions 后端，工具 schema 包含嵌套 `function` |
| Chat 工具回传 | assistant tool call 加 tool result | 请求包含 `assistant.tool_calls` 和匹配的 `tool_call_id` |
| 多工具响应 | 一次模型响应返回两个 `read_file` 调用 | 两个工具分别在连续 step 执行，只产生一次初始模型调用，结果一起回传后再请求最终答案 |
| 新建文件 | `write_file(created.txt, "created\n")` | 文件创建成功，`get_diff` 包含 `+created` |
| 分块读取 | `start_line=2`、`line_count=2` | 只返回第 2–3 行，`has_more=true` |
| 正则与 glob 搜索 | 正则 `value\d+`、glob `src/*.py` | 只返回 Python 文件中的匹配行 |
| 应用补丁 | unified diff 把 `old value` 改为 `new value` | 文件更新，diff 同时包含删除行和新增行 |
| 路径保护 | patch 目标为 `../outside.txt` | 返回 `PATH_BLOCKED`，工作区外没有文件产生 |
| 终端 artifact | 精确白名单命令输出 200 字符，显示上限为 20 | ToolResult 中输出被截断，artifact JSON 保存完整输出 |

## CLI 入口测试

```powershell
python -m harness_forge --help
harnessforge --help
```

预期：两种入口都列出 `doctor` 和 `run`。

在 `D:\vsc\HarnessForge\.env` 中写入有效模型配置，然后运行：

```powershell
python -m harness_forge doctor
```

预期：本地检查项显示 `[OK]`；API key 只显示为 `configured`，不会输出原文；
Provider 行明确显示没有发送模型请求。

DeepSeek 配置应包含：

```dotenv
PROVIDER_API=chat_completions
OPENAI_API_KEY=你的DeepSeek密钥
OPENAI_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-flash
```

此时 `doctor` 预期显示：

```text
[OK] PROVIDER_API: chat_completions
[OK] OPENAI_API_KEY: configured
[OK] Provider: OpenAIChatCompletionsProvider initialized; no request sent
```

## 可选的真实 Provider 冒烟测试

该测试会发送模型请求，可能产生费用。

```powershell
New-Item -ItemType Directory -Force .\demo_workspace
Set-Content -Encoding UTF8 .\demo_workspace\notes.txt "HarnessForge demo"

harnessforge run `
  --task-id local-demo `
  --instruction "Read notes.txt and report its content." `
  --workspace .\demo_workspace `
  --provider-api chat_completions `
  --tools list_dir,read_file `
  --max-steps 6 `
  --max-model-calls 6 `
  --max-tool-calls 4 `
  --wall-time 120
```

预期 stdout 是一个 JSON 对象，其中：

- `run_id` 非空；
- `harness_success` 为 `true`；
- `benchmark_success` 为 `null`；
- `stop_reason` 为 `final_answer`；
- 路径位于 `runs/<run_id>/`。

继续检查：

```powershell
Get-Content .\runs\<run_id>\result.json
Get-Content .\runs\<run_id>\trajectory.jsonl
Get-ChildItem .\runs\<run_id>\artifacts
```

这里的成功只表示 harness 正常完成，不代表任何官方 benchmark 分数。
