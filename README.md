# InterviewIQ AI

AI-powered, voice-based mock interview platform for engineering students (5th-sem Mini Project).
The AI asks a question out loud, the student answers by voice, the answer is transcribed, an LLM scores it
against a fixed rubric, and the student gets feedback, a report, history and a skill-improvement graph.

Implements every item in the Mini Project scope (sections 17-20 of *Project Idea*).

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # then put your GROQ_API_KEY in .env
python run.py                                          # http://127.0.0.1:5000
```

Open it in **Chrome or Edge** (speech recognition works best there) and allow the microphone.
Without an API key everything still works, but answers are scored by an offline keyword evaluator
(clearly labelled in the UI and the report).

```bash
python -m pytest -q                      # 44 tests, no network or API key needed
python scripts/eval_consistency.py       # scoring consistency table for your results chapter
flask --app run seed-questions           # load new questions after editing interviewiq/data/questions.json
```

## How it maps to the document

| Doc module | Code |
|---|---|
| 1 Student management (register, login, history) | `auth.py`, `interview.py` |
| 2 Question management (50 questions, 8 subjects) | `data/questions.json`, `db.py`, `schema.sql` |
| 3 Interview engine (selection, sequence, timing) | `engine.py`, `interview.py` |
| 4 Voice processing (TTS / STT) | `static/js/interview.js` (browser Web Speech API) |
| 5 AI answer evaluation | `evaluator.py` |
| 6 Performance report | `reports.py`, `templates/report.html` |
| 7 Basic analytics + improvement graph | `reports.progress_series`, `static/js/progress.js` (Chart.js) |

Architecture: `Browser (TTS+STT)  →  Flask API  →  SQLite`, with the evaluator called from the answer endpoint.

## Answer evaluation (the AI part)

* **Rubric**: relevance, technical correctness, completeness, key concepts, clarity (each 0-10).
* **Grounded**: the prompt includes the question's expected concepts, reference answer and criteria.
* **Deterministic final score**: the LLM only scores the five parameters; the 0-10 score is computed in code
  from fixed weights (30/25/20/15/10), so the model cannot dictate the total.
* **Structured + validated**: strict JSON, clamped to 0-10, malformed output is rejected.
* **Low variance**: `temperature=0`, fixed prompt. Measure it with `scripts/eval_consistency.py`.
* **Speech-aware**: the prompt tells the model to ignore transcription errors and filler words.
* **Injection-resistant**: the student's answer is passed as untrusted data; instructions inside it are ignored.
* **Fallback**: if the API is down or unconfigured, a keyword/concept-coverage evaluator is used and
  the result is stored with `evaluator = fallback-heuristic`.
* **Editable transcript**: the student reviews and corrects the speech-to-text output before it is scored,
  so recognition mistakes (especially technical terms) don't unfairly lower the score.

## Security notes

Passwords are hashed (no plaintext), CSRF protection on every POST, per-user access checks on every interview
URL, answer text is never rendered as HTML, expected concepts / reference answers are never sent to the browser
before an answer is submitted, transcript length is capped, and the debugger is off unless `FLASK_DEBUG=1`.

## Known limitations (state these in the report; the doc's section 22 already does)

* Web Speech API recognition: Chrome/Edge only, needs internet (audio goes to the browser vendor's service),
  accuracy varies with accent, noise and microphone. Swap in Whisper later if needed.
* LLM scores are an aid, not ground truth; they can differ from a human examiner.
* Small question bank (50). Add more in `data/questions.json`.
* No resume analysis, adaptive follow-ups or institution analytics: reserved for the Major Project.
* SQLite is fine for a prototype; move to PostgreSQL/Supabase for a multi-user deployment.

## Project layout

```
run.py                     entry point
interviewiq/               app package (create_app, auth, interview, engine, evaluator, reports, db)
  data/questions.json      question bank with expected concepts + reference answers
  templates/, static/      UI (Bootstrap 5, Chart.js, vanilla JS)
scripts/                   eval_consistency.py + sample answers
tests/                     pytest suite (evaluator, engine, full Flask flow)
```
