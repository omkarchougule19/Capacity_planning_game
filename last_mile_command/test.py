from events import pick_event, event_summary

print("--- Simulating 10 quarters of events ---")
for q in range(1, 11):
    event = pick_event(quarter=q)
    print(f"Q{q:02d}: {event_summary(event)}")