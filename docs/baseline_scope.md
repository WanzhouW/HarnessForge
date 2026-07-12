# Baseline Scope

HarnessForge's minimum baseline is designed for controlled comparisons.

## Fixed variables

- one explicitly selected model/backend per experiment, either the scripted
  test backend or one configured `LLMProvider`;
- one versioned system prompt;
- one declared tool set per task;
- one `BudgetConfig` covering steps, model calls, tool calls, wall time, and
  optional provider-reported token/cost limits;
- no memory or retrieval;
- no Debug workflow or automatic pytest repair loop;
- no dynamic skills;
- no user profile or persistent conversation session;
- no cross-task state;
- one independent workspace per task.

`harness_success` means that the agent reached a non-empty final answer without
a harness failure. `benchmark_success` and `official_score` remain `None`
because no official evaluator is connected. These meanings must not be merged.

Each run receives distinct run and attempt IDs and writes `result.json`,
`trajectory.jsonl`, and an artifact directory under `runs/<run_id>/` unless the
caller explicitly overrides those paths.

## Provider boundary

Phase 1 adds an OpenAI Responses API provider and is extended with an
OpenAI-compatible Chat Completions provider. `PROVIDER_API` must resolve to
`responses` or `chat_completions`; secrets are read from explicit values or the
environment and are not written to results, and provider conversation state is
scoped to one agent run. Tests use fake providers or injected clients and never
require a real API key or network request.

The provider does not change the baseline prompt, enabled tool set, workspace
guard, command policy, or exclusions. It also does not load benchmark tasks or
invoke an official evaluator.

## CLI boundary

The `doctor` and `run` commands are local orchestration only. `doctor` performs
no model request. `run` constructs `ProviderConfig`, `TaskSpec`, `RunConfig`, and
`BudgetConfig`, then delegates to `HarnessRunner`. CLI exit codes describe
harness execution and never claim benchmark correctness.

## Tool boundary

File mutations remain guarded by `WorkspaceGuard`. `get_diff` covers mutations
made through the task-scoped HarnessForge file tools; it is not a general Git
working-tree status command. `apply_patch` uses a bounded pure-Python unified
diff parser and validates every target before writing. The host terminal policy
is unchanged and still rejects arbitrary commands.

## Metrics

The primary metric in a future public adapter should be the benchmark's official
pass rate or official score. Planned secondary metrics include provider-reported
input/output tokens, cost, wall time, model calls, tool calls, repeated reads,
command time, and patch size.

`AgentRunResult` now records provider protocol, model name, model calls, and
provider-reported input/output/total tokens. Cost remains optional because
these APIs do not report request cost consistently.

## Terminal boundary

The default command policy permits only a few exact version-reporting commands.
It is a development safety baseline, not a useful Terminal-Bench shell.

Terminal stdout/stderr is bounded in the model-visible result. When output is
truncated, the full text can be stored in the trusted run artifact directory.

When Terminal-Bench support is implemented, general terminal access should be
opened inside the benchmark's official container or another isolated execution
environment. Host-side command execution should remain narrow.
