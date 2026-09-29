# jbomo'i

jbomo'i is the historical record of the Lojban community, kept as a public git
repository. The record includes the wiki and its history, the mailing lists,
the IRC logs, the dictionary and its history, and every edition of the CLL.
Each commit is one event from a source. This repository also holds the tools
that build the record, and instructions that let a coding assistant work as a
research librarian over a copy of it.

You are on the `tools` branch. Maintainers use this branch. It holds:

- the tools that build and update the record,
- the templates for the instruction files on `main`,
- the documentation,
- the CI setup.

End users clone `main` instead. The `main` branch holds the record itself. It
shares no history with `tools`. Maintainers keep a copy of `main` as a git
repository at `JBOMOHI_CORPUS` (by default, `~/lojban/corpus`).

- Start by reading `AGENTS.md`, which gives the rules for working here. Then
  read `doc/SPEC.md`.
- To work with other sessions, use the Herdr Collab project `jbomohi`. See the
  `herdr-collab` skill and the short section on it in `AGENTS.md`.
- Research and evidence are in `doc/research/`.
