from flask import Flask, jsonify, render_template, request
import requests
import os

app = Flask(__name__)

# Correct API endpoints
MATCHERINO_API = "https://api.matcherino.com/__api/games/brawlstars/match/stats"
BRAWLIFY_API = "https://api.brawlapi.com/v1/maps"

# In-memory data storage
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
    return "✅ Transcending Void Overlay API is running and connected!"


# --- Control panel page ---
@app.route('/control')
def control_panel():
    return render_template("control.html")


# --- Endpoint for setting match IDs (from panel or manually) ---
@app.route('/set_match', methods=['POST'])
def set_match():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    bounty_id = data.get("bounty_id")
    match_id = data.get("match_id")

    if not bounty_id or not match_id:
        return jsonify({"error": "Missing bounty_id or match_id"}), 400

    current_data["bounty_id"] = bounty_id
    current_data["match_id"] = match_id

    return jsonify({"status": "✅ Match IDs updated successfully"}), 200


# --- Overlay page for OBS ---
@app.route('/overlay')
def overlay():
    return render_template("overlay.html")


# --- API for control panel polling ---
@app.route('/draft')
def draft_state():
    return jsonify(current_data)


# --- Fetch actual match + map data ---
@app.route('/data')
def data():
    # Read from memory or query params
    bounty_id = current_data.get("bounty_id") or request.args.get("bountyId")
    match_id = current_data.get("match_id") or request.args.get("matchId")

    if not bounty_id or not match_id:
        return jsonify({"error": "Missing bountyId or matchId"}), 400

    try:
        # ✅ Correct Matcherino API URL
        url = f"{MATCHERINO_API}?bountyId={bounty_id}&matchIds={match_id}"
        headers = {"User-Agent": "Mozilla/5.0"}
        match_resp = requests.get(url, headers=headers)
        match_resp.raise_for_status()
        match_data = match_resp.json()
    except Exception as e:
        return jsonify({"error": f"❌ Failed to fetch match data: {str(e)}"}), 400

    # Ensure data exists
    if not match_data or not isinstance(match_data, list) or len(match_data) == 0:
        return jsonify({"error": "⚠️ No match data returned from API"}), 404

    match = match_data[0]

    # Extract team info
    teams = []
    for team in match.get("teams", []):
        teams.append({
            "name": team.get("name", "Unknown Team"),
            "players": [p.get("username", "Unknown") for p in team.get("players", [])]
        })

    # Extract bans and picks
    bans = []
    picks = []
    for team in match.get("teams", []):
        bans.extend([b.get("brawler", "Unknown") for b in team.get("bans", [])])
        picks.extend([p.get("brawler", "Unknown") for p in team.get("picks", [])])

    # Extract map
    map_name = match.get("map", {}).get("name", "Hard Rock Mine")

    # Get map info from Brawlify
    try:
        maps_resp = requests.get(BRAWLIFY_API)
        maps_resp.raise_for_status()
        maps_list = maps_resp.json()
        map_data = next((m for m in maps_list if m["name"].lower() == map_name.lower()), {"name": map_name})
    except Exception:
        map_data = {"name": map_name}

    # Update in-memory cache
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

