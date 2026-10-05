import pytest

from tracker.client import LLMError
from tracker.rank import build_judge_prompt, parse_judge_reply, rank_question
from tracker.types import Question

from .helpers import ALL50, LABELS4, Q, judge_scores, records4


def test_prompt_with_context_lists_three_criteria_and_no_model_names():
    p = build_judge_prompt(Question("q1", "What is X?", "X is a company"), [("A", "a1"), ("B", "a2")])
    assert "What is X?" in p and "X is a company" in p and "agreement" in p
    assert not any(label in p for label in LABELS4)


def test_prompt_without_context_omits_agreement():
    p = build_judge_prompt(Question("q1", "What is X?", ""), [("A", "a1"), ("B", "a2")])
    assert "agreement" not in p


def test_parse_plain_fenced_and_wrapped_json():
    body = '{"A": {"relevance": 8, "completeness": 6, "reason": "ok"}}'
    for text in (body, f"```json\n{body}\n```", f"Here you go:\n{body}\nThanks"):
        assert parse_judge_reply(text, ["A"]) == {"A": (70.0, "ok")}


def test_parse_rejects_missing_letter_and_out_of_range():
    with pytest.raises(ValueError):
        parse_judge_reply('{"A": {"relevance": 8, "completeness": 6, "reason": ""}}', ["A", "B"])
    with pytest.raises(ValueError):
        parse_judge_reply('{"A": {"relevance": 11, "completeness": 6, "reason": ""}}', ["A"])


def test_ranks_highest_score_first_and_keeps_input_order():
    out = rank_question(Q, records4(), judge_scores({"ChatGPT": 60, "Claude": 90, "Gemini": 30, "Grok": 75}), "j")
    assert [r.model_label for r in out] == LABELS4
    assert {r.model_label: r.rank for r in out} == {"Claude": 1, "Grok": 2, "ChatGPT": 3, "Gemini": 4}
    assert {r.model_label: r.score for r in out} == {"Claude": 90.0, "Grok": 75.0, "ChatGPT": 60.0, "Gemini": 30.0}


def test_ties_broken_by_label():
    out = rank_question(Q, records4(), judge_scores({l: 50 for l in LABELS4}), "j")
    assert {r.model_label: r.rank for r in out} == {"ChatGPT": 1, "Claude": 2, "Gemini": 3, "Grok": 4}


def test_errored_record_excluded_and_unranked():
    recs = records4(); recs[2].answer = None; recs[2].error = "timeout"
    seen = []
    out = rank_question(Q, recs, judge_scores({"ChatGPT": 60, "Claude": 90, "Grok": 75}, seen), "j")
    assert out[2].rank is None and out[2].score is None
    assert seen[0].count("Answer ") == 3
    assert sorted(r.rank for r in out if r.rank) == [1, 2, 3]


def test_unreadable_judge_reply_retried_once_then_unranked():
    calls = []
    out = rank_question(Q, records4(), lambda m, p: calls.append(1) or "not json", "j")
    assert len(calls) == 2
    assert all(r.rank is None and r.rationale == "judge reply unreadable" for r in out)


def test_judge_api_failure_leaves_question_unranked():
    def boom(m, p): raise LLMError("down")
    assert all(r.rank is None for r in rank_question(Q, records4(), boom, "j"))


def test_single_available_answer_ranked_first_without_calling_judge():
    recs = records4()
    for r in recs[1:]:
        r.answer, r.error = None, "x"
    calls = []
    out = rank_question(Q, recs, lambda m, p: calls.append(1) or "", "j")
    assert calls == [] and out[0].rank == 1 and out[0].rationale == "only answer available"


def test_shuffle_is_stable_for_same_date_and_question():
    a, b = [], []
    rank_question(Q, records4(), judge_scores(ALL50, a), "j")
    rank_question(Q, records4(), judge_scores(ALL50, b), "j")
    assert a == b


def test_judge_is_called_with_the_judge_model():
    used = []
    def ask(m, p):
        used.append(m)
        return judge_scores(ALL50)(m, p)
    rank_question(Q, records4(), ask, "prov/judge")
    assert used == ["prov/judge"]
