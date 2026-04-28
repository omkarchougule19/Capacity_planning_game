import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict

# ── Constants ──────────────────────────────────────────────────────────────────

QUARTERS = 10
STARTING_CASH = 300_000

# Capacity: how many orders each unit can handle per quarter
TRUCK_CAPACITY    = 1_000   # per truck
DRONE_CAPACITY    = 400     # per squad (urban only)
OUTSOURCE_CAP     = 500     # per 4PL contract slot

# Costs per
TRUCK_COST_PER    = 12_000
DRONE_COST_PER    = 6_0
HUB_COST_ONE_TIME = 25_000  # transshipment hub, one-time
OUTSOURCE_COST    = 18_000  # per slot per quarter
BUFFER_COST_UNIT  = 4       # per unit pre-positioned

# Revenue per delivered order
REVENUE_PER_ORDER = 28      # dollars

# Latency benchmarks (hours) — drones are faster in urban zones
LATENCY = {
    "urban_drone": 1.5,
    "urban_truck": 3.8,
    "suburban":    4.2,
    "rural":       6.5,
}

# Zone definitions: name, type, base demand per quarter
ZONES = [
    {"id": "urban",    "label": "Urban core",    "type": "urban",    "base_demand": 1200},
    {"id": "suburb_n", "label": "Suburbs North",  "type": "suburban", "base_demand": 800},
    {"id": "suburb_s", "label": "Suburbs South",  "type": "suburban", "base_demand": 600},
    {"id": "rural",    "label": "Rural East",     "type": "rural",    "base_demand": 320},
    {"id": "industrial","label":"Industrial West", "type": "suburban", "base_demand": 450},
    {"id": "airport",  "label": "Airport Hub",    "type": "suburban", "base_demand": 200},
]

@dataclass
class GameState:
    quarter: int = 1
    cash: float = STARTING_CASH
    trucks: int = 2          # starting fleet
    drones: int = 1          # starting drone squads
    hubs: int = 0            # transshipment hubs built so far
    outsource_slots: int = 0
    buffer_units: int = 0

    # History — one entry per completed quarter
    history: List[Dict] = field(default_factory=list)

    def is_over(self) -> bool:
        return self.quarter > QUARTERS or self.cash <= 0

    def to_dict(self) -> Dict:
        return {
            "quarter":        self.quarter,
            "cash":           round(self.cash),
            "trucks":         self.trucks,
            "drones":         self.drones,
            "hubs":           self.hubs,
            "outsource_slots":self.outsource_slots,
            "buffer_units":   self.buffer_units,
            "history":        self.history,
            "is_over":        self.is_over(),
        }

def generate_demand(quarter: int, event_modifier: float = 1.0) -> Dict:
    """
    Generate demand per zone for this quarter.
    Demand grows ~8% per quarter (e-commerce trend) plus random noise,
    then scaled by whatever market event hit this quarter.
    """
    rng = np.random.default_rng(seed=None)  # unseeded = different every game
    growth = 1 + (quarter - 1) * 0.08      # 8% quarterly growth trend

    demand = {}
    for zone in ZONES:
        base = zone["base_demand"] * growth
        noise = rng.normal(loc=1.0, scale=0.12)   # ±12% random noise
        noise = float(np.clip(noise, 0.7, 1.4))   # cap extremes
        demand[zone["id"]] = max(0, round(base * noise * event_modifier))

    return demand


def calculate_capacity(trucks: int, drones: int,
                        outsource_slots: int, hubs: int,
                        hub_drone_bonus: float = 0.25) -> Dict:

    truck_cap     = trucks * TRUCK_CAPACITY
    drone_cap     = round(drones * DRONE_CAPACITY * (1 + hubs * hub_drone_bonus))
    outsource_cap = outsource_slots * OUTSOURCE_CAP

    return {
        "urban":    truck_cap + drone_cap + outsource_cap,
        "suburban": truck_cap + outsource_cap,
        "rural":    truck_cap + outsource_cap,
        "total":    truck_cap + drone_cap + outsource_cap,
    }


def simulate_quarter(state: GameState, decisions: Dict, event: Dict) -> Dict:
    # ── 1. Apply decisions to state ───────────────────────────────────────────
    hub_spend = max(0, decisions["hubs"] - state.hubs) * HUB_COST_ONE_TIME
    state.trucks = decisions["trucks"]
    state.drones = decisions["drones"]
    state.hubs = decisions["hubs"]
    state.outsource_slots = decisions["outsource_slots"]
    state.buffer_units = decisions["buffer_units"]

    # ── 2. Operating costs — including fuel crisis extra cost ─────────────────
    extra_truck_cost = event.get("extra_cost", 0) * state.trucks
    op_costs = (
            state.trucks * TRUCK_COST_PER +
            state.drones * DRONE_COST_PER +
            state.outsource_slots * OUTSOURCE_COST +
            state.buffer_units * BUFFER_COST_UNIT +
            hub_spend +
            extra_truck_cost
    )

    # ── 3. Demand ─────────────────────────────────────────────────────────────
    demand = generate_demand(state.quarter, event.get("demand_mod", 1.0))

    # ── 4. Effective capacity — apply all event modifiers ─────────────────────
    truck_cap_mod = event.get("truck_cap_mod", 1.0)
    drone_cap_mod = event.get("drone_cap_mod", 1.0)
    hub_bonus_mod = event.get("hub_bonus_mod", 1.0)

    effective_trucks = round(state.trucks * truck_cap_mod)
    effective_drone_cap = round(
        state.drones * DRONE_CAPACITY *
        (1 + state.hubs * 0.25 * hub_bonus_mod) *
        drone_cap_mod
    )

    # ── 5. Fulfill demand zone by zone ────────────────────────────────────────
    # Total capacity pools — shared across ALL zones of that type
    remaining_truck = effective_trucks * TRUCK_CAPACITY
    remaining_drone = state.drones * DRONE_CAPACITY * (1 + state.hubs * 0.25)
    remaining_outsource = state.outsource_slots * OUTSOURCE_CAP


    zone_results = []
    total_demand = 0
    total_fulfilled = 0
    total_latency = 0.0

    buffer_available = state.buffer_units if total_demand > (effective_trucks * TRUCK_CAPACITY) else 0
    remaining_buffer = buffer_available
    buffer_hold_cost = state.buffer_units * 2  # $2/unit to hold
    buffer_activation = max(0, total_demand - effective_trucks * TRUCK_CAPACITY) * 3  # $3/unit activated

    for zone in ZONES:
        zid = zone["id"]
        ztype = zone["type"]
        zdemand = demand[zid]

        # Each zone draws from shared pools
        if ztype == "urban":
            # Urban can use trucks + drones + outsource + buffer
            drone_used = min(zdemand, remaining_drone)
            still_needed = zdemand - drone_used
            truck_used = min(still_needed, remaining_truck)
            still_needed -= truck_used
            out_used = min(still_needed, remaining_outsource)
            still_needed -= out_used
            buf_used = min(still_needed, remaining_buffer)

            remaining_drone -= drone_used
            remaining_truck -= truck_used
            remaining_outsource -= out_used
            remaining_buffer -= buf_used

            fulfilled = drone_used + truck_used + out_used + buf_used

            # Latency: weighted avg of drone vs truck deliveries
            if fulfilled > 0:
                lat = ((drone_used * LATENCY["urban_drone"]) +
                       (truck_used * LATENCY["urban_truck"])) / fulfilled
            else:
                lat = 0.0

        else:
            # Suburban / rural: trucks + outsource + buffer only
            truck_used = min(zdemand, remaining_truck)
            still_needed = zdemand - truck_used
            out_used = min(still_needed, remaining_outsource)
            still_needed -= out_used
            buf_used = min(still_needed, remaining_buffer)

            remaining_truck -= truck_used
            remaining_outsource -= out_used
            remaining_buffer -= buf_used

            fulfilled = truck_used + out_used + buf_used
            lat = LATENCY["suburban"] if ztype == "suburban" else LATENCY["rural"]

        zone_results.append({
            "zone": zone["label"],
            "type": ztype,
            "demand": zdemand,
            "fulfilled": int(fulfilled),
            "latency": round(lat, 2),
            "service_level": round(fulfilled / max(zdemand, 1), 3),
        })

        total_demand += zdemand
        total_fulfilled += int(fulfilled)
        total_latency += lat

    # ── 6. Calculate KPIs ─────────────────────────────────────────────────────
    total_capacity = (effective_trucks * TRUCK_CAPACITY) + effective_drone_cap + (state.outsource_slots * OUTSOURCE_CAP)
    service_level = round(total_fulfilled / max(total_demand, 1), 3)
    avg_latency = round(total_latency / len(ZONES), 2)
    utilization = round(total_fulfilled / max(total_capacity, 1), 3)

    revenue = total_fulfilled * REVENUE_PER_ORDER
    profit = revenue - op_costs
    state.cash += profit

    # ── 7. Pack results ───────────────────────────────────────────────────────
    result = {
        "quarter": state.quarter,
        "event": event,
        "demand": demand,
        "total_capacity":   total_capacity,    # ← replace with this
        "zone_results": zone_results,
        "total_demand": total_demand,
        "total_fulfilled": total_fulfilled,
        "service_level": service_level,
        "avg_latency": avg_latency,
        "utilization": utilization,
        "revenue": round(revenue),
        "op_costs": round(op_costs),
        "profit": round(profit),
        "cash": round(state.cash),
    }

    state.history.append(result)
    state.quarter += 1
    return result