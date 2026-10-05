from tracker.client import LLMError
from tracker.fetch import fetch_answers
from tracker.store import answer_hash
from tracker.types import Question

from .helpers import LABELS4, MODELS4, QS1, QS2


def test_one_record_per_question_and_model_in_order():
    recs = fetch_answers(QS2, MODELS4, lambda m, p: f"{m}:{p}", "2026-10-05", lambda: "T")
    assert len(recs) == 8
    assert [(r.question_id, r.model_label) for r in recs[:4]] == [("q1", l) for l in LABELS4]


def test_record_carries_answer_hash_and_metadata():
    r = fetch_answers(QS1, MODELS4[:1], lambda m, p: "an answer", "2026-10-05", lambda: "T")[0]
    assert (r.answer, r.error, r.fetched_at, r.run_date) == ("an answer", None, "T", "2026-10-05")
    assert r.sha256 == answer_hash("an answer")


def test_failing_model_recorded_and_others_continue():
    def ask(m, p):
        if m == MODELS4[1].model_id:
            raise LLMError("timeout")
        return "fine"
    recs = fetch_answers(QS1, MODELS4, ask, "2026-10-05", lambda: "T")
    bad = recs[1]
    assert (bad.answer, bad.sha256, bad.error) == (None, None, "timeout")
    assert [r.answer for r in recs if r is not bad] == ["fine"] * 3


def test_context_is_not_sent_to_answering_models():
    prompts = []
    fetch_answers([Question("q1", "What is X?", "SECRET CONTEXT")], MODELS4[:1],
                  lambda m, p: prompts.append(p) or "a", "2026-10-05", lambda: "T")
    assert prompts == ["What is X?"]
