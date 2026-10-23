import argparse
import sqlite3

import signals as S

ap = argparse.ArgumentParser()
ap.add_argument("--id", type=int, required=True)
args = ap.parse_args()

con = sqlite3.connect(S.DB)
thread = S.load_thread(con, args.id)
sig = con.execute(
    """SELECT status, needs_reply, conversation_closed, buying_signals,
              evidence_quote FROM llm_signals
       WHERE contact_id = ? ORDER BY rowid DESC LIMIT 1""", (args.id,)).fetchone()
rule = con.execute(
    """SELECT tier, last_message_direction, days_since_last, rule_status, reason
       FROM rule_results WHERE contact_id = ?""", (args.id,)).fetchone()
con.close()

print(f"--- THREAD (contact {args.id}) ---")
for i, m in enumerate(thread, 1):
    print(f"[{i}] {m['who']} | {m['date']}\n{m['text']}\n")
print("--- RULES ---\ntier, last direction, days since, status, reason:", rule)
print("--- AI ---\nstatus, needs_reply, closed, signals, quote:", sig)