# Architecture

HarnessForge keeps benchmark orchestration, agent policy, tools, and safety
boundaries separate:

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

## Layer responsibilities

- **TaskSpec** describes one isolated task: identity, instruction, workspace,
  enabled tools, and adapter metadata.
- **Runner** validates the task boundary, builds a task-scoped registry, applies
  the fixed run configuration, creates run/attempt IDs and output paths, and
  invokes the loop. It writes a JSON result and JSONL trajectory but does not
  evaluate a public benchmark.
- **Agent Loop** is an explicit model-action/tool-observation loop. It has no
  Debug outer loop, memory, profile, summary, dynamic skill discovery, or
  LangGraph dependency. When a provider returns multiple tool calls, the loop
  queues them, executes one tool per step, and requests the model again only
  after the queue is empty. Provider messages and the pending queue stay inside
  one run and are not persisted across tasks.
- **LLMProvider** normalizes provider messages, tool calls, text responses, and
  usage. `create_provider()` selects a Responses or Chat Completions backend
  from `ProviderConfig.provider_api`. Both use the official OpenAI Python SDK
  with configurable model, base URL, temperature, output-token limit, timeout,
  and retry count. Responses uses a flat function-tool schema; Chat Completions
  uses the nested `function` schema and translates `assistant.tool_calls` plus
  `tool_call_id` into the shared internal messages.
- **Tool Registry** owns registration, lookup, basic argument validation, and a
  single `ToolResult` protocol. It never prints.
- **Tools** expose structured directory listing, bounded line-range reads,
  literal/regex/glob search, exact replacement, file creation, task-scoped
  diffs, pure-Python unified-patch application, and a narrow command runner.
- **WorkspaceChangeTracker** remembers file contents immediately before the
  first HarnessForge mutation in a run. `get_diff` therefore reports changes
  made through `edit_file`, `write_file`, and `apply_patch` without requiring a
  Git repository or host subprocess.
- **WorkspaceGuard** is a host/task workspace path boundary. It prevents path
  escape and access to sensitive-looking paths. It is not a Docker or operating
  system sandbox.
- **CommandPolicy** allows only explicitly listed argv forms. The baseline
  policy is intentionally too narrow for Terminal-Bench.
- **Budget / Result** records explicit step/model/tool/wall-time budgets,
  reserved token/cost limits, stop reasons, model/tool counts, provider usage,
  and output paths. `harness_success` is independent from the currently unset
  `benchmark_success` and `official_score` fields.
- **CLI** is a thin `argparse` layer. `doctor` performs local checks without a
  model request, while `run` constructs existing configs and calls the Runner.
  `PROVIDER_API` or `--provider-api` selects only the provider protocol and does
  not change the Agent Loop.
- **Terminal artifacts** keep bounded stdout/stderr in `ToolResult`; truncated
  full output is written to a trusted run artifact directory.

## Dependency direction

The CLI and future benchmark adapters depend on harness schemas and the Runner.
The Runner depends on tools and the loop, the loop depends on provider
contracts, and tools depend on safety primitives. Provider contracts, safety,
and schemas do not depend on the Runner. Nothing imports CyberClaw.
