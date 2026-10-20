"""
Phase 2: the rules engine. No AI in here, just counting and if/else.

  python rules.py          pretend "today" is the day we pushed to HubSpot
  python rules.py --now    use the real clock instead

For every customer it works out:
  - who spoke last (us or them)
  - how long ago that was (calendar days and business days)
  - the deal tier (low / medium / high) from the deal amount
  - whether we have an overdue follow-up task
...then applies the two-clock rule and saves the verdict in a table called rule_results.
Finally it grades itself against the answer key (ground_truth).
"""
import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

DB_FILE = "rra.db"
MESSAGE_TYPES = ("email", "call", "note")   # tasks are plans, not messages

SAVE_TABLE = """
CREATE TABLE IF NOT EXISTS rule_results (
  contact_id              INTEGER PRIMARY KEY REFERENCES contacts(id),
  as_of                   TEXT,
  tier                    TEXT,
  last_message_direction  TEXT,
  last_message_at         TEXT,
  days_since_last         INTEGER,
  business_days_since     INTEGER,
  overdue_task            INTEGER,
  rule_status             TEXT,
  reason                  TEXT
)"""


def parse(ts):
    d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def business_days(start, end):
    """Weekdays that passed after 'start' up to 'end'. Saturday and Sunday don't count."""
    d, n = start.date(), 0
    while d < end.date():
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def pick_tier(amount, tiers):
    """tiers is sorted biggest minimum first, so the first one the amount clears wins."""
    if amount is None:
        return "medium"          # unknown value: don't ignore it, don't over-panic either
    for name, minimum, _, _ in tiers:
        if amount >= minimum:
            return name
    return tiers[-1][0]


def judge(acts, as_of, tiers, tier):
    """acts: this customer's activities, oldest first. Returns the features and the verdict."""
    cfg = {t[0]: t for t in tiers}[tier]
    neglect_after, stalled_after = cfg[2], cfg[3]

    messages = [a for a in acts if a["type"] in MESSAGE_TYPES]
    last = messages[-1] if messages else None
    overdue = any(a["type"] == "task" and not a["completed"] and a["due_at"]
                  and parse(a["due_at"]) < as_of for a in acts)

    f = {"last_dir": None, "last_at": None, "days": None, "bdays": None, "overdue": int(overdue)}
    if last:
        f["last_dir"] = last["direction"]
        f["last_at"] = last["occurred_at"]
        f["days"] = (as_of - parse(last["occurred_at"])).days
        f["bdays"] = business_days(parse(last["occurred_at"]), as_of)

    if overdue:
        return f, "neglected", "OVERDUE_FOLLOWUP_TASK"
    if not last or f["last_dir"] is None:
        return f, "ok", "NO_MESSAGE_TO_JUDGE"
    if f["last_dir"] == "inbound":
        if f["bdays"] > neglect_after:
            return f, "neglected", "THEY_WROTE_LAST_AND_WE_WAITED_TOO_LONG"
        return f, "ok", "THEY_WROTE_LAST_STILL_IN_REPLY_WINDOW"
    if f["days"] > stalled_after:
        return f, "stalled", "WE_WROTE_LAST_AND_THEY_WENT_QUIET"
    return f, "ok", "WE_WROTE_LAST_STILL_IN_WAIT_WINDOW"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", action="store_true", help="use the real clock")
    args = ap.parse_args()

    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    con.execute(SAVE_TABLE)

    tiers = [tuple(r) for r in con.execute(
        "SELECT tier, min_value_usd, neglect_after_bdays, stalled_after_days "
        "FROM tier_config ORDER BY min_value_usd DESC")]

    if args.now:
        as_of = datetime.now(timezone.utc)
    else:
        newest = con.execute("SELECT MAX(created_at) FROM contacts").fetchone()[0]
        if not newest:
            sys.exit("No contacts in rra.db. Run sync.py first.")
        as_of = parse(newest)
    print(f"Pretending today is: {as_of:%Y-%m-%d %H:%M} UTC "
          f"({'real clock' if args.now else 'the day we pushed to HubSpot'})")

    contacts = con.execute(
        "SELECT c.id, c.name, (SELECT MAX(amount_usd) FROM deals WHERE contact_id = c.id) AS amount "
        "FROM contacts c").fetchall()

    results = {}
    for c in contacts:
        acts = [dict(a) for a in con.execute(
            "SELECT id, type, direction, occurred_at, due_at, completed FROM activities "
            "WHERE contact_id = ?", (c["id"],))]
        acts.sort(key=lambda a: (parse(a["occurred_at"]), a["id"]))   # ties: the later insert is later
        tier = pick_tier(c["amount"], tiers)
        f, status, reason = judge(acts, as_of, tiers, tier)
        results[c["id"]] = (c["name"], tier, f, status, reason)
        con.execute(
            "INSERT OR REPLACE INTO rule_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (c["id"], as_of.isoformat(), tier, f["last_dir"], f["last_at"], f["days"],
             f["bdays"], f["overdue"], status, reason))
    con.commit()

    # ---- grade ourselves against the answer key ----
    truth = {r["contact_id"]: (r["status"], r["archetype"]) for r in
             con.execute("SELECT contact_id, status, archetype FROM ground_truth")}
    labels = ("neglected", "stalled", "ok")
    matrix = {t: {p: 0 for p in labels} for t in labels}
    wrong = []
    for cid, (name, tier, f, status, reason) in results.items():
        if cid not in truth:
            continue
        t, archetype = truth[cid]
        matrix[t][status] += 1
        if t != status:
            wrong.append((name, archetype, t, status, reason, tier, f))

    graded = sum(sum(row.values()) for row in matrix.values())
    right = sum(matrix[l][l] for l in labels)
    print(f"\nRules vs answer key: {right} of {graded} correct\n")
    print(f"{'truth \\ rules said':<20}" + "".join(f"{p:>11}" for p in labels))
    for t in labels:
        print(f"{t:<20}" + "".join(f"{matrix[t][p]:>11}" for p in labels))

    if wrong:
        print(f"\nThe {len(wrong)} it got wrong:")
        for name, archetype, t, status, reason, tier, f in wrong:
            print(f"  {name} ({archetype}, {tier} tier)")
            print(f"    truth: {t}   rules said: {status}   because {reason}")
            print(f"    last message: {f['last_dir']}, {f['days']} days ago ({f['bdays']} business days)")
    print("\nVerdicts saved in the rule_results table.")


if __name__ == "__main__":
    main()