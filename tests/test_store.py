import hashlib
import os

from tracker.store import answer_hash, list_run_dates, load_run, save_run
from tracker.types import AnswerRecord


def rec(**kw):
    base = dict(run_date="2026-10-05", question_id="q1", model_label="A", model_id="p/a",
                answer="hello", error=None, fetched_at="2026-10-05T03:30:00Z",
                sha256=answer_hash("hello"))
    base.update(kw)
    if "answer" in kw and "sha256" not in kw:
        base["sha256"] = answer_hash(kw["answer"]) if kw["answer"] is not None else None
    return AnswerRecord(**base)


def test_hash_is_sha256_of_utf8():
    assert answer_hash("héllo") == hashlib.sha256("héllo".encode("utf-8")).hexdigest()


def test_roundtrip_preserves_every_field(tmp_path):
    recs = [rec(answer="Line 1\nLine 2 ✓", score=87.5, rank=1, rationale="clear")]
    save_run(recs, str(tmp_path), "2026-10-05")
    assert load_run(str(tmp_path), "2026-10-05") == recs


def test_second_save_on_same_date_replaces_file(tmp_path):
    save_run([rec(model_label="A"), rec(model_label="B")], str(tmp_path), "2026-10-05")
    save_run([rec(model_label="A")], str(tmp_path), "2026-10-05")
    assert len(load_run(str(tmp_path), "2026-10-05")) == 1


def test_list_run_dates_sorted_and_ignores_other_files(tmp_path):
    for d in ("2026-10-12", "2026-10-05"):
        save_run([rec()], str(tmp_path), d)
    (tmp_path / "notes.txt").write_text("x")
    assert list_run_dates(str(tmp_path)) == ["2026-10-05", "2026-10-12"]


def test_list_run_dates_on_missing_dir(tmp_path):
    assert list_run_dates(str(tmp_path / "absent")) == []


def test_save_creates_missing_directories(tmp_path):
    path = save_run([rec()], str(tmp_path / "a" / "b"), "2026-10-05")
    assert os.path.exists(path)
