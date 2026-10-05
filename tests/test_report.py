from tracker.report import build_report, write_report
from tracker.store import answer_hash
from tracker.types import Question

from .helpers import LABELS4, QS1, QS2, order_of, ranked_run, row, section


def test_leaderboard_sorted_by_average_rank():
    html = build_report(QS2, ranked_run({"Claude": [1, 1], "Grok": [2, 3], "ChatGPT": [3, 2], "Gemini": [4, 4]}), None, "T")
    board = section(html, "leaderboard")
    assert order_of(board, LABELS4) == ["Claude", "ChatGPT", "Grok", "Gemini"]
    assert "1.0" in board and "2.5" in board


def test_change_symbols_against_previous_run():
    prev = ranked_run({"Claude": [2], "Grok": [1], "ChatGPT": [3], "Gemini": [4]}, date="2026-09-28")
    cur = ranked_run({"Claude": [1], "Grok": [3], "ChatGPT": [3 - 1 + 1], "Gemini": [4]})   # Claude up 1, Grok down 2
    q = section(build_report(QS1, cur, prev, "T"), "question-q1")
    assert "▲1" in row(q, "Claude") and "▼2" in row(q, "Grok") and ">=<" in row(q, "Gemini")


def test_leaderboard_change_uses_average_rank_to_one_decimal():
    prev = ranked_run({"Claude": [2, 2], "Grok": [1, 1]}, date="2026-09-28")
    cur = ranked_run({"Claude": [1, 1], "Grok": [2, 3]})
    board = section(build_report(QS2, cur, prev, "T"), "leaderboard")
    assert "▲1.0" in row(board, "Claude") and "▼1.5" in row(board, "Grok")


def test_first_run_marks_everything_new():
    assert section(build_report(QS1, ranked_run({l: [i + 1] for i, l in enumerate(LABELS4)}), None, "T"), "question-q1").count("new") == 4


def test_errored_answer_shows_no_answer_and_sorts_last():
    cur = ranked_run({"Claude": [1], "Grok": [2], "ChatGPT": [3], "Gemini": [None]}, errors={"Gemini": "timeout"})
    html = build_report(QS1, cur, None, "T")
    q = section(html, "question-q1")
    assert "no answer" in row(q, "Gemini")
    assert order_of(q, LABELS4)[-1] == "Gemini"
    assert order_of(section(html, "leaderboard"), LABELS4)[-1] == "Gemini"


def test_unranked_answer_is_labelled_unranked():
    cur = ranked_run({"Claude": [None], "Grok": [None]})
    assert "unranked" in row(section(build_report(QS1, cur, None, "T"), "question-q1"), "Claude")


def test_model_and_csv_text_is_escaped():
    cur = ranked_run({l: [i + 1] for i, l in enumerate(LABELS4)}, answer="<script>alert(1)</script>")
    html = build_report([Question("q1", "Is 2 < 3?", "<b>ctx</b>")], cur, None, "T")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "Is 2 &lt; 3?" in html and "&lt;b&gt;ctx&lt;/b&gt;" in html


def test_answers_shown_with_hash_inside_details():
    cur = ranked_run({l: [i + 1] for i, l in enumerate(LABELS4)}, answer="full text")
    html = build_report(QS1, cur, None, "T")
    assert html.count("<details") == 4 and answer_hash("full text") in html


def test_question_removed_from_csv_is_not_shown():
    cur = ranked_run({l: [i + 1] for i, l in enumerate(LABELS4)}, question_id="gone")
    assert "question-gone" not in build_report(QS1, cur, None, "T")


def test_title_and_run_date_shown():
    html = build_report(QS1, ranked_run({"Claude": [1], "Grok": [2]}), None, "2026-10-05T03:31:00Z")
    assert "LLM Answer Tracker" in html and "2026-10-05" in html and "2026-10-05T03:31:00Z" in html


def test_write_report_creates_directories(tmp_path):
    write_report("<html></html>", str(tmp_path / "docs" / "index.html"))
    assert (tmp_path / "docs" / "index.html").read_text(encoding="utf-8") == "<html></html>"
