import sqlite3
from collections import Counter
from pathlib import Path

DB = "rra.db"
STATUSES = {"neglected", "stalled", "ok"}
EXPECTED_RULES = {"neglected": 21, "stalled": 9, "ok": 20}

SCHEMA = """CREATE TABLE IF NOT EXISTS final_results (
  contact_id INTEGER PRIMARY KEY, rule_status TEXT, final_status TEXT,
  human_review INTEGER, reason TEXT)"""


def decide(rule_status, direction, overdue_task, llm):
    """llm is None or a dict: status, needs_reply, closed.
    Returns (final_status, human_review, reason). The AI can only cancel."""
    if rule_status == "ok":
        return "ok", 0, "rules_ok"
    if llm is None or llm["status"] != "accepted":
        return rule_status, 1, "llm_unavailable"
    if llm["needs_reply"] == "unclear":
        return rule_status, 1, "llm_unclear"
    if llm["closed"]:
        return "ok", 0, "ai_cancel_closed"
    if (rule_status == "neglected" and llm["needs_reply"] == "no"
            and direction == "inbound" and not overdue_task):
        return "ok", 0, "ai_cancel_no_reply_needed"
    return rule_status, 0, "rules_kept"


def main():
    if not Path(DB).exists():
        print("ERROR: rra.db not found")
        return 1
    con = sqlite3.connect(DB)
    try:
        rules = con.execute(
            """SELECT contact_id, rule_status, last_message_direction,
                      overdue_task FROM rule_results ORDER BY contact_id"""
        ).fetchall()
        sigs = {r[0]: {"status": r[1], "needs_reply": r[2], "closed": r[3]}
                for r in con.execute(
                    """SELECT contact_id, status, needs_reply,
                              conversation_closed FROM llm_signals
                       WHERE rowid IN (SELECT MAX(rowid) FROM llm_signals
                                       GROUP BY contact_id)""")}
    except sqlite3.OperationalError as e:
        print("ERROR:", e)
        return 1
    if not rules:
        print("ERROR: rule_results is empty - run python rules.py first")
        return 1

    values = {r[1] for r in rules}
    dirs = {r[2] for r in rules}
    print("rule_status values:", sorted(map(str, values)))
    print("direction values:  ", sorted(map(str, dirs)))
    if not values <= STATUSES or not dirs <= {"inbound", "outbound", None}:
        print("MISMATCH: unexpected values, tell me what you see above")
        return 1

    con.execute(SCHEMA)
    before, after = Counter(), Counter()
    reasons, humans, changed = Counter(), [], []
    for cid, rs, direction, overdue in rules:
        final, human, why = decide(rs, direction, overdue, sigs.get(cid))
        before[rs] += 1
        after[final] += 1
        reasons[why] += 1
        if human:
            humans.append(cid)
        if final != rs:
            changed.append((cid, rs, why))
        con.execute("INSERT OR REPLACE INTO final_results VALUES (?,?,?,?,?)",
                    (cid, rs, final, human, why))
    con.commit()
    con.close()

    print("\nRules only:      ", dict(before))
    ok_check = "OK" if dict(before) == EXPECTED_RULES else "MISMATCH"
    print(f"Expected rules:   {EXPECTED_RULES} -> {ok_check}")
    print("Rules + AI:      ", dict(after))
    print("Reasons:         ", dict(reasons))
    print(f"\nCancelled by AI ({len(changed)}):")
    for cid, rs, why in changed:
        print(f"  {cid}: {rs} -> ok ({why})")
    print(f"\nFlagged for a human ({len(humans)}): {humans}")
    print(f"\nprocessed {len(rules)} / succeeded {len(rules)} / "
          f"failed 0 / skipped 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())