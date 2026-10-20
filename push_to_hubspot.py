"""
Push the fake customers from seed.py into HubSpot.

  python push_to_hubspot.py --check      test the connection (read-only, changes nothing)
  python push_to_hubspot.py --dry-run    show what WOULD be sent, send nothing
  python push_to_hubspot.py --one        push only the first customer (John) as a test
  python push_to_hubspot.py              push everyone (skips anyone already pushed)
  python push_to_hubspot.py --wipe       delete everything this script created

Add --legacy to any command to use HubSpot's older /crm/v3 addresses.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

from seed import CUSTOMERS, BATCH

API_VERSION = "2026-09"          # HubSpot names API versions by date
BASE = "https://api.hubapi.com"
MAP_FILE = "push_map.json"       # remembers what we created, so we can wipe or resume
SLEEP = 0.15                     # free accounts allow ~100 requests per 10 seconds
REP_EMAIL = "sales@rra-demo.example"
LEGACY = False

# HubSpot's official default association IDs: (activity -> contact, activity -> deal)
ACTIVITY_ASSOC = {
    "emails": (198, 210),
    "calls": (194, 206),
    "notes": (202, 214),
    "tasks": (204, 216),
}
DEAL_TO_CONTACT = 3

CONTACT_PROPS = [
    ("rra_seed_batch", "RRA Seed Batch"),
    ("rra_seed_key", "RRA Seed Key"),
    ("rra_source", "RRA Source"),
]
DEAL_PROPS = [("rra_seed_batch", "RRA Seed Batch")]


# ---------- addresses (the one place that knows old vs new) ----------
def objects_path(kind):
    return f"/crm/v3/objects/{kind}" if LEGACY else f"/crm/objects/{API_VERSION}/{kind}"


def properties_path(kind):
    return f"/crm/v3/properties/{kind}" if LEGACY else f"/crm/properties/{API_VERSION}/{kind}"


def pipelines_path(kind):
    return f"/crm/v3/pipelines/{kind}" if LEGACY else f"/crm/pipelines/{API_VERSION}/{kind}"


# ---------- token + client ----------
def load_token():
    if os.path.exists(".env"):
        for line in open(".env", encoding="utf-8-sig"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    for name in ("HUBSPOT_TOKEN", "Access_Token", "ACCESS_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    sys.exit("No token found. Put HUBSPOT_TOKEN=your-token in a .env file next to this script.")


class Client:
    def __init__(self, token):
        import requests
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def call(self, method, path, body=None):
        r = None
        for attempt in range(5):
            r = self.session.request(method, BASE + path, json=body, timeout=30)
            time.sleep(SLEEP)
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("Retry-After", 2 ** attempt))
                print(f"  HubSpot said {r.status_code}. Waiting {wait:.0f}s, then retrying.")
                time.sleep(wait)
                continue
            return r
        return r


def must(r, what, ok=(200, 201, 204)):
    if r.status_code not in ok:
        sys.exit(f"\nFAILED: {what}\nStatus {r.status_code}\n{r.text[:600]}")
    return r


# ---------- helpers ----------
def iso(now, days_ago):
    return (now - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def split_name(full):
    parts = full.rsplit(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (full, "")


def email_for(c):
    return c["name"].lower().replace("'", "").replace(" ", ".") + "@example.com"


def assoc(record_id, type_id):
    rid = int(record_id) if str(record_id).isdigit() else record_id
    return {"to": {"id": rid},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": type_id}]}


def activity_request(e, contact_email, now):
    """Turn one story event into (HubSpot object type, properties)."""
    outbound = e["who"] == "us"
    text = e["text"]
    ts = iso(now, e["days_ago"])
    if e["type"] == "email":
        sender = REP_EMAIL if outbound else contact_email
        receiver = contact_email if outbound else REP_EMAIL
        headers = {"from": {"email": sender}, "to": [{"email": receiver}], "cc": [], "bcc": []}
        return "emails", {
            "hs_timestamp": ts,
            "hs_email_direction": "EMAIL" if outbound else "INCOMING_EMAIL",
            "hs_email_status": "SENT",
            "hs_email_subject": text[:60],
            "hs_email_text": text,
            "hs_email_headers": json.dumps(headers),
        }
    if e["type"] == "call":
        return "calls", {
            "hs_timestamp": ts,
            "hs_call_title": text[:60],
            "hs_call_body": text,
            "hs_call_direction": "OUTBOUND" if outbound else "INBOUND",
            "hs_call_status": "COMPLETED",
        }
    if e["type"] == "note":
        return "notes", {"hs_timestamp": ts, "hs_note_body": text}
    if e["type"] == "task":
        return "tasks", {   # for tasks, hs_timestamp means the DUE date
            "hs_timestamp": iso(now, e["due"]),
            "hs_task_subject": text,
            "hs_task_status": "COMPLETED" if e["done"] else "NOT_STARTED",
        }
    raise ValueError(f"unknown event type {e['type']}")


# ---------- one-time setup ----------
def ensure_properties(client):
    for kind, props in (("contacts", CONTACT_PROPS), ("deals", DEAL_PROPS)):
        group = "contactinformation" if kind == "contacts" else "dealinformation"
        for name, label in props:
            r = client.call("POST", properties_path(kind), {
                "name": name, "label": label, "type": "string",
                "fieldType": "text", "groupName": group,
            })
            if r.status_code in (200, 201):
                print(f"  created {kind} property {name}")
            elif r.status_code == 409:
                print(f"  {kind} property {name} already exists")
            else:
                must(r, f"create {kind} property {name} (needs the crm.schemas.{kind}.write scope)")


def get_legal_basis(client):
    """Accounts with GDPR features on (common on the EU data center) require hs_legal_basis
    on every new contact. Its allowed values differ per account, so we read them."""
    fallback = "Legitimate interest \u2013 prospect/lead"
    r = client.call("GET", properties_path("contacts") + "/hs_legal_basis")
    if r.status_code != 200:
        print(f"  could not read hs_legal_basis options ({r.status_code}); using the default value")
        return fallback
    options = r.json().get("options", [])
    for o in options:
        label = o.get("label", "").lower()
        if "legitimate" in label and ("lead" in label or "prospect" in label):
            return o["value"]
    for o in options:
        if "legitimate" in o.get("label", "").lower():
            return o["value"]
    return fallback


def get_stages(client):
    r = must(client.call("GET", pipelines_path("deals")), "read deal pipelines")
    pipelines = r.json()["results"]
    pipeline = next((p for p in pipelines if p["id"] == "default"), pipelines[0])
    stages = sorted(pipeline["stages"], key=lambda s: int(s.get("displayOrder", 0)))

    def closed(s):
        return str(s.get("metadata", {}).get("isClosed", "false")).lower() == "true"

    def lost(s):
        return closed(s) and float(s.get("metadata", {}).get("probability", 1)) == 0.0

    open_stages = [s for s in stages if not closed(s)]
    lost_stage = next((s for s in stages if lost(s)), stages[-1])
    pick = lambda i: open_stages[min(i, len(open_stages) - 1)]["id"]
    return {
        "pipeline": pipeline["id"],
        "map": {
            "new": pick(0), "qualified": pick(1), "proposal_sent": pick(2),
            "negotiation": pick(3), "closed_lost": lost_stage["id"],
        },
    }


# ---------- the push ----------
def load_map():
    if os.path.exists(MAP_FILE):
        return json.load(open(MAP_FILE, encoding="utf-8"))
    return {"batch": BATCH, "customers": {}}


def save_map(pmap):
    json.dump(pmap, open(MAP_FILE, "w", encoding="utf-8"), indent=2)


def push_customer(client, c, stages, now, pmap):
    email = email_for(c)
    first, last = split_name(c["name"])
    entry = {"contact_id": None, "deal_id": None, "activities": []}

    contact_props = {
        "email": email, "firstname": first, "lastname": last, "company": c["company"],
        "rra_seed_batch": BATCH, "rra_seed_key": c["key"], "rra_source": c["source"],
    }
    if stages.get("legal_basis"):
        contact_props["hs_legal_basis"] = stages["legal_basis"]
    r = client.call("POST", objects_path("contacts"), {"properties": contact_props})
    if r.status_code == 409:   # HubSpot already has this email: reuse that contact
        m = re.search(r"Existing ID:\s*(\d+)", r.text)
        if not m:
            must(r, f"create contact {c['name']}")
        entry["contact_id"] = m.group(1)
        print(f"  contact for {c['name']} already existed, reusing it")
    else:
        must(r, f"create contact {c['name']}")
        entry["contact_id"] = r.json()["id"]
    pmap["customers"][c["key"]] = entry
    save_map(pmap)

    r = must(client.call("POST", objects_path("deals"), {
        "properties": {
            "dealname": f"{c['company']} deal", "amount": str(c["deal_value"]),
            "pipeline": stages["pipeline"], "dealstage": stages["map"][c["stage"]],
            "rra_seed_batch": BATCH,
        },
        "associations": [assoc(entry["contact_id"], DEAL_TO_CONTACT)],
    }), f"create deal for {c['name']}")
    entry["deal_id"] = r.json()["id"]
    save_map(pmap)

    for e in sorted(c["events"], key=lambda ev: -ev["days_ago"]):
        kind, props = activity_request(e, email, now)
        to_contact, to_deal = ACTIVITY_ASSOC[kind]
        r = must(client.call("POST", objects_path(kind), {
            "properties": props,
            "associations": [assoc(entry["contact_id"], to_contact), assoc(entry["deal_id"], to_deal)],
        }), f"create {kind[:-1]} for {c['name']}")
        entry["activities"].append({
            "object": kind, "id": r.json()["id"],
            "direction": "outbound" if e["who"] == "us" else "inbound",
            "opens": e["opens"],   # HubSpot can't fake opens, so we remember them here
        })
        save_map(pmap)


def run_push(client, customers, now):
    print("Setting up custom properties...")
    ensure_properties(client)
    stages = get_stages(client)
    stages["legal_basis"] = get_legal_basis(client)
    print(f"Deal stages mapped: {stages['map']}")
    print(f"Legal basis value: {stages['legal_basis']}")
    pmap = load_map()
    for i, c in enumerate(customers, 1):
        if c["key"] in pmap["customers"] and pmap["customers"][c["key"]].get("activities") is not None \
                and pmap["customers"][c["key"]].get("deal_id"):
            print(f"[{i}/{len(customers)}] {c['name']}: already pushed, skipping")
            continue
        print(f"[{i}/{len(customers)}] {c['name']}")
        push_customer(client, c, stages, now, pmap)
    print(f"\nDone. HubSpot IDs saved in {MAP_FILE}.")


def wipe(client):
    pmap = load_map()
    if not pmap["customers"]:
        print("Nothing to wipe.")
        return
    for key, entry in pmap["customers"].items():
        print(f"Deleting {key}")
        for a in entry.get("activities", []):
            client.call("DELETE", f"{objects_path(a['object'])}/{a['id']}")
        if entry.get("deal_id"):
            client.call("DELETE", f"{objects_path('deals')}/{entry['deal_id']}")
        if entry.get("contact_id"):
            client.call("DELETE", f"{objects_path('contacts')}/{entry['contact_id']}")
    os.remove(MAP_FILE)
    print("Wiped.")


# ---------- safe commands ----------
def dry_run(customers, now):
    total = 0
    for c in customers:
        total += 2 + len(c["events"])
        print(f"{c['name']:<20} {c['company']:<32} {len(c['events'])} activities")
    print(f"\nWould create {len(customers)} contacts, {len(customers)} deals, "
          f"{total - 2 * len(customers)} activities ({total} requests).")
    c = customers[0]
    print(f"\nSample: first activity for {c['name']}:")
    kind, props = activity_request(sorted(c["events"], key=lambda e: -e["days_ago"])[0], email_for(c), now)
    print(kind, json.dumps(props, indent=2))


def check(client):
    global LEGACY
    original = LEGACY
    for mode in (False, True):
        LEGACY = mode
        label = "legacy /crm/v3" if mode else f"dated {API_VERSION}"
        print(f"\n--- {label} ---")
        tests = [
            ("read contacts", objects_path("contacts") + "?limit=1"),
            ("read contact properties", properties_path("contacts")),
            ("read deal pipelines", pipelines_path("deals")),
        ]
        for name, path in tests:
            r = client.call("GET", path)
            note = "" if r.status_code == 200 else " " + r.text[:160].replace("\n", " ")
            print(f"  {'OK  ' if r.status_code == 200 else 'FAIL'} {name} ({r.status_code}){note}")
    LEGACY = original


def main():
    global LEGACY
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--one", action="store_true")
    ap.add_argument("--wipe", action="store_true")
    ap.add_argument("--legacy", action="store_true")
    args = ap.parse_args()
    LEGACY = args.legacy

    now = datetime.now(timezone.utc)
    customers = CUSTOMERS[:1] if args.one else CUSTOMERS
    if args.dry_run:
        return dry_run(customers, now)
    client = Client(load_token())
    if args.check:
        return check(client)
    if args.wipe:
        return wipe(client)
    run_push(client, customers, now)


if __name__ == "__main__":
    main()
