from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from jbocirvei_tools.build import build_corpus
from jbocirvei_tools.config import Config
from jbocirvei_tools.corpus import CorpusError, corpus_status, init_corpus
from jbocirvei_tools.render import RenderContext, commit_instruction_refresh

HERE = Path(__file__).resolve()
WORKSPACE = HERE.parents[2]
TEMPLATES = WORKSPACE / "tools" / "templates" / "main"


def utc_z(value: str) -> str:
    """Write a zero UTC offset as `Z`, in either form that git prints.

    For `%aI`, `%cI` and `--date=iso-strict`, some git versions print a zero
    offset as `Z`, and others print `+00:00`. Both forms are the same ISO 8601
    instant. So the tests accept either form, and still pin the date and the
    zero offset.
    """

    return value[: -len("+00:00")] + "Z" if value.endswith("+00:00") else value


def run(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    actual_env = dict(os.environ)
    if env:
        actual_env.update(env)
    result = subprocess.run(
        list(args), cwd=cwd, env=actual_env, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def git(cwd: Path, *args: str) -> str:
    return run(cwd, "git", *args)


def seed_tools_repo(path: Path) -> str:
    path.mkdir()
    git(path, "init", "--initial-branch=tools")
    shutil.copytree(TEMPLATES, path / "tools/templates/main")
    (path / "README.md").write_text("seed tools checkout\n")
    git(path, "add", ".")
    env = {
        "GIT_AUTHOR_NAME": "fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
        "GIT_COMMITTER_NAME": "fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
    }
    run(path, "git", "commit", "-m", "seed", env=env)
    return git(path, "rev-parse", "HEAD")


def publish_main(source: Path, seed: Path) -> str:
    """Give the seed tools repository a `main` branch, as the real remote has."""

    source.mkdir()
    git(source, "init", "--initial-branch=main")
    (source / "_meta").mkdir()
    (source / "_meta" / "schema.toml").write_text("projection_schema = 1\n")
    git(source, "add", ".")
    run(
        source,
        "git",
        "commit",
        "-m",
        "published root",
        env={
            "GIT_AUTHOR_NAME": "jbocirvei",
            "GIT_AUTHOR_EMAIL": "tools@jbocirvei.invalid",
            "GIT_AUTHOR_DATE": "1970-01-01T00:00:00+00:00",
            "GIT_COMMITTER_NAME": "jbocirvei",
            "GIT_COMMITTER_EMAIL": "tools@jbocirvei.invalid",
            "GIT_COMMITTER_DATE": "1970-01-01T00:00:00+00:00",
        },
    )
    head = git(source, "rev-parse", "HEAD")
    git(seed, "fetch", "--no-tags", str(source), "main:refs/heads/main")
    return head


def clone_and_init(seed: Path, clone: Path) -> tuple[Config, str]:
    """Clone the tools checkout, create the corpus, and build its root.

    SPEC.md 2.2: the corpus is its own repository. If the remote publishes no
    `main`, `init` leaves the corpus empty. The first build makes the root
    commit, not init.
    """

    run(seed.parent, "git", "clone", "--branch", "tools", str(seed), str(clone))
    state = clone.parent / f"{clone.name}-state"
    config = Config(
        repo_root=clone,
        corpus=state / "corpus",
        archive=state / "archive",
        tmp=state / "tmp",
    )
    status, created = init_corpus(config)
    assert created
    assert status.branch == "main"
    assert status.commits == 0
    assert status.head is None
    # The corpus keeps its own objects. That is the purpose of the change.
    assert (config.corpus / ".git" / "objects").is_dir()
    # It also takes its remote from the tools checkout, so the maintainer
    # configures only one remote.
    assert git(config.corpus, "remote", "get-url", "origin") == git(
        clone, "remote", "get-url", "origin"
    )

    report = build_corpus(config, {})
    status = corpus_status(config.corpus)
    # A build with no sources makes the root and one refresh commit at the tip.
    assert status.commits == 2
    assert status.head == report.head
    return config, git(config.corpus, "rev-list", "--max-parents=0", "HEAD")


def test_clean_clone_gets_one_rendered_epoch_root(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    tools_commit = seed_tools_repo(seed)
    config, root = clone_and_init(seed, tmp_path / "clone")

    status = corpus_status(config.corpus)
    assert status == corpus_status(config.corpus)
    assert utc_z(git(config.corpus, "show", "-s", "--format=%aI", root)) == (
        "1970-01-01T00:00:00Z"
    )
    assert utc_z(git(config.corpus, "show", "-s", "--format=%cI", root)) == (
        "1970-01-01T00:00:00Z"
    )
    assert (
        git(config.corpus, "show", "-s", "--format=%an <%ae>", root)
        == "jbocirvei <tools@jbocirvei.invalid>"
    )
    message = git(config.corpus, "show", "-s", "--format=%B", root)
    assert "Source: meta" in message
    assert "Source-Id: root" in message
    assert "Event: refresh" in message
    assert "Time-Confidence: exact" in message

    files = set(git(config.corpus, "ls-tree", "-r", "--name-only", root).splitlines())
    assert files == {
        ".agents/rules/jbocirvei.md",
        ".gitignore",
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        "README.md",
        "_meta/schema.toml",
    }
    readme = git(config.corpus, "show", f"{root}:README.md")
    assert "{{" not in readme
    # SPEC.md 3.11/§5: the root names neither the tools commit nor a snapshot.
    # So a new tools commit does not change every hash in main. The refresh
    # commit at the tip contains both.
    assert tools_commit not in readme
    # The test checks that the root renders the placeholder, not the identity of
    # a real build. An earlier test pinned the full sentence. Then an edit to the
    # README prose looked like a regression in the contract of the root.
    assert "`pending`" in readme
    schema = git(config.corpus, "show", f"{root}:_meta/schema.toml")
    assert "tools_commit" not in schema
    assert "projection_schema = 1" in schema
    assert "instructions = 1" in schema


def test_root_commit_is_deterministic_across_two_clean_clones(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed_tools_repo(seed)
    _first_config, first = clone_and_init(seed, tmp_path / "clone-one")
    _second_config, second = clone_and_init(seed, tmp_path / "clone-two")
    assert first == second


def test_corpus_init_is_idempotent(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed_tools_repo(seed)
    config, _root = clone_and_init(seed, tmp_path / "clone")
    built = corpus_status(config.corpus)
    status, created = init_corpus(config)
    assert not created
    assert status.head == built.head
    assert status.commits == built.commits


def occupied_corpus_config(tmp_path: Path, corpus: Path) -> Config:
    tools = tmp_path / "tools-repo"
    if not tools.exists():
        seed_tools_repo(tools)
    return Config(
        repo_root=tools,
        corpus=corpus,
        archive=tmp_path / "archive",
        tmp=tmp_path / "tmp",
    )


def test_corpus_init_rejects_a_repository_holding_unrelated_history(
    tmp_path: Path,
) -> None:
    """SPEC.md 2.2: nobody can recognize a standalone corpus by its objects.

    While the corpus was a worktree, the check was that it belonged to the tools
    repository. Now it is its own repository. So the sign is the one file that
    every projected commit contains.
    """

    unrelated = tmp_path / "corpus"
    unrelated.mkdir()
    git(unrelated, "init", "--initial-branch=main")
    (unrelated / "notes.txt").write_text("someone else's work\n")
    git(unrelated, "add", ".")
    run(
        unrelated,
        "git",
        "commit",
        "-m",
        "unrelated",
        env={
            "GIT_AUTHOR_NAME": "fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        },
    )
    config = occupied_corpus_config(tmp_path, unrelated)
    with pytest.raises(CorpusError, match="refusing to build the corpus over"):
        init_corpus(config)


def test_corpus_init_clones_a_published_main(tmp_path: Path) -> None:
    """SPEC.md 2.2: if the remote already publishes main, init fetches it.

    Only the first maintainer builds a root. All other maintainers start from
    the published main, and their corpus tracks it.
    """

    seed = tmp_path / "seed"
    seed_tools_repo(seed)
    published = publish_main(tmp_path / "published", seed)

    clone = tmp_path / "clone"
    run(tmp_path, "git", "clone", "--branch", "tools", str(seed), str(clone))
    state = tmp_path / "clone-state"
    config = Config(
        repo_root=clone,
        corpus=state / "corpus",
        archive=state / "archive",
        tmp=state / "tmp",
    )
    status, created = init_corpus(config)
    assert created
    assert status.head == published
    assert status.branch == "main"
    assert (config.corpus / "_meta" / "schema.toml").is_file()
    assert git(config.corpus, "rev-parse", "--abbrev-ref", "main@{upstream}") == (
        "origin/main"
    )
    # A second init accepts it, because the schema file shows that it is a corpus.
    again, created_again = init_corpus(config)
    assert not created_again
    assert again.head == published


def test_corpus_init_rejects_a_repository_on_another_branch(tmp_path: Path) -> None:
    elsewhere = tmp_path / "corpus"
    elsewhere.mkdir()
    git(elsewhere, "init", "--initial-branch=trunk")
    config = occupied_corpus_config(tmp_path, elsewhere)
    with pytest.raises(CorpusError, match="expected main"):
        init_corpus(config)


def test_corpus_init_rejects_the_old_worktree_layout(tmp_path: Path) -> None:
    """A corpus that is still a worktree keeps its objects in the tools checkout."""

    seed = tmp_path / "tools-repo"
    seed_tools_repo(seed)
    corpus = tmp_path / "corpus"
    git(seed, "worktree", "add", "--orphan", "-b", "main", str(corpus))
    assert (corpus / ".git").is_file()
    config = occupied_corpus_config(tmp_path, corpus)
    with pytest.raises(CorpusError, match="worktree of another repository"):
        init_corpus(config)


def test_corpus_init_rejects_a_path_that_is_not_a_repository(tmp_path: Path) -> None:
    occupied = tmp_path / "corpus"
    occupied.mkdir()
    (occupied / "stray.txt").write_text("not a corpus\n")
    config = occupied_corpus_config(tmp_path, occupied)
    with pytest.raises(CorpusError, match="not a git repository"):
        init_corpus(config)


def test_instruction_refresh_is_one_source_event(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    tools_commit = seed_tools_repo(seed)
    config, root = clone_and_init(seed, tmp_path / "clone")
    event_time = datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
    context = RenderContext(
        snapshot="snapshot/20200102T030405Z",
        tools_commit=tools_commit,
        coverage_tables="Wiki: 10 revisions.",
    )
    refreshed = commit_instruction_refresh(
        config.repo_root,
        config.corpus,
        source_time=event_time,
        source_id="refresh@20200102T030405Z",
        context=context,
    )
    assert refreshed != root
    # The build made the root and the refresh at its tip. This adds a third commit.
    assert git(config.corpus, "rev-list", "--count", "HEAD") == "3"
    assert (
        utc_z(git(config.corpus, "show", "-s", "--format=%aI"))
        == "2020-01-02T03:04:05Z"
    )
    message = git(config.corpus, "show", "-s", "--format=%B")
    assert "Event: refresh" in message
    assert "Source-Id: refresh@20200102T030405Z" in message
    assert "Wiki: 10 revisions." in (config.corpus / "README.md").read_text()
