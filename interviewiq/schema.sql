PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    department    TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    text                TEXT NOT NULL UNIQUE,
    subject             TEXT NOT NULL,
    topic               TEXT,
    difficulty          TEXT NOT NULL CHECK (difficulty IN ('basic', 'intermediate', 'advanced')),
    category            TEXT NOT NULL CHECK (category IN ('technical', 'hr')),
    expected_concepts   TEXT NOT NULL,           -- JSON list; "a|b" means a or b counts
    reference_answer    TEXT NOT NULL,
    evaluation_criteria TEXT
);

CREATE TABLE IF NOT EXISTS interviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category        TEXT NOT NULL,
    role            TEXT NOT NULL,
    difficulty      TEXT NOT NULL,
    skills          TEXT NOT NULL,               -- JSON list
    status          TEXT NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'completed')),
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    overall_score   REAL,                        -- percentage 0-100
    total_questions INTEGER NOT NULL
);

-- One row per question in an interview; answer/evaluation columns are NULL until answered.
CREATE TABLE IF NOT EXISTS interview_items (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_id          INTEGER NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    position              INTEGER NOT NULL,
    question_id           INTEGER NOT NULL REFERENCES questions(id),
    transcript            TEXT,
    duration_sec          INTEGER,
    score                 REAL,                  -- 0-10
    relevance             REAL,
    technical_correctness REAL,
    completeness          REAL,
    clarity               REAL,
    key_concepts          REAL,
    covered_concepts      TEXT,                  -- JSON list
    missing_concepts      TEXT,                  -- JSON list
    strengths             TEXT,                  -- JSON list
    improvements          TEXT,                  -- JSON list
    feedback              TEXT,
    suggestion            TEXT,
    evaluator             TEXT,                  -- which evaluator produced the score
    answered_at           TEXT,
    UNIQUE (interview_id, position)
);

CREATE INDEX IF NOT EXISTS idx_interviews_user ON interviews(user_id, status, finished_at);
CREATE INDEX IF NOT EXISTS idx_items_interview ON interview_items(interview_id, position);
CREATE INDEX IF NOT EXISTS idx_questions_pick ON questions(subject, difficulty);
