"""Git implementation of the Workspace port: one worktree per configuration."""

import os
import shutil
import subprocess
from pathlib import Path

from ia_testing.domain.run import WorkspaceError

_TIMEOUT_S = 60


class GitWorkspace:
    def __init__(self, path: Path | None = None) -> None:
        """`path=None` means the current directory; git is resolved once, here."""
        self._path = path
        self._root: Path | None = None
        self._git = shutil.which("git")

    def open(self) -> Path:
        """Return the root of the repository that contains the path."""
        output = self._run(["rev-parse", "--show-toplevel"], failure="not a git repository")
        self._root = Path(output.strip())
        return self._root

    def resolve(self, ref: str) -> str:
        """Return the commit `ref` points to. Option-like refs never reach git."""
        if not ref or ref.startswith("-"):
            raise WorkspaceError("invalid ref")
        output = self._run(
            ["rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
            failure="unknown ref",
        )
        return output.strip()

    def is_dirty(self) -> bool:
        """Whether there are uncommitted changes, including untracked files."""
        return bool(self._run(["status", "--porcelain"], failure="cannot read git status").strip())

    def create(self, path: Path, branch: str, commit: str) -> None:
        """Create a worktree at `path` on the new `branch`, without hooks or Git LFS."""
        self._run(
            [
                "-c",
                "core.hooksPath=/dev/null",
                "worktree",
                "add",
                "-b",
                branch,
                "--",
                str(path),
                commit,
            ],
            failure="cannot create worktree",
            skip_lfs=True,
        )

    def _run(self, args: list[str], *, failure: str, skip_lfs: bool = False) -> str:
        if self._git is None:
            raise WorkspaceError("git is not installed")
        env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"} if skip_lfs else None
        cwd = self._root or self._path
        try:
            completed = subprocess.run(  # noqa: S603 security-reviewed: absolute git path, argument list without shell, ref validated and passed after --end-of-options, 60 s timeout
                [self._git, *args],
                cwd=cwd,
                env=env,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=_TIMEOUT_S,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise WorkspaceError("cannot run git") from exc
        if completed.returncode != 0:
            raise WorkspaceError(failure)
        return completed.stdout
