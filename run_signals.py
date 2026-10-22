import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import time

from dotenv import load_dotenv

import signals as S

SCHEMA = """CREATE TABLE IF NOT EXISTS llm_signals (
  contact_id INTEGER NOT NULL, key_hash TEXT NOT NULL, model TEXT NOT NULL,
  status TEXT NOT NULL, reason TEXT,
  needs_reply TEXT, conversation_closed INTEGER,
  buying_signals TEXT, evidence_quote TEXT,
  prompt_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (contact_id, key_hash))"""


def make_hash(thread, model):
    payload = json.dumps([model, S.PROMPT_HEAD, thread], sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model")
    args = ap.parse_args()

    load_dotenv()
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("ERROR: GEMINI_API_KEY is missing from .env")
        return 1
    try:
        cfg = json.loads(Path("llm_config.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        print("ERROR: llm_config.json not found")
        return 1
    model = args.model or cfg.get("model")
    if not model:
        print('ERROR: set "model" in llm_config.json (or pass --model)')
        return 1
    if not Path(S.DB).exists():
        print("ERROR: rra.db not found")
        return 1

    con = sqlite3.connect(S.DB)
    con.execute(SCHEMA)
    con.commit()
    ids = [r[0] for r in con.execute("SELECT id FROM contacts ORDER BY id")]
    if args.limit:
        ids = ids[:args.limit]
    if not ids:
        print("ERROR: no contacts in rra.db")
        return 1

    c = {"processed": 0, "ok": 0, "failed": 0, "skipped": 0, "cached": 0}
    tok = [0, 0, 0]
    print(f"Model: {model}")
    for cid in ids:
        c["processed"] += 1
        thread = S.load_thread(con, cid)
        if not thread:
            c["skipped"] += 1
            print(f"{cid:>3} | skipped (no messages)")
            continue
        h = make_hash(thread, model)
        row = con.execute(
            """SELECT status, reason, needs_reply, conversation_closed,
                      buying_signals FROM llm_signals
               WHERE contact_id = ? AND key_hash = ?""", (cid, h)).fetchone()
        if row:
            c["cached"] += 1
            status, reason, nr, closed, sigs = row
            c["ok" if status == "accepted" else "failed"] += 1
            print(f"{cid:>3} | cached | {status} | {nr} | closed={closed} "
                  f"| {sigs} | {reason or ''}")
            continue
        time.sleep(4)  # avoid rate limit
        try:
            raw, usage = S.call_gemini(model, key, S.build_prompt(thread))
        except RuntimeError as e:
            msg = str(e).replace(key, "[REDACTED]")
            S.log_error(f"contact {cid}: {msg}")
            c["failed"] += 1
            print(f"{cid:>3} | ERROR (not cached) | {msg[:120]}")
            continue
        pt, ot, tt = (usage.get(k) or 0 for k in
                      ("promptTokenCount", "candidatesTokenCount",
                       "totalTokenCount"))
        tok[0] += pt
        tok[1] += ot
        tok[2] += tt
        sig, why = S.parse_answer(raw, thread)
        if sig is None:
            status, reason, vals = "rejected", why, (None, None, None, None)
            c["failed"] += 1
        else:
            status, reason = "accepted", None
            vals = (sig.needs_reply, int(sig.conversation_closed),
                    json.dumps(sig.buying_signals), sig.evidence_quote)
            c["ok"] += 1
        con.execute(
            """INSERT OR REPLACE INTO llm_signals
               (contact_id, key_hash, model, status, reason, needs_reply,
                conversation_closed, buying_signals, evidence_quote,
                prompt_tokens, output_tokens, total_tokens)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, h, model, status, reason, *vals, pt, ot, tt))
        con.commit()
        print(f"{cid:>3} | {status} | {vals[0]} | closed={vals[1]} "
              f"| {vals[2]} | {tt} tok | {reason or ''}")
    con.close()

    print(f"\nTokens this run: prompt {tok[0]}, output {tok[1]}, total {tok[2]}")
    print(f"processed {c['processed']} / succeeded {c['ok']} / "
          f"failed {c['failed']} / skipped {c['skipped']}   "
          f"(served from cache: {c['cached']})")
    if args.limit is None:
        print("Customers processed:",
              "OK" if c["processed"] == 50 else "MISMATCH (expected 50)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())