# LLM Answer Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a schedule (weekly by default), ask every question in a CSV file to a configurable set of LLMs, keep a dated record of each answer, rank the answers per question, and publish a report.

**Architecture:** A small Python package run by a scheduled GitHub Actions workflow. All models are reached through Straive's LLM Foundry gateway, using its OpenRouter route, so one token and one request format cover every model and adding or swapping a model is a one-line config change. Each run writes one dated JSONL file (the permanent record, with a SHA-256 hash per answer) and regenerates a static HTML report served from GitHub Pages.

**Tech Stack:** Python 3.11+, httpx, PyYAML, pytest, GitHub Actions, GitHub Pages. No database, no web framework.

**Spec:** No separate spec document. The spec is the request of 5 Oct 2026, restated in "Spec as understood" below. Save this plan in the repo at `docs/superpowers/plans/2026-10-05-llm-answer-tracker.md`.

## Spec as understood

1. Input is a CSV file of questions.
2. Every week, and the interval must be changeable, each question is sent to the top 4 LLMs.
3. The answers are ranked "as per context and answers".
4. Which LLMs are used must be configurable.

**Assumptions made where the request was open (change these before execution if wrong):**

- **"Context"** is an optional `context` column in the CSV: what a good answer should say or mention for that question (for example, facts about Straive). An independent judge model scores each answer against the question and that context, and the models are ranked 1 to N per question.
- **"Top 4 LLMs"** means four entries in `config.yaml`. The code accepts 2 to 8.
- **Answers come from APIs, not chat apps.** They can differ from what ChatGPT or Copilot shows a logged-in user. Web search is not enabled in version 1.
- **Schedule** is a cron line in the workflow file. A manual "Run workflow" button is included for demos.

## Global Constraints

- Python 3.11 or newer.
- Runtime dependencies limited to `httpx` and `PyYAML`. Test dependency: `pytest`.
- The API key is read only from the environment variable `LLMFOUNDRY_TOKEN`. It never appears in config, data files, logs or the report.
- All timestamps are UTC, ISO 8601. Run dates are `YYYY-MM-DD` in UTC.
- All files are read and written as UTF-8.
- No test makes a network call. Tests inject fake `ask` functions or use `httpx.MockTransport`.
- Every request to LLM Foundry carries the header `Cache-Control: no-cache`. Foundry caches all responses by default; without this header a weekly run would get last week's answer back.
- A run never aborts because one model or one question fails.
- Model IDs live only in `config.yaml`. No model name is hard-coded in Python.

## Review Focus

1. **One model's API is down or times out.** The run finishes; that answer is recorded with an `error`, has no rank, and the report shows "no answer". Test in Task 4.
2. **CSV saved from Excel.** A byte-order mark, quoted commas, line breaks inside a question, and blank rows must all parse correctly. Test in Task 2.
3. **The judge returns something that is not valid JSON.** One retry, then the question is left unranked with the rationale "judge reply unreadable". The run continues. Test in Task 5.
4. **The run is started twice on the same date.** The second run replaces that date's file. No duplicate rows. Test in Task 3.
5. **Answer text containing HTML.** A model reply with `<script>` or `<table>` must appear as text in the report, never as markup. Test in Task 6.

## File Structure

| File | Responsibility |
|---|---|
| `questions.csv` | The questions. Columns: `id` (optional), `question`, `context` (optional) |
| `config.yaml` | Models, judge model, paths, timeout |
| `tracker/types.py` | The three dataclasses shared by every module |
| `tracker/config.py` | Load and validate `config.yaml` |
| `tracker/questions.py` | Load and validate the CSV |
| `tracker/client.py` | One function that sends a prompt to a model through LLM Foundry |
| `tracker/store.py` | Read and write dated run files; hash answers |
| `tracker/fetch.py` | Ask every question to every model |
| `tracker/rank.py` | Build the judge prompt, parse its reply, assign ranks |
| `tracker/report.py` | Build the HTML report |
| `tracker/cli.py`, `tracker/__main__.py` | `python -m tracker run` |
| `.github/workflows/tracker.yml` | Schedule, run, commit results |
| `tests/test_*.py` | One test file per module |

---

### Task 1: Project scaffold, shared types, config loading

**Files:**
- Create: `pyproject.toml`, `tracker/__init__.py`, `tracker/types.py`, `tracker/config.py`, `config.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces, in `tracker/types.py`:

```python
@dataclass(frozen=True)
class Question:
    id: str
    question: str
    context: str            # "" when the CSV has none

@dataclass(frozen=True)
class ModelSpec:
    label: str              # shown in the report, e.g. "ChatGPT"
    model_id: str           # OpenRouter model id

@dataclass
class AnswerRecord:
    run_date: str           # YYYY-MM-DD
    question_id: str
    model_label: str
    model_id: str
    answer: str | None
    error: str | None
    fetched_at: str         # ISO 8601 UTC
    sha256: str | None      # hash of answer, None when answer is None
    score: float | None = None      # 0-100
    rank: int | None = None         # 1 = best
    rationale: str | None = None
```

- Produces, in `tracker/config.py`:

```python
@dataclass(frozen=True)
class Config:
    models: list[ModelSpec]
    judge_model_id: str
    project: str            # default "llm-answer-tracker"; label Foundry logs usage under
    questions_path: str     # default "questions.csv"
    data_dir: str           # default "data/runs"
    report_path: str        # default "docs/index.html"
    timeout_s: int          # default 120

class ConfigError(ValueError): ...

def load_config(path: str) -> Config
```

- `config.yaml` shape (the IDs below are placeholders; replace them with current IDs copied from openrouter.ai/models, since Foundry's OpenRouter route accepts every OpenRouter model ID):

```yaml
models:
  - label: ChatGPT
    model_id: openai/REPLACE-ME
  - label: Claude
    model_id: anthropic/REPLACE-ME
  - label: Gemini
    model_id: google/REPLACE-ME
  - label: Grok
    model_id: x-ai/REPLACE-ME
judge_model_id: provider/REPLACE-ME
project: llm-answer-tracker
questions_path: questions.csv
data_dir: data/runs
report_path: docs/index.html
timeout_s: 120
```

- [ ] **Step 1: Write the failing tests**

```python
def test_loads_valid_config(tmp_path):
    cfg = load_config(write(tmp_path, VALID_YAML))   # 4 models
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
```

- [ ] **Step 2: Run** `pytest tests/test_config.py -v`. Expected: FAIL, `tracker.config` not found.
- [ ] **Step 3: Create `pyproject.toml`** (package `tracker`, dependencies per Global Constraints), `tracker/types.py` exactly as above, and implement `load_config` in `tracker/config.py`.
- [ ] **Step 4: Run** `pytest tests/test_config.py -v`. Expected: 6 passed.
- [ ] **Step 5: Commit** `feat: project scaffold, shared types and config loading`

---

### Task 2: Question loading

**Files:**
- Create: `tracker/questions.py`, `questions.csv` (three sample rows)
- Test: `tests/test_questions.py`

**Interfaces:**
- Consumes: `Question` from Task 1.
- Produces:

```python
class QuestionsError(ValueError): ...

def load_questions(path: str) -> list[Question]
```

Rules: header names are matched case-insensitively after trimming. `question` is required. When there is no `id` column, ids are `q1`, `q2`, ... in file order. Rows whose question is blank are skipped.

- [ ] **Step 1: Write the failing tests**

```python
def test_reads_question_and_context(tmp_path):
    qs = load_questions(csv(tmp_path, "id,question,context\na1,What is Straive?,Content and data company\n"))
    assert qs == [Question("a1", "What is Straive?", "Content and data company")]

def test_excel_bom_quoted_commas_and_newlines(tmp_path):
    text = '\ufeffQuestion,Context\n"Best vendors for X, Y?","line one\nline two"\n'
    qs = load_questions(csv(tmp_path, text))
    assert qs[0].question == "Best vendors for X, Y?"
    assert qs[0].context == "line one\nline two"
    assert qs[0].id == "q1"

def test_blank_rows_skipped_and_ids_follow_kept_rows(tmp_path):
    qs = load_questions(csv(tmp_path, "question\nfirst\n\n   \nsecond\n"))
    assert [(q.id, q.question) for q in qs] == [("q1", "first"), ("q2", "second")]

def test_missing_context_column_gives_empty_context(tmp_path):
    assert load_questions(csv(tmp_path, "question\nhello\n"))[0].context == ""

def test_missing_question_column_rejected(tmp_path):
    with pytest.raises(QuestionsError, match="question"):
        load_questions(csv(tmp_path, "prompt\nhello\n"))

def test_duplicate_ids_rejected(tmp_path):
    with pytest.raises(QuestionsError, match="duplicate id"):
        load_questions(csv(tmp_path, "id,question\nx,a\nx,b\n"))

def test_no_questions_rejected(tmp_path):
    with pytest.raises(QuestionsError, match="no questions"):
        load_questions(csv(tmp_path, "question\n\n"))
```

- [ ] **Step 2: Run** `pytest tests/test_questions.py -v`. Expected: FAIL, module not found.
- [ ] **Step 3: Implement `load_questions`** using the standard `csv` module, opening the file with `encoding="utf-8-sig"` and `newline=""`.
- [ ] **Step 4: Run** `pytest tests/test_questions.py -v`. Expected: 7 passed.
- [ ] **Step 5: Commit** `feat: load questions from csv`

---

### Task 3: Run storage and answer hashing

**Files:**
- Create: `tracker/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `AnswerRecord` from Task 1.
- Produces:

```python
def answer_hash(text: str) -> str                      # sha256 hex of the UTF-8 bytes
def save_run(records: list[AnswerRecord], data_dir: str, run_date: str) -> str   # returns file path
def load_run(data_dir: str, run_date: str) -> list[AnswerRecord]
def list_run_dates(data_dir: str) -> list[str]         # ascending; [] if dir missing
```

File name: `<data_dir>/<run_date>.jsonl`, one JSON object per line, keys equal to the `AnswerRecord` field names, `ensure_ascii=False`.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run** `pytest tests/test_store.py -v`. Expected: FAIL, module not found.
- [ ] **Step 3: Implement the four functions.** `save_run` writes to a temporary file in the same directory and renames it over the target, so an interrupted run cannot leave a half-written file.
- [ ] **Step 4: Run** `pytest tests/test_store.py -v`. Expected: 6 passed.
- [ ] **Step 5: Commit** `feat: dated run storage with answer hashes`

---

### Task 4: LLM client and answer fetching

**Files:**
- Create: `tracker/client.py`, `tracker/fetch.py`
- Test: `tests/test_client.py`, `tests/test_fetch.py`

**Interfaces:**
- Consumes: `Question`, `ModelSpec`, `AnswerRecord` (Task 1); `answer_hash` (Task 3).
- Produces:

```python
# tracker/client.py
class LLMError(RuntimeError): ...

AskFn = Callable[[str, str], str]      # (model_id, prompt) -> answer text

def make_ask(token: str | None, project: str, timeout_s: int,
             transport: httpx.BaseTransport | None = None) -> AskFn

# tracker/fetch.py
def fetch_answers(questions: list[Question], models: list[ModelSpec], ask: AskFn,
                  run_date: str, now: Callable[[], str]) -> list[AnswerRecord]
```

`make_ask` posts to `https://llmfoundry.straive.com/openrouter/v1/chat/completions` with body `{"model": model_id, "messages": [{"role": "user", "content": prompt}]}` and two headers: `Authorization: Bearer <token>:<project>` and `Cache-Control: no-cache`. It returns `choices[0].message.content`. If the response carries the header `X-Cache: HIT`, it raises `LLMError("served from cache")`, because a cached answer is not this week's answer. It retries on HTTP 429 and 5xx and on timeouts: 3 attempts in total, waiting 2 s then 4 s. The wait function is a module-level `_sleep` so tests can replace it.

`fetch_answers` returns exactly `len(questions) * len(models)` records, ordered by question then by model as listed in config. The prompt sent is the question text alone; `context` is never shown to the answering models.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_client.py
def test_returns_message_content():
    ask = make_ask("k", "proj", 5, transport=mock(200, {"choices": [{"message": {"content": "hi"}}]}))
    assert ask("openai/x", "hello") == "hi"

def test_sends_model_prompt_token_project_and_no_cache():
    seen = {}
    ask = make_ask("secret", "llm-answer-tracker", 5, transport=capture(seen))
    ask("openai/x", "hello")
    assert seen["url"] == "https://llmfoundry.straive.com/openrouter/v1/chat/completions"
    assert seen["json"]["model"] == "openai/x"
    assert seen["json"]["messages"] == [{"role": "user", "content": "hello"}]
    assert seen["headers"]["authorization"] == "Bearer secret:llm-answer-tracker"
    assert seen["headers"]["cache-control"] == "no-cache"

def test_cached_response_rejected():
    t = mock(200, {"choices": [{"message": {"content": "old"}}]}, headers={"X-Cache": "HIT"})
    with pytest.raises(LLMError, match="served from cache"):
        make_ask("k", "proj", 5, transport=t)("m", "p")

def test_retries_then_succeeds(no_sleep):
    ask = make_ask("k", "proj", 5, transport=sequence([503, 429, 200]))
    assert ask("m", "p") == "ok"

def test_gives_up_after_three_attempts(no_sleep):
    with pytest.raises(LLMError, match="503"):
        make_ask("k", "proj", 5, transport=sequence([503, 503, 503]))("m", "p")

def test_client_error_not_retried(no_sleep):
    t = sequence([400, 200])
    with pytest.raises(LLMError, match="400"):
        make_ask("k", "proj", 5, transport=t)("m", "p")
    assert t.calls == 1

def test_missing_token_raises_clear_error():
    with pytest.raises(LLMError, match="LLMFOUNDRY_TOKEN is not set"):
        make_ask(None, "proj", 5)

def test_empty_or_missing_content_raises():
    with pytest.raises(LLMError, match="empty answer"):
        make_ask("k", "proj", 5, transport=mock(200, {"choices": [{"message": {"content": ""}}]}))("m", "p")

# tests/test_fetch.py
def test_one_record_per_question_and_model_in_order():
    recs = fetch_answers(QS2, MODELS4, lambda m, p: f"{m}:{p}", "2026-10-05", lambda: "T")
    assert len(recs) == 8
    assert [(r.question_id, r.model_label) for r in recs[:4]] == [("q1", l) for l in LABELS4]

def test_record_carries_answer_hash_and_metadata():
    r = fetch_answers(QS1, MODELS4[:1], lambda m, p: "an answer", "2026-10-05", lambda: "T")[0]
    assert (r.answer, r.error, r.fetched_at, r.run_date) == ("an answer", None, "T", "2026-10-05")
    assert r.sha256 == answer_hash("an answer")

def test_failing_model_recorded_and_others_continue():       # Review Focus 1
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
```

- [ ] **Step 2: Run** `pytest tests/test_client.py tests/test_fetch.py -v`. Expected: FAIL, modules not found.
- [ ] **Step 3: Implement `make_ask` and `fetch_answers`.** `fetch_answers` catches `LLMError` only; any other exception is a bug and should surface.
- [ ] **Step 4: Run** the same command. Expected: 12 passed.
- [ ] **Step 5: Commit** `feat: llm foundry client and answer fetching`

---

### Task 5: Ranking

**Files:**
- Create: `tracker/rank.py`
- Test: `tests/test_rank.py`

**Interfaces:**
- Consumes: `Question`, `AnswerRecord` (Task 1); `AskFn`, `LLMError` (Task 4).
- Produces:

```python
def build_judge_prompt(question: Question, lettered: list[tuple[str, str]]) -> str
    # lettered = [("A", answer_text), ...]

def parse_judge_reply(text: str, letters: list[str]) -> dict[str, tuple[float, str]]
    # {"A": (score, reason)}; raises ValueError if unreadable or any letter missing

def rank_question(question: Question, records: list[AnswerRecord],
                  ask: AskFn, judge_model_id: str) -> list[AnswerRecord]
    # returns the same records, in the same order, with score/rank/rationale filled in
```

**Scoring rules the judge prompt must state:**

- Each answer gets 0 to 10 on each criterion. Criteria when `context` is non-empty: *relevance* (does it answer the question asked), *agreement with context* (does it match the reference information supplied), *completeness*. When `context` is empty, only *relevance* and *completeness*.
- The judge returns only JSON: `{"A": {"relevance": n, "agreement": n, "completeness": n, "reason": "one sentence"}, ...}`. The `agreement` key is omitted when there is no context.
- `score` = mean of the criteria present × 10, rounded to 1 decimal place, so always 0 to 100.

**Ranking rules:**

- Answers are shown to the judge as A, B, C, ... with model names removed. The order is shuffled with `random.Random(f"{run_date}:{question_id}")`, so a rerun gives the same order.
- Records with `error` set are not sent to the judge and keep `score`, `rank` and `rationale` as `None`.
- Rank 1 is the highest score. Equal scores are ordered by `model_label` alphabetically and get consecutive ranks.
- `parse_judge_reply` accepts JSON wrapped in a Markdown code fence or with text before and after it: take the span from the first `{` to the last `}`.
- If the reply cannot be parsed, ask the judge once more. If the second reply also fails, or the judge call raises `LLMError`, every record for that question gets `score=None`, `rank=None`, `rationale="judge reply unreadable"`.
- If fewer than 2 answers are available, the judge is not called: a single available answer gets `rank=1`, `score=None`, `rationale="only answer available"`.

- [ ] **Step 1: Write the failing tests**

```python
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

def test_unreadable_judge_reply_retried_once_then_unranked():      # Review Focus 3
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
```

`judge_scores(by_label, seen=None)` is a test helper: it reads the lettered answers out of the prompt (each test answer text contains its model label), returns matching JSON, and appends the prompt to `seen`.

- [ ] **Step 2: Run** `pytest tests/test_rank.py -v`. Expected: FAIL, module not found.
- [ ] **Step 3: Implement the three functions.** In the prompt, introduce each answer with the literal line `Answer A:` (and so on), which is what `test_errored_record_excluded_and_unranked` counts.
- [ ] **Step 4: Run** `pytest tests/test_rank.py -v`. Expected: 11 passed.
- [ ] **Step 5: Commit** `feat: judge-based ranking of answers`

---

### Task 6: HTML report

**Files:**
- Create: `tracker/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `Question`, `AnswerRecord` (Task 1).
- Produces:

```python
def build_report(questions: list[Question], current: list[AnswerRecord],
                 previous: list[AnswerRecord] | None, generated_at: str) -> str   # full HTML page
def write_report(html: str, path: str) -> None      # creates parent directories
```

**Page content, top to bottom:**

1. Title "LLM Answer Tracker", the run date, and `generated_at`.
2. **Leaderboard table:** one row per model, columns Model, Average rank (1 decimal), Questions ranked, Change. Sorted by average rank ascending, then label. A model with no ranked answers shows "–" and sorts last.
3. **One section per question**, in CSV order: the question text, the context if any, then a table with columns Rank, Model, Score, Change, Why (the rationale). Rows sorted by rank; unranked rows last, labelled "no answer" when `error` is set and "unranked" otherwise.
4. Under each table, each model's full answer inside a `<details>` element, with its `sha256` and `fetched_at`.

**Change column:** compares rank with the same model and question id in `previous`. Improved by n: `▲n`. Dropped by n: `▼n`. Same: `=`. No earlier rank, or `previous` is `None`: `new`. The leaderboard uses the same symbols on average rank, with the difference shown to 1 decimal.

All text from the CSV and from models goes through `html.escape`. One inline `<style>` block; no JavaScript and no external files.

- [ ] **Step 1: Write the failing tests**

```python
def test_leaderboard_sorted_by_average_rank():
    html = build_report(QS2, ranked_run({"Claude": [1, 1], "Grok": [2, 3], "ChatGPT": [3, 2], "Gemini": [4, 4]}), None, "T")
    board = section(html, "leaderboard")
    assert order_of(board, LABELS4) == ["Claude", "ChatGPT", "Grok", "Gemini"]
    assert "1.0" in board and "2.5" in board

def test_change_symbols_against_previous_run():
    prev = ranked_run({"Claude": [2], "Grok": [1], "ChatGPT": [3], "Gemini": [4]}, date="2026-09-28")
    cur = ranked_run({"Claude": [1], "Grok": [3], "ChatGPT": [3 - 1 + 1], "Gemini": [4]})   # Claude up 1, Grok down 2
    q = section(build_report(QS1, cur, prev, "T"), "question-q1")
    assert "▲1" in row(q, "Claude") and "▼2" in row(q, "Grok") and "=" in row(q, "Gemini")

def test_first_run_marks_everything_new():
    assert section(build_report(QS1, ranked_run({l: [i + 1] for i, l in enumerate(LABELS4)}), None, "T"), "question-q1").count("new") == 4

def test_errored_answer_shows_no_answer_and_sorts_last():
    cur = ranked_run({"Claude": [1], "Grok": [2], "ChatGPT": [3], "Gemini": [None]}, errors={"Gemini": "timeout"})
    q = section(build_report(QS1, cur, None, "T"), "question-q1")
    assert "no answer" in row(q, "Gemini")
    assert order_of(q, LABELS4)[-1] == "Gemini"

def test_model_and_csv_text_is_escaped():                       # Review Focus 5
    cur = ranked_run({l: [i + 1] for i, l in enumerate(LABELS4)}, answer="<script>alert(1)</script>")
    html = build_report([Question("q1", "Is 2 < 3?", "<b>ctx</b>")], cur, None, "T")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "Is 2 &lt; 3?" in html and "&lt;b&gt;ctx&lt;/b&gt;" in html

def test_answers_shown_with_hash_inside_details():
    cur = ranked_run({l: [i + 1] for i, l in enumerate(LABELS4)}, answer="full text")
    html = build_report(QS1, cur, None, "T")
    assert html.count("<details") == 4 and answer_hash("full text") in html

def test_question_removed_from_csv_is_not_shown():
    cur = ranked_run({l: [i + 1] for i, l in enumerate(LABELS4)}, question_id="gone")
    assert "question-gone" not in build_report(QS1, cur, None, "T")

def test_write_report_creates_directories(tmp_path):
    write_report("<html></html>", str(tmp_path / "docs" / "index.html"))
    assert (tmp_path / "docs" / "index.html").read_text(encoding="utf-8") == "<html></html>"
```

The helpers `section(html, id)` and `row(html, label)` find an element by `id` and a table row containing a label. The implementation must therefore give the leaderboard `id="leaderboard"` and each question section `id="question-<question id>"`.

- [ ] **Step 2: Run** `pytest tests/test_report.py -v`. Expected: FAIL, module not found.
- [ ] **Step 3: Implement `build_report` and `write_report`** with string templates from the standard library.
- [ ] **Step 4: Run** `pytest tests/test_report.py -v`. Expected: 8 passed.
- [ ] **Step 5: Commit** `feat: html report with leaderboard and week-on-week change`

---

### Task 7: Command line, schedule and README

**Files:**
- Create: `tracker/cli.py`, `tracker/__main__.py`, `.github/workflows/tracker.yml`, `README.md`, `.gitignore`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything produced in Tasks 1 to 6.
- Produces:

```python
def run(config_path: str, run_date: str | None = None, ask: AskFn | None = None) -> int
    # returns the process exit code
def main(argv: list[str] | None = None) -> int
```

Command: `python -m tracker run [--config config.yaml] [--date YYYY-MM-DD]`

**`run` behaviour, in order:**

1. Load config and questions. On `ConfigError`, `QuestionsError`, or a missing API key: print one line starting `error:` to stderr and return 2. Nothing is written.
2. `run_date` defaults to today's date in UTC.
3. Fetch answers, then rank each question.
4. Save the run. The previous run is the latest date in `list_run_dates` that is earlier than `run_date`.
5. Build and write the report.
6. Print one summary line: `run 2026-10-05: 3 questions, 4 models, 12 answers, 0 failed`.
7. Return 0 if at least one answer was fetched. Return 1 if every request failed; the run file and report are still written.

**Workflow `.github/workflows/tracker.yml`:**

- Triggers: `schedule` with cron `30 3 * * 1` (Mondays 03:30 UTC, which is 09:00 IST) and `workflow_dispatch`.
- `permissions: contents: write`.
- Steps: checkout, set up Python 3.11, `pip install .`, `python -m tracker run` with `LLMFOUNDRY_TOKEN` taken from repository secrets, then commit `data/runs` and `docs` with message `run: <date>` and push. The commit step is skipped when nothing changed.
- `concurrency: tracker` so two runs cannot push at once.

**README sections:** what it does; one-time setup (add the `LLMFOUNDRY_TOKEN` secret, enable GitHub Pages on the `/docs` folder, put real model IDs in `config.yaml`); which token to use (a personal Foundry token is acceptable for a demo; for ongoing scheduled runs, Foundry's production guide says to request a group token from servicedesk@straive.com so cost is billed to the project and not to one person); how to run it on a Straive machine with the system scheduler if company policy does not allow the token in GitHub's secret store; how to edit `questions.csv`; how to change the schedule, with three ready-made cron lines (daily, weekly, monthly); how to add or swap a model; the limits listed under "Known limits" below.

- [ ] **Step 1: Write the failing tests**

```python
def test_full_run_writes_data_and_report(project):            # project = tmp dir with config.yaml + questions.csv
    code = run(project.config, "2026-10-05", ask=fake_ask)
    assert code == 0
    recs = load_run(project.data_dir, "2026-10-05")
    assert len(recs) == 3 * 4 and all(r.rank for r in recs)
    assert "LLM Answer Tracker" in project.report.read_text(encoding="utf-8")

def test_second_run_compares_with_earlier_date(project):
    run(project.config, "2026-09-28", ask=fake_ask)
    run(project.config, "2026-10-05", ask=fake_ask)
    assert "new" not in section(project.report.read_text(encoding="utf-8"), "question-q1")

def test_rerun_same_date_does_not_duplicate(project):         # Review Focus 4, end to end
    run(project.config, "2026-10-05", ask=fake_ask)
    run(project.config, "2026-10-05", ask=fake_ask)
    assert len(load_run(project.data_dir, "2026-10-05")) == 12

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

def test_summary_line(project, capsys):
    run(project.config, "2026-10-05", ask=fake_ask)
    assert "run 2026-10-05: 3 questions, 4 models, 12 answers, 0 failed" in capsys.readouterr().out

def test_invalid_date_argument_rejected(project):
    assert main(["run", "--config", project.config, "--date", "05-10-2026"]) == 2
```

`fake_ask` returns a short answer for an answering model and valid judge JSON when the prompt contains `Answer A:`.

- [ ] **Step 2: Run** `pytest tests/test_cli.py -v`. Expected: FAIL, module not found.
- [ ] **Step 3: Implement `run` and `main`**, then write the workflow file, README and `.gitignore` (`__pycache__/`, `.pytest_cache/`, `*.egg-info/`, `.env`).
- [ ] **Step 4: Run** `pytest -v`. Expected: all 58 tests pass.
- [ ] **Step 5: Manual check with real models.** Put real model IDs in `config.yaml`, export `LLMFOUNDRY_TOKEN`, run `python -m tracker run`, and open `docs/index.html`. Expected: a leaderboard and one section per sample question, each with four ranked answers. Run it a second time with a different `--date` and confirm the answers are freshly generated (different `fetched_at`, and no "served from cache" errors).
- [ ] **Step 6: Commit** `feat: cli, weekly workflow and readme`

---

## Known limits (state these in the README and in any demo)

- **API answers are not chat-app answers.** No web search, memory or hidden product instructions, so results can differ from what a person sees in ChatGPT or Copilot.
- **The ranking is one model's judgment.** It is consistent and repeatable, but it is an opinion. Answers are anonymised and shuffled to reduce bias; if the judge is also one of the ranked models, some bias toward its own style may remain. Using a judge that is not among the ranked models avoids this.
- **A high rank is not proof of accuracy.** With no `context` supplied, the judge can only assess relevance and completeness.
- **Each run costs money**: questions × models answer calls, plus one judge call per question. Usage is logged by LLM Foundry against the token used.
- **Questions leave Straive's tenant.** The OpenRouter route sends prompts to outside providers, so `questions.csv` must hold only public, non-confidential questions.
- **LLM Foundry has planned downtime** of a few minutes a day. A run that lands in it records failures for those calls and can be rerun for the same date.
- **Similar paid products exist.** AI-visibility platforms already run scheduled prompts across several models and track brand presence. This tool's difference is that it is free to run, fully configurable, and keeps the raw dated answers in your own repository.

## Not in version 1

- Web search for the answering models.
- Tracking a named brand's position inside each answer.
- Trend charts across more than two runs.
- Email or chat notifications after a run.
