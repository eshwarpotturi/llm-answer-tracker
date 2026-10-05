"""Load and validate config.yaml."""
from __future__ import annotations

from dataclasses import dataclass

import yaml

from .types import ModelSpec


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    models: list[ModelSpec]
    judge_model_id: str
    project: str
    questions_path: str
    data_dir: str
    report_path: str
    timeout_s: int


def load_config(path: str) -> Config:
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except yaml.YAMLError as e:
        raise ConfigError(f"config file is not valid YAML: {e}") from None
    if not isinstance(raw, dict):
        raise ConfigError("config file must contain a list of models and a judge_model_id")

    entries = raw.get("models") or []
    if not isinstance(entries, list) or not 2 <= len(entries) <= 8:
        raise ConfigError("config must list between 2 and 8 models")
    models: list[ModelSpec] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ConfigError("each model needs a label and a model_id")
        label = str(entry.get("label") or "").strip()
        model_id = str(entry.get("model_id") or "").strip()
        if not label or not model_id:
            raise ConfigError("each model needs a label and a model_id")
        if label in seen:
            raise ConfigError(f"duplicate model label: {label}")
        seen.add(label)
        models.append(ModelSpec(label, model_id))

    judge = str(raw.get("judge_model_id") or "").strip()
    if not judge:
        raise ConfigError("judge_model_id is missing")

    try:
        timeout_s = int(raw.get("timeout_s", 120))
    except (TypeError, ValueError):
        raise ConfigError("timeout_s must be a whole number of seconds") from None
    if timeout_s <= 0:
        raise ConfigError("timeout_s must be a whole number of seconds")

    return Config(
        models=models,
        judge_model_id=judge,
        project=str(raw.get("project") or "llm-answer-tracker").strip(),
        questions_path=str(raw.get("questions_path") or "questions.csv"),
        data_dir=str(raw.get("data_dir") or "data/runs"),
        report_path=str(raw.get("report_path") or "docs/index.html"),
        timeout_s=timeout_s,
    )
