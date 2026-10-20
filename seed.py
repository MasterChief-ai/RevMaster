import sqlite3
from datetime import datetime, timedelta, timezone

BATCH = "rra-v1"


# ---------------------------------------------------------------
# HOW TO READ THIS FILE
# E(...)  = one event in a customer's story
#   days_ago : how long ago it happened
#   who      : "lead" = they did it, "us" = we did it
#   type     : email / call / note / task
#   opens    : times they opened an email WE sent
#   due, done: tasks only. due = days ago it was due, done = finished?
# C(...)  = one customer. Last two fields before events are the
#           archetype and the label (neglected / stalled / ok).
# Labels come from the STORY, not from counting days.
# ---------------------------------------------------------------
def E(days_ago, who, type, text, opens=0, due=None, done=False):
    return {"days_ago": days_ago, "who": who, "type": type, "text": text,
            "opens": opens, "due": due, "done": done}


def C(key, name, company, source, value, stage, archetype, status, events):
    return {"key": key, "name": name, "company": company, "source": source,
            "deal_value": value, "stage": stage, "archetype": archetype,
            "status": status, "events": events}


CUSTOMERS = [
    # ===== 1. HOT BUT GHOSTED (neglected): they asked, we never answered =====
    C("john-stewart", "John Stewart", "Green Lantern Corps", "phone_call", 60_000_000, "qualified",
      "hot_but_ghosted", "neglected", [
        E(14, "lead", "call", "Asked for a brochure to look through."),
        E(12, "us", "email", "Sent the property brochure.", opens=6),
        E(9, "lead", "email", "Can you share financing details and how we move forward with the deal?"),
    ]),
    C("priya-raman", "Priya Raman", "Meridian Crest Partners", "website_form", 85_000_000, "proposal_sent",
      "hot_but_ghosted", "neglected", [
        E(21, "lead", "note", "Website form: interested in the Meridian Plaza tower."),
        E(19, "us", "email", "Sent the brochure and fact sheet.", opens=4),
        E(15, "lead", "email", "We reviewed the brochure. Can you share the financing structure and the expected closing timeline?"),
    ]),
    C("marcus-bell", "Marcus Bell", "Bell & Okafor Holdings", "phone_call", 120_000_000, "negotiation",
      "hot_but_ghosted", "neglected", [
        E(16, "lead", "call", "Interested in the full portfolio. Wants to discuss terms."),
        E(14, "us", "email", "Sent portfolio summary.", opens=9),
        E(7, "lead", "email", "Our board meets Friday. We need the financing terms before then."),
    ]),
    C("elena-voss", "Elena Voss", "Voss Logistics Realty", "brochure_request", 52_000_000, "qualified",
      "hot_but_ghosted", "neglected", [
        E(10, "lead", "note", "Requested the warehouse portfolio brochure."),
        E(9, "us", "email", "Sent brochure.", opens=2),
        E(5, "lead", "email", "Does the seller offer financing? Also what are the tax implications of an asset deal?"),
    ]),
    C("tom-whitaker", "Tom Whitaker", "Whitaker Industrial Trust", "phone_call", 34_000_000, "proposal_sent",
      "hot_but_ghosted", "neglected", [
        E(20, "lead", "call", "Asked for details on the Dayton industrial park."),
        E(18, "us", "email", "Sent the property specs.", opens=5),
        E(12, "lead", "email", "We're ready to move ahead. Please send the purchase agreement draft."),
    ]),
    C("sofia-marchetti", "Sofia Marchetti", "Marchetti Hospitality Group", "website_form", 67_000_000, "qualified",
      "hot_but_ghosted", "neglected", [
        E(25, "lead", "note", "Website form: interested in the coastal resort."),
        E(23, "us", "email", "Sent brochure.", opens=7),
        E(18, "lead", "email", "Can we schedule a call to discuss price flexibility?"),
    ]),
    C("omar-haddad", "Omar Haddad", "Haddad Capital Advisors", "phone_call", 58_000_000, "new",
      "hot_but_ghosted", "neglected", [
        E(6, "lead", "call", "Needs financing options for a Q4 close."),
        E(5, "lead", "email", "Following up on my call. How soon can we see financing terms?"),
    ]),

    # ===== 2. WENT COLD AFTER PRICING (stalled): we answered, they went quiet =====
    C("maria-alvarez", "Maria Alvarez", "Harbor Ridge Capital", "website_form", 12_000_000, "proposal_sent",
      "went_cold_after_pricing", "stalled", [
        E(22, "lead", "email", "What is the asking price for the Harbor Street building?"),
        E(20, "us", "email", "Sent pricing and a summary of the building.", opens=3),
    ]),
    C("linda-park", "Linda Park", "Parkside Realty Fund", "website_form", 28_000_000, "proposal_sent",
      "went_cold_after_pricing", "stalled", [
        E(30, "lead", "email", "Please send pricing for the Parkside office complex."),
        E(28, "us", "email", "Sent pricing summary.", opens=4),
    ]),
    C("greg-anders", "Greg Anders", "Anders Development Co.", "phone_call", 9_000_000, "proposal_sent",
      "went_cold_after_pricing", "stalled", [
        E(55, "lead", "call", "Asked what the strip mall would cost."),
        E(52, "us", "email", "Sent pricing and rent roll.", opens=2),
    ]),
    C("hannah-cole", "Hannah Cole", "Cole Medical Properties", "brochure_request", 63_000_000, "proposal_sent",
      "went_cold_after_pricing", "stalled", [
        E(20, "lead", "note", "Requested the medical office brochure."),
        E(18, "us", "email", "Sent pricing and financing overview.", opens=5),
    ]),
    C("raj-mehta", "Raj Mehta", "Mehta Retail Partners", "website_form", 41_000_000, "proposal_sent",
      "went_cold_after_pricing", "stalled", [
        E(19, "lead", "email", "What's the price on the retail center?"),
        E(17, "us", "email", "Sent pricing.", opens=3),
    ]),
    C("carla-jimenez", "Carla Jimenez", "Jimenez Storage Holdings", "phone_call", 15_000_000, "proposal_sent",
      "went_cold_after_pricing", "stalled", [
        E(40, "lead", "call", "Asked about pricing on the storage portfolio."),
        E(38, "us", "email", "Sent pricing.", opens=6),
        E(31, "us", "email", "Checking in on the pricing summary. Any questions?"),
    ]),

    # ===== 3. OVERDUE FOLLOW-UP, LOW VALUE (neglected, low priority) =====
    C("brian-foster", "Brian Foster", "Foster Self Storage LLC", "website_form", 3_200_000, "qualified",
      "overdue_followup_low_value", "neglected", [
        E(18, "lead", "email", "Could someone call me about the unit mix and cap rate?"),
        E(17, "us", "task", "Call Brian re: unit mix and cap rate", due=15, done=False),
    ]),
    C("nina-patel", "Nina Patel", "Patel Family Trust", "phone_call", 7_500_000, "qualified",
      "overdue_followup_low_value", "neglected", [
        E(13, "lead", "call", "Wants to see the rent roll."),
        E(13, "us", "task", "Send rent roll to Nina", due=10, done=False),
    ]),
    C("kevin-obrien", "Kevin O'Brien", "O'Brien Dental Properties", "brochure_request", 2_100_000, "qualified",
      "overdue_followup_low_value", "neglected", [
        E(25, "lead", "note", "Requested the dental office brochure."),
        E(24, "us", "email", "Sent brochure.", opens=3),
        E(20, "lead", "email", "Is a site visit possible this month?"),
        E(20, "us", "task", "Schedule site visit with Kevin", due=17, done=False),
    ]),
    C("dana-whitfield", "Dana Whitfield", "Whitfield Auto Group", "website_form", 5_800_000, "qualified",
      "overdue_followup_low_value", "neglected", [
        E(12, "lead", "email", "Interested in the parking structure. What's the occupancy?"),
        E(12, "us", "task", "Send occupancy numbers to Dana", due=9, done=False),
    ]),
    C("samir-qureshi", "Samir Qureshi", "Qureshi Convenience Holdings", "phone_call", 4_400_000, "qualified",
      "overdue_followup_low_value", "neglected", [
        E(30, "lead", "call", "Wants lease terms for the gas station sites."),
        E(29, "us", "task", "Call Samir back with lease terms", due=24, done=False),
        E(28, "us", "email", "Will call you this week with the lease terms.", opens=1),
    ]),

    # ===== 4. HEALTHY AND ACTIVE (ok) =====
    C("david-chen", "David Chen", "Chen Family Office", "brochure_request", 4_000_000, "qualified",
      "healthy_active", "ok", [
        E(6, "lead", "email", "Can we arrange a site visit?"),
        E(5, "us", "email", "Proposed three visit dates.", opens=2),
        E(1, "lead", "email", "Thursday works for us."),
    ]),
    C("angela-ruiz", "Angela Ruiz", "Ruiz Office Partners", "referral", 45_000_000, "qualified",
      "healthy_active", "ok", [
        E(8, "lead", "email", "Can you send the floor plans?"),
        E(7, "us", "email", "Sent floor plans.", opens=2),
        E(4, "lead", "email", "Thanks. Can we tour Thursday?"),
        E(3, "us", "email", "Thursday 10am is confirmed."),
    ]),
    C("peter-lindqvist", "Peter Lindqvist", "Lindqvist Capital", "website_form", 92_000_000, "qualified",
      "healthy_active", "ok", [
        E(5, "lead", "note", "Website form: portfolio acquisition inquiry."),
        E(4, "us", "call", "Intro call: discussed their portfolio goals."),
        E(3, "us", "email", "Sent call recap.", opens=3),
        E(1, "lead", "email", "Recap looks right. Please send the data room link."),
    ]),
    C("maya-thompson", "Maya Thompson", "Thompson Retail REIT", "brochure_request", 61_000_000, "qualified",
      "healthy_active", "ok", [
        E(9, "lead", "note", "Requested the retail portfolio brochure."),
        E(8, "us", "email", "Sent brochure.", opens=4),
        E(6, "lead", "email", "Can we get on a call?"),
        E(5, "us", "email", "Proposed Tuesday or Wednesday."),
        E(3, "lead", "email", "Tuesday works."),
        E(2, "us", "email", "Booked for Tuesday 2pm."),
    ]),
    C("chris-daniels", "Chris Daniels", "Daniels Flex Space LLC", "phone_call", 8_900_000, "qualified",
      "healthy_active", "ok", [
        E(9, "lead", "call", "Asked about flex warehouse space."),
        E(8, "us", "email", "Sent availability and rates.", opens=2),
        E(3, "lead", "email", "Thanks, reviewing with my partner."),
    ]),
    C("isabel-moreau", "Isabel Moreau", "Moreau Wine Estates", "website_form", 22_000_000, "negotiation",
      "healthy_active", "ok", [
        E(14, "lead", "note", "Website form: interested in the vineyard property."),
        E(13, "us", "email", "Sent details.", opens=3),
        E(10, "lead", "email", "What water rights come with the property?"),
        E(9, "us", "email", "Sent water rights summary."),
        E(6, "lead", "email", "Is the equipment included?"),
        E(5, "us", "email", "Yes, full equipment list attached.", opens=2),
        E(2, "lead", "email", "Perfect. Speaking with my lender this week."),
    ]),
    # HARD NEGATIVE: "reviewing" needs no reply, but a simple rule will see an unanswered inbound.
    C("trevor-nash", "Trevor Nash", "Nash Logistics Park", "referral", 140_000_000, "negotiation",
      "healthy_active", "ok", [
        E(6, "lead", "note", "Referral from existing investor."),
        E(6, "us", "call", "Intro call: covered park specs and timeline."),
        E(4, "us", "email", "Sent term sheet outline.", opens=5),
        E(3, "lead", "email", "Thanks, reviewing with counsel."),
    ]),
    C("fiona-gallagher", "Fiona Gallagher", "Gallagher Senior Living", "website_form", 31_000_000, "qualified",
      "healthy_active", "ok", [
        E(7, "lead", "note", "Website form: interested in the senior living facility."),
        E(7, "us", "email", "Thanks for your interest. Details attached.", opens=2),
        E(5, "lead", "email", "What's the current occupancy?"),
        E(4, "us", "email", "Occupancy report attached.", opens=2),
    ]),
    C("hector-salazar", "Hector Salazar", "Salazar Land Co.", "phone_call", 6_300_000, "qualified",
      "healthy_active", "ok", [
        E(12, "lead", "call", "Asked about the 40-acre parcel."),
        E(11, "us", "email", "Sent parcel details.", opens=2),
        E(9, "lead", "email", "Great. Please send the survey."),
        E(8, "us", "email", "Survey attached.", opens=3),
        E(4, "lead", "email", "Got it. We'll visit next week."),
    ]),
    C("yuki-tanaka", "Yuki Tanaka", "Tanaka Hospitality Partners", "brochure_request", 76_000_000, "qualified",
      "healthy_active", "ok", [
        E(4, "lead", "note", "Requested the hotel brochure."),
        E(3, "us", "email", "Sent brochure.", opens=3),
        E(3, "us", "call", "Left a voicemail introducing ourselves."),
        E(1, "lead", "email", "Got your voicemail. Call me tomorrow at 9am."),
    ]),
    C("walter-briggs", "Walter Briggs", "Briggs Industrial Supply", "referral", 19_000_000, "negotiation",
      "healthy_active", "ok", [
        E(15, "lead", "note", "Referral from a mutual contact."),
        E(14, "us", "email", "Sent property overview.", opens=2),
        E(11, "lead", "email", "Can you add the zoning documents?"),
        E(10, "us", "email", "Zoning documents attached.", opens=1),
        E(7, "lead", "email", "Zoning looks fine. What's next?"),
        E(6, "us", "email", "Next is an offer letter. Draft attached."),
        E(2, "lead", "email", "Offer letter looks good. Reviewing internally."),
    ]),
    C("zoe-kim", "Zoe Kim", "Kim Mixed-Use Development", "website_form", 47_000_000, "qualified",
      "healthy_active", "ok", [
        E(3, "lead", "email", "What's the timeline for closing on the mixed-use building?"),
        E(2, "us", "email", "Typical close is 60 to 90 days. Details attached."),
        E(1, "lead", "email", "Great. Please send the lease abstracts."),
    ]),

    # ===== 5. AWAITING THEIR REPLY, INSIDE THE WINDOW (ok) =====
    C("aaron-blake", "Aaron Blake", "Blake Equity Partners", "website_form", 73_000_000, "proposal_sent",
      "awaiting_reply_in_window", "ok", [
        E(6, "lead", "email", "Can you outline the financing options?"),
        E(5, "us", "email", "Sent financing summary.", opens=2),
    ]),
    C("natalie-ford", "Natalie Ford", "Ford Cold Storage", "phone_call", 55_000_000, "proposal_sent",
      "awaiting_reply_in_window", "ok", [
        E(6, "lead", "call", "Asked about the cold storage facility's capacity."),
        E(4, "us", "email", "Sent capacity and utilization report.", opens=1),
    ]),
    C("derek-osei", "Derek Osei", "Osei Mixed Use", "website_form", 26_000_000, "proposal_sent",
      "awaiting_reply_in_window", "ok", [
        E(12, "lead", "email", "Please send a proposal for the mixed-use site."),
        E(10, "us", "email", "Proposal sent.", opens=3),
    ]),
    C("julia-bergman", "Julia Bergman", "Bergman Apartments LLC", "referral", 38_000_000, "proposal_sent",
      "awaiting_reply_in_window", "ok", [
        E(15, "lead", "email", "What's the price for the apartment complex?"),
        E(13, "us", "email", "Sent pricing.", opens=4),
    ]),
    C("victor-lam", "Victor Lam", "Lam Parking Holdings", "phone_call", 2_900_000, "qualified",
      "awaiting_reply_in_window", "ok", [
        E(22, "lead", "call", "Asked about the downtown parking lot."),
        E(20, "us", "email", "Sent lot details and revenue history.", opens=2),
    ]),
    C("beth-carroway", "Beth Carroway", "Carroway Daycare Properties", "website_form", 5_100_000, "qualified",
      "awaiting_reply_in_window", "ok", [
        E(26, "lead", "note", "Website form: interested in the daycare building."),
        E(25, "us", "email", "Sent property details."),
    ]),

    # ===== 6. DECLINED (ok): no action needed =====
    # HARD NEGATIVE: the decline was never answered, so a simple rule will flag it.
    C("gordon-pryce", "Gordon Pryce", "Pryce Manufacturing", "website_form", 44_000_000, "proposal_sent",
      "declined", "ok", [
        E(30, "lead", "note", "Website form: interested in the manufacturing plant."),
        E(29, "us", "email", "Sent details.", opens=3),
        E(18, "lead", "email", "We've decided to buy elsewhere. Thank you."),
    ]),
    # HARD NEGATIVE: same pattern.
    C("ingrid-sol", "Ingrid Sol", "Sol Pharma Real Estate", "referral", 90_000_000, "proposal_sent",
      "declined", "ok", [
        E(25, "lead", "note", "Referral for the lab campus."),
        E(24, "us", "email", "Sent details.", opens=5),
        E(14, "lead", "email", "Not moving forward. Our budget changed."),
    ]),
    C("leon-marsh", "Leon Marsh", "Marsh Warehousing", "phone_call", 8_200_000, "closed_lost",
      "declined", "ok", [
        E(40, "lead", "call", "Asked about the warehouse."),
        E(38, "us", "email", "Sent details.", opens=1),
        E(27, "lead", "email", "Pass for now."),
        E(27, "us", "email", "Understood. Our door is open if things change."),
    ]),
    C("rosa-delgado", "Rosa Delgado", "Delgado Foods", "website_form", 30_000_000, "closed_lost",
      "declined", "ok", [
        E(33, "lead", "note", "Website form: interested in the distribution center."),
        E(32, "us", "email", "Sent details.", opens=2),
        E(20, "lead", "email", "Another buyer closed first. Please remove me from your list."),
        E(19, "us", "email", "Removed. Thanks for your time."),
    ]),

    # ===== 7a. HIGH VALUE, INQUIRY NEVER ANSWERED, NO INTENT (neglected) =====
    C("franklin-doyle", "Franklin Doyle", "Doyle Global Holdings", "website_form", 110_000_000, "new",
      "high_value_never_answered", "neglected", [
        E(9, "lead", "note", "Website form submitted: general inquiry, no message."),
    ]),
    C("mei-zhao", "Mei Lin Zhao", "Zhao Investment Group", "website_form", 65_000_000, "new",
      "high_value_never_answered", "neglected", [
        E(21, "lead", "note", "Website form submitted: general inquiry, no message."),
    ]),
    C("anders-holm", "Anders Holm", "Holm Pacific Partners", "brochure_request", 80_000_000, "new",
      "high_value_never_answered", "neglected", [
        E(5, "lead", "note", "Brochure request submitted online."),
    ]),

    # ===== 7b. HIGH VALUE, WE REPLIED, LEAD SILENT PAST WINDOW (stalled) =====
    C("patrick-sheehan", "Patrick Sheehan", "Sheehan Equity", "website_form", 70_000_000, "new",
      "high_value_we_replied_silent", "stalled", [
        E(16, "lead", "note", "Website form submitted: general inquiry."),
        E(14, "us", "email", "Introduced ourselves and attached the brochure.", opens=2),
    ]),
    C("camille-durand", "Camille Durand", "Durand Capital", "website_form", 95_000_000, "new",
      "high_value_we_replied_silent", "stalled", [
        E(12, "lead", "note", "Website form submitted: general inquiry."),
        E(9, "us", "email", "Introduced ourselves and attached the brochure.", opens=1),
    ]),

    # ===== 8a. INTENT ONLY IN FREE TEXT, UNANSWERED (neglected) =====
    C("wes-kowalski", "Wes Kowalski", "Kowalski Brothers Realty", "phone_call", 18_000_000, "qualified",
      "free_text_intent_unanswered", "neglected", [
        E(11, "lead", "email", "hey we're thinking of pulling the trigger before year end, who do i talk to about the money side?"),
    ]),
    C("gabrielle-fontaine", "Gabrielle Fontaine", "Fontaine Heritage Hotels", "website_form", 75_000_000, "qualified",
      "free_text_intent_unanswered", "neglected", [
        E(6, "lead", "email", "Our partners want to see numbers soon. What do you need from us to start due diligence?"),
    ]),
    C("raymond-teller", "Raymond Teller", "Teller Brothers Plumbing Supply", "phone_call", 6_000_000, "qualified",
      "free_text_intent_unanswered", "neglected", [
        E(20, "lead", "call", "Call notes: says he's ready to buy if the price is right. Wants comps sent."),
    ]),

    # ===== 8b. INTENT IN FREE TEXT, WE ANSWERED, STILL IN WINDOW (ok) =====
    C("helen-carver", "Helen Carver", "Carver Medical Plaza", "website_form", 22_000_000, "negotiation",
      "free_text_intent_answered", "ok", [
        E(8, "lead", "email", "we're close to deciding, just need the CAM charges"),
        E(5, "us", "email", "CAM charges attached.", opens=2),
    ]),
    C("isaac-rowe", "Isaac Rowe", "Rowe Capital Group", "phone_call", 52_000_000, "negotiation",
      "free_text_intent_answered", "ok", [
        E(4, "lead", "email", "our board wants the financing terms by month end"),
        E(3, "us", "email", "Financing terms attached.", opens=1),
    ]),
]


def main():
    con = sqlite3.connect("rra.db")
    con.execute("PRAGMA foreign_keys = ON")
    now = datetime.now(timezone.utc)

    def ago(days):
        return (now - timedelta(days=days)).isoformat()

    # Wipe only our fake data (children first), then put it all back.
    con.execute("DELETE FROM ground_truth WHERE contact_id IN (SELECT id FROM contacts WHERE seed_batch = ?)", (BATCH,))
    con.execute("DELETE FROM activities WHERE seed_batch = ?", (BATCH,))
    con.execute("DELETE FROM deals WHERE seed_batch = ?", (BATCH,))
    con.execute("DELETE FROM contacts WHERE seed_batch = ?", (BATCH,))

    for c in CUSTOMERS:
        first_day = max(e["days_ago"] for e in c["events"])
        email = c["name"].lower().replace("'", "").replace(" ", ".") + "@example.com"

        cur = con.execute(
            "INSERT INTO contacts (hubspot_id, name, company, email, source, created_at, seed_batch) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"local-{c['key']}", c["name"], c["company"], email, c["source"], ago(first_day), BATCH),
        )
        contact_id = cur.lastrowid

        cur = con.execute(
            "INSERT INTO deals (hubspot_id, contact_id, name, amount_usd, stage, created_at, seed_batch) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"local-deal-{c['key']}", contact_id, f"{c['company']} deal", c["deal_value"], c["stage"], ago(first_day), BATCH),
        )
        deal_id = cur.lastrowid

        for e in c["events"]:
            direction = "inbound" if e["who"] == "lead" else "outbound"
            due_at = ago(e["due"]) if e["due"] is not None else None
            con.execute(
                "INSERT INTO activities (contact_id, deal_id, type, direction, occurred_at, body, open_count, due_at, completed, seed_batch) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (contact_id, deal_id, e["type"], direction, ago(e["days_ago"]), e["text"],
                 e["opens"], due_at, int(e["done"]), BATCH),
            )

        con.execute(
            "INSERT INTO ground_truth (contact_id, archetype, status) VALUES (?, ?, ?)",
            (contact_id, c["archetype"], c["status"]),
        )

    con.commit()

    print("Customers:", con.execute("SELECT COUNT(*) FROM contacts").fetchone()[0])
    print("By label:", con.execute("SELECT status, COUNT(*) FROM ground_truth GROUP BY status").fetchall())
    print("By archetype:", con.execute("SELECT archetype, COUNT(*) FROM ground_truth GROUP BY archetype").fetchall())


if __name__ == "__main__":
    main()
