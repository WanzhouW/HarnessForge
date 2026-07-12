# Extraction Notes

HarnessForge copies design ideas, not CyberClaw runtime dependencies.

| HarnessForge module | CyberClaw reference | Preserved | Removed or changed |
| --- | --- | --- | --- |
| `safety/workspace.py` | `cyberclaw/workspace.py` | resolved-root boundary, traversal rejection, sensitive-path policy | CyberClaw imports and product workspace assumptions; the new docstring distinguishes host boundary from container isolation |
| `tools/registry.py` | `cyberclaw/tools.py` | named registration, lookup, basic schema checks | printing, LangChain conversion, time/calculator/profile tools, default registry, dynamic skills |
| `tools/filesystem.py` | `cyberclaw/coding_tools.py` | bounded directory listing and UTF-8 text reading | natural-language-only results and closure-based construction |
| `tools/search.py` | `cyberclaw/coding_tools.py` | bounded recursive literal search, binary/large-file skipping | memory-note side effects and product logging |
| `tools/edit.py` | `cyberclaw/coding_tools.py` | exact unique replacement and unified diff | in-repository backup directory and restore workflow |
| `tools/terminal.py` | `cyberclaw/coding_tools.py` | `shell=False`, argv parsing, timeout, structured output | pytest-specific failure semantics and the claim that a host whitelist is a general benchmark terminal |
| `agent/loop.py` | `cyberclaw/agent.py` | model action → tool result → next action control flow | LangGraph, Debug workflow, profile, session, M5 memory, summary, dynamic skills |
| `logging/` | `cyberclaw/logger.py` | JSONL event idea | background thread and implicit global logger; writes are synchronous and explicit |
| `harness/` | `cyberclaw/benchmark_runner.py` and `benchmark_memory.py` | task/result separation, attempts at tool accounting | `expect_contains`, shared profile, internal fixtures, memory metrics, and unimplemented verifier declarations |

The new project does not directly import CyberClaw because doing so would make
the baseline drift with CyberClaw's interactive runtime and would reintroduce
hidden variables.

The Debug workflow is excluded because public terminal tasks are not uniformly
pytest repair tasks. An automatic test/fix/retest outer loop would add extra
model calls and task-specific policy outside the baseline agent loop.

Memory, profile, and session components are excluded because the baseline must
start each task with fresh state. They alter prompts, can trigger extra model
calls, and create cross-task leakage risks. They may later return only as
explicit, separately measured experiment policies.

