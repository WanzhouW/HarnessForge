from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from harness_forge.harness.result_schema import (
    AgentRunResult,
    StepRecord,
    ToolCallRecord,
)
from harness_forge.harness.task import RunConfig
from harness_forge.logging.events import RunEvent
from harness_forge.logging.trajectory import TrajectoryWriter
from harness_forge.providers.base import (
    LLMProvider,
    ModelMessage,
    ModelResponse,
    ProviderError,
    ToolCall,
    ToolDefinition,
)
from harness_forge.tools.registry import ToolRegistry, ToolResult

from .prompts import BASELINE_SYSTEM_PROMPT
from .state import AgentAction, AgentRunState, ModelRequest


def run_agent(
    task_instruction: str,
    workspace_root: str | Path,
    tools: ToolRegistry,
    config: RunConfig,
) -> AgentRunResult:
    """Run the explicit baseline model/tool loop.

    `harness_success=True` means the harness reached a non-empty final answer.
    Public benchmark correctness remains the responsibility of a future adapter.
    """

    if not task_instruction.strip():
        raise ValueError("task_instruction must be non-empty")
    root = Path(workspace_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"invalid workspace_root: {workspace_root}")

    model = config.model
    provider = model if isinstance(model, LLMProvider) else None
    if provider is None and not hasattr(model, "next_action"):
        raise TypeError(
            "config.model must implement next_action(request) or be an LLMProvider"
        )

    run_id = config.run_id or uuid4().hex
    task_id = config.task_id or "adhoc"
    attempt_id = config.attempt_id or uuid4().hex
    enabled_tools = config.enabled_tools or tools.names()
    unknown_enabled = sorted(set(enabled_tools) - set(tools.names()))
    if unknown_enabled:
        raise ValueError("enabled_tools are not registered: " + ", ".join(unknown_enabled))

    budget = config.budget
    system_prompt = config.system_prompt.strip() or BASELINE_SYSTEM_PROMPT.strip()
    rendered_prompt = (
        f"{system_prompt}\n\n"
        f"Enabled tools: {', '.join(enabled_tools)}\n\n"
        f"Task:\n{task_instruction.strip()}"
    )
    writer = TrajectoryWriter(config.trajectory_path) if config.trajectory_path else None
    if writer is not None:
        writer.reset()
    state = AgentRunState()
    trajectory: list[StepRecord] = []
    provider_responses: list[ModelResponse] = []
    pending_provider_tool_calls: list[ToolCall] = []
    provider_messages = (
        [
            ModelMessage(role="system", content=system_prompt),
            ModelMessage(
                role="user",
                content=(
                    f"Enabled tools: {', '.join(enabled_tools)}\n\n"
                    f"Task:\n{task_instruction.strip()}"
                ),
            ),
        ]
        if provider is not None
        else []
    )
    provider_tools = (
        _build_tool_definitions(tools, enabled_tools) if provider is not None else ()
    )
    model_name = (
        provider.config.model_name
        if provider is not None
        else str(getattr(model, "model_name", type(model).__name__))
    )
    model_config = _public_model_config(model, model_name)
    prompt_version = config.prompt_version.strip() or "baseline-v1"
    started = time.perf_counter()

    _emit(
        writer,
        RunEvent(
            run_id=run_id,
            task_id=task_id,
            step_id=0,
            event_type="run_started",
            payload={
                "workspace_root": str(root),
                "enabled_tools": list(enabled_tools),
                "max_steps": budget.max_steps,
                "max_tool_calls": budget.max_tool_calls,
                "max_model_calls": budget.max_model_calls,
                "wall_time_seconds": budget.wall_time_seconds,
                "model_name": model_name,
                "attempt_id": attempt_id,
                "prompt_version": prompt_version,
            },
        ),
    )

    stop_reason = "max_steps"
    harness_success = False
    final_answer = ""

    for step_id in range(1, budget.max_steps + 1):
        if time.perf_counter() - started >= budget.wall_time_seconds:
            stop_reason = "wall_time"
            state.errors.append("agent wall-time budget exceeded")
            break
        needs_model_call = provider is None or not pending_provider_tool_calls
        if needs_model_call and state.model_call_count >= budget.max_model_calls:
            stop_reason = "max_model_calls"
            state.errors.append("model-call budget exceeded")
            break

        state.step_count = step_id
        request = ModelRequest(
            task_instruction=task_instruction,
            rendered_prompt=rendered_prompt,
            workspace_root=str(root),
            enabled_tools=tuple(enabled_tools),
            step_id=step_id,
            observations=tuple(state.observations),
        )
        provider_response: ModelResponse | None = None
        provider_tool_call: ToolCall | None = None
        try:
            if provider is not None:
                if pending_provider_tool_calls:
                    provider_tool_call = pending_provider_tool_calls.pop(0)
                    action = AgentAction.tool(
                        provider_tool_call.name, provider_tool_call.arguments
                    )
                else:
                    state.model_call_count += 1
                    provider_response = provider.complete(
                        tuple(provider_messages), provider_tools
                    )
                    if not isinstance(provider_response, ModelResponse):
                        raise TypeError(
                            "provider returned "
                            f"{type(provider_response).__name__}, expected ModelResponse"
                        )
                    provider_responses.append(provider_response)
                    model_name = provider_response.model_name or model_name
                    if provider_response.tool_calls:
                        pending_provider_tool_calls.extend(
                            provider_response.tool_calls
                        )
                        provider_messages.append(
                            ModelMessage(
                                role="assistant",
                                content=provider_response.content,
                                tool_calls=provider_response.tool_calls,
                            )
                        )
                        provider_tool_call = pending_provider_tool_calls.pop(0)
                        action = AgentAction.tool(
                            provider_tool_call.name,
                            provider_tool_call.arguments,
                        )
                    else:
                        action = AgentAction.final(provider_response.content)
            else:
                state.model_call_count += 1
                action = model.next_action(request)  # type: ignore[attr-defined]
        except Exception as exc:
            stop_reason = "provider_error" if isinstance(exc, ProviderError) else "model_error"
            state.errors.append(f"{type(exc).__name__}: {exc}")
            break
        if time.perf_counter() - started >= budget.wall_time_seconds:
            stop_reason = "wall_time"
            state.errors.append("agent wall-time budget exceeded")
            break
        usage_stop_reason = _usage_budget_stop_reason(budget, provider_responses)
        if usage_stop_reason is not None:
            stop_reason = usage_stop_reason
            state.errors.append(f"{usage_stop_reason.replace('_', '-')} budget exceeded")
            break
        if not isinstance(action, AgentAction):
            stop_reason = "invalid_model_action"
            state.errors.append(
                f"model returned {type(action).__name__}, expected AgentAction"
            )
            break

        _emit(
            writer,
            RunEvent(
                run_id=run_id,
                task_id=task_id,
                step_id=step_id,
                event_type="model_action",
                payload={
                    "action_type": action.action_type,
                    "tool_name": action.tool_name,
                    "arguments": action.arguments,
                    "content": action.content,
                    "model_name": model_name,
                    "input_tokens": (
                        provider_response.input_tokens if provider_response else None
                    ),
                    "output_tokens": (
                        provider_response.output_tokens if provider_response else None
                    ),
                    "total_tokens": (
                        provider_response.total_tokens if provider_response else None
                    ),
                    "queued_tool_calls_remaining": len(
                        pending_provider_tool_calls
                    ),
                },
            ),
        )

        if action.action_type == "final":
            final_answer = action.content.strip()
            trajectory.append(
                StepRecord(
                    step_id=step_id,
                    action_type="final",
                    model_content=final_answer,
                )
            )
            if final_answer:
                harness_success = True
                stop_reason = "final_answer"
            else:
                stop_reason = "empty_final_answer"
                state.errors.append("model returned an empty final answer")
            break

        if action.action_type != "tool" or not action.tool_name:
            stop_reason = "invalid_model_action"
            state.errors.append("model action must be 'tool' with a name or 'final'")
            break

        if state.tool_call_count >= budget.max_tool_calls:
            stop_reason = "max_tool_calls"
            state.errors.append("tool-call budget exceeded")
            break

        state.tool_call_count += 1
        if action.tool_name not in enabled_tools:
            tool_result = ToolResult.fail(
                f"tool is disabled for this task: {action.tool_name}",
                "TOOL_DISABLED",
            )
        else:
            tool_result = tools.invoke(action.tool_name, action.arguments)

        call_record = ToolCallRecord(
            step_id=step_id,
            tool_name=action.tool_name,
            arguments=dict(action.arguments),
            success=tool_result.success,
            result=tool_result.output,
            error=tool_result.error,
            error_type=tool_result.error_type,
        )
        state.observations.append(call_record)
        if not tool_result.success and tool_result.error:
            state.errors.append(f"{action.tool_name}: {tool_result.error}")
        trajectory.append(
            StepRecord(
                step_id=step_id,
                action_type="tool",
                tool_call=call_record,
            )
        )
        if provider is not None and provider_tool_call is not None:
            provider_messages.append(
                ModelMessage(
                    role="tool",
                    tool_call_id=provider_tool_call.call_id,
                    content=json.dumps(
                        tool_result.to_dict(), ensure_ascii=False, sort_keys=True
                    ),
                )
            )
        _emit(
            writer,
            RunEvent(
                run_id=run_id,
                task_id=task_id,
                step_id=step_id,
                event_type="tool_result",
                payload=call_record.to_dict(),
            ),
        )
        if time.perf_counter() - started >= budget.wall_time_seconds:
            stop_reason = "wall_time"
            state.errors.append("agent wall-time budget exceeded")
            break

    if stop_reason == "max_steps" and not harness_success:
        state.errors.append("step budget exhausted")
    duration = round(time.perf_counter() - started, 6)
    input_tokens = _sum_complete_usage(
        [response.input_tokens for response in provider_responses]
    )
    output_tokens = _sum_complete_usage(
        [response.output_tokens for response in provider_responses]
    )
    total_tokens = _sum_complete_usage(
        [response.total_tokens for response in provider_responses]
    )
    cost = _sum_complete_cost([response.cost for response in provider_responses])
    result = AgentRunResult(
        run_id=run_id,
        task_id=task_id,
        attempt_id=attempt_id,
        instruction=task_instruction,
        workspace_root=str(root),
        model_config=model_config,
        prompt_version=prompt_version,
        enabled_tools=list(enabled_tools),
        max_steps=budget.max_steps,
        max_tool_calls=budget.max_tool_calls,
        wall_time_limit=budget.wall_time_seconds,
        max_model_calls=budget.max_model_calls,
        stop_reason=stop_reason,
        harness_success=harness_success,
        benchmark_success=None,
        official_score=None,
        model_name=model_name,
        model_call_count=state.model_call_count,
        tool_call_count=state.tool_call_count,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost=cost,
        final_answer=final_answer,
        trajectory=trajectory,
        tool_calls=list(state.observations),
        errors=list(state.errors),
        duration_seconds=duration,
        trajectory_path=(str(Path(config.trajectory_path).resolve()) if config.trajectory_path else None),
        artifact_path=(str(Path(config.artifact_path).resolve()) if config.artifact_path else None),
        result_path=(str(Path(config.result_path).resolve()) if config.result_path else None),
    )
    _emit(
        writer,
        RunEvent(
            run_id=run_id,
            task_id=task_id,
            step_id=state.step_count,
            event_type="run_finished",
            payload={
                "stop_reason": stop_reason,
                "harness_success": harness_success,
                "benchmark_success": None,
                "official_score": None,
                "duration_seconds": duration,
                "model_name": model_name,
                "model_calls": state.model_call_count,
                "tool_calls": state.tool_call_count,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "cost": cost,
                "errors": list(state.errors),
            },
        ),
    )
    return result


def _emit(writer: TrajectoryWriter | None, event: RunEvent) -> None:
    if writer is not None:
        writer.append(event)


def _build_tool_definitions(
    registry: ToolRegistry, enabled_tools: tuple[str, ...]
) -> tuple[ToolDefinition, ...]:
    definitions: list[ToolDefinition] = []
    for name in enabled_tools:
        spec = registry.get(name)
        if spec is None:  # validated before this helper is called
            continue
        properties = {
            parameter_name: _json_schema_for_type(expected)
            for parameter_name, expected in spec.parameters.items()
        }
        definitions.append(
            ToolDefinition(
                name=spec.name,
                description=spec.description,
                parameters={
                    "type": "object",
                    "properties": properties,
                    "required": sorted(spec.required),
                    "additionalProperties": spec.allow_extra,
                },
            )
        )
    return tuple(definitions)


def _json_schema_for_type(expected: type | tuple[type, ...]) -> dict[str, Any]:
    if isinstance(expected, tuple):
        variants = [_json_schema_for_type(item) for item in expected]
        unique: list[dict[str, Any]] = []
        for variant in variants:
            if variant not in unique:
                unique.append(variant)
        return unique[0] if len(unique) == 1 else {"anyOf": unique}
    mapping: dict[type, str] = {
        str: "string",
        bool: "boolean",
        int: "integer",
        float: "number",
        list: "array",
        tuple: "array",
        dict: "object",
    }
    return {"type": mapping.get(expected, "object")}


def _sum_complete_usage(values: list[int | None]) -> int | None:
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _sum_complete_cost(values: list[float | None]) -> float | None:
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _usage_budget_stop_reason(
    budget: Any, responses: list[ModelResponse]
) -> str | None:
    input_tokens = _sum_complete_usage([item.input_tokens for item in responses])
    output_tokens = _sum_complete_usage([item.output_tokens for item in responses])
    cost = _sum_complete_cost([item.cost for item in responses])
    if (
        budget.max_input_tokens is not None
        and input_tokens is not None
        and input_tokens > budget.max_input_tokens
    ):
        return "max_input_tokens"
    if (
        budget.max_output_tokens is not None
        and output_tokens is not None
        and output_tokens > budget.max_output_tokens
    ):
        return "max_output_tokens"
    if budget.max_cost is not None and cost is not None and cost > budget.max_cost:
        return "max_cost"
    return None


def _public_model_config(model: object, model_name: str) -> dict[str, Any]:
    provider_config = getattr(model, "config", None)
    public_dict = getattr(provider_config, "public_dict", None)
    if callable(public_dict):
        value = public_dict()
        if isinstance(value, dict):
            return dict(value)
    return {
        "backend": type(model).__name__,
        "model_name": model_name,
    }
