"""Ask every question to every model."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .client import AskFn, LLMError
from .store import answer_hash
from .types import AnswerRecord, ModelSpec, Question

WORKERS = 4


def fetch_answers(questions: list[Question], models: list[ModelSpec], ask: AskFn,
                  run_date: str, now: Callable[[], str]) -> list[AnswerRecord]:
    """One record per question and model, ordered by question, then by model as listed."""

    def one(pair: tuple[Question, ModelSpec]) -> AnswerRecord:
        question, model = pair
        try:
            # Only the question is sent. The context column is for the judge.
            answer, error = ask(model.model_id, question.question), None
        except LLMError as e:
            answer, error = None, str(e)
        return AnswerRecord(
            run_date=run_date, question_id=question.id, model_label=model.label,
            model_id=model.model_id, answer=answer, error=error, fetched_at=now(),
            sha256=answer_hash(answer) if answer is not None else None,
        )

    pairs = [(q, m) for q in questions for m in models]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return list(pool.map(one, pairs))  # map keeps input order
