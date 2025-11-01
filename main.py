from flask import Flask, jsonify, render_template, request
import requests
import os

app = Flask(__name__)

MATCHERINO_API = "https://matcherino.com/__api/bounties/"
BRAWLIFY_API = "https://api.brawlapi.com/v1"

# Temporary storage (until we add a proper control panel)
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
    return "Transcending Void Overlay API running!"

@app.route('/set_match', methods=['POST'])
def set_match():
    data = request.json
    current_data["bounty_id"] = data.get("bounty_id")
    current_data["match_id"] = data.get("match_id")
    return jsonify({"status": "Match IDs updated"}), 200

@app.route('/overlay')
def overlay():
    return render_template("overlay.html")

@app.route('/data')
def data():
    bounty_id = current_data.get("bounty_id")
    match_id = current_data.get("match_id")

    if not bounty_id or not match_id:
        return jsonify({"error": "No match set"}), 400

    # Fetch match data from Matcherino
    url = f"{MATCHERINO_API}{bounty_id}/matches/{match_id}"
    resp = requests.get(url)
    if resp.status_code != 200:
        return jsonify({"error": "Could not fetch match data"}), 400

    match_data = resp.json()

    # Parse teams, players, bans, etc.
    teams = []
    for team in match_data.get("teams", []):
        teams.append({
            "name": team.get("name"),
            "players": [p.get("username") for p in team.get("players", [])]
        })

    # Example static data (replace with real once Matcherino integration known)
    bans = ["crow", "fang"]
    picks = ["gus", "max", "poco"]

    map_name = match_data.get("map", "Hard Rock Mine")

    # Fetch map info from Brawlify
    map_resp = requests.get(f"{BRAWLIFY_API}/maps")
    map_data = next((m for m in map_resp.json() if m["name"].lower() == map_name.lower()), None)

    current_data.update({
        "teams": teams,
        "map": map_data or {"name": map_name},
        "bans": bans,
        "picks": picks
    })

    return jsonify(current_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
