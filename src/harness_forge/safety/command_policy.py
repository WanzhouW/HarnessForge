from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class CommandPolicyError(ValueError):
    """Raised when an argv sequence is not allowed by the command policy."""


@dataclass(frozen=True)
class CommandPolicy:
    """Exact argv allowlist for host-side baseline commands.

    A future benchmark adapter should supply a container-scoped policy instead
    of widening this host policy indiscriminately.
    """

    allowed_commands: tuple[tuple[str, ...], ...] = (
        ("python", "--version"),
        ("python", "-V"),
        ("python.exe", "--version"),
        ("python.exe", "-V"),
        ("git", "--version"),
        ("git.exe", "--version"),
    )

    def normalize(self, argv: Iterable[str]) -> tuple[str, ...]:
        normalized = tuple(str(item).strip() for item in argv)
        if not normalized or any(not item for item in normalized):
            raise CommandPolicyError("command argv must contain non-empty strings")
        executable = Path(normalized[0]).name.lower()
        return (executable, *normalized[1:])

    def validate(self, argv: Iterable[str]) -> tuple[str, ...]:
        raw = tuple(str(item) for item in argv)
        normalized = self.normalize(raw)
        allowed = {
            (Path(command[0]).name.lower(), *command[1:])
            for command in self.allowed_commands
        }
        if normalized not in allowed:
            raise CommandPolicyError(
                "command is not allowed by the baseline host policy: "
                + " ".join(raw)
            )
        return raw
