# jbomo'i — the Lojban historical record as a git repository

<!-- Generated file; edit the template on the tools branch. -->

This repository publishes the public historical record of the Lojban community
again, as plain text in git. It contains:

- the wiki, with the full history of its revisions;
- the older Tiki wiki that the current wiki replaced;
- the mailing lists;
- the IRC logs;
- the dictionary, with the history of its definitions;
- every edition of *The Complete Lojban Language*;
- the formal grammars.

**Each commit is one event from a source**: a wiki revision, a mail message, a
day of IRC, or a version of a definition. The author of the commit is the
person who made the event, and its date is when they made it. This is the main
idea of the repository. It means that common tools can answer questions about
the history of the language. `rg` finds the words. `git log`, `git blame` and
`git show` find when something happened, who did it, and what changed.

Snapshot `{{snapshot}}`.

## What is where

{{layout_summary}}

## What this snapshot covers

{{coverage_tables}}

This matters when you read an answer, not only when you look for one. "Nobody
ever proposed that" always means only "not in what this snapshot covers". The
gaps files under `_meta/` record what was left out on purpose, and why.

## Start here

```sh
git clone --recurse-submodules {{repo_url}} jbomohi
cd jbomohi

# what does the record say about a word?
rg -n "xorlo" wiki/ mail/ | head

# what happened across every source in one fortnight?
git log --since=2004-12-20 --until=2005-01-05 --format='%ad %an %s' --date=short

# how did one page get to be the way it is?
git log --follow -p -- "wiki/main/BPFK_Section%3A_gadri.wiki" | less

# what did this page say in 2015?
git show "$(git log -1 --format=%H --before=2015-06-01 -- wiki/main/xorlo.wiki)":wiki/main/xorlo.wiki
```

`cll/src` and the `src` directories under `grammars/` may be empty. If they
are, you cloned without `--recurse-submodules`. Run
`git submodule update --init --recursive` inside the clone to fill them. Most
questions do not need this step, because the plain-text editions under
`cll/editions/` and the grammars copied into this repository need no
submodule. But an empty directory looks like a missing source, so check for
this first.

## Citing what you find

```
<path>@<Source-Id>:L<start>[-<end>]
```

The `Source-Id` names a version of the source, not a commit hash, so a
citation still works after the repository is built again. It is:

- `revid=<n>` for a wiki revision;
- the `Message-ID` for mail;
- the date for a day of IRC;
- `definition=<id> version=<n>` for a dictionary entry;
- `cll=<edition>` for the book.

The same ids appear in the commit trailers. Next to them are `Source:`,
`Event:` and `Time-Confidence:`, and, where they apply, `Event-Window:` and
`Source-Date:`. So `git log --grep='Source-Id: revid=108932'` takes you from a
citation back to its commit. `AGENTS.md` gives the full citation format,
examples, and how to read each trailer.

The thread views of mail and the text of CLL editions are renderings. They are
not the originals. Line 1 of each one names what it was made from. The
originals are the Maildir files and the `cll/src` submodule.

## Contributing

Put research notes under `notes/<YYYY>/<date>-<slug>.md`, and attestations
about identities in `who/attestations.csv`, as ordinary commits. Every claim in
them must cite primary units. This is because a note is a map to the evidence,
not evidence itself. `AGENTS.md` gives the citation format they must use.

Never edit data files by hand. This snapshot is generated.

## Provenance and terms

{{provenance}}

The grammar and parser submodules keep the licence files of their upstream
projects. `_meta/grammars/index.csv` lists the terms for each source.

Names and email addresses appear as the public archives hold them. Some
addresses are made up, to fill the author field of git commits:
`…@mw.lojban.org`, `…@jbovlaste.lojban.org`, `irclogs@irc.lojban.org`. Mail
sent to them will not arrive. Who a person is, is recorded as a dated claim
with a citation. It is never recorded as a settled fact.

## Reading this with an assistant

Open the clone in a coding assistant and ask your question. `AGENTS.md` tells
the assistant how the repository is arranged, how to search each kind of
file, and how to cite what it finds. Some assistants read `AGENTS.md` by
themselves. Others must be told to read it.

Built by tools commit `{{tools_commit}}`. To build this snapshot again or to
update it, you need the tools and instructions on the `tools` branch of this
repository.
