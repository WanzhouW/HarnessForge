from __future__ import annotations

from pathlib import Path
from typing import Iterable

from harness_forge.harness.result_schema import AgentRunResult
from harness_forge.harness.task import TaskSpec

from .base import AdapterEvaluation, BenchmarkAdapter


class SweBenchAdapter(BenchmarkAdapter):
    """Interface placeholder; SWE-bench is not implemented."""

    name = "swe-bench"

    def load_tasks(self, source: str | Path) -> Iterable[TaskSpec]:
        # TODO: load official SWE-bench instances and retain instance metadata
        # for checkout and evaluation.
        raise NotImplementedError("SWE-bench instance loading is not implemented")

    def prepare_task(self, task: TaskSpec) -> TaskSpec:
        # TODO: create an isolated checkout at the official base commit.
        raise NotImplementedError("SWE-bench repository checkout is not implemented")

    def evaluate(self, task: TaskSpec, result: AgentRunResult) -> AdapterEvaluation:
        # TODO: export the patch and invoke the official SWE-bench evaluator.
        raise NotImplementedError("SWE-bench evaluation is not implemented")

