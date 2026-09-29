"""Render what the snapshot covers, and where things are, from the corpus.

The README once pasted every integer of every `coverage.toml` file, as one line
of comma-separated values for each file. The result was twenty lines of
counters that a reader cannot use. It also said nothing about the wiki, because
the coverage file of the wiki holds only `[additive.*]` tables and no top-level
integers. The layout in `AGENTS.md` had the opposite fault. It was a fixed
list. So it described `irc/`, `who/`, `notes/`, `loglan/` and `llg/` as
present, but the snapshot had none of them.

Now this module reads both from the corpus that the tools build.
"""

from __future__ import annotations

import csv
import tomllib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..git import run_git

# What each top-level directory holds, in the terms that a reader needs before
# opening one: the format on disk and the encoding. This list never states that
# a directory is present. layout_summary() reads that from the corpus.
LAYOUT: tuple[tuple[str, str], ...] = (
    (
        "wiki/",
        (
            "MediaWiki pages as raw wikitext (the markup source of a page), in "
            "UTF-8. There is one file for each page, and git holds the full "
            "history of revisions. `wiki/talk/` holds the Talk namespace: the "
            "pages where people discuss other pages."
        ),
    ),
    (
        "tiki/",
        (
            "The Tiki wiki from before 2013, in Tiki markup and UTF-8, with its "
            "history. `tiki/forums/` holds the WikiDiscuss threads, and "
            "`tiki/talk/` holds the comments on pages. Some text is stored as "
            "mojibake (text decoded with the wrong character set). This "
            "repository publishes that text without repair."
        ),
    ),
    (
        "mail/",
        (
            "One Maildir (a folder with one file for each message) for each "
            "list, under `<list>/cur/`. Each message is in RFC 822 format, with "
            "exactly the bytes that the archives hold. So the transfer "
            "encodings and the original character sets do not change. "
            "`<list>/threads/<YYYY>/` holds decoded renderings of threads, in "
            "UTF-8. A tool made these views from the originals, and each view "
            "names its originals."
        ),
    ),
    (
        "irc/",
        (
            "One UTF-8 file for each channel and day, at "
            "`<channel>/<YYYY>/<date>.txt`. A header line in each file gives "
            "the timezone and the format of the lines."
        ),
    ),
    (
        "dict/",
        (
            "One directory for each word. It holds `word.toml` for the word and "
            "its etymology, one `<lang>-<id>.md` file for each definition with "
            "its examples, and `comments.md`. The files are UTF-8, and their "
            "front matter (the header block at the start of a file) is TOML."
        ),
    ),
    (
        "cll/",
        (
            "*The Complete Lojban Language* as plain UTF-8 text, under "
            "`cll/editions/<edition>/`. There is one file for each chapter of "
            "each edition. These files need no submodule. `cll/src` is a "
            "submodule that holds the DocBook source. If it is empty, run "
            "`git submodule update --init`."
        ),
    ),
    (
        "grammars/",
        (
            "Formal grammars and parsers: the official baselines in YACC and "
            "BNF form, camxes and the parsers that descend from it, ilmentufa, "
            "zantufa, zasni gerna, and others. The vendored grammars (copies "
            "that this repository keeps) are ordinary files. The others are "
            "submodules. If a `src` directory is empty, run "
            "`git submodule update --init`. `_meta/grammars/index.csv` tells "
            "which grammars are files and which are submodules, and under what "
            "terms each one is published."
        ),
    ),
    (
        "who/",
        (
            "`attestations.csv`: dated claims, with citations, that connect "
            "nicknames, email addresses and wiki user names. These are claims. "
            "They never settle who a person is."
        ),
    ),
    (
        "notes/",
        (
            "Research notes that people contributed, under `<YYYY>/`, as UTF-8 "
            "Markdown with TOML front matter. A note is a map to the evidence. "
            "It is never evidence itself."
        ),
    ),
    (
        "loglan/",
        (
            "Documents from the Loglan era. This directory holds only the "
            "documents whose terms allow republication."
        ),
    ),
    (
        "llg/",
        "The publications of the Logical Language Group itself.",
    ),
    (
        "_meta/",
        (
            "Coverage files (what each source holds and lacks), archive "
            "manifests (a record of each archived source file) and CSV indexes. "
            "The files are UTF-8 text, in TOML or in CSV with a header row."
        ),
    ),
)


@dataclass(slots=True)
class SourceTally:
    """What one source contributed: its event count and its first and last time."""

    events: int = 0
    first: datetime | None = None
    last: datetime | None = None

    def record(self, moment: datetime) -> None:
        self.events += 1
        if self.first is None or moment < self.first:
            self.first = moment
        if self.last is None or moment > self.last:
            self.last = moment


@dataclass(slots=True)
class _SourceCoverage:
    events: int
    period: str
    notes: list[str] = field(default_factory=list)


def _period(tally: SourceTally) -> str:
    if tally.first is None or tally.last is None:
        return "unknown"
    # Use UTC, because the tallies come from the history, and the fast-import
    # backend stores every commit time in UTC. So an IRC event at 20:00 -08:00
    # on 31 December is in the next year there, whichever backend wrote it.
    first = tally.first.astimezone(UTC).date()
    last = tally.last.astimezone(UTC).date()
    return str(first.year) if first.year == last.year else f"{first.year}–{last.year}"


def _rows(path: Path) -> int:
    with path.open(encoding="utf-8", newline="") as handle:
        return max(sum(1 for _ in csv.reader(handle)) - 1, 0)


def _load(path: Path) -> dict[str, object]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return {}


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count:,} {singular if count == 1 else (plural or singular + 's')}"


def _gap_counts(path: Path, counts: dict[str, int]) -> int:
    """Count the rows of one gaps file, and add its reasons to `counts`.

    A gap is a source item that the tools did not project into a commit.
    """

    total = 0
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            total += 1
            reason = (row.get("reason") or row.get("cause") or "").strip()
            if reason:
                counts[reason] = counts.get(reason, 0) + 1
    return total


def _top_reasons(counts: dict[str, int], most: int = 2) -> list[str]:
    """Return the most common reasons, with their counts, ready to render.

    If no reason occurs more than once, return none. Then each row has its own
    reason, for example a quoted date header, and two rows picked from a tie
    tell the reader nothing. The file path in the note leads to the details.
    """

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    if not ranked or ranked[0][1] < 2:
        return []
    return [f'"{_clip(reason)}" ({count:,})' for reason, count in ranked[:most]]


def _gap_files(root: Path, source: str, paths: list[Path]) -> str:
    """Name the gaps files of one source for the notes column.

    Up to three files are named one by one. More files are named by one path
    pattern and their number, so that the note stays short.
    """

    names = [f"`_meta/{source}/{path.relative_to(root).as_posix()}`" for path in paths]
    if len(names) == 1:
        return names[0]
    if len(names) <= 3:
        return ", ".join(names[:-1]) + " and " + names[-1]
    return f"The {len(names):,} files `_meta/{source}/**/gaps.csv`"


def _clip(text: str, width: int = 52) -> str:
    """Return enough of a reason to recognize it. The file has the full text."""

    collapsed = " ".join(text.split())
    if len(collapsed) <= width:
        return collapsed
    return collapsed[: width - 1].rstrip(" ,;") + "…"


def _notes_for(corpus: Path, source: str) -> list[str]:
    """List the gaps of one source, from what the source recorded about itself."""

    notes: list[str] = []
    root = corpus / "_meta" / source
    # Some sources keep one gaps file for each channel or list, one level
    # deeper: IRC has `_meta/irc/<channel>/gaps.csv`. The table read only the
    # top-level file, so it told readers that IRC had no gaps, when those
    # files listed 6,334 missing days (#66).
    counts: dict[str, int] = {}
    listed: list[Path] = []
    total = 0
    for path in sorted(root.rglob("gaps.csv")):
        rows = _gap_counts(path, counts)
        if rows:
            listed.append(path)
            total += rows
    if total:
        files = _gap_files(root, source, listed)
        verb = "lists" if len(listed) == 1 else "list"
        note = f"{files} {verb} {_plural(total, 'gap')}."
        reasons = _top_reasons(counts)
        if reasons:
            # A five-figure count alone looks like damage. The two most
            # common reasons tell what kind of absence it is.
            label = "reason is" if len(reasons) == 1 else "reasons are"
            note += f" The most common {label} " + " and ".join(reasons) + "."
        notes.append(note)
    incomplete: list[str] = []
    unusable = 0
    unfetched = 0
    for coverage in sorted(root.rglob("coverage.toml")):
        data = _load(coverage)
        archive_gaps = data.get("archive_gaps")
        if isinstance(archive_gaps, dict) and archive_gaps:
            incomplete.append(coverage.parent.name)
        value = data.get("unusable_date_headers")
        if isinstance(value, int):
            unusable += value
        # A source can also record that its fetch got less than the upstream
        # offered. That fact is different from a gap in the record.
        archive_block = data.get("archive")
        if isinstance(archive_block, dict):
            short = archive_block.get("files_listed_but_not_archived")
            if isinstance(short, int) and short:
                unfetched += short
    if incomplete:
        notes.append(
            "Known incomplete archives: " + ", ".join(sorted(incomplete)) + "."
        )
    if unusable:
        verb = "is" if unusable == 1 else "are"
        notes.append(f"{_plural(unusable, 'date header')} {verb} unusable.")
    if unfetched:
        notes.append(
            "The upstream site (the origin of the source) listed "
            f"{_plural(unfetched, 'file')} that this archive does not hold."
        )
    return notes


# One record for each commit. ASCII separator characters split the fields and
# the records, so that no trailer value can look like a boundary.
_TALLY_FORMAT = (
    "%x1e%ct%x1f"
    "%(trailers:key=Source,valueonly,separator=%x2c)%x1f"
    "%(trailers:key=Event,valueonly,separator=%x2c)%x1f"
    "%(trailers:key=Time-Confidence,valueonly,separator=%x2c)%x1f"
    "%(trailers:key=Source-Date,valueonly,separator=%x2c)"
)


def _source_date(value: str) -> datetime:
    """Return the true date of a pre-epoch event, as precise as its trailer.

    A pre-epoch event is an event from before 1970.
    """

    parts = [int(part) for part in value.split("-")]
    year, month, day = (*parts, 1, 1)[:3]
    return datetime(year, month, day, tzinfo=UTC)


def corpus_tallies(corpus: Path) -> dict[str, SourceTally]:
    """Read from the corpus history what each source contributed.

    Every refresh renders its coverage table from this function, whether
    `build`, `update` or `refresh` makes the commit. So by design, the three
    render the same table for the same corpus. The old code counted the
    projector stream (the events that the projectors yield) instead. That
    needed the archive, and it described what the stream gave, not what the
    corpus holds. For example, an `update` of one source rendered a table with
    one row. Each source event is one commit. Its `Source:` trailer names the
    source, and its committer time is the source time (SPEC.md 2.4). The walk
    takes about 16 seconds over 307,103 commits. Pre-epoch events are the
    exception to the committer time, because git clamps their time to the
    epoch. Their true date is in `Source-Date:`. Tool commits (`Source: meta`),
    contributed notes and attestations are not source events, so this function
    does not count them.
    """

    listing = run_git(corpus, ["log", f"--format={_TALLY_FORMAT}", "HEAD"]).stdout
    tallies: dict[str, SourceTally] = {}
    for record in listing.split("\x1e"):
        if not record.strip():
            continue
        stamp, source, event, confidence, source_date = record.strip("\n").split("\x1f")
        if not source or source == "meta" or event == "contributed":
            continue
        if confidence == "pre-epoch":
            moment = _source_date(source_date)
        else:
            moment = datetime.fromtimestamp(int(stamp), tz=UTC)
        tallies.setdefault(source.split("/", 1)[0], SourceTally()).record(moment)
    return tallies


def coverage_table(corpus: Path, tallies: dict[str, SourceTally]) -> str:
    """Render one row for each source: its events, their period, and its gaps."""

    if not tallies:
        return "The repository has no source events yet."
    grouped: dict[str, SourceTally] = {}
    for name, tally in tallies.items():
        top = name.split("/", 1)[0]
        merged = grouped.setdefault(top, SourceTally())
        merged.events += tally.events
        for moment in (tally.first, tally.last):
            if moment is not None:
                merged.record(moment)
                merged.events -= 1
    lines = [
        "| source | events | period | notes |",
        "|---|---:|---|---|",
    ]
    for source in sorted(grouped):
        tally = grouped[source]
        notes = _notes_for(corpus, source)
        lines.append(
            f"| `{source}/` | {tally.events:,} | {_period(tally)} | "
            f"{' '.join(notes) if notes else 'None recorded.'} |"
        )
    total = sum(tally.events for tally in grouped.values())
    lines.append(f"\nTotal: {total:,} source events.")
    return "\n".join(lines)


def layout_summary(corpus: Path) -> str:
    """Render the directory map, and show which directories this snapshot has."""

    lines = []
    for name, description in LAYOUT:
        present = (corpus / name.rstrip("/")).is_dir()
        marker = "" if present else " *Not yet in this snapshot.*"
        lines.append(f"- `{name}`: {description}{marker}")
    return "\n".join(lines)
