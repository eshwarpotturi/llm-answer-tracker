"""python -m tracker run [--config config.yaml] [--date YYYY-MM-DD]"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, timezone

from .client import AskFn, LLMError, make_ask
from .config import ConfigError, load_config
from .fetch import fetch_answers
from .questions import QuestionsError, load_questions
from .rank import rank_question
from .report import build_report, write_report
from .store import list_run_dates, load_run, save_run


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def run(config_path: str, run_date: str | None = None, ask: AskFn | None = None) -> int:
    try:
        cfg = load_config(config_path)
        placeholders = [m.label for m in cfg.models if "REPLACE-ME" in m.model_id]
        if placeholders or "REPLACE-ME" in cfg.judge_model_id:
            raise ConfigError("config.yaml still has REPLACE-ME placeholders; put real model IDs in it")
        # Paths in the config are relative to the folder the config file is in.
        base = os.path.dirname(os.path.abspath(config_path))
        questions = load_questions(os.path.join(base, cfg.questions_path))
        if ask is None:
            ask = make_ask(os.environ.get("LLMFOUNDRY_TOKEN"), cfg.project, cfg.timeout_s)
    except (ConfigError, QuestionsError, LLMError) as e:
        return _fail(str(e))

    data_dir = os.path.join(base, cfg.data_dir)
    report_path = os.path.join(base, cfg.report_path)
    run_date = run_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"asking {len(questions)} questions to {len(cfg.models)} models...", flush=True)
    records = fetch_answers(questions, cfg.models, ask, run_date, _now)
    print("ranking the answers...", flush=True)
    for question in questions:
        rank_question(question, [r for r in records if r.question_id == question.id], ask, cfg.judge_model_id)

    earlier = [d for d in list_run_dates(data_dir) if d < run_date]
    previous = load_run(data_dir, earlier[-1]) if earlier else None
    save_run(records, data_dir, run_date)
    write_report(build_report(questions, records, previous, _now()), report_path)

    failed = [r for r in records if r.answer is None]
    for r in failed:
        print(f"warning: {r.model_label} gave no answer to {r.question_id}: {r.error}", file=sys.stderr)
    unranked = sorted({r.question_id for r in records if r.answer is not None and r.rank is None})
    if unranked:
        print(f"warning: could not rank {', '.join(unranked)} (the judge model gave no usable reply)", file=sys.stderr)
    answered = len(records) - len(failed)
    print(f"run {run_date}: {len(questions)} questions, {len(cfg.models)} models, "
          f"{answered} answers, {len(failed)} failed")
    print(f"report: {report_path}")
    return 0 if answered else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tracker", description="Ask a CSV of questions to several LLMs and rank the answers.")
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="fetch answers, rank them and write the report")
    run_parser.add_argument("--config", default="config.yaml", help="path to the config file (default: config.yaml)")
    run_parser.add_argument("--date", default=None, help="run date as YYYY-MM-DD (default: today, UTC)")
    args = parser.parse_args(argv)

    if args.date is not None:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
                raise ValueError
            date.fromisoformat(args.date)
        except ValueError:
            return _fail(f"--date must look like 2026-10-05, got {args.date}")
    return run(args.config, args.date)
