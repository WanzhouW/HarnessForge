from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from harness_forge.harness.result_schema import AgentRunResult
from harness_forge.harness.task import TaskSpec


@dataclass(frozen=True)
class AdapterEvaluation:
    passed: bool
    score: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


class BenchmarkAdapter(ABC):
    """Contract between a public benchmark and the generic harness."""

    name: str

    @abstractmethod
    def load_tasks(self, source: str | Path) -> Iterable[TaskSpec]:
        """Load benchmark-native records into generic TaskSpec objects."""

    @abstractmethod
    def prepare_task(self, task: TaskSpec) -> TaskSpec:
        """Create or select an isolated task workspace."""

    @abstractmethod
    def evaluate(self, task: TaskSpec, result: AgentRunResult) -> AdapterEvaluation:
        """Run the benchmark's official evaluator or equivalent contract."""

    def cleanup_task(self, task: TaskSpec) -> None:
        """Release adapter-owned task resources."""

