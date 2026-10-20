import sqlite3
from datetime import datetime, timedelta, timezone

con = sqlite3.connect("rra.db")
con.execute("PRAGMA foreign_keys = ON")  # SQLite enforces foreign keys per connection

now = datetime.now(timezone.utc)
def ago(days):
    return (now - timedelta(days=days)).isoformat()

cur = con.execute(
    "INSERT INTO contacts (hubspot_id, name, email, source, created_at, seed_batch) "
    "VALUES (?, ?, ?, ?, ?, ?)",
    ("local-test-1", "Test Lead", "test@example.com", "brochure_request", ago(14), "rra-v1"),
)
contact_id = cur.lastrowid  # the id SQLite just assigned; child rows need it

cur = con.execute(
    "INSERT INTO deals (hubspot_id, contact_id, name, amount_usd, stage, created_at, seed_batch) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)",
    ("local-deal-1", contact_id, "Test Tower", 60_000_000, "qualified", ago(14), "rra-v1"),
)

con.execute(
    "INSERT INTO activities (contact_id, deal_id, type, direction, occurred_at, body, seed_batch) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)",
    (contact_id, cur.lastrowid, "email", "inbound", ago(9), "Can you share financing options?", "rra-v1"),
)

con.execute(
    "INSERT INTO ground_truth (contact_id, archetype, status) VALUES (?, ?, ?)",
    (contact_id, "hot_but_ghosted", "neglected"),
)

con.commit()  # nothing is saved to disk until this line runs
print(con.execute("SELECT contact_id, direction, occurred_at, body FROM activities").fetchall())
