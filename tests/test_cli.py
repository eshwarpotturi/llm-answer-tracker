import json
from types import SimpleNamespace

import pytest

from tracker.cli import main, run
from tracker.client import LLMError
from tracker.store import load_run

from .helpers import lettered_answers, section

CONFIG = """models:
  - label: ChatGPT
    model_id: prov/chatgpt
  - label: Claude
    model_id: prov/claude
  - label: Gemini
    model_id: prov/gemini
  - label: Grok
    model_id: prov/grok
judge_model_id: prov/judge
"""
QUESTIONS = "question,context\nWhat is X?,X is a company\nWho makes Y?,\nWhere is Z?,Z is in India\n"


@pytest.fixture
def project(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(CONFIG, encoding="utf-8")
    (tmp_path / "questions.csv").write_text(QUESTIONS, encoding="utf-8")
    return SimpleNamespace(config=str(config_file), config_file=config_file,
                           data_dir=str(tmp_path / "data" / "runs"),
                           report=tmp_path / "docs" / "index.html")


def fake_ask(model_id, prompt):
    letters = lettered_answers(prompt)
    if letters:  # the judge
        return json.dumps({l: {"relevance": 9 - i, "agreement": 9 - i, "completeness": 9 - i, "reason": "fine"}
                           for i, l in enumerate(sorted(letters))})
    return f"reply by {model_id}"


def test_full_run_writes_data_and_report(project):
    code = run(project.config, "2026-10-05", ask=fake_ask)
    assert code == 0
    recs = load_run(project.data_dir, "2026-10-05")
    assert len(recs) == 3 * 4 and all(r.rank for r in recs)
    assert "LLM Answer Tracker" in project.report.read_text(encoding="utf-8")


def test_second_run_compares_with_earlier_date(project):
    run(project.config, "2026-09-28", ask=fake_ask)
    run(project.config, "2026-10-05", ask=fake_ask)
    assert "new" not in section(project.report.read_text(encoding="utf-8"), "question-q1")


def test_rerun_same_date_does_not_duplicate(project):
    run(project.config, "2026-10-05", ask=fake_ask)
    run(project.config, "2026-10-05", ask=fake_ask)
    assert len(load_run(project.data_dir, "2026-10-05")) == 12


def test_later_run_on_disk_is_not_used_as_previous(project):
    run(project.config, "2026-10-12", ask=fake_ask)
    run(project.config, "2026-10-05", ask=fake_ask)
    assert section(project.report.read_text(encoding="utf-8"), "question-q1").count("new") == 4


def test_all_requests_failing_returns_1_but_still_writes(project):
    def down(m, p): raise LLMError("down")
    assert run(project.config, "2026-10-05", ask=down) == 1
    assert project.report.exists()


def test_bad_config_returns_2_and_writes_nothing(project, capsys):
    project.config_file.write_text("models: []\njudge_model_id: j\n")
    assert run(project.config, "2026-10-05", ask=fake_ask) == 2
    assert capsys.readouterr().err.startswith("error:")
    assert not project.report.exists()


def test_missing_api_key_returns_2(project, monkeypatch, capsys):
    monkeypatch.delenv("LLMFOUNDRY_TOKEN", raising=False)
    assert run(project.config, "2026-10-05") == 2
    assert "LLMFOUNDRY_TOKEN is not set" in capsys.readouterr().err


def test_placeholder_model_ids_rejected(project, capsys):
    project.config_file.write_text(CONFIG.replace("prov/grok", "x-ai/REPLACE-ME"), encoding="utf-8")
    assert run(project.config, "2026-10-05", ask=fake_ask) == 2
    assert "REPLACE-ME" in capsys.readouterr().err


def test_summary_line(project, capsys):
    run(project.config, "2026-10-05", ask=fake_ask)
    assert "run 2026-10-05: 3 questions, 4 models, 12 answers, 0 failed" in capsys.readouterr().out


def test_invalid_date_argument_rejected(project):
    assert main(["run", "--config", project.config, "--date", "05-10-2026"]) == 2
