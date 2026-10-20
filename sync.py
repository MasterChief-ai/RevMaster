"""
Pull our records back from HubSpot into the local database (rra.db).

  python sync.py            copy HubSpot -> rra.db
  python sync.py --legacy   same, using HubSpot's older /crm/v3 addresses

Flow from now on:  seed.py stories -> push_to_hubspot.py -> HubSpot -> sync.py -> rra.db
"""
import argparse
import sqlite3
import sys

import push_to_hubspot as hs
from seed import CUSTOMERS

DB_FILE = "rra.db"

PROPS = {
    "contacts": ["email", "firstname", "lastname", "company", "createdate",
                 "rra_seed_key", "rra_seed_batch", "rra_source"],
    "deals": ["dealname", "amount", "dealstage", "createdate", "rra_seed_batch"],
    "emails": ["hs_timestamp", "hs_email_direction", "hs_email_subject", "hs_email_text"],
    "calls": ["hs_timestamp", "hs_call_direction", "hs_call_body"],
    "notes": ["hs_timestamp", "hs_note_body"],
    "tasks": ["hs_timestamp", "hs_task_subject", "hs_task_status"],
}
TYPE_NAME = {"emails": "email", "calls": "call", "notes": "note", "tasks": "task"}


def batch_read(client, kind, ids):
    """Ask HubSpot for many records at once (up to 100 per request)."""
    found = {}
    ids = [str(i) for i in ids]
    for start in range(0, len(ids), 100):
        chunk = ids[start:start + 100]
        r = client.call("POST", hs.objects_path(kind) + "/batch/read", {
            "properties": PROPS[kind],
            "inputs": [{"id": i} for i in chunk],
        })
        hs.must(r, f"read {kind} from HubSpot", ok=(200, 207))
        for rec in r.json().get("results", []):
            found[str(rec["id"])] = rec.get("properties", {})
    missing = [i for i in ids if i not in found]
    if missing:
        print(f"  WARNING: {len(missing)} {kind} not found in HubSpot (deleted?): {missing[:5]}")
    return found


def direction_of(kind, props, fallback):
    if kind == "emails":
        return "inbound" if props.get("hs_email_direction") == "INCOMING_EMAIL" else "outbound"
    if kind == "calls":
        return "inbound" if props.get("hs_call_direction") == "INBOUND" else "outbound"
    return fallback   # notes and tasks have no direction in HubSpot, so we use what we wrote down


def body_of(kind, props):
    return {"emails": props.get("hs_email_text"), "calls": props.get("hs_call_body"),
            "notes": props.get("hs_note_body"), "tasks": props.get("hs_task_subject")}[kind]


def run_sync(client, con):
    pmap = hs.load_map()
    entries = {k: v for k, v in pmap["customers"].items() if v.get("contact_id") and v.get("deal_id")}
    if not entries:
        sys.exit("push_map.json is missing or empty. Run push_to_hubspot.py first.")
    labels = {c["key"]: (c["archetype"], c["status"]) for c in CUSTOMERS}

    print("Reading from HubSpot...")
    contacts = batch_read(client, "contacts", [e["contact_id"] for e in entries.values()])
    deals = batch_read(client, "deals", [e["deal_id"] for e in entries.values()])
    acts = {}
    for kind in TYPE_NAME:
        ids = [a["id"] for e in entries.values() for a in e["activities"] if a["object"] == kind]
        acts[kind] = batch_read(client, kind, ids) if ids else {}

    print("Rebuilding the local copy...")
    con.execute("DELETE FROM ground_truth WHERE contact_id IN (SELECT id FROM contacts WHERE seed_batch = ?)", (hs.BATCH,))
    con.execute("DELETE FROM activities WHERE seed_batch = ?", (hs.BATCH,))
    con.execute("DELETE FROM deals WHERE seed_batch = ?", (hs.BATCH,))
    con.execute("DELETE FROM contacts WHERE seed_batch = ?", (hs.BATCH,))

    direction_mismatches = 0
    for key, e in entries.items():
        cp = contacts.get(str(e["contact_id"]))
        dp = deals.get(str(e["deal_id"]))
        if cp is None or dp is None:
            print(f"  skipping {key}: contact or deal missing in HubSpot")
            continue
        name = f"{cp.get('firstname') or ''} {cp.get('lastname') or ''}".strip()
        cur = con.execute(
            "INSERT INTO contacts (hubspot_id, name, company, email, source, created_at, seed_batch) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(e["contact_id"]), name, cp.get("company"), cp.get("email"), cp.get("rra_source"),
             cp.get("createdate"), cp.get("rra_seed_batch") or hs.BATCH))
        contact_id = cur.lastrowid
        cur = con.execute(
            "INSERT INTO deals (hubspot_id, contact_id, name, amount_usd, stage, created_at, seed_batch) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(e["deal_id"]), contact_id, dp.get("dealname"),
             float(dp["amount"]) if dp.get("amount") else None,
             dp.get("dealstage"), dp.get("createdate"), hs.BATCH))
        deal_id = cur.lastrowid

        for a in e["activities"]:
            p = acts[a["object"]].get(str(a["id"]))
            if p is None:
                continue
            kind = a["object"]
            direction = direction_of(kind, p, a["direction"])
            if direction != a["direction"]:
                direction_mismatches += 1
            is_task = kind == "tasks"
            con.execute(
                "INSERT INTO activities (hubspot_id, contact_id, deal_id, type, direction, occurred_at, body, "
                "open_count, due_at, completed, seed_batch) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"{kind}:{a['id']}",            # IDs repeat across types, so we add the type
                 contact_id, deal_id, TYPE_NAME[kind], direction, p.get("hs_timestamp"),
                 body_of(kind, p), a["opens"],
                 p.get("hs_timestamp") if is_task else None,
                 int(p.get("hs_task_status") == "COMPLETED") if is_task else 0,
                 hs.BATCH))

        archetype, status = labels.get(cp.get("rra_seed_key"), (None, None))
        if status is None:
            print(f"  WARNING: no label for {name} (key {cp.get('rra_seed_key')})")
            continue
        con.execute("INSERT INTO ground_truth (contact_id, archetype, status) VALUES (?, ?, ?)",
                    (contact_id, archetype, status))
    con.commit()
    return direction_mismatches


def report(con, direction_mismatches):
    q = lambda sql: con.execute(sql).fetchall()
    print("\nLocal copy now holds:")
    print("  contacts:", q("SELECT COUNT(*) FROM contacts")[0][0])
    print("  deals:", q("SELECT COUNT(*) FROM deals")[0][0])
    print("  activities:", q("SELECT type, COUNT(*) FROM activities GROUP BY type"))
    print("  labels:", q("SELECT status, COUNT(*) FROM ground_truth GROUP BY status"))
    expected = sum(len(c["events"]) for c in CUSTOMERS)
    have = q("SELECT COUNT(*) FROM activities")[0][0]
    print(f"\nCheck 1: activities expected {expected}, have {have} -> {'OK' if expected == have else 'MISMATCH'}")
    print(f"Check 2: direction in HubSpot vs what we wrote down, mismatches: {direction_mismatches}")
    print("\nJohn's timeline (from the local copy):")
    for row in q("SELECT a.occurred_at, a.direction, a.type, a.open_count, a.body FROM activities a "
                 "JOIN contacts c ON c.id = a.contact_id WHERE c.email = 'john.stewart@example.com' "
                 "ORDER BY a.occurred_at"):
        print(" ", row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--legacy", action="store_true")
    args = ap.parse_args()
    hs.LEGACY = args.legacy
    client = hs.Client(hs.load_token())
    con = sqlite3.connect(DB_FILE)
    con.execute("PRAGMA foreign_keys = ON")
    report(con, run_sync(client, con))


if __name__ == "__main__":
    main()