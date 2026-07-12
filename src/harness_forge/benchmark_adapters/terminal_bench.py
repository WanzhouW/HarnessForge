from __future__ import annotations

from pathlib import Path
from typing import Iterable

from harness_forge.harness.result_schema import AgentRunResult
from harness_forge.harness.task import TaskSpec

from .base import AdapterEvaluation, BenchmarkAdapter


class TerminalBenchAdapter(BenchmarkAdapter):
    """Interface placeholder; Terminal-Bench is not implemented."""

    name = "terminal-bench"

    def load_tasks(self, source: str | Path) -> Iterable[TaskSpec]:
        # TODO: load official Terminal-Bench task definitions without copying
        # benchmark-specific fields into the agent loop.
        raise NotImplementedError("Terminal-Bench task loading is not implemented")

    def prepare_task(self, task: TaskSpec) -> TaskSpec:
        # TODO: start/select the official task container and provide a
        # container-scoped terminal policy.
        raise NotImplementedError("Terminal-Bench environment setup is not implemented")

    def evaluate(self, task: TaskSpec, result: AgentRunResult) -> AdapterEvaluation:
        # TODO: invoke the official Terminal-Bench evaluator and preserve its
        # native score/details in AdapterEvaluation.
        raise NotImplementedError("Terminal-Bench evaluation is not implemented")

