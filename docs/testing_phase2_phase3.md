# Phase 2–3 Testing Guide

This guide verifies the Phase 2 runner/result/budget work, the Phase 2.5 CLI,
and the Phase 3 tools. None of these checks invokes an official benchmark
evaluator.

## Environment setup

```powershell
conda activate aiagent
cd D:\vsc\HarnessForge
python --version
python -m pip install -e .
python -m pip check
```

Expected: Python 3.11 or newer and `No broken requirements found`.

## Automated verification

Run the complete suite:

```powershell
python -m unittest discover -s tests -v
```

Run one phase at a time:

```powershell
python -m unittest discover -s tests -p "test_runner_phase2.py" -v
python -m unittest discover -s tests -p "test_cli.py" -v
python -m unittest discover -s tests -p "test_providers.py" -v
python -m unittest discover -s tests -p "test_phase3_tools.py" -v
```

Expected: every test ends in `ok` and the command ends in `OK`.

The deterministic test inputs and expected results include:

| Area | Input | Expected result |
| --- | --- | --- |
| Normal run | scripted model returns `done` | `harness_success=true`, `benchmark_success=null`, result and trajectory files exist |
| Step budget | one tool action with `max_steps=1` | `stop_reason=max_steps` |
| Model budget | two scripted actions with `max_model_calls=1` | only one model request; `stop_reason=max_model_calls` |
| Tool budget | a tool action with `max_tool_calls=0` | tool is not invoked; `stop_reason=max_tool_calls` |
| Wall time | model sleeps longer than the configured limit | `stop_reason=wall_time` |
| Token budget | provider reports 11 input tokens with a limit of 10 | `stop_reason=max_input_tokens` |
| Provider protocol | `PROVIDER_API=chat_completions` | factory selects Chat Completions and the tool schema contains nested `function` |
| Chat tool round trip | assistant tool call followed by tool result | request contains `assistant.tool_calls` and matching `tool_call_id` |
| Multiple tool response | one model response contains two `read_file` calls | tools execute on consecutive steps; one initial model request, then both results are sent before the final request |
| File creation | `write_file(created.txt, "created\n")` | file is created and `get_diff` contains `+created` |
| Chunked read | `start_line=2`, `line_count=2` | only lines 2–3 are returned and `has_more=true` |
| Regex/glob search | regex `value\d+`, glob `src/*.py` | only matching Python-file lines are returned |
| Patch | unified diff replaces `old value` | file contains `new value`; diff contains the removal and addition |
| Path guard | patch target `../outside.txt` | `PATH_BLOCKED`; no outside file is created |
| Terminal artifact | exact-allowlisted command emits 200 characters with a 20-character limit | tool output is truncated; artifact JSON contains the full output |

## CLI checks

```powershell
python -m harness_forge --help
harnessforge --help
```

Expected: both commands list `doctor` and `run`.

Create `D:\vsc\HarnessForge\.env` with a valid model configuration, then run:

```powershell
python -m harness_forge doctor
```

Expected: local checks show `[OK]`; the API key is reported only as
`configured`; the command states that no request was sent.

A DeepSeek configuration should contain:

```dotenv
PROVIDER_API=chat_completions
OPENAI_API_KEY=your-deepseek-api-key
OPENAI_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-flash
```

`doctor` should then include:

```text
[OK] PROVIDER_API: chat_completions
[OK] OPENAI_API_KEY: configured
[OK] Provider: OpenAIChatCompletionsProvider initialized; no request sent
```

## Optional live-provider smoke test

This check sends model requests and may incur cost.

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

Expected stdout is one JSON object containing a non-empty `run_id`,
`harness_success: true`, `benchmark_success: null`, `stop_reason:
"final_answer"`, and paths under `runs/<run_id>/`. Verify:

```powershell
Get-Content .\runs\<run_id>\result.json
Get-Content .\runs\<run_id>\trajectory.jsonl
Get-ChildItem .\runs\<run_id>\artifacts
```

The result is a harness completion signal, not an official benchmark score.
