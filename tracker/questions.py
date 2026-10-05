"""Load and validate the questions CSV."""
from __future__ import annotations

import csv

from .types import Question


class QuestionsError(ValueError):
    pass


def load_questions(path: str) -> list[Question]:
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
    except FileNotFoundError:
        raise QuestionsError(f"questions file not found: {path}") from None
    except UnicodeDecodeError:
        raise QuestionsError(f"questions file is not UTF-8 text: {path} (save it as 'CSV UTF-8')") from None
    if not rows:
        raise QuestionsError("no questions found: the file is empty")

    header = [h.strip().lower() for h in rows[0]]
    if "question" not in header:
        raise QuestionsError("the CSV needs a column named 'question'")
    qi = header.index("question")
    ci = header.index("context") if "context" in header else None
    ii = header.index("id") if "id" in header else None

    def cell(row: list[str], i: int | None) -> str:
        return row[i].strip() if i is not None and i < len(row) else ""

    out: list[Question] = []
    seen: set[str] = set()
    for row in rows[1:]:
        text = cell(row, qi)
        if not text:
            continue
        qid = cell(row, ii) or f"q{len(out) + 1}"
        if qid in seen:
            raise QuestionsError(f"duplicate id in questions file: {qid}")
        seen.add(qid)
        out.append(Question(qid, text, cell(row, ci)))
    if not out:
        raise QuestionsError("no questions found in the file")
    return out
