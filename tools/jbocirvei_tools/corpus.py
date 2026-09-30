"""Create and inspect the corpus repository.

SPEC.md 2.2 (2026-09-15): the corpus is its own git repository at
`JBOCIRVEI_CORPUS`, with its own object store. It is not a worktree of the tools
checkout. A worktree (a second working directory of a repository) uses the
objects of its repository. So the whole projection (many gigabytes) went into
the tools checkout, and the charter keeps bulk state out of that checkout.
Also, a build wrote there, and not at the configured path of the corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .git import GitError, git_output, run_git


class CorpusError(RuntimeError):
    """The requested state of the corpus is not safe or not valid."""


@dataclass(frozen=True, slots=True)
class CorpusStatus:
    path: Path
    exists: bool
    branch: str | None = None
    head: str | None = None
    commits: int = 0


def corpus_status(path: Path) -> CorpusStatus:
    resolved = path.resolve()
    if not resolved.exists():
        return CorpusStatus(path=resolved, exists=False)
    marker = resolved / ".git"
    if marker.is_file():
        raise CorpusError(
            f"corpus at {resolved} is a worktree of another repository, so its "
            "objects are outside it (SPEC.md 2.2). Copy the history into a new "
            "repository at this path. Then remove the worktree and the main ref "
            "from the repository that held it."
        )
    if not marker.is_dir():
        raise CorpusError(f"corpus path exists but is not a git repository: {resolved}")
    branch_result = run_git(
        resolved, ["symbolic-ref", "--quiet", "--short", "HEAD"], check=False
    )
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    head_result = run_git(resolved, ["rev-parse", "--verify", "HEAD"], check=False)
    head = head_result.stdout.strip() if head_result.returncode == 0 else None
    commits = int(git_output(resolved, ["rev-list", "--count", "HEAD"])) if head else 0
    return CorpusStatus(
        path=resolved, exists=True, branch=branch, head=head, commits=commits
    )


def _has_schema(corpus: Path) -> bool:
    """Return True if the tip of the corpus is a projection, not other history.

    A worktree can belong only to the tools repository, and that fact was the
    check. A standalone repository gives no such sign. So the marker is the one
    file that every projected commit contains.
    """

    return (
        run_git(
            corpus, ["cat-file", "-e", "HEAD:_meta/schema.toml"], check=False
        ).returncode
        == 0
    )


def _remote_url(repo_root: Path, remote: str = "origin") -> str | None:
    result = run_git(repo_root, ["remote", "get-url", remote], check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def init_corpus(config: Config) -> tuple[CorpusStatus, bool]:
    """Create the corpus repository. A second run changes nothing.

    If the corpus exists, this function uses it unchanged. If not, the function
    creates the repository at `JBOCIRVEI_CORPUS`, with the remote of the tools
    checkout as `origin`. If that remote publishes `main`, the function fetches
    it. If not, the repository stays unborn (it has no commits), and the first
    build commits the root.
    """

    current = corpus_status(config.corpus)
    if current.exists:
        if current.branch != "main":
            raise CorpusError(
                f"existing corpus is on {current.branch or 'detached HEAD'}, expected main"
            )
        if current.head and not _has_schema(config.corpus):
            raise CorpusError(
                f"existing repository at {current.path} has commits but no "
                "_meta/schema.toml: refusing to build the corpus over unrelated history"
            )
        return current, False
    if config.corpus.is_symlink():
        raise CorpusError(
            f"the corpus path is a symlink, which is not allowed: {config.corpus}"
        )

    config.corpus.parent.mkdir(parents=True, exist_ok=True)
    run_git(
        config.corpus.parent,
        ["init", "--initial-branch=main", str(config.corpus)],
    )
    url = _remote_url(config.repo_root)
    if url:
        run_git(config.corpus, ["remote", "add", "origin", url])
        published = run_git(
            config.corpus,
            ["ls-remote", "--heads", "origin", "refs/heads/main"],
            check=False,
        )
        if published.returncode == 0 and published.stdout.strip():
            run_git(
                config.corpus,
                [
                    "fetch",
                    "--no-tags",
                    "origin",
                    "refs/heads/main:refs/remotes/origin/main",
                ],
            )
            run_git(config.corpus, ["reset", "--hard", "refs/remotes/origin/main"])
            run_git(config.corpus, ["branch", "--set-upstream-to=origin/main", "main"])
            if not _has_schema(config.corpus):
                raise CorpusError(
                    f"{url} publishes a main without _meta/schema.toml: "
                    "refusing to build the corpus over unrelated history"
                )
    status = corpus_status(config.corpus)
    if status.branch != "main":
        raise GitError("corpus init did not make a main branch")
    return status, True
