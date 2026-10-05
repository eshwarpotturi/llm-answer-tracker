"""Dated run files: one JSONL file per run date, plus the answer fingerprint."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, fields

from .types import AnswerRecord

_DATE_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")
_FIELDS = {f.name for f in fields(AnswerRecord)}


def answer_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _path(data_dir: str, run_date: str) -> str:
    return os.path.join(data_dir, f"{run_date}.jsonl")


def save_run(records: list[AnswerRecord], data_dir: str, run_date: str) -> str:
    os.makedirs(data_dir, exist_ok=True)
    target = _path(data_dir, run_date)
    fd, tmp = tempfile.mkstemp(dir=data_dir, prefix=".tmp-", suffix=".jsonl")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            for r in records:
                f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return target


def load_run(data_dir: str, run_date: str) -> list[AnswerRecord]:
    out: list[AnswerRecord] = []
    with open(_path(data_dir, run_date), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                out.append(AnswerRecord(**{k: v for k, v in data.items() if k in _FIELDS}))
    return out


def list_run_dates(data_dir: str) -> list[str]:
    if not os.path.isdir(data_dir):
        return []
    return sorted(m.group(1) for name in os.listdir(data_dir) if (m := _DATE_FILE.match(name)))
