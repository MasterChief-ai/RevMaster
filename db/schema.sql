-- Revenue Recovery Agent: local mirror of HubSpot (SQLite)
PRAGMA foreign_keys = ON;

CREATE TABLE contacts (
  id          INTEGER PRIMARY KEY,
  hubspot_id  TEXT UNIQUE NOT NULL,   -- natural key: lets re-syncs upsert, not duplicate
  name        TEXT,
  company     TEXT,
  email       TEXT,
  source      TEXT,                   -- e.g. brochure_request, website_form
  created_at  TEXT NOT NULL,          -- ISO 8601 UTC
  seed_batch  TEXT                    -- 'rra-v1' for synthetic rows, NULL for real ones
);

CREATE TABLE deals (
  id          INTEGER PRIMARY KEY,
  hubspot_id  TEXT UNIQUE NOT NULL,
  contact_id  INTEGER NOT NULL REFERENCES contacts(id),
  name        TEXT,
  amount_usd  REAL,                   -- NULL allowed: real CRMs have missing values
  stage       TEXT,
  created_at  TEXT NOT NULL,
  seed_batch  TEXT
);

CREATE TABLE activities (
  id            INTEGER PRIMARY KEY,
  hubspot_id    TEXT UNIQUE,          -- NULL for activities that exist only locally
  contact_id    INTEGER NOT NULL REFERENCES contacts(id),
  deal_id       INTEGER REFERENCES deals(id),
  type          TEXT NOT NULL CHECK (type IN ('email','note','call','meeting','task')),
  direction     TEXT CHECK (direction IN ('inbound','outbound')),  -- who acted: drives "ball in court"
  occurred_at   TEXT NOT NULL,
  body          TEXT,                 -- free text the LLM reads in Phase 3
  open_count    INTEGER DEFAULT 0,    -- local only: HubSpot's API can't fake open events
  due_at        TEXT,                 -- tasks only: when the follow-up was due
  completed     INTEGER DEFAULT 0,    -- tasks only: 1 = done
  seed_batch    TEXT
);

-- Ground truth lives apart so scoring code never touches it (prevents label leakage)
CREATE TABLE ground_truth (
  contact_id    INTEGER PRIMARY KEY REFERENCES contacts(id),
  archetype     TEXT NOT NULL,
  status        TEXT NOT NULL CHECK (status IN ('neglected','stalled','ok'))
);

-- Policy as data, not code: change a threshold without touching Python
-- Two clocks, because "who owes whom" decides which one applies:
--   neglect_after_bdays: business owes a reply/follow-up (ball with us) -> NEGLECTED
--   stalled_after_days:  we acted last, customer silent (ball with them) -> STALLED
CREATE TABLE tier_config (
  tier                TEXT PRIMARY KEY,
  min_value_usd       REAL NOT NULL,  -- inclusive lower bound
  neglect_after_bdays INTEGER NOT NULL,
  stalled_after_days  INTEGER NOT NULL
);
INSERT INTO tier_config VALUES
  ('low',    0,         10, 30),
  ('medium', 10000000,   5, 14),
  ('high',   50000000,   2,  7);

CREATE INDEX idx_activities_contact_time ON activities(contact_id, occurred_at);
