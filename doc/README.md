# doc/

- `SPEC.md` — the functional specification. It sets the rules. Where it and the research report disagree, the spec is right.
- `research/` — the evidence behind the design:
  - `REPORT.md` — research on the design, results from the prototype, and a comparison with the report from Codex.
  - `data-survey.md` — a list of the local data, and the odd cases found when parsing it.
  - `domain-data-handling.md` — online sources that were checked.
  - `retrieval-sota.md`, `embeddings-landscape.md`, `agent-harness.md`, `codex-architecture-research.md`, `proto-notes.md`.
- `eval/` — material for evaluation. `questions.jsonl` holds realistic questions for the librarian, sorted by category. Scoring rules will be added later.
- `future/` — design for later (indexes, a librarian service, interfaces). It is not a backlog.
- `decisions/` — records of decisions, one dated file each. They cover gates and the open questions that the human partner has decided.
- `issues/` — numbered drafts of issues, used until the GitHub issue tracker exists.
