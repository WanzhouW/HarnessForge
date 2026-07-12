from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetConfig:
    max_steps: int = 20
    max_tool_calls: int = 15
    wall_time_seconds: float = 300.0
    max_model_calls: int = 20
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_cost: float | None = None

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        if self.max_tool_calls < 0:
            raise ValueError("max_tool_calls must be non-negative")
        if self.wall_time_seconds <= 0:
            raise ValueError("wall_time_seconds must be positive")
        if self.max_model_calls < 1:
            raise ValueError("max_model_calls must be at least 1")
        if self.max_input_tokens is not None and self.max_input_tokens < 1:
            raise ValueError("max_input_tokens must be positive")
        if self.max_output_tokens is not None and self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")
        if self.max_cost is not None and self.max_cost <= 0:
            raise ValueError("max_cost must be positive")
