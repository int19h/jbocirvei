# jbocirvei: the Lojban historical record as a git repository

<!-- Generated file. Edit the template on the tools branch. -->

This repository publishes the public historical record of the Lojban community
again, as plain text in git. It contains:

- The wiki, with the full history of its revisions.
- The older Tiki wiki that the current wiki replaced.
- The mailing lists.
- The IRC logs.
- The dictionary, with the history of its definitions.
- Every edition of *The Complete Lojban Language*.
- The formal grammars.

Each commit is one event from a source: a wiki revision, a mail message, a day
of IRC, or a version of a definition. The author of the commit is the person
behind the event, and its date is the time of the event. This is the main
idea of the repository. Because of it, common tools can answer questions about
the history of the language. `rg` finds the words. `git log`, `git blame` and
`git show` find when something happened, who did it, and what changed.

Snapshot `snapshot/20260916T095816Z`.

## What is where

- `wiki/`: MediaWiki pages as raw wikitext (the markup source of a page), in UTF-8. There is one file for each page, and git holds the full history of revisions. `wiki/talk/` holds the Talk namespace: the pages where people discuss other pages.
- `tiki/`: The Tiki wiki from before 2013, in Tiki markup and UTF-8, with its history. `tiki/forums/` holds the WikiDiscuss threads, and `tiki/talk/` holds the comments on pages. Some text is stored as mojibake (text decoded with the wrong character set). This repository publishes that text without repair.
- `mail/`: One Maildir (a folder with one file for each message) for each list, under `<list>/cur/`. Each message is in RFC 822 format, with exactly the bytes that the archives hold. So the transfer encodings and the original character sets do not change. `<list>/threads/<YYYY>/` holds decoded renderings of threads, in UTF-8. A tool made these views from the originals, and each view names its originals.
- `irc/`: One UTF-8 file for each channel and day, at `<channel>/<YYYY>/<date>.txt`. A header line in each file gives the timezone and the format of the lines.
- `dict/`: One directory for each word. It holds `word.toml` for the word and its etymology, one `<lang>-<id>.md` file for each definition with its examples, and `comments.md`. The files are UTF-8, and their front matter (the header block at the start of a file) is TOML.
- `cll/`: *The Complete Lojban Language* as plain UTF-8 text, under `cll/editions/<edition>/`. There is one file for each chapter of each edition. These files need no submodule. `cll/src` is a submodule that holds the DocBook source. If it is empty, run `git submodule update --init`.
- `grammars/`: Formal grammars and parsers: the official baselines in YACC and BNF form, camxes and the parsers that descend from it, ilmentufa, zantufa, zasni gerna, and others. The vendored grammars (copies that this repository keeps) are ordinary files. The others are submodules. If a `src` directory is empty, run `git submodule update --init`. `_meta/grammars/index.csv` tells which grammars are files and which are submodules, and under what terms each one is published.
- `who/`: `attestations.csv`: dated claims, with citations, that connect nicknames, email addresses and wiki user names. These are claims. They never settle who a person is. *Not yet in this snapshot.*
- `notes/`: Research notes that people contributed, under `<YYYY>/`, as UTF-8 Markdown with TOML front matter. A note is a map to the evidence. It is never evidence itself. *Not yet in this snapshot.*
- `loglan/`: Documents from the Loglan era. This directory holds only the documents whose terms allow republication. *Not yet in this snapshot.*
- `llg/`: The publications of the Logical Language Group itself. *Not yet in this snapshot.*
- `_meta/`: Coverage files (what each source holds and lacks), archive manifests (a record of each archived source file) and CSV indexes. The files are UTF-8 text, in TOML or in CSV with a header row.

## What this snapshot covers

| source | events | period | notes |
|---|---:|---|---|
| `cll/` | 11 | 2008–2026 | None recorded. |
| `dict/` | 100,189 | 2003–2026 | None recorded. |
| `grammars/` | 72 | 1989–2026 | `_meta/grammars/gaps.csv` lists 4 gaps. The most common reasons are "YACC form never published; BNF form survives" (2) and "referenced by surviving drafts but never published" (1). |
| `irc/` | 14,006 | 2000–2026 | `_meta/irc/ckule/gaps.csv`, `_meta/irc/jbosnu/gaps.csv` and `_meta/irc/lojban/gaps.csv` list 6,334 gaps. The most common reason is "no source file" (6,334). |
| `mail/` | 112,300 | 1989–2025 | `_meta/mail/lojban-list/gaps.csv` lists 9 gaps. The most common reason is "date header unusable" (9). Known incomplete archives: lojban-beginners, lojban-list. 9 date headers are unusable. |
| `tiki/` | 21,047 | 2001–2015 | `_meta/tiki/gaps.csv` lists 180 gaps. The most common reasons are "no current row; rename/deletion undocumented" (171) and "forum parent 4475 absent from export" (4). |
| `wiki/` | 59,474 | 2005–2026 | `_meta/wiki/gaps.csv` lists 21,224 gaps. The most common reasons are "move; history not API-accessible" (6,204) and "deleted; history not API-accessible" (3,410). |

Total: 307,099 source events.

These limits are important when you read an answer, not only when you look for
one. If an answer says "Nobody ever proposed that", read it as "not in what
this snapshot covers". The gaps files under `_meta/` record what was left out
on purpose, and why.

## Start here

```sh
git clone --recurse-submodules https://github.com/int19h/jbocirvei.git jbocirvei
cd jbocirvei

# what does the record say about a word?
rg -n "xorlo" wiki/ mail/ | head

# what happened across every source in one fortnight?
git log --since=2004-12-20 --until=2005-01-05 --format='%ad %an %s' --date=short

# how did one page get to be the way it is?
git log --follow -p -- "wiki/main/BPFK_Section%3A_gadri.wiki" | less

# what did this page say in 2015?
git show "$(git log -1 --format=%H --before=2015-06-01 -- wiki/main/xorlo.wiki)":wiki/main/xorlo.wiki
```

If `cll/src` or the `src` directories under `grammars/` are empty, you cloned
without `--recurse-submodules`. To fill them, run
`git submodule update --init --recursive` inside the clone. Most questions do
not need this step. The plain-text editions under `cll/editions/` and the
grammars that this repository holds as ordinary files need no submodule. But an
empty directory looks like a missing source. So, first make sure that these
directories are not empty.

## Citing what you find

```
<path>@<Source-Id>:L<start>[-<end>]
```

The `Source-Id` names a version of the source, not a commit hash. So a
citation still works after a new build of the repository. The `Source-Id` is:

- `revid=<n>` for a wiki revision.
- The `Message-ID` for mail.
- The date for a day of IRC.
- `definition=<id> version=<n>` for a dictionary entry.
- `cll=<edition>` for the book.

The same ids are in the commit trailers (the `Key: value` lines at the end of
a commit message). Each commit also has the trailers `Source:`, `Event:` and
`Time-Confidence:`. Some commits also have `Event-Window:` and `Source-Date:`.
So `git log --grep='Source-Id: revid=108932'` takes you from a citation back
to its commit. `AGENTS.md` gives the full citation format, examples, and the
meaning of each trailer.

The thread views of mail and the text of CLL editions are renderings (text
that a tool made from an original). Line 1 of each rendering names its
original. The originals are the Maildir files and the `cll/src` submodule.

## Contributing

Put research notes under `notes/<YYYY>/<date>-<slug>.md`. Put attestations in
`who/attestations.csv`. An attestation is a dated claim, with citations, about
who a person is. Add both as ordinary commits. Every claim in them must cite
primary units, because a note is a map to the evidence, not evidence itself.
`AGENTS.md` gives the citation format that they must use.

Do not edit data files by hand. A tool generates this snapshot.

## Provenance and terms

This repository publishes each source again, under the terms of that source as its owner published them. The repository claims no license of its own over the data.

The grammar and parser submodules keep the license files of their upstream
projects. `_meta/grammars/index.csv` lists the terms for each source.

Names and email addresses appear as the public archives hold them. Some
addresses are not real. They fill the author field of git commits:
`…@mw.lojban.org`, `…@jbovlaste.lojban.org`, `irclogs@irc.lojban.org`. Mail
to them does not arrive. The identity of a person is recorded as a dated claim
with citations. It is never recorded as a settled fact.

## Reading this with an assistant

Open the clone in a coding assistant and ask your question. `AGENTS.md` tells
the assistant how the repository is arranged, how to search each type of file,
and how to cite the results. Some assistants read `AGENTS.md` automatically.
You must tell others to read it.

Built by tools commit `613c9e16214510a5f52cc5e8168daa82e712f481`. To build this snapshot again or to
update it, you need the tools and instructions on the `tools` branch of this
repository.
