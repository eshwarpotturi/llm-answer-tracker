import pytest

from tracker.config import ConfigError, load_config

MODELS4 = """models:
  - label: ChatGPT
    model_id: openai/a
  - label: Claude
    model_id: anthropic/b
  - label: Gemini
    model_id: google/c
  - label: Grok
    model_id: x-ai/d
"""
VALID_YAML = MODELS4 + """judge_model_id: provider/j
project: llm-answer-tracker
questions_path: questions.csv
data_dir: data/runs
report_path: docs/index.html
timeout_s: 120
"""
ONLY_MODELS_AND_JUDGE = MODELS4 + "judge_model_id: provider/j\n"
TWO_MODELS_SAME_LABEL = """models:
  - label: Same
    model_id: a/a
  - label: Same
    model_id: b/b
judge_model_id: provider/j
"""
ONE_MODEL = """models:
  - label: Only
    model_id: a/a
judge_model_id: provider/j
"""
NO_JUDGE = MODELS4


def write(tmp_path, text):
    p = tmp_path / "config.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_loads_valid_config(tmp_path):
    cfg = load_config(write(tmp_path, VALID_YAML))
    assert [m.label for m in cfg.models] == ["ChatGPT", "Claude", "Gemini", "Grok"]
    assert cfg.timeout_s == 120 and cfg.data_dir == "data/runs"


def test_defaults_applied_when_optional_keys_missing(tmp_path):
    cfg = load_config(write(tmp_path, ONLY_MODELS_AND_JUDGE))
    assert cfg.questions_path == "questions.csv"
    assert cfg.report_path == "docs/index.html"
    assert cfg.project == "llm-answer-tracker"


def test_rejects_duplicate_labels(tmp_path):
    with pytest.raises(ConfigError, match="duplicate model label"):
        load_config(write(tmp_path, TWO_MODELS_SAME_LABEL))


def test_rejects_fewer_than_two_or_more_than_eight_models(tmp_path):
    with pytest.raises(ConfigError, match="between 2 and 8 models"):
        load_config(write(tmp_path, ONE_MODEL))


def test_rejects_missing_judge(tmp_path):
    with pytest.raises(ConfigError, match="judge_model_id"):
        load_config(write(tmp_path, NO_JUDGE))


def test_missing_file_gives_config_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(str(tmp_path / "nope.yaml"))
