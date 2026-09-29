"""Run the build, update, snapshot and verification steps.

A build is transactional: it changes main only if every step succeeds.
"""

from __future__ import annotations

import csv
import heapq
import json
import re
import stat
import tempfile
import tomllib
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from pathlib import Path

from .archive.manifest import ArchiveManifest
from .config import Config
from .corpus import CorpusError, corpus_status, init_corpus
from .git import (
    EPOCH,
    BuildCommitSession,
    Event,
    EventError,
    FastImportSession,
    GitError,
    Identity,
    commit_event,
    git_output,
    run_git,
)
from .render import (
    RenderContext,
    commit_instruction_refresh,
    commit_root,
    corpus_tallies,
    coverage_table,
    layout_summary,
    render_main,
)

EventFactory = Callable[[], Iterable[Event]]
_TRAILER = re.compile(r"^([A-Z][A-Za-z0-9-]*): (.*)$")
_MAX_CORPUS_FILE = 100 * 1024 * 1024
_MAILDIR_NAME = re.compile(r"[0-9]+\.[0-9a-f]{16}\.jbomohi:2,S")
_IRC_HEADER = re.compile(
    r"^# irc #(?P<channel>[a-z][a-z0-9_-]*) "
    r"(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"(?:\.\.[0-9]{4}-[0-9]{2}-[0-9]{2})?) "
    r"tz=(?:unknown|[+-][0-9]{4}(?:/[+-][0-9]{4})*) "
    r"source=\S+ "
    r"format=(?:iso|legacy|bracket|irssi|undated)"
    r"(?:\+(?:iso|legacy|bracket|irssi|undated))*"
    r"(?P<days> days=unknown)?$"
)
_IRC_LINE = re.compile(
    r"^(?:(?P<clock>[0-9]{2}:[0-9]{2}:[0-9]{2}|--:--:--) "
    r"(?:<[^>]+> .*|\* \S+ .*|-- .*)|-- day boundary [0-9]+)$"
)
_DEFINITION_NAME = re.compile(r"[^/]+-[0-9]+\.md")
_DEFINITION_FIELDS = {
    "id",
    "word",
    "lang",
    "author",
    "updated",
    "version",
    "score",
    "score_as_of",
    "status",
    "jargon",
    "selmaho",
    "keywords",
}


@dataclass(frozen=True, slots=True)
class BuildReport:
    head: str
    commits: int
    events: int
    snapshot: str
    coverage: str
    # What an update did, so that it can report it, and the reader does not
    # have to guess. A build sets none of these, because it writes everything.
    events_by_source: Mapping[str, int] = field(default_factory=dict)
    refreshed: bool = False
    tagged: bool = False


@dataclass(frozen=True, slots=True)
class VerifyReport:
    commits: int
    files: int
    sources: int
    csv_indexes: int
    mail_messages: int


@dataclass(frozen=True, slots=True)
class PushReport:
    main_updates: int
    snapshot: str


def require_clean_tools(repo_root: Path) -> str:
    """Return the exact tools commit for the rendered metadata. It must be clean."""

    dirty = git_output(repo_root, ["status", "--porcelain=v1", "--untracked-files=all"])
    if dirty:
        raise CorpusError(
            "tools worktree is dirty. Commit or remove the changes before you run "
            "build, update or refresh."
        )
    return git_output(repo_root, ["rev-parse", "HEAD"])


def merge_named_events(
    sources: Mapping[str, EventFactory],
    *,
    until: datetime | None = None,
    meta_sink: dict[str, dict[str, str | bytes]] | None = None,
) -> Iterator[tuple[str, Event]]:
    """Merge the source streams (a k-way merge). Keep the fixed order in each stream."""

    heap: list[
        tuple[tuple[int, datetime, str, str], str, int, Event, Iterator[Event]]
    ] = []
    sequence = 0

    def key(event: Event) -> tuple[int, datetime, str, str]:
        return (
            0 if event.time_confidence == "pre-epoch" else 1,
            event.source_time,
            event.source,
            event.source_id,
        )

    for name, factory in sorted(sources.items()):
        iterator = iter(factory())
        try:
            event = next(iterator)
        except StopIteration:
            continue
        event.validate()
        heapq.heappush(heap, (key(event), name, sequence, event, iterator))
        sequence += 1
    while heap:
        _key, name, _sequence, event, iterator = heapq.heappop(heap)
        if until is None or event.source_time <= until:
            yield name, event
        try:
            following = next(iterator)
        except StopIteration:
            if meta_sink is not None:
                meta_sink[name] = {
                    path: value
                    for path, value in event.changes.items()
                    if path.startswith("_meta/")
                }
            continue
        following.validate()
        heapq.heappush(heap, (key(following), name, sequence, following, iterator))
        sequence += 1


def merge_events(
    sources: Mapping[str, EventFactory], *, until: datetime | None = None
) -> Iterator[Event]:
    for _name, event in merge_named_events(sources, until=until):
        yield event


def _archive_manifest_changes(archive: Path) -> dict[str, bytes]:
    changes: dict[str, bytes] = {}
    consolidated: dict[tuple[str, str], list[ArchiveManifest]] = {}
    root = archive / "manifests"
    if not root.exists():
        return changes
    for path in sorted(root.rglob("*.toml")):
        if path.is_symlink() or not path.is_file():
            raise CorpusError(f"unsafe archive manifest path: {path}")
        manifest = ArchiveManifest.load(path)
        if manifest.kind in {"mhonarc-page", "numbered-rfc822"}:
            if not manifest.source.startswith("mail/"):
                raise CorpusError(f"per-page manifest has non-mail source: {path}")
            list_name = manifest.source.removeprefix("mail/")
            consolidated.setdefault((list_name, manifest.kind), []).append(manifest)
            continue
        relative = path.relative_to(root).as_posix()
        changes[f"_meta/archive/{relative}"] = path.read_bytes()
    for (list_name, kind), manifests in sorted(consolidated.items()):
        lines: list[str] = []
        for manifest in sorted(manifests, key=lambda item: item.origin):
            lines.extend(
                [
                    "[[objects]]",
                    f"source = {json.dumps(manifest.source)}",
                    f"kind = {json.dumps(manifest.kind)}",
                    f"origin = {json.dumps(manifest.origin)}",
                    f"fetched_at = {manifest.fetched_at.isoformat(timespec='seconds')}",
                    f"sha256 = {json.dumps(manifest.sha256)}",
                    f"bytes = {manifest.bytes}",
                    f"notes = {json.dumps(manifest.notes)}",
                    "",
                    "[objects.coverage]",
                    f"from = {json.dumps(manifest.coverage['from'])}",
                    f"to = {json.dumps(manifest.coverage['to'])}",
                ]
            )
            if "character_encoding" in manifest.coverage:
                lines.append(
                    "character_encoding = "
                    + json.dumps(manifest.coverage["character_encoding"])
                )
            lines.extend(["", "[objects.coverage.counts]"])
            lines.extend(
                f"{json.dumps(name)} = {count}"
                for name, count in sorted(manifest.coverage["counts"].items())
            )
            lines.append("")
        target = f"_meta/archive/mail/{list_name}/{kind}.toml"
        changes[target] = ("\n".join(lines) + "\n").encode("utf-8")
    return changes


def _snapshot_name(source_time: datetime) -> str:
    return "snapshot/" + source_time.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _tag_snapshot(
    corpus: Path,
    head: str,
    name: str,
    source_time: datetime,
    message: str,
    *,
    replace: bool = False,
) -> None:
    """Tag the snapshot. Replace a stale tag only for a rebuild.

    SPEC.md 4.2: `build` replaces `main` by definition. So a snapshot tag can
    name a commit that is no longer in the history. That tag is stale, and the
    build points it at the new commit. `update` only appends. So a tag that it
    moves names a commit that is still there, and the move breaks a citation.
    """

    existing = run_git(
        corpus, ["rev-parse", "--verify", f"refs/tags/{name}^{{}}"], check=False
    )
    if existing.returncode == 0:
        previous = existing.stdout.strip()
        if previous == head:
            return
        reachable = run_git(
            corpus,
            ["merge-base", "--is-ancestor", previous, head],
            check=False,
        )
        if not replace or reachable.returncode == 0:
            raise GitError(f"snapshot tag already names another commit: {name}")
        run_git(corpus, ["tag", "-d", name])
    date = source_time.astimezone(UTC).replace(microsecond=0).isoformat()
    run_git(
        corpus,
        ["tag", "-a", name, head, "-m", message],
        env={
            "GIT_COMMITTER_NAME": Identity.tool().name,
            "GIT_COMMITTER_EMAIL": Identity.tool().email,
            "GIT_COMMITTER_DATE": date,
        },
    )


def _install_main(config: Config, scratch: Path, final_head: str) -> None:
    """Move the finished history into the corpus repository, not the tools one."""

    old = run_git(
        config.corpus, ["rev-parse", "--verify", "refs/heads/main"], check=False
    )
    old_head = old.stdout.strip() if old.returncode == 0 else "0" * len(final_head)
    run_git(config.corpus, ["fetch", "--no-tags", str(scratch), "main"])
    run_git(config.corpus, ["update-ref", "refs/heads/main", final_head, old_head])
    run_git(config.corpus, ["reset", "--hard", final_head])
    _materialize_maildir_modes(config.corpus)


def _materialize_maildir_modes(corpus: Path) -> None:
    """Set the Maildir file mode in the working tree. Git trees cannot keep it."""

    root = corpus / "mail"
    if not root.exists():
        return
    for path in sorted(root.glob("*/cur/*")):
        if path.is_symlink() or not path.is_file():
            raise CorpusError(f"unsafe Maildir message path: {path}")
        path.chmod(0o444)


BACKENDS = ("fast-import", "session", "plumbing")


def _commit_all(
    scratch: Path, events: Iterable[Event], backend: str
) -> tuple[int, datetime]:
    """Commit the whole event stream through the selected backend.

    Every backend must make the same commits. The backends differ only in how
    much work they do. All three stay callable, so that a test can prove this
    claim on the real corpus, and not only on fixtures.
    """

    count = 0
    last_time = EPOCH
    if backend == "fast-import":
        with FastImportSession(scratch) as session:
            for event in events:
                session.commit(event)
                count += 1
                last_time = event.source_time
    elif backend == "session":
        with BuildCommitSession(scratch) as live:
            for event in events:
                live.commit(event)
                count += 1
                last_time = event.source_time
    elif backend == "plumbing":
        for event in events:
            commit_event(event, scratch)
            count += 1
            last_time = event.source_time
    else:
        raise GitError(f"unknown build backend: {backend!r}")
    return count, last_time


def build_corpus(
    config: Config,
    sources: Mapping[str, EventFactory],
    *,
    until: datetime | None = None,
    backend: str = "fast-import",
) -> BuildReport:
    """Build a new orphan main history. Install it only if every step succeeds."""

    tools_commit = require_clean_tools(config.repo_root)
    status, _created = init_corpus(config)
    if status.branch != "main":
        raise CorpusError("build needs the corpus repository on main")
    dirty = git_output(
        config.corpus, ["status", "--porcelain=v1", "--untracked-files=all"]
    )
    if dirty:
        raise CorpusError(
            "corpus working tree is dirty: refusing the transactional build"
        )

    temporary_root = config.tmp
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="jbomohi-build-", dir=temporary_root
    ) as temporary:
        scratch = Path(temporary) / "main"
        run_git(
            scratch.parent,
            ["init", "--initial-branch=main", str(scratch)],
        )
        commit_root(config.repo_root, scratch)
        event_count, last_time = _commit_all(
            scratch,
            (event for _name, event in merge_named_events(sources, until=until)),
            backend,
        )
        snapshot = _snapshot_name(last_time)
        # Read the table from the history, as every refresh does. Then build,
        # update and refresh always render the same table for one corpus (#63).
        coverage = coverage_table(scratch, corpus_tallies(scratch))
        refresh_id = "refresh@" + snapshot.removeprefix("snapshot/")
        commit_instruction_refresh(
            config.repo_root,
            scratch,
            source_time=last_time,
            source_id=refresh_id,
            context=RenderContext(
                snapshot=snapshot,
                tools_commit=tools_commit,
                coverage_tables=coverage,
                layout_summary=layout_summary(scratch),
            ),
            extra_changes=_archive_manifest_changes(config.archive),
        )
        final_head = git_output(scratch, ["rev-parse", "HEAD"])
        commits = int(git_output(scratch, ["rev-list", "--count", "HEAD"]))
        _install_main(config, scratch, final_head)
    _tag_snapshot(
        config.corpus, final_head, snapshot, last_time, coverage, replace=True
    )
    return BuildReport(final_head, commits, event_count, snapshot, coverage)


@dataclass(frozen=True, slots=True)
class EventAudit:
    """What `verify --events` found in the merged stream."""

    events: int
    invalid: tuple[tuple[str, str, str], ...]


def audit_events(
    sources: Mapping[str, EventFactory], until: datetime | None = None
) -> EventAudit:
    """Make sure that each event from the sources is valid, and commit none.

    A build stops at its first invalid event. So each instance of a problem
    across the corpus costs one full build to find. Run this before `build`.

    The function walks each source by itself, not through the merge. An event
    that is invalid at construction raises an error out of its projector, and
    that ends its stream. In a merge, one such event hides the problems of all
    other sources behind it. A separate walk also costs nothing, because
    validity is a property of an event, not of its place in the order.
    """

    invalid: list[tuple[str, str, str]] = []
    count = 0
    for name in sorted(sources):
        stream = iter(sources[name]())
        produced = 0
        while True:
            try:
                event = next(stream)
            except StopIteration:
                break
            except EventError as exc:
                # The projector was not able to make the event, and that ends
                # this stream. Report where it stopped, because there is no id.
                invalid.append((name, f"<after {produced} events>", str(exc)))
                break
            produced += 1
            count += 1
            if until is not None and event.source_time > until:
                continue
            try:
                event.validate()
            except EventError as exc:
                invalid.append((name, event.source_id, str(exc)))
    return EventAudit(count, tuple(invalid))


def _lf_lines(text: str) -> list[str]:
    """Split on LF only, because LF is the line delimiter of the corpus.

    `str.splitlines` also splits on U+0085, U+2028 and U+2029. Those are
    ordinary characters in archived text. For example, a 2007 #lojban line
    contains U+0085. A split on them makes one stored line into several lines,
    and moves every line number after it. Then a file that the projector wrote
    looks malformed to the reader. SPEC.md 3.1.2 sets LF as the delimiter.
    """

    text = text.removesuffix("\n")
    return text.split("\n") if text else []


def _trailers_from_body(body: str) -> dict[str, str]:
    trailers: dict[str, str] = {}
    for line in _lf_lines(body):
        matched = _TRAILER.fullmatch(line)
        if matched:
            trailers[matched.group(1)] = matched.group(2)
    return trailers


def _history_records(corpus: Path) -> list[tuple[str, str, tuple[str, ...]]]:
    output = run_git(
        corpus,
        [
            "log",
            "--reverse",
            "-z",
            "--format=%x1e%H%x00%B%x00",
            "--name-only",
        ],
    ).stdout
    records: list[tuple[str, str, tuple[str, ...]]] = []
    for chunk in output.split("\x1e"):
        if not chunk.strip("\0\n"):
            continue
        try:
            commit, body, raw_paths = chunk.split("\0", 2)
        except ValueError as exc:
            raise CorpusError("cannot parse streamed git history") from exc
        paths = tuple(
            path.lstrip("\n")
            for path in raw_paths.strip("\0\n").split("\0")
            if path.lstrip("\n")
        )
        records.append((commit, body, paths))
    return records


def existing_source_ids(corpus: Path) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for _commit, body, _paths in _history_records(corpus):
        trailers = _trailers_from_body(body)
        source = trailers.get("Source")
        source_id = trailers.get("Source-Id")
        if source and source_id:
            result.add((source, source_id))
    return result


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise CorpusError(f"CSV index has no header: {path}")
            return list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise CorpusError(f"cannot read CSV index {path}: {exc}") from exc


def _verify_irc(corpus: Path) -> None:
    root = corpus / "irc"
    if not root.exists():
        return
    for path in sorted(root.rglob("*.txt")):
        relative = path.relative_to(corpus).as_posix()
        parts = path.relative_to(root).parts
        if len(parts) != 3:
            raise CorpusError(f"invalid IRC output path: {relative}")
        channel, year, filename = parts
        try:
            lines = _lf_lines(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            raise CorpusError(f"cannot read IRC output {relative}: {exc}") from exc
        matched = _IRC_HEADER.fullmatch(lines[0] if lines else "")
        if matched is None:
            raise CorpusError(f"invalid IRC header: {relative}")
        date_key = matched["date"]
        if matched["channel"] != channel or date_key[:4] != year:
            raise CorpusError(
                f"IRC output sits under the wrong channel/year: {relative}"
            )
        expected_filename = date_key.replace("..", "--") + ".txt"
        if filename != expected_filename:
            raise CorpusError(f"IRC output filename disagrees with header: {relative}")
        dates = date_key.split("..")
        try:
            parsed_dates = [date.fromisoformat(value) for value in dates]
        except ValueError as exc:
            raise CorpusError(f"invalid IRC date in {relative}") from exc
        if len(parsed_dates) == 2 and parsed_dates[0] > parsed_dates[1]:
            raise CorpusError(f"reversed IRC date window: {relative}")
        if (matched["days"] is not None) != (len(parsed_dates) == 2):
            raise CorpusError(f"IRC range/header mismatch: {relative}")
        for line_number, line in enumerate(lines[1:], 2):
            body_match = _IRC_LINE.fullmatch(line)
            if body_match is None:
                raise CorpusError(
                    f"invalid normalized IRC line at {relative}:{line_number}"
                )
            clock = body_match["clock"]
            if clock is not None and clock != "--:--:--":
                try:
                    time.fromisoformat(clock)
                except ValueError as exc:
                    raise CorpusError(
                        f"invalid IRC clock at {relative}:{line_number}"
                    ) from exc


def _verify_dictionary(corpus: Path) -> None:
    for votes in sorted(corpus.glob("**/votes.csv")):
        raise CorpusError(f"deprecated dictionary votes.csv is present: {votes}")
    root = corpus / "dict"
    if not root.exists():
        return
    for path in sorted(root.glob("*/*.md")):
        if not _DEFINITION_NAME.fullmatch(path.name):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise CorpusError(
                f"cannot read dictionary definition {path}: {exc}"
            ) from exc
        if not text.startswith("+++\n") or "\n+++\n" not in text[4:]:
            raise CorpusError(f"invalid dictionary front matter delimiters: {path}")
        front_matter, _body = text[4:].split("\n+++\n", 1)
        try:
            data = tomllib.loads(front_matter)
        except tomllib.TOMLDecodeError as exc:
            raise CorpusError(
                f"invalid dictionary front matter in {path}: {exc}"
            ) from exc
        missing = _DEFINITION_FIELDS - data.keys()
        if missing:
            raise CorpusError(
                f"dictionary front matter is missing {', '.join(sorted(missing))}: {path}"
            )
        if data["status"] not in {"current", "deleted", "superseded"}:
            raise CorpusError(f"invalid dictionary definition status: {path}")
        if not all(
            isinstance(data[name], str)
            for name in (
                "word",
                "lang",
                "author",
                "updated",
                "score_as_of",
                "jargon",
                "selmaho",
            )
        ):
            raise CorpusError(f"invalid dictionary front matter text field: {path}")
        if not all(
            isinstance(data[name], int) and not isinstance(data[name], bool)
            for name in ("id", "version", "score")
        ):
            raise CorpusError(f"invalid dictionary front matter integer field: {path}")
        definition_id = data["id"]
        filename_suffix = f"-{definition_id}.md"
        if definition_id < 1 or not path.name.endswith(filename_suffix):
            raise CorpusError(f"dictionary definition id/path disagree: {path}")
        if path.name.removesuffix(filename_suffix) != data["lang"]:
            raise CorpusError(f"dictionary definition language/path disagree: {path}")
        try:
            updated = datetime.fromisoformat(data["updated"])
            date.fromisoformat(data["score_as_of"])
        except ValueError as exc:
            raise CorpusError(f"invalid dictionary front matter date: {path}") from exc
        if updated.tzinfo is None:
            raise CorpusError(f"dictionary updated timestamp has no offset: {path}")
        keywords = data["keywords"]
        if not isinstance(keywords, list) or any(
            not isinstance(item, dict)
            or set(item) != {"word", "sense", "place"}
            or not isinstance(item["word"], str)
            or not isinstance(item["sense"], str)
            or not isinstance(item["place"], int)
            or isinstance(item["place"], bool)
            or item["place"] < 0
            for item in keywords
        ):
            raise CorpusError(f"invalid dictionary keywords: {path}")


def _verify_mail(corpus: Path) -> int:
    mail_messages = 0
    mail_root = corpus / "mail"
    if not mail_root.exists():
        return mail_messages
    for list_dir in sorted(path for path in mail_root.iterdir() if path.is_dir()):
        for required_dir in ("cur", "new", "tmp", "threads"):
            if not (list_dir / required_dir).is_dir():
                raise CorpusError(
                    f"mail list {list_dir.name} is missing {required_dir}/"
                )
        for staging_name in ("new", "tmp"):
            for path in (list_dir / staging_name).iterdir():
                if path.name != ".keep":
                    raise CorpusError(f"Maildir {staging_name}/ is not empty: {path}")
        for path in (list_dir / "cur").iterdir():
            if (
                path.is_symlink()
                or not path.is_file()
                or not _MAILDIR_NAME.fullmatch(path.name)
            ):
                raise CorpusError(f"invalid Maildir filename: {path}")
            if stat.S_IMODE(path.stat().st_mode) != 0o444:
                raise CorpusError(
                    f"Maildir message is writable, expected mode 0444: {path}"
                )
            mail_messages += 1

        message_index = corpus / "_meta" / "mail" / list_dir.name / "messages.csv"
        thread_index = corpus / "_meta" / "mail" / list_dir.name / "threads.csv"
        if not message_index.is_file() or not thread_index.is_file():
            raise CorpusError(
                f"mail list {list_dir.name} is missing message/thread indexes"
            )
        thread_rows = _read_csv(thread_index)
        thread_paths: dict[str, str] = {}
        thread_counts: dict[str, int] = {}
        for row_number, row in enumerate(thread_rows, 2):
            key = row.get("thread_key", "")
            path = row.get("path", "")
            if not key or not path or key in thread_paths:
                raise CorpusError(
                    f"invalid thread index row at {thread_index}:{row_number}"
                )
            try:
                thread_counts[key] = int(row.get("messages", ""))
            except ValueError as exc:
                raise CorpusError(
                    f"invalid thread message count at {thread_index}:{row_number}"
                ) from exc
            thread_paths[key] = path
        observed_counts = {key: 0 for key in thread_paths}
        expected_entries: dict[str, list[tuple[str, int]]] = {
            path: [] for path in thread_paths.values()
        }
        for row_number, row in enumerate(_read_csv(message_index), 2):
            key = row.get("thread_key", "")
            message_id = row.get("message_id", "")
            message_file = row.get("file", "")
            thread_path = thread_paths.get(key)
            if not message_id or not message_file or thread_path is None:
                raise CorpusError(
                    f"message lacks a valid thread mapping at {message_index}:{row_number}"
                )
            marker = f" | {message_id} | {message_file}"
            expected_entries[thread_path].append((marker, row_number))
            observed_counts[key] += 1
        if observed_counts != thread_counts:
            raise CorpusError(f"mail thread counts disagree for list {list_dir.name}")
        for thread_path, markers in expected_entries.items():
            try:
                entry_lines = [
                    line
                    for line in _lf_lines(
                        (corpus / thread_path).read_text(encoding="utf-8")
                    )
                    if line.startswith("=== ")
                ]
            except (OSError, UnicodeError) as exc:
                raise CorpusError(
                    f"cannot read mail thread view {thread_path}: {exc}"
                ) from exc
            for marker, row_number in markers:
                if not any(marker in line for line in entry_lines):
                    raise CorpusError(
                        f"message has no thread-view entry at {message_index}:{row_number}"
                    )
    return mail_messages


# The number of events that an update commits before it moves HEAD. It is small,
# so a kill loses only seconds of work. It is large enough that the cost of the
# ref update is too small to notice.
UPDATE_FLUSH_EVENTS = 256


def update_corpus(
    config: Config,
    sources: Mapping[str, EventFactory],
) -> BuildReport:
    """Append the source IDs that are not already present. Then refresh and snapshot.

    This function always returns a report, also for a run that changes nothing.
    If an update says only "no new source events", the reader must guess what
    happened to the instruction files and the tag. One time, a reader guessed
    success from a short message. So a refresh that was not possible was almost
    accepted as a real refresh.
    """

    tools_commit = _open_for_append(config, "update")
    known = existing_source_ids(config.corpus)
    event_count = 0
    by_source: Counter[str] = Counter()
    last_time: datetime | None = None
    source_meta: dict[str, dict[str, str | bytes]] = {}
    # Use one session for the whole append. Before, each event went through
    # `commit_event`, which proved that the worktree was clean and rebuilt the
    # index from HEAD. So each appended day cost a scan of the whole corpus. An
    # append of 3,300 IRC days to a corpus of 286,212 files ran at 7 seconds a
    # commit. That was six hours for work that the events do in milliseconds.
    with BuildCommitSession(config.corpus) as live:
        for source_name, event in merge_named_events(sources, meta_sink=source_meta):
            if (event.source, event.source_id) in known:
                continue
            live.commit(event)
            known.add((event.source, event.source_id))
            event_count += 1
            by_source[source_name] += 1
            last_time = event.source_time
            if event_count % UPDATE_FLUSH_EVENTS == 0:
                # If a session moves HEAD only at the end, a kill loses the
                # whole append. The flush lets an interrupted update resume. So
                # someone stopped a six-hour run, and it kept the days that it
                # already wrote.
                live.flush()
    refresh_only = last_time is None
    if refresh_only:
        # No source has a new event. Before this change, the function returned
        # here. So on a quiet day, a template change was not able to reach main
        # at all. Only a refresh commit renders the instruction files, and a
        # refresh commit came only as a side effect of new events. A refresh is
        # not a new snapshot of the record. It is the same snapshot, rendered
        # again. So it uses the same snapshot name and mints no tag.
        last_time = _tip_time(config.corpus)
        snapshot = _current_snapshot(config.corpus, last_time)
    else:
        snapshot = _snapshot_name(last_time)
    assert last_time is not None
    # The table describes the corpus, not the stream. The code reads it from the
    # history, so it counts every event. This includes the events of sources
    # that this update did not project. It is also the table that a later
    # `refresh` renders (#63).
    coverage = coverage_table(config.corpus, corpus_tallies(config.corpus))
    refresh_changes = _archive_manifest_changes(config.archive)
    # Add the metadata of every source, not only of the sources with new events.
    # A source that appended nothing still has `_meta` files that the current
    # projector renders. When the code added only the active sources, a quiet
    # source kept the shape from its last event. That was the defect of #52, one
    # level down. Git records a change only where the content differs. So the
    # diff is larger only when there is something to record.
    for source_name in sorted(source_meta):
        for path, value in source_meta.get(source_name, {}).items():
            previous = refresh_changes.get(path)
            if previous is not None and previous != value:
                raise CorpusError(f"refresh metadata collision at {path}")
            refresh_changes[path] = value
    if refresh_only:
        return _refresh_in_place(
            config,
            tools_commit=tools_commit,
            tip_time=last_time,
            snapshot=snapshot,
            coverage=coverage,
            extra_changes=refresh_changes,
        )
    context = RenderContext(
        snapshot=snapshot,
        tools_commit=tools_commit,
        layout_summary=layout_summary(config.corpus),
        coverage_tables=coverage,
    )
    commit_instruction_refresh(
        config.repo_root,
        config.corpus,
        source_time=last_time,
        source_id="refresh@" + snapshot.removeprefix("snapshot/"),
        context=context,
        extra_changes=refresh_changes,
    )
    head = git_output(config.corpus, ["rev-parse", "HEAD"])
    _tag_snapshot(config.corpus, head, snapshot, last_time, coverage)
    commits = int(git_output(config.corpus, ["rev-list", "--count", "HEAD"]))
    return BuildReport(
        head=head,
        commits=commits,
        events=event_count,
        snapshot=snapshot,
        coverage=coverage,
        events_by_source=dict(sorted(by_source.items())),
        refreshed=True,
        tagged=True,
    )


def refresh_corpus(config: Config) -> BuildReport:
    """Render the instruction files again at the tip, from the corpus only.

    A template change needs no projection. The corpus already holds every
    event, and `corpus_tallies` reads the tallies of the coverage table back
    from its history. So this function needs neither the archive nor the memory
    of a projection. It does not change `_meta/archive/` or the `_meta` files of
    any source. `update` is still the command that refreshes those.

    This function commits the same thing that `update` commits when it finds no
    new event and no changed metadata. That is the same snapshot, rendered
    again, with no new tag (SPEC.md 4.2).
    """

    tools_commit = _open_for_append(config, "refresh")
    tip_time = _tip_time(config.corpus)
    return _refresh_in_place(
        config,
        tools_commit=tools_commit,
        tip_time=tip_time,
        snapshot=_current_snapshot(config.corpus, tip_time),
        coverage=coverage_table(config.corpus, corpus_tallies(config.corpus)),
        extra_changes={},
    )


def _open_for_append(config: Config, command: str) -> str:
    """Make sure that the tools checkout and the corpus are ready for an append.

    Return the tools commit.
    """

    tools_commit = require_clean_tools(config.repo_root)
    status, _created = init_corpus(config)
    if status.branch != "main" or status.head is None:
        raise CorpusError(f"{command} requires an initialized main corpus")
    _materialize_maildir_modes(config.corpus)
    dirty = git_output(
        config.corpus, ["status", "--porcelain=v1", "--untracked-files=all"]
    )
    if dirty:
        raise CorpusError(
            f"corpus working tree is dirty: refusing {command}. If someone kills "
            "an update between flushes, it leaves the files of up to "
            f"{UPDATE_FLUSH_EVENTS} events that it did not commit. If that is the "
            "cause, `git -C <corpus> reset --hard HEAD` discards them, and the "
            "next run appends the events again. Before you do this, make sure "
            "that none of the changes is contributed work."
        )
    return tools_commit


def _refresh_in_place(
    config: Config,
    *,
    tools_commit: str,
    tip_time: datetime,
    snapshot: str,
    coverage: str,
    extra_changes: Mapping[str, str | bytes],
) -> BuildReport:
    """Commit a refresh with no new events. If no file changes, commit nothing.

    A refresh is not a new snapshot of the record. It is the same snapshot,
    rendered again. So it uses the same snapshot name and mints no tag.
    """

    context = RenderContext(
        snapshot=snapshot,
        tools_commit=tools_commit,
        layout_summary=layout_summary(config.corpus),
        coverage_tables=coverage,
    )
    # A refresh-only commit can have no changes. An empty commit is still a
    # correct commit (SPEC.md 3.3 rule 4b). But it claims a refresh when the
    # render changed nothing.
    pending = dict(render_main(config.repo_root, context))
    pending.update(extra_changes)
    refreshed = _differs_from_worktree(config.corpus, pending)
    if refreshed:
        # The parent gives this refresh a unique name, because each refresh has
        # a different parent. A citation of the refresh means "the refresh on
        # top of <commit>". The id from the snapshot name belongs to the update
        # that minted the snapshot, so this code cannot use it again.
        commit_instruction_refresh(
            config.repo_root,
            config.corpus,
            source_time=tip_time,
            source_id="refresh@" + git_output(config.corpus, ["rev-parse", "HEAD"]),
            context=context,
            extra_changes=extra_changes,
        )
    return BuildReport(
        head=git_output(config.corpus, ["rev-parse", "HEAD"]),
        commits=int(git_output(config.corpus, ["rev-list", "--count", "HEAD"])),
        events=0,
        snapshot=snapshot,
        coverage=coverage,
        events_by_source={},
        refreshed=refreshed,
        tagged=False,
    )


def _tip_time(corpus: Path) -> datetime:
    """Return the committer time of the corpus tip, the time of its newest event.

    A refresh has no source time of its own. SPEC.md 2.4 forbids clock time in
    committed content. The time of the tip is a pure function of the corpus. So
    two refreshes of the same corpus give the same date.
    """

    return datetime.fromisoformat(git_output(corpus, ["log", "-1", "--format=%cI"]))


def _current_snapshot(corpus: Path, tip_time: datetime) -> str:
    """Return the snapshot name under which this corpus is already published.

    The tag decides. If the corpus has no tag, the fallback is a name made from
    the time of the tip. That name agrees with the tag when the tip is the
    commit that got the tag.
    """

    described = run_git(
        corpus,
        ["describe", "--tags", "--abbrev=0", "--match", "snapshot/*", "HEAD"],
        check=False,
    )
    name = described.stdout.strip()
    return name if described.returncode == 0 and name else _snapshot_name(tip_time)


def _differs_from_worktree(corpus: Path, changes: Mapping[str, str | bytes]) -> bool:
    """Return True if any rendered file changes.

    Before an update runs, the code proves that the corpus worktree is clean. So
    the worktree has the content of HEAD, and the code can read it directly, not
    through `git show`.
    """

    for path, value in changes.items():
        data = value.encode("utf-8") if isinstance(value, str) else value
        target = corpus / path
        try:
            if target.read_bytes() != data:
                return True
        except OSError:
            return True
    return False


def verify_corpus(corpus: Path) -> VerifyReport:
    """Make sure that the corpus is valid.

    The checks cover commit trailers, source IDs, file limits, CSV paths and
    Maildirs.
    """

    status = corpus_status(corpus)
    if not status.exists or status.head is None:
        raise CorpusError("cannot verify a missing or unborn corpus")
    dirty = git_output(corpus, ["status", "--porcelain=v1", "--untracked-files=all"])
    if dirty:
        raise CorpusError("corpus working tree is dirty")
    seen: set[tuple[str, str, str]] = set()
    sources: set[str] = set()
    records = _history_records(corpus)
    required = {"Source", "Source-Id", "Event", "Time-Confidence"}
    for commit, body, changed in records:
        trailers = _trailers_from_body(body)
        missing = required - trailers.keys()
        if missing:
            raise CorpusError(
                f"commit {commit} is missing trailers: {', '.join(sorted(missing))}"
            )
        for path in changed:
            identity = (trailers["Source"], path, trailers["Source-Id"])
            if identity in seen:
                raise CorpusError(f"duplicate Source-Id for source/path: {identity!r}")
            seen.add(identity)
        sources.add(trailers["Source"])

    files = [
        path
        for path in corpus.rglob("*")
        if path.is_file() and ".git" not in path.parts
    ]
    for path in files:
        if path.stat().st_size > _MAX_CORPUS_FILE:
            raise CorpusError(f"corpus file exceeds 100 MiB: {path}")

    csv_indexes = 0
    for path in (
        sorted((corpus / "_meta").rglob("*.csv")) if (corpus / "_meta").exists() else ()
    ):
        csv_indexes += 1
        if path.name == "gaps.csv":
            # A gaps file names what a projector was *not* able to project. So its
            # paths are not an index of corpus files. Some are absent by
            # definition (the Tiki page with a NUL byte, SPEC.md 3.2.5(d)). Some
            # exist for another reason (a page that only its history keeps still
            # has a file). So the check must require neither.
            continue
        for row_number, row in enumerate(_read_csv(path), 2):
            referenced = row.get("path") or row.get("file")
            state = row.get("state")
            if state is not None:
                # SPEC.md 4.4: an index says if a row still has a file. The row
                # has a path if and only if it has a file.
                if state not in {"current", "deleted", "not-projected"}:
                    raise CorpusError(
                        f"unknown index state at {path}:{row_number}: {state!r}"
                    )
                if bool(referenced) != (state == "current"):
                    raise CorpusError(
                        f"index state and path disagree at {path}:{row_number}: "
                        f"state={state!r} path={referenced!r}"
                    )
            if referenced and not (corpus / referenced).is_file():
                raise CorpusError(
                    f"CSV path missing at {path}:{row_number}: {referenced}"
                )

    mail_messages = _verify_mail(corpus)
    _verify_irc(corpus)
    _verify_dictionary(corpus)
    return VerifyReport(
        len(records), len(files), len(sources), csv_indexes, mail_messages
    )


def push_main_ranges(
    corpus: Path,
    snapshot: str,
    *,
    remote: str = "origin",
    commits_per_push: int = 5_000,
) -> PushReport:
    """Fast-forward main in commit ranges of limited size. Then push one snapshot tag.

    This function runs in the corpus repository, which holds `main` and its tags
    (SPEC.md 2.2).
    """

    if commits_per_push < 1:
        raise ValueError("commits_per_push must be positive")
    local_head = git_output(corpus, ["rev-parse", "refs/heads/main"])
    advertised = run_git(
        corpus,
        ["ls-remote", "--heads", remote, "refs/heads/main"],
    ).stdout.strip()
    remote_head = advertised.split()[0] if advertised else None
    if remote_head is not None:
        run_git(corpus, ["fetch", "--no-tags", remote, "refs/heads/main"])
        if (
            run_git(
                corpus,
                ["merge-base", "--is-ancestor", remote_head, local_head],
                check=False,
            ).returncode
            != 0
        ):
            raise GitError("remote main is not an ancestor of the built main")
        revset = f"{remote_head}..{local_head}"
    else:
        revset = local_head
    commits = git_output(corpus, ["rev-list", "--reverse", revset]).splitlines()
    updates = 0
    for index in range(commits_per_push - 1, len(commits), commits_per_push):
        run_git(
            corpus,
            ["push", remote, f"{commits[index]}:refs/heads/main"],
        )
        updates += 1
    if commits and (len(commits) - 1) % commits_per_push != commits_per_push - 1:
        run_git(corpus, ["push", remote, f"{local_head}:refs/heads/main"])
        updates += 1
    run_git(corpus, ["push", remote, f"refs/tags/{snapshot}"])
    return PushReport(updates, snapshot)
