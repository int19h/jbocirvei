# doc/

This directory holds the documentation. It contains:

- `SPEC.md`: the functional specification. It sets the rules. If it and the research report disagree, follow the spec.
- `research/`: the evidence for the design. It contains:
  - `REPORT.md`: research on the design, results from the prototype, and a comparison with the report from Codex.
  - `data-survey.md`: a list of the local data, and the unusual cases that parsing found.
  - `domain-data-handling.md`: online sources, each one examined and found to work.
  - `retrieval-sota.md`, `embeddings-landscape.md`, `agent-harness.md`, `codex-architecture-research.md`, `proto-notes.md`.
- `eval/`: material for evaluation. `questions.jsonl` holds realistic questions for the librarian, sorted by category. Scoring rules will come later.
- `future/`: design for later (indexes, a librarian service, interfaces). It is not a backlog.
- `decisions/`: records of decisions, one dated file each. They record gates (benchmark results that a design must reach before the project adopts it) and the open questions that the human partner decided.
- `issues/`: numbered drafts of issues. The project uses them until the GitHub issue tracker exists.
