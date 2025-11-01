from flask import Flask, jsonify, render_template, request
import requests
import os

app = Flask(__name__)

# --- API Endpoints ---
MATCHERINO_STATS_API = "https://api.matcherino.com/__api/games/brawlstars/match/stats"
MATCHERINO_FALLBACK_API = "https://matcherino.com/__api/bounties"
BRAWLIFY_API = "https://api.brawlapi.com/v1/maps"

# --- In-memory cache ---
current_data = {
    "bounty_id": None,
    "match_id": None,
    "teams": [],
    "map": {},
    "bans": [],
    "picks": [],
    "source": "none"  # To show if data came from stats or fallback
}


@app.route('/')
def index():
    return "✅ Transcending Void Overlay API is running and connected!"


# --- Control Panel Page ---
@app.route('/control')
def control_panel():
    return render_template("control.html")


# --- Update current match manually (from control panel) ---
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


# --- Control panel live polling ---
@app.route('/draft')
def draft_state():
    return jsonify(current_data)


# --- Main data fetcher ---
@app.route('/data')
def data():
    bounty_id = current_data.get("bounty_id") or request.args.get("bountyId")
    match_id = current_data.get("match_id") or request.args.get("matchId")

    if not bounty_id or not match_id:
        return jsonify({"error": "Missing bountyId or matchId"}), 400

    headers = {"User-Agent": "Mozilla/5.0"}

    # --- 1️⃣ Try Brawl Stars stats API first ---
    try:
        stats_url = f"{MATCHERINO_STATS_API}?bountyId={bounty_id}&matchIds={match_id}"
        stats_resp = requests.get(stats_url, headers=headers)
        stats_resp.raise_for_status()
        stats_data = stats_resp.json()
    except Exception as e:
        print(f"⚠️ Stats API failed: {e}")
        stats_data = []

    # --- 2️⃣ If stats API empty, fallback to bounty matches API ---
    match = None
    if stats_data and isinstance(stats_data, list) and len(stats_data) > 0:
        match = stats_data[0]
        current_data["source"] = "stats"
        print("✅ Using Brawl Stars stats API data.")
    else:
        print("⚠️ Stats API returned no data, using fallback.")
        try:
            fb_url = f"{MATCHERINO_FALLBACK_API}/{bounty_id}/matches"
            fb_resp = requests.get(fb_url, headers=headers)
            fb_resp.raise_for_status()
            all_matches = fb_resp.json()
            match = next((m for m in all_matches if str(m.get("id")) == str(match_id)), None)
            current_data["source"] = "fallback"
        except Exception as e:
            return jsonify({"error": f"❌ Fallback API also failed: {str(e)}"}), 400

    if not match:
        return jsonify({"error": "⚠️ No match data found from either API"}), 404

    # --- Extract Team Info ---
    teams = []
    if "teams" in match:
        for team in match.get("teams", []):
            teams.append({
                "name": team.get("name", "Unknown Team"),
                "players": [p.get("username", "Unknown") for p in team.get("players", [])]
            })
    else:
        # fallback legacy format
        entrant_a = match.get("entrantA", {})
        entrant_b = match.get("entrantB", {})
        teams = [
            {"name": entrant_a.get("name", f"Team A ({entrant_a.get('entrantId', '?')})"), "players": []},
            {"name": entrant_b.get("name", f"Team B ({entrant_b.get('entrantId', '?')})"), "players": []}
        ]

    # --- Extract Bans and Picks (if exist) ---
    bans = []
    picks = []
    for team in match.get("teams", []):
        bans.extend([b.get("brawler", "Unknown") for b in team.get("bans", []) if b])
        picks.extend([p.get("brawler", "Unknown") for p in team.get("picks", []) if p])

    # --- Map Info ---
    map_name = (
        match.get("map", {}).get("name")
        or match.get("map", "Hard Rock Mine")
    )

    try:
        maps_resp = requests.get(BRAWLIFY_API)
        maps_resp.raise_for_status()
        maps_list = maps_resp.json()
        map_data = next((m for m in maps_list if m["name"].lower() == map_name.lower()), {"name": map_name})
    except Exception:
        map_data = {"name": map_name}

    # --- Update cache ---
    current_data.update({
        "bounty_id": bounty_id,
        "match_id": match_id,
        "teams": teams,
        "map": map_data,
        "bans": bans,
        "picks": picks
    })

    return jsonify(current_data)


# --- Run Server ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
