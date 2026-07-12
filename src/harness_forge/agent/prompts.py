BASELINE_SYSTEM_PROMPT = """You are a benchmark-facing terminal coding agent.
Work only inside the provided task workspace.
Use only the enabled tools.
Do not assume a Debug workflow, persistent memory, or cross-task state.
Return a concise final answer when the task is complete.
"""


def build_task_prompt(task_instruction: str, enabled_tools: tuple[str, ...]) -> str:
    tool_text = ", ".join(enabled_tools)
    return (
        f"{BASELINE_SYSTEM_PROMPT.strip()}\n\n"
        f"Enabled tools: {tool_text}\n\n"
        f"Task:\n{task_instruction.strip()}"
    )

