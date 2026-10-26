import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from ia_testing.adapters.workspace.git import GitWorkspace
from ia_testing.domain.run import WorkspaceError

GIT = shutil.which("git") or "git"


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603 security-reviewed: test helper, fixed git binary and literal test arguments, no shell
        [
            GIT,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return completed.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    (root / "a.txt").write_text("one\n")
    git(root, "add", "a.txt")
    git(root, "commit", "-m", "first")
    return root.resolve()


def test_open_from_subdirectory_returns_root(repo: Path) -> None:
    sub = repo / "sub" / "deeper"
    sub.mkdir(parents=True)

    assert GitWorkspace(sub).open() == repo


def test_open_defaults_to_cwd(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)

    assert GitWorkspace().open() == repo


def test_open_not_a_repo_raises(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()

    with pytest.raises(WorkspaceError, match="not a git repository"):
        GitWorkspace(plain).open()


def test_resolve_head_and_branch(repo: Path) -> None:
    first = git(repo, "rev-parse", "HEAD")
    git(repo, "branch", "feature")
    (repo / "a.txt").write_text("two\n")
    git(repo, "commit", "-am", "second")
    second = git(repo, "rev-parse", "HEAD")
    workspace = GitWorkspace(repo)

    assert workspace.resolve("HEAD") == second
    assert workspace.resolve("feature") == first


@pytest.mark.parametrize("ref", ["--foo", "-x", ""])
def test_resolve_rejects_option_like_ref(
    ref: str, repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # With no git on PATH, only a rejection that happens before calling git can say "invalid ref".
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    workspace = GitWorkspace(repo)

    with pytest.raises(WorkspaceError, match="invalid ref"):
        workspace.resolve(ref)


def test_unknown_ref_raises(repo: Path) -> None:
    with pytest.raises(WorkspaceError, match="unknown ref"):
        GitWorkspace(repo).resolve("does-not-exist")


def test_is_dirty_counts_untracked(repo: Path) -> None:
    workspace = GitWorkspace(repo)
    assert workspace.is_dirty() is False

    (repo / "new.txt").write_text("untracked\n")
    assert workspace.is_dirty() is True

    (repo / "new.txt").unlink()
    (repo / "a.txt").write_text("changed\n")
    assert workspace.is_dirty() is True


def test_git_missing_raises_workspace_error(
    repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    workspace = GitWorkspace(repo)

    with pytest.raises(WorkspaceError, match="git is not installed"):
        workspace.open()
    with pytest.raises(WorkspaceError, match="git is not installed"):
        workspace.is_dirty()


def test_create_worktree_on_new_branch_from_commit(repo: Path, tmp_path: Path) -> None:
    first = git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("two\n")
    git(repo, "commit", "-am", "second")
    target = tmp_path / "out" / "worktrees" / "a"
    target.parent.mkdir(parents=True)

    GitWorkspace(repo).create(target, "ia-testing/run-1/a", first)

    assert (target / "a.txt").read_text() == "one\n"
    assert git(target, "rev-parse", "HEAD") == first
    assert git(target, "branch", "--show-current") == "ia-testing/run-1/a"


def test_create_does_not_run_post_checkout_hook(repo: Path, tmp_path: Path) -> None:
    hook = repo / ".git" / "hooks" / "post-checkout"
    hook.write_text('#!/bin/sh\ntouch "$(git rev-parse --show-toplevel)/hook-ran"\n')
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    commit = git(repo, "rev-parse", "HEAD")

    # Control: without the protection the hook does run, so the check below is not vacuous.
    control = tmp_path / "control"
    git(repo, "worktree", "add", "-b", "control", str(control), commit)
    assert (control / "hook-ran").exists()

    target = tmp_path / "wt"
    GitWorkspace(repo).create(target, "ia-testing/run-1/a", commit)

    assert target.is_dir()
    assert not (target / "hook-ran").exists()


def test_existing_branch_raises(repo: Path, tmp_path: Path) -> None:
    commit = git(repo, "rev-parse", "HEAD")
    workspace = GitWorkspace(repo)
    workspace.create(tmp_path / "one", "ia-testing/run-1/a", commit)

    with pytest.raises(WorkspaceError, match="cannot create worktree"):
        workspace.create(tmp_path / "two", "ia-testing/run-1/a", commit)

    assert not (tmp_path / "two").exists()
