# jbomo'i

jbomo'i is the historical record of the Lojban community, kept as a public git
repository. The record includes the wiki and its history, the mailing lists,
the IRC logs, the dictionary and its history, and every edition of the CLL.
Each commit is one event from a source. This repository also holds the tools
that build the record, and instructions that let a coding assistant work as a
research librarian over a copy of the record.

You are on the `tools` branch. Maintainers use this branch. It holds:

- The tools that build and update the record.
- The templates for the instruction files on `main`.
- The documentation.
- The CI setup.

Users who only read the record clone `main`. The `main` branch holds the
record itself, and it shares no history with `tools`. Maintainers keep a copy
of `main` as a separate git repository at `JBOMOHI_CORPUS`. By default, this
path is `~/lojban/corpus`.

Start with `AGENTS.md`, which gives the rules for work in this repository. Then
read `doc/SPEC.md`. To work with other sessions, use the Herdr Collab project
`jbomohi`. The `herdr-collab` skill and the "Herdr Collab" section of
`AGENTS.md` tell you how. The research and the evidence for the design are in
`doc/research/`.
