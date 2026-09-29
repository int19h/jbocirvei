"""Render the files that the tools generate for the corpus."""

from .coverage import SourceTally, corpus_tallies, coverage_table, layout_summary
from .templates import (
    RenderContext,
    commit_instruction_refresh,
    commit_root,
    render_main,
)

__all__ = [
    "RenderContext",
    "SourceTally",
    "commit_instruction_refresh",
    "commit_root",
    "corpus_tallies",
    "coverage_table",
    "layout_summary",
    "render_main",
]
