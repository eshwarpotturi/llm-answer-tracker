"""Build the static HTML report. No JavaScript, no external files."""
from __future__ import annotations

import os
from html import escape

from .types import AnswerRecord, Question

DASH = "–"

STYLE = """
:root { --bg:#f6f7f9; --card:#fff; --ink:#16202b; --muted:#5d6b7a; --line:#dfe4ea; --accent:#0b6bcb;
        --up:#12784a; --down:#b3261e; --first:#fff6d6; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#10151b; --card:#19212b; --ink:#e8edf2; --muted:#9aa8b6; --line:#2b3643; --accent:#6db3ff;
          --up:#5fd39b; --down:#ff8a80; --first:#3a3212; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
main { max-width:980px; margin:0 auto; padding:32px 16px 64px; }
h1 { margin:0 0 4px; font-size:28px; }
h2 { margin:0 0 12px; font-size:19px; }
.sub { color:var(--muted); margin:0 0 28px; font-size:14px; }
section { background:var(--card); border:1px solid var(--line); border-radius:10px;
          padding:20px; margin:0 0 20px; overflow-x:auto; }
.context { color:var(--muted); font-size:14px; margin:-4px 0 14px; white-space:pre-wrap; }
table { width:100%; border-collapse:collapse; font-size:15px; }
th { text-align:left; font-weight:600; color:var(--muted); font-size:13px;
     padding:6px 10px; border-bottom:2px solid var(--line); white-space:nowrap; }
td { padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
tr.first td { background:var(--first); }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
td.model { font-weight:600; white-space:nowrap; }
td.why { color:var(--muted); font-size:14px; }
td.chg { white-space:nowrap; font-variant-numeric:tabular-nums; }
.up { color:var(--up); } .down { color:var(--down); } .flat { color:var(--muted); }
details { border-top:1px solid var(--line); padding:10px 0 2px; }
details:first-of-type { margin-top:16px; }
summary { cursor:pointer; color:var(--accent); font-weight:600; font-size:14px; }
.answer { white-space:pre-wrap; overflow-wrap:anywhere; margin:10px 0 6px; font-size:15px; }
.meta { color:var(--muted); font-size:12px; margin:0 0 8px; overflow-wrap:anywhere; }
.meta code { font-size:12px; }
footer { color:var(--muted); font-size:13px; margin-top:28px; }
footer li { margin-bottom:4px; }
"""

NOTES = [
    "Answers come from each model's API, not its chat app, with no web search. A person using the chat app may see a different answer.",
    "The ranking is one judge model's opinion. Answers are shown to the judge without model names and in shuffled order.",
    "A high rank means the answer was relevant, complete and in line with the supplied context. It is not proof that the answer is correct.",
    "The sha256 value is a fingerprint of the exact answer text stored for this run.",
]


def _change(previous: float | None, current: float | None, decimals: int) -> str:
    """Cell text for the Change column. Lower rank numbers are better."""
    if current is None:
        return f'<span class="flat">{DASH}</span>'
    if previous is None:
        return '<span class="flat">new</span>'
    diff = round(previous - current, decimals)
    if diff == 0:
        return '<span class="flat">=</span>'
    amount = f"{abs(diff):.{decimals}f}"
    return f'<span class="up">▲{amount}</span>' if diff > 0 else f'<span class="down">▼{amount}</span>'


def _averages(records: list[AnswerRecord]) -> dict[str, tuple[float | None, int]]:
    """{model label: (average rank or None, number of questions ranked)}, in first-seen order."""
    ranks: dict[str, list[int]] = {}
    for r in records:
        ranks.setdefault(r.model_label, [])
        if r.rank is not None:
            ranks[r.model_label].append(r.rank)
    return {label: (sum(v) / len(v) if v else None, len(v)) for label, v in ranks.items()}


def _leaderboard(current: list[AnswerRecord], previous: list[AnswerRecord] | None) -> str:
    now = _averages(current)
    before = _averages(previous) if previous is not None else {}
    order = sorted(now, key=lambda label: (now[label][0] is None, now[label][0] or 0, label))
    rows = []
    for position, label in enumerate(order):
        average, count = now[label]
        shown = f"{average:.1f}" if average is not None else DASH
        css = ' class="first"' if position == 0 and average is not None else ""
        rows.append(
            f'<tr{css}><td class="model">{escape(label)}</td><td class="num">{shown}</td>'
            f'<td class="num">{count}</td>'
            f'<td class="chg">{_change(before.get(label, (None, 0))[0], average, 1)}</td></tr>'
        )
    return (
        '<section id="leaderboard"><h2>Leaderboard</h2><table><thead><tr><th>Model</th>'
        '<th class="num">Average rank</th><th class="num">Questions ranked</th><th>Change</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></section>"
    )


def _question(question: Question, records: list[AnswerRecord],
              previous_rank: dict[tuple[str, str], int | None], has_previous: bool) -> str:
    ordered = sorted(records, key=lambda r: (r.rank is None, r.rank or 0, r.model_label))
    rows, answers = [], []
    for r in ordered:
        if r.rank is None:
            score = "no answer" if r.error else "unranked"
        else:
            score = f"{r.score:.1f}" if r.score is not None else DASH
        why = r.error if (r.error and r.rank is None) else (r.rationale or "")
        before = previous_rank.get((r.model_label, question.id)) if has_previous else None
        css = ' class="first"' if r.rank == 1 else ""
        rows.append(
            f'<tr{css}><td class="num">{r.rank if r.rank is not None else DASH}</td>'
            f'<td class="model">{escape(r.model_label)}</td><td class="num">{score}</td>'
            f'<td class="chg">{_change(before, r.rank, 0)}</td><td class="why">{escape(why)}</td></tr>'
        )
        if r.answer is not None:
            body = f'<div class="answer">{escape(r.answer)}</div>'
            meta = f"sha256 <code>{escape(r.sha256 or '')}</code> · fetched {escape(r.fetched_at)} · {escape(r.model_id)}"
        else:
            body = f'<div class="answer">No answer was received: {escape(r.error or "unknown problem")}</div>'
            meta = f"attempted {escape(r.fetched_at)} · {escape(r.model_id)}"
        answers.append(
            f"<details><summary>{escape(r.model_label)}: full answer</summary>{body}"
            f'<p class="meta">{meta}</p></details>'
        )
    context = f'<p class="context">Context: {escape(question.context)}</p>' if question.context.strip() else ""
    return (
        f'<section id="question-{escape(question.id, quote=True)}"><h2>{escape(question.question)}</h2>{context}'
        '<table><thead><tr><th class="num">Rank</th><th>Model</th><th class="num">Score</th>'
        "<th>Change</th><th>Why</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        + "".join(answers) + "</section>"
    )


def build_report(questions: list[Question], current: list[AnswerRecord],
                 previous: list[AnswerRecord] | None, generated_at: str) -> str:
    wanted = {q.id for q in questions}
    current = [r for r in current if r.question_id in wanted]
    if previous is not None:
        previous = [r for r in previous if r.question_id in wanted]
    previous_rank = {(r.model_label, r.question_id): r.rank for r in (previous or [])}

    run_date = current[0].run_date if current else ""
    compared = f" · compared with the run of {escape(previous[0].run_date)}" if previous else ""
    sections = [
        _question(q, [r for r in current if r.question_id == q.id], previous_rank, previous is not None)
        for q in questions
    ]
    notes = "".join(f"<li>{escape(n)}</li>" for n in NOTES)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>LLM Answer Tracker</title><style>{STYLE}</style></head><body><main>"
        f'<h1>LLM Answer Tracker</h1><p class="sub">Run of {escape(run_date)}{compared} · '
        f"generated {escape(generated_at)}</p>"
        + _leaderboard(current, previous) + "".join(sections)
        + f"<footer><strong>How to read this page</strong><ul>{notes}</ul></footer></main></body></html>"
    )


def write_report(html: str, path: str) -> None:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(html)
