import random
from typing import Dict

EVENTS = [
    {
        "id":           "stable",
        "label":        "Stable market",
        "description":  "No major disruptions. Operations running smoothly.",
        "type":         "neutral",
        "demand_mod":   1.0,
        "truck_cap_mod":1.0,
        "probability":  0.20,
    },
    {
        "id":           "ecommerce_boom",
        "label":        "E-commerce surge",
        "description":  "A viral product drives massive online orders in your zones.",
        "type":         "good",
        "demand_mod":   1.35,
        "truck_cap_mod":1.0,
        "probability":  0.12,
    },
    {
        "id":           "driver_shortage",
        "label":        "Driver shortage",
        "description":  "Labor dispute cuts your truck capacity by 30% this quarter.",
        "type":         "bad",
        "demand_mod":   1.0,
        "truck_cap_mod":0.70,
        "probability":  0.12,
    },
    {
        "id":           "drone_regulation",
        "label":        "Drone regulation",
        "description":  "New FAA rules ground all drones for 6 weeks. Drone capacity zero.",
        "type":         "bad",
        "demand_mod":   1.0,
        "truck_cap_mod":1.0,
        "drone_cap_mod":0.0,   # new field — we'll handle this next step
        "probability":  0.08,
    },
    {
        "id":           "competitor_exit",
        "label":        "Competitor exits",
        "description":  "A rival shuts down. Their customers flood into your network.",
        "type":         "good",
        "demand_mod":   1.25,
        "truck_cap_mod":1.0,
        "probability":  0.10,
    },
    {
        "id":           "covid_disruption",
        "label":        "Supply chain shock",
        "description":  "Port closures and shortages hit. Costs up, suburban demand drops.",
        "type":         "bad",
        "demand_mod":   0.80,
        "truck_cap_mod":0.85,
        "probability":  0.10,
    },
    {
        "id":           "holiday_surge",
        "label":        "Holiday season",
        "description":  "Peak season hits. Demand spikes across all zones.",
        "type":         "good",
        "demand_mod":   1.45,
        "truck_cap_mod":1.0,
        "probability":  0.10,
    },
    {
        "id":           "fuel_crisis",
        "label":        "Fuel price crisis",
        "description":  "Fuel costs surge. Each truck costs $3K more this quarter.",
        "type":         "bad",
        "demand_mod":   1.0,
        "truck_cap_mod":1.0,
        "extra_cost":   3000,  # per truck, handled in simulate_quarter
        "probability":  0.08,
    },
    {
        "id":           "tech_breakthrough",
        "label":        "Drone range upgrade",
        "description":  "New battery tech extends drone range. Hubs get a 50% bonus this quarter.",
        "type":         "good",
        "demand_mod":   1.0,
        "truck_cap_mod":1.0,
        "hub_bonus_mod":1.50,  # multiplies hub_drone_bonus temporarily
        "probability":  0.10,
    },
]


def pick_event(quarter: int) -> Dict:
    """
    Picks a weighted random event for this quarter.
    Early quarters lean neutral/good. Later quarters get harsher.
    """
    pool = EVENTS.copy()

    # After Q5, increase weight of bad events
    if quarter > 5:
        for e in pool:
            if e["type"] == "bad":
                e = dict(e)  # don't mutate original

    weights = [e["probability"] for e in pool]

    # Normalize weights so they sum to 1
    total = sum(weights)
    weights = [w / total for w in weights]

    chosen = random.choices(pool, weights=weights, k=1)[0]
    return chosen


def event_summary(event: Dict) -> str:
    """Returns a one-line console summary of the event."""
    icons = {"good": "++", "bad": "--", "neutral": "=="}
    icon  = icons.get(event["type"], "  ")
    return f"[{icon}] {event['label']}: {event['description']}"