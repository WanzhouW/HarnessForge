from __future__ import annotations

from pathlib import Path


class WorkspaceSecurityError(ValueError):
    """Raised when a path violates the configured workspace policy."""


class WorkspaceGuard:
    """Protect the host/task workspace boundary.

    This guard constrains paths used by HarnessForge tools. It is not a Docker,
    VM, operating-system, network, or process sandbox.
    """

    _EXACT_BLOCKED_NAMES = frozenset({".env", "id_rsa", "id_dsa", "secret", "token"})
    _BLOCKED_SUFFIXES = (".key", ".pem")
    _BLOCKED_KEYWORDS = ("secret", "token")

    def __init__(self, root_dir: str | Path) -> None:
        root = Path(root_dir).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise WorkspaceSecurityError(f"invalid workspace root: {root_dir}")
        self.root_dir = root

    def resolve_path(
        self,
        path: str | Path,
        *,
        must_exist: bool = False,
        expected_type: str | None = None,
    ) -> Path:
        if not isinstance(path, (str, Path)) or not str(path).strip():
            raise WorkspaceSecurityError("path must be a non-empty string or Path")

        requested = Path(path).expanduser()
        candidate = requested if requested.is_absolute() else self.root_dir / requested
        resolved = candidate.resolve(strict=False)

        try:
            resolved.relative_to(self.root_dir)
        except ValueError as exc:
            raise WorkspaceSecurityError(f"path escapes workspace root: {path}") from exc

        if self.is_sensitive_path(resolved):
            raise WorkspaceSecurityError(f"sensitive path is blocked: {path}")
        if must_exist and not resolved.exists():
            raise WorkspaceSecurityError(f"path does not exist: {path}")
        if expected_type == "file" and (not resolved.exists() or not resolved.is_file()):
            raise WorkspaceSecurityError(f"path is not a file: {path}")
        if expected_type == "dir" and (not resolved.exists() or not resolved.is_dir()):
            raise WorkspaceSecurityError(f"path is not a directory: {path}")
        return resolved

    def is_sensitive_path(self, path: str | Path) -> bool:
        candidate = Path(path).expanduser()
        resolved = (
            candidate.resolve(strict=False)
            if candidate.is_absolute()
            else (self.root_dir / candidate).resolve(strict=False)
        )
        try:
            parts = resolved.relative_to(self.root_dir).parts
        except ValueError:
            parts = resolved.parts

        for raw_part in parts:
            part = raw_part.lower()
            if part in self._EXACT_BLOCKED_NAMES:
                return True
            if any(part.endswith(suffix) for suffix in self._BLOCKED_SUFFIXES):
                return True
            if any(keyword in part for keyword in self._BLOCKED_KEYWORDS):
                return True
        return False

    def relative_label(self, path: str | Path) -> str:
        resolved = Path(path).resolve(strict=False)
        try:
            label = resolved.relative_to(self.root_dir).as_posix()
        except ValueError:
            return resolved.as_posix()
        return label or "."

