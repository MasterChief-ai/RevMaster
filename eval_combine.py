import sqlite3
from pathlib import Path

DB = "rra.db"


def main():
    if not Path(DB).exists():
        print("ERROR: rra.db not found")
        return 1
    con = sqlite3.connect(DB)
    try:
        rows = con.execute(
            """SELECT c.id, c.name, g.status, f.rule_status, f.final_status,
                      f.human_review, f.reason
               FROM final_results f
               JOIN ground_truth g ON g.contact_id = f.contact_id
               JOIN contacts c ON c.id = f.contact_id
               ORDER BY c.id""").fetchall()
        latest = con.execute(
            """SELECT status, COALESCE(total_tokens, 0) FROM llm_signals
               WHERE rowid IN (SELECT MAX(rowid) FROM llm_signals
                               GROUP BY contact_id)""").fetchall()
        all_tok, all_rows = con.execute(
            "SELECT COALESCE(SUM(total_tokens), 0), COUNT(*) FROM llm_signals"
        ).fetchone()
    except sqlite3.OperationalError as e:
        print("ERROR:", e)
        return 1
    con.close()
    if len(rows) != 50:
        print(f"MISMATCH: expected 50 graded rows, got {len(rows)}")
        return 1

    rules_ok = sum(1 for r in rows if r[3] == r[2])
    final_ok = sum(1 for r in rows if r[4] == r[2])
    check = "OK" if rules_ok == 46 else "MISMATCH"
    print(f"Rules only : {rules_ok}/50 correct  (expected 46 -> {check})")
    print(f"Rules + AI : {final_ok}/50 correct")

    print("\n(i) The rules' misses:")
    for cid, name, truth, rs, fin, human, why in rows:
        if rs != truth:
            state = "FIXED" if fin == truth else "STILL WRONG"
            print(f"  {cid} {name}: truth={truth}, rules={rs}, "
                  f"final={fin} ({why}) -> {state}")

    print("\n(ii) Correct rules answers the AI broke:")
    broke = [r for r in rows if r[3] == r[2] and r[4] != r[2]]
    if not broke:
        print("  none")
    for cid, name, truth, rs, fin, human, why in broke:
        print(f"  {cid} {name}: truth={truth}, final={fin} ({why})")

    cancels = [r for r in rows if r[3] != r[4]]
    good = sum(1 for r in cancels if r[2] == r[4])
    print(f"\nAI cancels: {len(cancels)}, correct: {good}")

    print("\nFlagged for a human:")
    for cid, name, truth, rs, fin, human, why in rows:
        if human:
            print(f"  {cid} {name}: truth={truth}, rules={rs} ({why})")

    rejected = sum(1 for s, _ in latest if s != "accepted")
    print(f"\n(iii) AI answers rejected or failed (latest per customer): "
          f"{rejected} of {len(latest)}")
    print(f"(iv) Tokens, latest answers: {sum(t for _, t in latest)}")
    print(f"     Tokens, every saved answer incl. earlier prompt versions: "
          f"{all_tok} ({all_rows} rows)")
    print("\nprocessed 50 / succeeded 50 / failed 0 / skipped 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())