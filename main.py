from flask import Flask, jsonify, render_template, request
import requests
import os

app = Flask(__name__)

MATCHERINO_API = "https://matcherino.com/__api/bounties"
BRAWLIFY_API = "https://api.brawlapi.com/v1/maps"

# In-memory storage
current_data = {
    "bounty_id": None,
    "match_id": None,
    "teams": [],
    "map": {},
    "bans": [],
    "picks": []
}


@app.route('/')
def index():
    return "✅ Transcending Void Overlay API is running!"


# --- CONTROL PANEL PAGE ---
@app.route('/control')
def control_panel():
    return render_template("control.html")


# --- Set current match (handles HTML form + JSON) ---
@app.route('/set_match', methods=['POST'])
def set_match():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form  # form data from control.html

    bounty_id = data.get("bounty_id")
    match_id = data.get("match_id")

    if not bounty_id or not match_id:
        return jsonify({"error": "Missing bounty_id or match_id"}), 400

    current_data["bounty_id"] = bounty_id
    current_data["match_id"] = match_id

    return jsonify({"status": "Match IDs updated successfully"}), 200


# --- Serve overlay for OBS ---
@app.route('/overlay')
def overlay():
    return render_template("overlay.html")


# --- API that control panel polls ---
@app.route('/draft')
def draft_state():
    return jsonify(current_data)


# --- Overlay data API ---
@app.route('/data')
def data():
    # Try from memory first
    bounty_id = current_data.get("bounty_id")
    match_id = current_data.get("match_id")

    # If not set in memory, try reading from query params
    bounty_id = bounty_id or request.args.get("bountyId")
    match_id = match_id or request.args.get("matchId")

    if not bounty_id or not match_id:
        return jsonify({"error": "No match set or missing parameters"}), 400

    try:
        url = f"{MATCHERINO_API}/{bounty_id}/matches/{match_id}"
        headers = {"User-Agent": "Mozilla/5.0"}
        match_resp = requests.get(url, headers=headers)
        match_resp.raise_for_status()
        match_data = match_resp.json()
    except Exception as e:
        return jsonify({"error": f"Failed to fetch match data: {str(e)}"}), 400

    # Extract teams
    teams = []
    for team in match_data.get("teams", []):
        teams.append({
            "name": team.get("name", "Unknown Team"),
            "players": [p.get("username", "Unknown") for p in team.get("players", [])]
        })

    bans = ["Crow", "Fang"]
    picks = ["Gus", "Max", "Poco"]

    # Map info
    map_name = match_data.get("map", "Hard Rock Mine")
    try:
        maps_resp = requests.get(BRAWLIFY_API)
        maps_resp.raise_for_status()
        maps_list = maps_resp.json()
        map_data = next((m for m in maps_list if m["name"].lower() == map_name.lower()), {"name": map_name})
    except Exception:
        map_data = {"name": map_name}

    # Update memory cache
    current_data.update({
        "bounty_id": bounty_id,
        "match_id": match_id,
        "teams": teams,
        "map": map_data,
        "bans": bans,
        "picks": picks
    })

    return jsonify(current_data)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

