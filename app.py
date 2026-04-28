from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from engine import GameState, simulate_quarter, calculate_capacity
from events import pick_event
import os

app = Flask(__name__, static_folder="static")
CORS(app)

# One global game state — single player for now
game_state = GameState()


# ── Serve the frontend ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ── API: get current game state ───────────────────────────────────────────────

@app.route("/api/state", methods=["GET"])
def get_state():
    return jsonify(game_state.to_dict())


# ── API: preview cost before confirming ──────────────────────────────────────

@app.route("/api/preview", methods=["POST"])
def preview():
    data = request.json
    decisions = data["decisions"]

    hub_spend = max(0, decisions["hubs"] - game_state.hubs) * 25000
    op_costs  = (
        decisions["trucks"]          * 12000 +
        decisions["drones"]          * 6000  +
        decisions["outsource_slots"] * 18000 +
        decisions["buffer_units"]    * 4     +
        hub_spend
    )
    capacity = calculate_capacity(
        trucks=decisions["trucks"],
        drones=decisions["drones"],
        outsource_slots=decisions["outsource_slots"],
        hubs=decisions["hubs"],
    )
    return jsonify({
        "op_costs": round(op_costs),
        "capacity": capacity,
        "affordable": op_costs <= game_state.cash,
    })


# ── API: confirm quarter ──────────────────────────────────────────────────────

@app.route("/api/simulate", methods=["POST"])
def simulate():
    global game_state

    if game_state.is_over():
        return jsonify({"error": "Game is already over"}), 400

    data      = request.json
    decisions = data["decisions"]
    event     = pick_event(game_state.quarter)
    result    = simulate_quarter(game_state, decisions, event)

    return jsonify({
        "result":    result,
        "state":     game_state.to_dict(),
        "game_over": game_state.is_over(),
    })


# ── API: restart game ─────────────────────────────────────────────────────────

@app.route("/api/restart", methods=["POST"])
def restart():
    global game_state
    game_state = GameState()
    return jsonify(game_state.to_dict())


# ── API: final score ──────────────────────────────────────────────────────────

@app.route("/api/score", methods=["GET"])
def score():
    if not game_state.history:
        return jsonify({"error": "No history yet"}), 400

    history = game_state.history
    avg_sl      = sum(q["service_level"]  for q in history) / len(history)
    avg_lat     = sum(q["avg_latency"]    for q in history) / len(history)
    avg_util    = sum(q["utilization"]    for q in history) / len(history)
    total_profit= sum(q["profit"]         for q in history)

    # Scoring — weighted like the professor's KPI framework
    sl_score    = min(avg_sl   * 40,  40)   # 40 pts — service level
    lat_score   = max(0, (6 - avg_lat) / 6 * 30)  # 30 pts — lower latency = better
    util_score  = min(avg_util * 20,  20)   # 20 pts — utilization
    profit_score= min(max(total_profit / 500000 * 10, 0), 10)  # 10 pts — profit

    total = round(sl_score + lat_score + util_score + profit_score)
    grade = "A" if total >= 85 else "B" if total >= 70 else "C" if total >= 55 else "F"

    return jsonify({
        "score":        total,
        "grade":        grade,
        "avg_sl":       round(avg_sl * 100, 1),
        "avg_latency":  round(avg_lat, 2),
        "avg_util":     round(avg_util * 100, 1),
        "total_profit": round(total_profit),
        "breakdown": {
            "service_level": round(sl_score, 1),
            "latency":       round(lat_score, 1),
            "utilization":   round(util_score, 1),
            "profit":        round(profit_score, 1),
        }
    })


if __name__ == "__main__":
    os.makedirs("static", exist_ok=True)
    app.run(debug=True, port=5000)