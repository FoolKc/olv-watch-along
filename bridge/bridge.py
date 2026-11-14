"""OLV Watch-Along bridge.

Keeps in memory what the user is watching in the browser and now and then sends the
Open-LLM-VTuber character an EVENT. No personality text lives here: the character only
receives "[EVENT ...]" messages, and how to react is written in your prompt
(see prompts/system_rules.txt). Listens on 127.0.0.1 only.
  POST /update            -> new state (from the extension, JSON)
  POST /clear             -> forget the state
  GET  /state             -> latest state (read by the MCP server)
  GET  /comments          -> spontaneous comment status
  POST /comments          -> {"enabled": true/false}
  GET  /turn              -> is the current turn started by the bridge? (the MCP server locks
                             side-effect tools during those turns)
  GET/POST /command       -> playback command queue (MCP server -> extension)
  GET/POST /command/result
Every event is one LLM request.

Optional environment variables:
  WATCH_USER_NAME  how events refer to you (default: "the user")
  OLV_DIR          Open-LLM-VTuber folder, used only for the mic mute flag (default: current folder)
"""
import asyncio
import json
import os
import re
import time
from datetime import date
from pathlib import Path

import aiohttp
from aiohttp import web

HOST, PORT = "127.0.0.1", 12450
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
EXT_HEADER = "X-Watch-Along"                       # sent by the extension when it asks for commands
TEXT_FIELDS = ("site", "title", "channel", "url", "subtitle", "description")
MAX_LEN = 500
USER = os.environ.get("WATCH_USER_NAME", "the user")

# --- Spontaneous comment settings ---
COMMENTS_ENABLED = True       # on at startup?
COOLDOWN_S = 300              # at least 5 minutes between caption comments on the same video
NEW_VIDEO_SETTLE_S = 15       # comment on each new video 15 s after it opens
QUIET_AFTER_USER_S = 45       # no comments for 45 s after the user talks to the character
STALE_S = 150                 # no update from the extension for 150 s = not watching
DAILY_CAP = 60                # max events per day (comments + check-ins)
RESPECT_MUTE = False          # True: no events while the mic mute flag exists (F8)
MUTE_FLAG = Path(os.environ.get("OLV_DIR", ".")) / "mic_muted.flag"
PROXY_URL = "ws://127.0.0.1:12393/proxy-ws"
REPLY_TIMEOUT_S = 90          # clear the queue if a reply does not finish in 90 s (e.g. frontend closed)

# --- Idle check-in settings ---
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
    "last_event": 0.0, "event_started": False, "release_on_start": False,
}


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def deny() -> web.Response:
    return web.json_response({"ok": False, "error": "forbidden"}, status=403)


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_text(value: str) -> str:
    """Drop control characters and collapse whitespace."""
    return " ".join(_CONTROL.sub(" ", value).split())


def for_prompt(value) -> str:
    """Text from the video is written by strangers: make sure it cannot open fake tags or fake events."""
    text = clean_text(str(value or ""))
    return text.replace("<", "(").replace(">", ")").replace("[", "(").replace("]", ")")


# ---------------- Protection ----------------
@web.middleware
async def guard(request: web.Request, handler):
    # 1) DNS rebinding: reject requests whose Host header is not 127.0.0.1/localhost.
    if request.host not in ALLOWED_HOSTS:
        return deny()
    # 2) Websites open in the browser (and sandboxed "null" origins) must not get in. The extension's
    #    origin is moz-extension://; the MCP server and PowerShell send no Origin at all.
    origin = request.headers.get("Origin")
    if origin is not None and not origin.startswith(("moz-extension://", "chrome-extension://")):
        return deny()
    return await handler(request)


async def read_json(request: web.Request):
    if request.content_type != "application/json":
        return None
    try:
        return await request.json()
    except Exception:
        return None


# ---------------- HTTP ----------------
async def update(request: web.Request) -> web.Response:
    data = await read_json(request)
    if not isinstance(data, dict) or not isinstance(data.get("title"), str) or not data["title"].strip():
        return web.json_response({"ok": False, "error": "JSON with 'title' required"}, status=400)

    new = {}
    for key in TEXT_FIELDS:
        if isinstance(data.get(key), str):
            new[key] = clean_text(data[key])[:MAX_LEN]
    if isinstance(data.get("paused"), bool):
        new["paused"] = data["paused"]
    new["updated_at"] = time.time()

    if (new.get("url"), new.get("title")) != (state.get("url"), state.get("title")):
        rt["changed_at"] = new["updated_at"]
        log(f"[new video] {new.get('site', '?')} | {new.get('title')}")
    state.clear()
    state.update(new)
    return web.json_response({"ok": True})


async def clear(request: web.Request) -> web.Response:
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
        data = await read_json(request)
        if not isinstance(data, dict) or "enabled" not in data:
            return web.json_response({"ok": False, "error": 'expected {"enabled": true/false}'}, status=400)
        rt["enabled"] = bool(data["enabled"])
        log(f"[comments] {'ON' if rt['enabled'] else 'OFF'}")
    reset_day()
    return web.json_response({
        "enabled": rt["enabled"],
        "connected_to_character": rt["ws"] is not None,
        "today": rt["count"], "daily_cap": DAILY_CAP,
        "cooldown_s": COOLDOWN_S,
        "last_comment_ago_s": int(time.time() - rt["last_comment"]) if rt["last_comment"] else None,
    })


async def turn(request: web.Request) -> web.Response:
    """Asked by the MCP server: is the character answering a bridge event right now? If so, no
    side-effect tools. last_event_ago_s: seconds since the last event (event text stays in the
    chat history, so tools that change things can treat that time as untrusted)."""
    return web.json_response({
        "system_turn": bool(rt["pending_since"]),
        "last_event_ago_s": int(time.time() - rt["last_event"]) if rt["last_event"] else None,
    })


# ---------------- Proxy connection ----------------
def handle_proxy_message(data: dict) -> None:
    kind = data.get("type")
    if kind == "user-input-transcription":
        rt["last_user"] = time.time()
        if rt["pending_since"] and rt["event_started"]:
            rt["release_on_start"] = True      # unlock when the user's own turn STARTS, not mid-event
    elif kind == "control":
        if data.get("text") == "conversation-chain-start":
            rt["busy"], rt["busy_since"] = True, time.time()
            if rt["pending_since"] and not rt["event_started"]:
                rt["event_started"] = True     # this chain is the bridge's event
            elif rt["pending_since"] and rt["release_on_start"]:
                rt["pending_since"] = 0.0      # this chain is the user's: tools unlocked
                rt["event_started"] = rt["release_on_start"] = False
        elif data.get("text") == "conversation-chain-end":
            rt["busy"], rt["pending_since"], rt["last_char"] = False, 0.0, time.time()
            rt["event_started"] = rt["release_on_start"] = False


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


# ---------------- Events ----------------
EVENT_HEAD = f"(sent by the watch-along system, not typed by {USER})"


def reset_day() -> None:
    today = date.today().isoformat()
    if rt["day"] != today:
        rt["day"], rt["count"] = today, 0


def watch_event(s: dict, new_video: bool) -> str:
    lines = [f"[EVENT {'new_video' if new_video else 'captions'}] {EVENT_HEAD}",
             f"site: {for_prompt(s.get('site') or 'web')}",
             f"title: {for_prompt(s.get('title'))}"]
    if s.get("channel"):
        lines.append(f"channel: {for_prompt(s['channel'])}")
    data = []
    if s.get("description"):
        data.append(f"description: {for_prompt(s['description'])}")
    if s.get("subtitle"):
        data.append(f"recent subtitles: {for_prompt(s['subtitle'])}")
    if data:
        lines += ["<video_data>", *data, "</video_data>"]
    return "\n".join(lines)


def idle_event(minutes: int) -> str:
    return f"[EVENT idle] {EVENT_HEAD}\nquiet_minutes: {minutes}"


async def send_event(ws, text: str) -> None:
    await ws.send_json({"type": "text-input", "text": text})
    rt["pending_since"] = rt["last_event"] = time.time()
    rt["event_started"] = rt["release_on_start"] = False
    rt["count"] += 1


async def comment_loop(app: web.Application) -> None:
    while True:
        await asyncio.sleep(5)
        try:
            await maybe_comment()
            await maybe_checkin()
        except Exception as e:
            log(f"[error] {e}")


def can_send(now: float):
    """Shared gate: may an event be sent now? Returns the websocket if so."""
    ws = rt["ws"]
    if not rt["enabled"] or ws is None or rt["busy"] or rt["pending_since"]:
        return None
    if RESPECT_MUTE and MUTE_FLAG.exists():
        return None
    if rt["count"] >= DAILY_CAP:
        return None
    return ws


async def maybe_comment() -> None:
    now = time.time()
    reset_day()
    if rt["busy"] and now - rt["busy_since"] > 180:
        rt["busy"] = False                     # stuck: let go
    ws = rt["ws"]
    if rt["pending_since"] and ws is not None and now - rt["pending_since"] > REPLY_TIMEOUT_S:
        await ws.send_json({"type": "interrupt-signal", "text": ""})
        rt["pending_since"], rt["busy"] = 0.0, False
        rt["event_started"] = rt["release_on_start"] = False
        log("[character] reply did not finish (frontend closed?), queue cleared")
        return
    ws = can_send(now)
    if ws is None:
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
    await send_event(ws, watch_event(snapshot, new_video))
    rt["last_comment"], rt["last_key"], rt["last_subtitle"] = now, key, subtitle
    log(f"[comment] requested ({'new video' if new_video else 'new captions'}) {rt['count']}/{DAILY_CAP} | {snapshot.get('title')}")


async def maybe_checkin() -> None:
    now = time.time()
    if not CHECKINS_ENABLED:
        return
    ws = can_send(now)
    if ws is None:
        return
    quiet_since = max(rt["last_user"], rt["last_char"], rt["connected_at"])
    if now - quiet_since < IDLE_CHECKIN_S:
        return
    if rt["last_checkin"] and now - rt["last_checkin"] < CHECKIN_REPEAT_S:
        return
    minutes = int((now - quiet_since) // 60)
    await send_event(ws, idle_event(minutes))
    rt["last_checkin"] = now
    log(f"[check-in] {minutes} min of silence {rt['count']}/{DAILY_CAP}")


# ---------------- Playback control ----------------
ACTIONS = ("pause", "play", "next", "previous", "search", "quieter", "louder")
COMMAND_TTL_S = 15            # a command the extension does not pick up within 15 s expires
EXT_SEEN_S = 10               # no poll from the extension in 10 s = browser not connected


async def command(request: web.Request) -> web.Response:
    now = time.time()
    if request.method == "POST":               # from the MCP server
        data = await read_json(request)
        action = data.get("action") if isinstance(data, dict) else None
        if action not in ACTIONS:
            return web.json_response({"ok": False, "error": f"unknown action: {action}"}, status=400)
        query = clean_text(str(data.get("query", "")))[:150] if action == "search" else ""
        if action == "search" and not query:
            return web.json_response({"ok": False, "error": "search needs a query"}, status=400)
        if now - rt["ext_seen"] > EXT_SEEN_S:
            return web.json_response({"ok": False, "error": "browser extension not connected"})
        rt["cmd_id"] += 1
        rt["command"] = {"id": rt["cmd_id"], "action": action, "query": query, "at": now}
        log(f"[command] #{rt['cmd_id']} {action} {query}".rstrip())
        return web.json_response({"ok": True, "id": rt["cmd_id"]})
    if request.headers.get(EXT_HEADER) != "1":                        # GET: extension only
        return deny()
    rt["ext_seen"] = now
    cmd, rt["command"] = rt["command"], None
    if not cmd or now - cmd["at"] > COMMAND_TTL_S:
        return web.json_response({"command": None})
    return web.json_response({"command": {"id": cmd["id"], "action": cmd["action"], "query": cmd["query"]}})


async def command_result(request: web.Request) -> web.Response:
    if request.method == "POST":               # from the extension
        data = await read_json(request)
        try:
            cid, result = int(data.get("id")), clean_text(str(data.get("result", "")))[:200]
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
    app = web.Application(middlewares=[guard], client_max_size=64 * 1024)
    app.add_routes([
        web.post("/update", update),
        web.post("/clear", clear),
        web.get("/state", get_state),
        web.get("/comments", comments),
        web.post("/comments", comments),
        web.get("/turn", turn),
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
