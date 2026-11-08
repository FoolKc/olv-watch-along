"""OLV Watch-Along bridge.

Keeps in memory what the user is watching in the browser and now and then asks
the Open-LLM-VTuber character for a short comment. Listens on 127.0.0.1 only.
  POST /update          -> new state (from the extension, JSON)
  POST /clear           -> forget the state
  GET  /state           -> latest state (read by the MCP server)
  GET  /comments        -> spontaneous comment status
  POST /comments        -> {"enabled": true/false} to turn comments on/off
  GET/POST /command     -> playback command queue (MCP server -> extension)
  GET/POST /command/result
Comments are sent to the Open-LLM-VTuber proxy (ws://127.0.0.1:12393/proxy-ws) as
text-input; every comment is one LLM request.

Optional environment variables:
  WATCH_USER_NAME  how the character should refer to you in system notes (default: "the user")
  OLV_DIR          Open-LLM-VTuber folder, used only for the mic mute flag (default: current folder)
"""
import asyncio
import json
import os
import time
from datetime import date
from pathlib import Path

import aiohttp
from aiohttp import web

HOST, PORT = "127.0.0.1", 12450
FIELDS = ("site", "title", "channel", "url", "paused", "subtitle", "description")
MAX_LEN = 500
USER = os.environ.get("WATCH_USER_NAME", "the user")

# --- Spontaneous comment settings ---
COMMENTS_ENABLED = True       # on at startup?
COOLDOWN_S = 300              # at least 5 minutes between caption comments on the same video
NEW_VIDEO_SETTLE_S = 15       # comment on each new video 15 s after it opens
QUIET_AFTER_USER_S = 45       # no comments for 45 s after the user talks to the character
STALE_S = 150                 # no update from the extension for 150 s = not watching
DAILY_CAP = 60                # max comments per day
RESPECT_MUTE = False          # True: no comments while the mic mute flag exists (F8)
MUTE_FLAG = Path(os.environ.get("OLV_DIR", ".")) / "mic_muted.flag"
PROXY_URL = "ws://127.0.0.1:12393/proxy-ws"
REPLY_TIMEOUT_S = 90          # clear the queue if a comment does not finish in 90 s (e.g. frontend closed)
CHECKINS_ENABLED = True       # character speaks up after a long silence
IDLE_CHECKIN_S = 600          # after 10 minutes of silence
CHECKIN_REPEAT_S = 1800       # if there is no answer, at most every 30 minutes

state: dict = {}
rt = {
    "ws": None,
    "enabled": COMMENTS_ENABLED,
    "busy": False, "busy_since": 0.0,
    "last_user": 0.0,
    "last_comment": 0.0,
    "last_key": None, "last_subtitle": "",
    "changed_at": 0.0, "pending_since": 0.0,
    "last_char": 0.0, "last_checkin": 0.0, "connected_at": 0.0,
    "day": date.today().isoformat(), "count": 0,
    "command": None, "cmd_id": 0, "ext_seen": 0.0, "results": {},
}


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def from_website(request: web.Request) -> bool:
    return request.headers.get("Origin", "").startswith(("http://", "https://"))


def deny() -> web.Response:
    return web.json_response({"ok": False, "error": "forbidden"}, status=403)


# ---------------- HTTP ----------------
async def update(request: web.Request) -> web.Response:
    # Random websites open in the browser must not be able to write here.
    if request.content_type != "application/json":
        return web.json_response({"ok": False, "error": "application/json required"}, status=415)
    if from_website(request):
        return deny()
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "JSON expected"}, status=400)
    if not isinstance(data, dict) or not data.get("title"):
        return web.json_response({"ok": False, "error": "'title' required"}, status=400)

    new = {}
    for key in FIELDS:
        if key in data:
            value = data[key]
            new[key] = value[:MAX_LEN] if isinstance(value, str) else value
    new["updated_at"] = time.time()

    if (new.get("url"), new.get("title")) != (state.get("url"), state.get("title")):
        rt["changed_at"] = new["updated_at"]
        log(f"[new video] {new.get('site', '?')} | {new.get('title')}")
    state.clear()
    state.update(new)
    return web.json_response({"ok": True})


async def clear(request: web.Request) -> web.Response:
    if from_website(request):
        return deny()
    state.clear()
    log("[cleared]")
    return web.json_response({"ok": True})


async def get_state(request: web.Request) -> web.Response:
    if not state:
        return web.json_response({"watching": False})
    age = int(time.time() - state["updated_at"])
    return web.json_response({"watching": True, "age_seconds": age, **state})


async def comments(request: web.Request) -> web.Response:
    if request.method == "POST":
        if from_website(request) or request.content_type != "application/json":
            return deny()
        data = await request.json()
        rt["enabled"] = bool(data.get("enabled"))
        log(f"[comments] {'ON' if rt['enabled'] else 'OFF'}")
    reset_day()
    return web.json_response({
        "enabled": rt["enabled"],
        "connected_to_character": rt["ws"] is not None,
        "today": rt["count"], "daily_cap": DAILY_CAP,
        "cooldown_s": COOLDOWN_S,
        "last_comment_ago_s": int(time.time() - rt["last_comment"]) if rt["last_comment"] else None,
    })


# ---------------- Proxy connection ----------------
def handle_proxy_message(data: dict) -> None:
    kind = data.get("type")
    if kind == "user-input-transcription":
        rt["last_user"] = time.time()          # the user spoke or typed
    elif kind == "control":
        if data.get("text") == "conversation-chain-start":
            rt["busy"], rt["busy_since"] = True, time.time()
        elif data.get("text") == "conversation-chain-end":
            rt["busy"], rt["pending_since"], rt["last_char"] = False, 0.0, time.time()


async def proxy_loop(app: web.Application) -> None:
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.ws_connect(PROXY_URL, heartbeat=30, max_msg_size=0) as ws:
                    rt["ws"] = ws
                    rt["connected_at"] = time.time()
                    log("[character] connected to the proxy")
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                handle_proxy_message(json.loads(msg.data))
                            except Exception:
                                pass
                        elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                            break
                log("[character] proxy connection lost")
            except asyncio.CancelledError:
                raise
            except Exception:
                pass                            # Open-LLM-VTuber is not up yet; retry quietly
            rt["ws"] = None
            await asyncio.sleep(10)


# ---------------- Comment gate ----------------
def reset_day() -> None:
    today = date.today().isoformat()
    if rt["day"] != today:
        rt["day"], rt["count"] = today, 0


def build_prompt(s: dict, new_video: bool) -> str:
    who = f'"{s.get("title")}"' + (f' by {s["channel"]}' if s.get("channel") else "")
    note = f"(Watch-along note from the system, not typed by {USER}.)"
    if new_video:
        text = f"{note} {USER} just started watching {who} on {s.get('site', 'the web')}."
    else:
        text = f"{note} {USER} is still watching {who} on {s.get('site', 'the web')}."
    if s.get("description"):
        text += f" Description: {s['description']}"
    if s.get("subtitle"):
        text += f" Recent subtitles: {s['subtitle']}"
    text += (" Make one short spontaneous comment, one or two sentences, like you are watching it together."
             " Do not repeat the title word for word. No spoilers. Do not use any tools or search the web.")
    return text


async def comment_loop(app: web.Application) -> None:
    while True:
        await asyncio.sleep(5)
        try:
            await maybe_comment()
            await maybe_checkin()
        except Exception as e:
            log(f"[error] {e}")


async def maybe_comment() -> None:
    now = time.time()
    reset_day()
    if rt["busy"] and now - rt["busy_since"] > 180:
        rt["busy"] = False                     # stuck: let go
    ws = rt["ws"]
    if rt["pending_since"] and ws is not None and now - rt["pending_since"] > REPLY_TIMEOUT_S:
        await ws.send_json({"type": "interrupt-signal", "text": ""})
        rt["pending_since"], rt["busy"] = 0.0, False
        log("[character] comment reply did not finish (frontend closed?), queue cleared")
        return
    if not rt["enabled"] or ws is None or rt["busy"] or rt["pending_since"]:
        return
    if RESPECT_MUTE and MUTE_FLAG.exists():
        return
    if rt["count"] >= DAILY_CAP:
        return
    if not state or state.get("paused") or now - state["updated_at"] > STALE_S:
        return
    if now - rt["last_user"] < QUIET_AFTER_USER_S:
        return

    key = state.get("url") or state.get("title")
    new_video = key != rt["last_key"]
    subtitle = state.get("subtitle", "")
    if new_video:
        if now - rt["changed_at"] < NEW_VIDEO_SETTLE_S:
            return
    elif now - rt["last_comment"] < COOLDOWN_S or not subtitle or subtitle == rt["last_subtitle"]:
        return                                  # same video, nothing new

    snapshot = dict(state)
    await ws.send_json({"type": "text-input", "text": build_prompt(snapshot, new_video)})
    rt["last_comment"], rt["last_key"], rt["last_subtitle"] = now, key, subtitle
    rt["pending_since"] = now
    rt["count"] += 1
    log(f"[comment] requested ({'new video' if new_video else 'new captions'}) {rt['count']}/{DAILY_CAP} | {snapshot.get('title')}")


# ---------------- Idle check-in ----------------
async def maybe_checkin() -> None:
    now = time.time()
    ws = rt["ws"]
    if not CHECKINS_ENABLED or not rt["enabled"] or ws is None or rt["busy"] or rt["pending_since"]:
        return
    if rt["count"] >= DAILY_CAP:
        return
    quiet_since = max(rt["last_user"], rt["last_char"], rt["connected_at"])
    if now - quiet_since < IDLE_CHECKIN_S:
        return
    if rt["last_checkin"] and now - rt["last_checkin"] < CHECKIN_REPEAT_S:
        return
    minutes = int((now - quiet_since) // 60)
    text = (f"(System note, not typed by {USER}.) {USER} has been quiet for about {minutes} minutes."
            " Check in gently in one or two short sentences: ask how they are doing or what they are up to,"
            " in your own words. Do not mention this note. Do not use any tools.")
    await ws.send_json({"type": "text-input", "text": text})
    rt["last_checkin"] = rt["pending_since"] = now
    rt["count"] += 1
    log(f"[check-in] {minutes} min of silence, character checks in {rt['count']}/{DAILY_CAP}")


# ---------------- Playback control ----------------
ACTIONS = ("pause", "play", "next", "previous", "search", "louder", "quieter")
COMMAND_TTL_S = 15            # a command expires if the extension does not pick it up in 15 s
EXT_SEEN_S = 10               # extension has not polled in the last 10 s = browser not connected


async def command(request: web.Request) -> web.Response:
    if from_website(request):
        return deny()
    now = time.time()
    if request.method == "POST":               # from the MCP server
        if request.content_type != "application/json":
            return deny()
        try:
            data = await request.json()
        except Exception:
            data = None
        action = data.get("action") if isinstance(data, dict) else None
        if action not in ACTIONS:
            return web.json_response({"ok": False, "error": f"unknown action: {action}"}, status=400)
        query = str(data.get("query", "")).strip()[:150] if action == "search" else ""
        if action == "search" and not query:
            return web.json_response({"ok": False, "error": "search needs a query"}, status=400)
        if now - rt["ext_seen"] > EXT_SEEN_S:
            return web.json_response({"ok": False, "error": "browser extension not connected"})
        rt["cmd_id"] += 1
        rt["command"] = {"id": rt["cmd_id"], "action": action, "query": query, "at": now}
        log(f"[command] #{rt['cmd_id']} {action} {query}".rstrip())
        return web.json_response({"ok": True, "id": rt["cmd_id"]})
    if request.headers.get("X-Watch-Along") != "1":  # GET: extension only
        return deny()
    rt["ext_seen"] = now
    cmd, rt["command"] = rt["command"], None
    if not cmd or now - cmd["at"] > COMMAND_TTL_S:
        return web.json_response({"command": None})
    return web.json_response({"command": {"id": cmd["id"], "action": cmd["action"], "query": cmd.get("query", "")}})


async def command_result(request: web.Request) -> web.Response:
    if from_website(request):
        return deny()
    if request.method == "POST":               # from the extension
        if request.content_type != "application/json":
            return deny()
        try:
            data = await request.json()
            cid, result = int(data.get("id")), str(data.get("result", ""))[:200]
        except Exception:
            return web.json_response({"ok": False, "error": "bad result"}, status=400)
        rt["results"][cid] = result
        for old in [k for k in rt["results"] if k < cid - 20]:
            del rt["results"][old]
        log(f"[command] #{cid} result: {result}")
        return web.json_response({"ok": True})
    try:
        cid = int(request.query.get("id", "0"))
    except ValueError:
        cid = 0
    return web.json_response({"id": cid, "result": rt["results"].get(cid)})


# ---------------- Startup ----------------
async def start_background(app: web.Application) -> None:
    app["tasks"] = [asyncio.create_task(proxy_loop(app)), asyncio.create_task(comment_loop(app))]


async def stop_background(app: web.Application) -> None:
    for task in app["tasks"]:
        task.cancel()


def main() -> None:
    app = web.Application()
    app.add_routes([
        web.post("/update", update),
        web.post("/clear", clear),
        web.get("/state", get_state),
        web.get("/comments", comments),
        web.post("/comments", comments),
        web.get("/command", command),
        web.post("/command", command),
        web.get("/command/result", command_result),
        web.post("/command/result", command_result),
    ])
    app.on_startup.append(start_background)
    app.on_cleanup.append(stop_background)
    log(f"Watch-along bridge: http://{HOST}:{PORT}  (Ctrl+C to stop)")
    log(f"Spontaneous comments: {'ON' if rt['enabled'] else 'OFF'}, {NEW_VIDEO_SETTLE_S} s after each new video, "
        f"captions every {COOLDOWN_S // 60} min, max {DAILY_CAP} per day")
    log(f"Idle check-in: {'ON' if CHECKINS_ENABLED else 'OFF'}, after {IDLE_CHECKIN_S // 60} min of silence, "
        f"at most every {CHECKIN_REPEAT_S // 60} min")
    web.run_app(app, host=HOST, port=PORT, print=None)


if __name__ == "__main__":
    main()
