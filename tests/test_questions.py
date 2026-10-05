import pytest

from tracker.questions import QuestionsError, load_questions
from tracker.types import Question


def csv(tmp_path, text):
    p = tmp_path / "questions.csv"
    p.write_text(text, encoding="utf-8", newline="")
    return str(p)


def test_reads_question_and_context(tmp_path):
    qs = load_questions(csv(tmp_path, "id,question,context\na1,What is Straive?,Content and data company\n"))
    assert qs == [Question("a1", "What is Straive?", "Content and data company")]


def test_excel_bom_quoted_commas_and_newlines(tmp_path):
    text = '﻿Question,Context\n"Best vendors for X, Y?","line one\nline two"\n'
    qs = load_questions(csv(tmp_path, text))
    assert qs[0].question == "Best vendors for X, Y?"
    assert qs[0].context == "line one\nline two"
    assert qs[0].id == "q1"


def test_blank_rows_skipped_and_ids_follow_kept_rows(tmp_path):
    qs = load_questions(csv(tmp_path, "question\nfirst\n\n   \nsecond\n"))
    assert [(q.id, q.question) for q in qs] == [("q1", "first"), ("q2", "second")]


def test_missing_context_column_gives_empty_context(tmp_path):
    assert load_questions(csv(tmp_path, "question\nhello\n"))[0].context == ""


def test_missing_question_column_rejected(tmp_path):
    with pytest.raises(QuestionsError, match="question"):
        load_questions(csv(tmp_path, "prompt\nhello\n"))


def test_duplicate_ids_rejected(tmp_path):
    with pytest.raises(QuestionsError, match="duplicate id"):
        load_questions(csv(tmp_path, "id,question\nx,a\nx,b\n"))


def test_no_questions_rejected(tmp_path):
    with pytest.raises(QuestionsError, match="no questions"):
        load_questions(csv(tmp_path, "question\n\n"))
