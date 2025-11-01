from flask import Flask, jsonify, render_template, request
import requests
import os

app = Flask(__name__)

MATCHERINO_API = "https://api.matcherino.com/__api/games/brawlstars/match/stats"
BRAWLIFY_API = "https://api.brawlapi.com/v1/maps"

current_data = {
    "bounty_id": None,
    "match_id": None,
    "teams": [],
    "map": {},
    "bans": [],
    "picks": [],
}


@app.route('/')
def index():
    return "✅ Transcending Void Overlay API is running and connected!"


@app.route('/control')
def control_panel():
    return render_template("control.html")


@app.route('/set_match', methods=['POST'])
def set_match():
    data = request.get_json() if request.is_json else request.form
    bounty_id = data.get("bounty_id")
    match_id = data.get("match_id")

    if not bounty_id or not match_id:
        return jsonify({"error": "Missing bounty_id or match_id"}), 400

    current_data["bounty_id"] = bounty_id
    current_data["match_id"] = match_id
    return jsonify({"status": "✅ Match IDs updated successfully"}), 200


@app.route('/overlay')
def overlay():
    return render_template("overlay.html")


@app.route('/draft')
def draft_state():
    return jsonify(current_data)


@app.route('/data')
def data():
    bounty_id = current_data.get("bounty_id") or request.args.get("bountyId")
    match_id = current_data.get("match_id") or request.args.get("matchId")

    if not bounty_id or not match_id:
        return jsonify({"error": "Missing bountyId or matchId"}), 400

    try:
        url = f"{MATCHERINO_API}?bountyId={bounty_id}&matchIds={match_id}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        return jsonify({"error": f"❌ Failed to fetch match data: {str(e)}"}), 400

    # Handle empty data
    if not result or "matches" not in result["body"]:
        return jsonify({"error": "⚠️ No match data returned from Matcherino API"}), 404

    match = result["body"]["matches"][0]

    # Extract team info (entrantA, entrantB)
    teams = []
    entrant_a = match.get("entrantA", {})
    entrant_b = match.get("entrantB", {})
    teams.append({
        "name": f"Team A ({entrant_a.get('entrantId', '?')})",
        "score": entrant_a.get("score", 0),
    })
    teams.append({
        "name": f"Team B ({entrant_b.get('entrantId', '?')})",
        "score": entrant_b.get("score", 0),
    })

    # Dummy draft placeholders (until live picks)
    bans = ["Crow", "Fang"]
    picks = ["Gus", "Max", "Poco"]

    # Map info (static fallback until map field is known)
    map_name = "Hard Rock Mine"
    try:
        maps_resp = requests.get(BRAWLIFY_API)
        maps_resp.raise_for_status()
        maps_list = maps_resp.json()
        map_data = next((m for m in maps_list if m["name"].lower() == map_name.lower()), {"name": map_name})
    except Exception:
        map_data = {"name": map_name}

    current_data.update({
        "bounty_id": bounty_id,
        "match_id": match_id,
        "teams": teams,
        "map": map_data,
        "bans": bans,
        "picks": picks,
    })

    return jsonify(current_data)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
