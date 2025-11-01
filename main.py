# main.py
import os
import time
import asyncio
import requests
from fastapi import FastAPI, Request, Form
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.cors import CORSMiddleware
import json

# ---------- CONFIG ----------
MATCHERINO_BASE = "https://api.matcherino.com/__api/games/brawlstars/match/stats"
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "2"))  # seconds
CONTROL_SECRET = os.getenv("CONTROL_SECRET", "")      # optional control secret
PORT = int(os.getenv("PORT", "10000"))

# ---------- APP SETUP ----------
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ensure static folders exist
if not os.path.exists("static"):
    os.makedirs("static")
if not os.path.exists("static/assets"):
    os.makedirs("static/assets")

templates = Jinja2Templates(directory="static")
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

# ---------- STATE ----------
state = {
    "bounty_id": None,
    "match_id": None,
    "raw": None,
    "parsed": {
        "teamA": {"name": "", "players": [], "picks": [], "bans": []},
        "teamB": {"name": "", "players": [], "picks": [], "bans": []},
        "map": "", "mode": "", "status": "idle"
    },
    "previous_parsed": None,
    "last_polled": 0
}

# Optional ID->slug mapping (if Matcherino returns numeric brawler IDs)
ID_MAP_PATH = os.path.join("static", "assets", "id_to_slug.json")
if os.path.exists(ID_MAP_PATH):
    try:
        with open(ID_MAP_PATH, "r", encoding="utf-8") as f:
            ID_MAP = json.load(f)
    except Exception:
        ID_MAP = {}
else:
    ID_MAP = {}

# ---------- HELPERS ----------
def fetch_match_stats(bounty_id: str, match_id: str):
    params = {"bountyId": bounty_id, "matchIds": match_id}
    try:
        res = requests.get(MATCHERINO_BASE, params=params, timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print("fetch_match_stats error:", e)
        return None

def normalize_brawler_entry(item):
    """
    item may be:
     - a string name "Shelly"
     - a dict { "name": "...", "id": ...}
     - a numeric id (e.g., 23)
    We return a slug/name string for display & icon lookup.
    """
    if item is None:
        return ""
    # if dict, try common keys
    if isinstance(item, dict):
        return str(item.get("name") or item.get("brawlerName") or item.get("brawler") or item.get("id") or "")
    # numeric-like -> try ID map
    if isinstance(item, (int, float)) or (isinstance(item, str) and item.isdigit()):
        key = str(int(item))
        if key in ID_MAP:
            return ID_MAP[key]
        return key  # fallback to id string
    # otherwise string
    return str(item)

def try_extract_players(match):
    a = match.get("entrantA") or {}
    b = match.get("entrantB") or {}
    a_players = []
    b_players = []
    for k in ("players","entrantPlayers","playersList"):
        if k in a and isinstance(a[k], list):
            a_players = [p.get("name") if isinstance(p, dict) else str(p) for p in a[k]]
        if k in b and isinstance(b[k], list):
            b_players = [p.get("name") if isinstance(p, dict) else str(p) for p in b[k]]
    if not a_players:
        name = a.get("entrantName") or a.get("teamName") or a.get("entrantId")
        if name:
            a_players = [str(name)]
    if not b_players:
        name = b.get("entrantName") or b.get("teamName") or b.get("entrantId")
        if name:
            b_players = [str(name)]
    return a_players, b_players

def parse_match_json(raw_json, match_id):
    parsed = {"teamA": {"name": "", "players": [], "picks": [], "bans": []},
              "teamB": {"name": "", "players": [], "picks": [], "bans": []},
              "map": "", "mode": "", "status": "unknown"}
    try:
        body = raw_json.get("body", {}) if isinstance(raw_json, dict) else {}
        matches = body.get("matches", []) or []
        match_obj = None
        for m in matches:
            if str(m.get("id")) == str(match_id):
                match_obj = m; break
        if match_obj is None and matches:
            match_obj = matches[0]
        if not match_obj:
            return parsed

        parsed["status"] = match_obj.get("status", "unknown")
        entrantA = match_obj.get("entrantA") or {}
        entrantB = match_obj.get("entrantB") or {}
        parsed["teamA"]["name"] = entrantA.get("entrantName") or entrantA.get("teamName") or str(entrantA.get("entrantId") or "")
        parsed["teamB"]["name"] = entrantB.get("entrantName") or entrantB.get("teamName") or str(entrantB.get("entrantId") or "")

        a_players, b_players = try_extract_players(match_obj)
        parsed["teamA"]["players"] = a_players
        parsed["teamB"]["players"] = b_players

        # common picks/bans keys to try
        picks_keys = ("picks", "selected", "selectedBrawlers", "pickIds", "selected_brawlers")
        bans_keys  = ("bans", "banIds", "banned", "bannedBrawlers")

        def extract_for(key_list, side_labels):
            outA, outB = [], []
            for k in key_list:
                v = match_obj.get(k)
                if v:
                    if isinstance(v, dict):
                        outA = v.get(side_labels[0]) or v.get("entrantA") or v.get("teamA") or outA
                        outB = v.get(side_labels[1]) or v.get("entrantB") or v.get("teamB") or outB
                    elif isinstance(v, list):
                        # if a list present, assume it's the picks for teamA (fallback)
                        outA = v
                    break
            return outA, outB

        pA, pB = extract_for(picks_keys, ("teamA","teamB"))
        bA, bB = extract_for(bans_keys, ("teamA","teamB"))

        parsed["teamA"]["picks"] = [normalize_brawler_entry(x) for x in (pA or [])]
        parsed["teamB"]["picks"] = [normalize_brawler_entry(x) for x in (pB or [])]
        parsed["teamA"]["bans"]  = [normalize_brawler_entry(x) for x in (bA or [])]
        parsed["teamB"]["bans"]  = [normalize_brawler_entry(x) for x in (bB or [])]

        parsed["map"] = match_obj.get("map") or match_obj.get("stage") or ""
        parsed["mode"] = match_obj.get("mode") or ""
    except Exception as e:
        print("parse_match_json error:", e)
    return parsed

def diff_parsed(prev, curr):
    diff = {"teamA":{"new_picks":[],"new_bans":[]},"teamB":{"new_picks":[],"new_bans":[]}}
    if not prev:
        diff["teamA"]["new_picks"] = curr["teamA"]["picks"]
        diff["teamB"]["new_picks"] = curr["teamB"]["picks"]
        diff["teamA"]["new_bans"] = curr["teamA"]["bans"]
        diff["teamB"]["new_bans"] = curr["teamB"]["bans"]
        return diff
    def new_items(old, new):
        old_list = list(old or [])
        return [x for x in (new or []) if x not in old_list]
    diff["teamA"]["new_picks"] = new_items(prev["teamA"]["picks"], curr["teamA"]["picks"])
    diff["teamB"]["new_picks"] = new_items(prev["teamB"]["picks"], curr["teamB"]["picks"])
    diff["teamA"]["new_bans"] = new_items(prev["teamA"]["bans"], curr["teamA"]["bans"])
    diff["teamB"]["new_bans"] = new_items(prev["teamB"]["bans"], curr["teamB"]["bans"])
    return diff

# ---------- BACKGROUND POLLER ----------
async def poller():
    while True:
        try:
            b = state.get("bounty_id"); m = state.get("match_id")
            if b and m:
                raw = fetch_match_stats(b, m)
                if raw:
                    state["raw"] = raw
                    parsed = parse_match_json(raw, m)
                    prev = state.get("parsed")
                    diff = diff_parsed(prev, parsed)
                    state["previous_parsed"] = state["parsed"]
                    state["parsed"] = parsed
                    state["parsed"]["_diff"] = diff
                    state["last_polled"] = time.time()
        except Exception as e:
            print("poller loop error:", e)
        await asyncio.sleep(POLL_INTERVAL)

@app.on_event("startup")
async def startup():
    loop = asyncio.get_event_loop()
    loop.create_task(poller())

# ---------- ROUTES ----------
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/draft")
def get_draft():
    # return parsed state for overlay
    return JSONResponse(state["parsed"])

@app.post("/set_match")
def set_match(match_id: str = Form(...), bounty_id: str = Form(...), secret: str = Form(None)):
    if CONTROL_SECRET and secret != CONTROL_SECRET:
        return JSONResponse({"error":"unauthorized"}, status_code=401)
    state["bounty_id"] = str(bounty_id)
    state["match_id"]  = str(match_id)
    # immediate fetch to update state
    raw = fetch_match_stats(state["bounty_id"], state["match_id"])
    if raw:
        state["raw"] = raw
        parsed = parse_match_json(raw, state["match_id"])
        state["previous_parsed"] = state["parsed"]
        state["parsed"] = parsed
        state["parsed"]["_diff"] = diff_parsed(state.get("previous_parsed"), parsed)
    return RedirectResponse(url="/control", status_code=302)

@app.get("/overlay", response_class=HTMLResponse)
def overlay_page(request: Request):
    path = os.path.join("static", "overlay.html")
    if not os.path.exists(path):
        return HTMLResponse("<h3>Overlay not found (static/overlay.html)</h3>", status_code=404)
    return templates.TemplateResponse("overlay.html", {"request": request})

@app.get("/control", response_class=HTMLResponse)
def control_page(request: Request):
    path = os.path.join("static", "control.html")
    if not os.path.exists(path):
        return HTMLResponse("<h3>Control page not found (static/control.html)</h3>", status_code=404)
    return templates.TemplateResponse("control.html", {"request": request, "state": state})
