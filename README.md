# HarnessForge

HarnessForge is a minimal benchmark-facing terminal agent harness baseline. It
extracts general design ideas from CyberClaw into an independent project without
modifying or importing CyberClaw's main runtime.

The current baseline provides:

- a small explicit agent loop with both a scripted-model test backend and an
  `LLMProvider` abstraction;
- Responses API and Chat Completions API providers implemented with the
  official Python SDK, including compatible services such as DeepSeek;
- reproducible run/attempt IDs, structured results, JSONL trajectories, and
  step/model/tool/wall-time/token/cost budgets;
- a workspace boundary guard;
- structured `list_dir`, chunked `read_file`, regex/glob `search_text`,
  `edit_file`, `write_file`, `get_diff`, and pure-Python `apply_patch` tools;
- a deliberately narrow `shell=False` terminal interface;
- truncated terminal output with full-output JSON artifacts;
- `doctor` and local-task `run` CLI commands;
- interface-only stubs for future Terminal-Bench and SWE-bench adapters.

The baseline intentionally excludes Debug workflows, automatic pytest repair,
user profiles, persistent sessions, M5 memory, conversation summarization,
dynamic skills, and cross-task state.

It does **not** currently provide full Terminal-Bench or SWE-bench integration.
In particular, it does not download benchmarks, create official benchmark
containers, invoke official evaluators, or claim that its default terminal
policy is sufficient for public benchmark tasks.

## Project structure

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
│   ├── cli.py              # doctor and local run commands
│   ├── agent/              # agent loop, prompts, and state
│   ├── benchmark_adapters/ # interface stubs for future benchmark adapters
│   ├── harness/            # task specs, budgets, runner, and result schemas
│   ├── logging/            # trajectory event records and JSONL logging
│   ├── providers/          # contracts, Responses, and Chat Completions backends
│   ├── safety/             # workspace and command policy boundaries
│   └── tools/              # filesystem, search, edit, terminal, and registry
└── tests/                  # unit and smoke tests
```

## Development

The package uses a `src/` layout. Runtime dependencies are the official
`openai` Python package and `python-dotenv`; scripted tests do not make network
requests.

```powershell
python -m pip install -e .
```

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

## Command-line entry point

Both entry forms use the same `argparse` implementation:

```powershell
python -m harness_forge --help
harnessforge --help
```

Check Python, dependencies, `.env`, and provider initialization without making
a model request:

```powershell
harnessforge doctor
```

Run one local task:

```powershell
harnessforge run `
  --task-id local-demo `
  --instruction "Read notes.txt and summarize it." `
  --workspace .\demo_workspace `
  --tools list_dir,read_file
```

By default, each run writes `result.json`, `trajectory.jsonl`, and an
`artifacts/` directory under `runs/<run_id>/`. CLI exit codes describe harness
execution only: 0 completed, 1 harness failure, 2 configuration error, and 3
provider error. They do not represent an official benchmark pass/fail.

## Model provider configuration

HarnessForge supports both the `responses` and `chat_completions` protocols.
Configure one explicitly, with process environment variables, or with a `.env`
file in the directory where HarnessForge is launched. For the repository
workflow, place the file at `D:\vsc\HarnessForge\.env`.

OpenAI Responses API example:

```dotenv
PROVIDER_API=responses
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=your-model-name
```

DeepSeek Chat Completions example:

```dotenv
PROVIDER_API=chat_completions
OPENAI_API_KEY=your-deepseek-api-key
OPENAI_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-flash
```

The `OPENAI_API_KEY` name is retained because DeepSeek is accessed through the
OpenAI-compatible SDK. `PROVIDER_API` selects `/responses` or
`/chat/completions`; OpenAI compatibility does not imply support for both. The
CLI option `--provider-api responses|chat_completions` overrides the
environment value.

`ProviderConfig.from_env()` calls `load_dotenv()` automatically. Existing
process environment variables take precedence over values in `.env`. A custom
file can be selected with `ProviderConfig.from_env(dotenv_path=...)`.

The equivalent PowerShell configuration is:

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

Pass `provider` as `RunConfig.model`. Provider calls are synchronous. The
Responses backend disables API storage and parallel tool calls; the Chat
Completions backend uses the broadly compatible standard message and function
tool formats. If a compatible service still returns multiple tool calls in one
response, the Agent Loop queues them and executes one tool per step before the
next model request. Both delegate timeout and retry behavior to the official SDK.
`AgentRunResult.model_config.provider_api` records the selected protocol along
with the served model name, model-call count, and provider-reported token usage.
Cost remains `None` unless a compatible
provider reports it.

The real provider does not make HarnessForge benchmark-ready by itself. Public
benchmark adapters, official evaluators, and container lifecycle support remain
unimplemented.

See:

- `docs/architecture.md` for component boundaries;
- `docs/baseline_scope.md` for controlled variables;
- `docs/extraction_notes.md` for provenance and deliberate exclusions;
- `docs/phase0_status.md` for the clean-skeleton acceptance record;
- `docs/testing_phase2_phase3.md` for inputs and expected test outputs.

Chinese versions are available alongside the English documents with the
`_zh.md` suffix.
