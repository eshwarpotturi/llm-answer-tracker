# LLM Answer Tracker

Asks every question in `questions.csv` to a set of LLMs, keeps a dated copy of
each answer, ranks the answers for each question, and writes a report page.
It can run by hand or on a schedule (weekly by default).

All models are called through Straive's LLM Foundry, so one Foundry token covers
every model.

## Run it on your laptop

You need Python 3.11 or newer (`python3 --version` shows yours).

**Mac**

```bash
cd path/to/llm-answer-tracker
python3 -m venv .venv
source .venv/bin/activate
pip install httpx pyyaml
export LLMFOUNDRY_TOKEN='paste-your-foundry-token-here'
python -m tracker run
open docs/index.html
```

**Windows (PowerShell)**

```powershell
cd path\to\llm-answer-tracker
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install httpx pyyaml
$env:LLMFOUNDRY_TOKEN = 'paste-your-foundry-token-here'
python -m tracker run
start docs\index.html
```

Your token is on https://llmfoundry.straive.com/code. Paste only the token: the
tool adds the project label itself. Never put the token in a file in this folder.

A run prints one summary line, for example:

```
run 2026-10-05: 3 questions, 4 models, 12 answers, 0 failed
```

To see the "Change" column fill in, run again on a later day, or pretend with
`python -m tracker run --date 2026-10-12`.

## What you can change

### The questions: `questions.csv`

| Column | Required | Meaning |
|---|---|---|
| `question` | yes | The question sent to every model |
| `context` | no | What a good answer should say or mention. Only the judge sees this |
| `id` | no | A short name for the question. Without it, questions are `q1`, `q2`, ... |

Keep the `id` of a question the same from week to week, so the report can show
how each model's rank changed. Saving the file from Excel as "CSV UTF-8" works.

Only put public, non-confidential questions here. This route sends the questions
to providers outside Straive's tenant.

### The models: `config.yaml`

Each entry has a `label` (shown in the report) and a `model_id`. The IDs are
OpenRouter model IDs, listed at https://openrouter.ai/models. To swap a model,
change its `model_id`. To add one, add an entry. Between 2 and 8 models work.

`judge_model_id` is the model that scores the answers. It is fairer to use a
judge that is not one of the models being ranked.

### The schedule: `.github/workflows/tracker.yml`

Change the `cron` line. Times are in UTC (IST is UTC + 5:30).

| Interval | Line |
|---|---|
| Every day at 09:00 IST | `cron: "30 3 * * *"` |
| Every Monday at 09:00 IST | `cron: "30 3 * * 1"` |
| First day of each month at 09:00 IST | `cron: "30 3 1 * *"` |

## Run it every week on GitHub

1. Put this folder in a GitHub repository.
2. In the repository: Settings, then Secrets and variables, then Actions. Add a
   secret named `LLMFOUNDRY_TOKEN`.
3. Settings, then Pages. Publish from the `main` branch, `/docs` folder. The
   report is then a web page that updates after every run.
4. The Actions tab has a "Run workflow" button for a run on demand.

**Which token.** Your personal Foundry token is fine for a demo. For a standing
weekly job, Foundry's production guide asks for a group token: create a Google
Group for the project and send its address to servicedesk@straive.com. The cost
is then billed to the project and not to you.

**If the token may not be stored on GitHub.** Run it on a Straive machine with
the system scheduler instead. On Mac or Linux, add a line like this with
`crontab -e` (the token goes in the environment of that job, not in this folder):

```
30 9 * * 1 cd /path/to/llm-answer-tracker && LLMFOUNDRY_TOKEN=... .venv/bin/python -m tracker run
```

## How the ranking works

1. Each model gets the question alone. It never sees the context.
2. The judge model gets the question, the context, and the answers labelled A,
   B, C... with no model names, in shuffled order.
3. The judge marks each answer from 0 to 10 for relevance, completeness, and
   (when there is context) agreement with the context. The score is the average
   of those marks, out of 100.
4. The highest score is rank 1. The leaderboard shows each model's average rank
   across all questions.

## Where things are kept

| Path | What it is |
|---|---|
| `data/runs/YYYY-MM-DD.jsonl` | Every answer from that run, with the time it was fetched and a SHA-256 fingerprint of the text |
| `docs/index.html` | The latest report |

Running twice on the same date replaces that date's file.

## Known limits

- **API answers are not chat-app answers.** There is no web search, memory or
  hidden product instructions, so results can differ from what a person sees in
  ChatGPT or Copilot.
- **The ranking is one model's judgment.** It is repeatable, but it is an
  opinion. If the judge belongs to the same family as a ranked model, some bias
  toward that model's style may remain.
- **A high rank is not proof of accuracy.** With no context supplied, the judge
  can only assess relevance and completeness.
- **Each run costs money**: questions x models answer calls, plus one judge call
  per question. Foundry logs usage against the token used.
- **Foundry has a few minutes of planned downtime a day.** A run that lands in it
  records failures for those calls. Run it again for the same date.
- **Similar paid products exist.** AI-visibility platforms run scheduled prompts
  across models and track brand presence. This tool is free to run, fully
  configurable, and keeps the raw dated answers in your own repository.

## Tests

```bash
pip install pytest
python -m pytest
```

No test calls a real model.
