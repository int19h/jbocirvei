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

Snapshot `pending`.

## What is where

See `AGENTS.md` for the map of the directories in the repository.

## What this snapshot covers

The repository has no source events yet.

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

Built by tools commit `pending`. To build this snapshot again or to
update it, you need the tools and instructions on the `tools` branch of this
repository.
