"""The three records every module shares."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    context: str  # "" when the CSV has none


@dataclass(frozen=True)
class ModelSpec:
    label: str     # shown in the report, e.g. "ChatGPT"
    model_id: str  # OpenRouter model id


@dataclass
class AnswerRecord:
    run_date: str            # YYYY-MM-DD
    question_id: str
    model_label: str
    model_id: str
    answer: str | None
    error: str | None
    fetched_at: str          # ISO 8601 UTC
    sha256: str | None       # hash of answer, None when answer is None
    score: float | None = None   # 0-100
    rank: int | None = None      # 1 = best
    rationale: str | None = None
