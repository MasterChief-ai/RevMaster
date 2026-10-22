import sqlite3
from collections import Counter

import signals as S

con = sqlite3.connect(S.DB)
rows = con.execute(
    """SELECT contact_id, needs_reply, conversation_closed
       FROM llm_signals WHERE status = 'accepted' AND rowid IN
       (SELECT MAX(rowid) FROM llm_signals GROUP BY contact_id) ORDER BY contact_id"""
).fetchall()

matrix = Counter()
suspect, odd = [], []
for cid, nr, closed in rows:
    thread = S.load_thread(con, cid)
    if not thread:
        continue
    last = thread[-1]
    matrix[(last["who"], nr)] += 1
    if last["who"] == "CUSTOMER" and nr == "no" and not closed:
        suspect.append((cid, last))
    if last["who"] == "US" and nr == "yes":
        odd.append((cid, last))
con.close()

print("Who wrote last / needs_reply -> count")
for k in sorted(matrix):
    print(f"  {k[0]:<9} {k[1]:<8} {matrix[k]}")

print("\nSUSPECT: customer wrote last, AI says no reply needed")
for cid, m in suspect:
    print(f"  {cid} | {m['date']} | {m['text'][:200]}")

print("\nODD: we wrote last, AI says a reply is needed")
for cid, m in odd:
    print(f"  {cid} | {m['date']} | {m['text'][:200]}")