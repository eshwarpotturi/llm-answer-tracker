"""Shared fixtures for tests. Nothing here touches the network."""
import json
import re

from tracker.store import answer_hash
from tracker.types import AnswerRecord, ModelSpec, Question

LABELS4 = ["ChatGPT", "Claude", "Gemini", "Grok"]
MODELS4 = [ModelSpec(l, f"prov/{l.lower()}") for l in LABELS4]
QS1 = [Question("q1", "What is X?", "X is a company")]
QS2 = QS1 + [Question("q2", "Who makes Y?", "")]
Q = QS1[0]
ALL50 = {l: 50 for l in LABELS4}


def records4(run_date="2026-10-05", question_id="q1"):
    out = []
    for m in MODELS4:
        text = f"{m.label} reply text"
        out.append(AnswerRecord(run_date, question_id, m.label, m.model_id, text, None,
                                "2026-10-05T03:30:00Z", answer_hash(text)))
    return out


def lettered_answers(prompt):
    """{'A': 'answer text', ...} as shown to the judge."""
    parts = re.split(r"^Answer ([A-Z]):\s*$", prompt, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def judge_scores(by_label, seen=None):
    """A fake judge: scores each lettered answer by the model label inside its text."""
    def ask(model_id, prompt):
        if seen is not None:
            seen.append(prompt)
        reply = {}
        for letter, text in lettered_answers(prompt).items():
            label = next(l for l in by_label if l in text)
            v = by_label[label] / 10
            reply[letter] = {"relevance": v, "agreement": v, "completeness": v, "reason": f"scored {by_label[label]}"}
        return json.dumps(reply)
    return ask


def section(html, element_id):
    """Text of the <section id=...> element."""
    m = re.search(rf'<section id="{re.escape(element_id)}".*?</section>', html, flags=re.S)
    assert m, f"no section with id {element_id}"
    return m.group(0)


def row(html, label):
    """The first table row that names this model."""
    for r in re.findall(r"<tr.*?</tr>", html, flags=re.S):
        if f">{label}<" in r:
            return r
    raise AssertionError(f"no row for {label}")


def order_of(html, labels):
    """Labels in the order their table rows appear."""
    found = []
    for r in re.findall(r"<tr.*?</tr>", html, flags=re.S):
        for l in labels:
            if f">{l}<" in r and l not in found:
                found.append(l)
    return found


def ranked_run(ranks_by_label, date="2026-10-05", errors=None, answer="answer text", question_id=None):
    """Records for one run. ranks_by_label = {"Claude": [rank for q1, rank for q2, ...]}."""
    errors = errors or {}
    out = []
    for label, ranks in ranks_by_label.items():
        for i, rank in enumerate(ranks):
            failed = label in errors
            text = None if failed else answer
            out.append(AnswerRecord(
                run_date=date, question_id=question_id or f"q{i + 1}", model_label=label,
                model_id=f"prov/{label.lower()}", answer=text, error=errors.get(label),
                fetched_at=f"{date}T03:30:00Z", sha256=answer_hash(text) if text else None,
                score=None if rank is None else float(100 - rank * 10), rank=rank,
                rationale=None if rank is None else "because",
            ))
    return out
