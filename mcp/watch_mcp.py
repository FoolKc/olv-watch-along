"""OLV Watch-Along MCP server: get_watching, control_video, play_on_youtube.

Open-LLM-VTuber starts this file as a separate process (stdio) for each session.
No state is kept here; everything is read from the bridge (127.0.0.1:12450).
Note: stdout is the MCP channel, so never print() here.

Tool descriptions only say what each tool does. How the character should talk about the
results (tool first, then a short in-character reaction) belongs in your prompt:
see prompts/tool_rules.txt.

Safety:
- Video titles, descriptions and captions are written by strangers. They are cleaned so they
  cannot open fake tags, and wrapped in <video_data> so the prompt can treat them as data.
- While the character is answering a bridge event (a turn the user did not start), the
  playback tools refuse to run, so text inside a video cannot make the character act.
"""
import json
import time
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP

BRIDGE = "http://127.0.0.1:12450"

# Ignore system proxy settings so local requests are not routed through a proxy.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

mcp = FastMCP("watch-along")

BLOCKED = ("Not allowed in this turn: it was started by the watch-along system, not by the user. "
           "Do not retry; just reply without tools.")


def _bridge(path: str, body: dict | None = None, timeout: float = 3) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BRIDGE + path, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        with _opener.open(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)
        except Exception:
            return {"ok": False, "error": f"HTTP {e.code}"}


def _system_turn() -> bool:
    try:
        return bool(_bridge("/turn", timeout=2).get("system_turn"))
    except Exception:
        return False                            # bridge not running: no events either


def _safe(value) -> str:
    """Text from the video: make sure it cannot open fake tags or fake events."""
    text = " ".join(str(value or "").split())
    return text.replace("<", "(").replace(">", ")").replace("[", "(").replace("]", ")")


def _wait_result(cid: int, tries: int) -> str | None:
    for _ in range(tries):
        time.sleep(0.5)
        try:
            result = _bridge(f"/command/result?id={cid}", timeout=2).get("result")
        except Exception:
            result = None
        if result:
            return result
    return None


def _send_command(body: dict) -> tuple[dict | None, str | None]:
    try:
        r = _bridge("/command", body)
    except Exception:
        return None, "The watch bridge is not running, so nothing happened in the browser."
    if not r.get("ok"):
        err = r.get("error", "")
        if "not connected" in err:
            return None, "The browser extension is not connected, so nothing happened in the browser."
        return None, f"Could not send the command: {err}"
    return r, None


@mcp.tool()
def get_watching() -> str:
    """Get what the user is watching in their web browser right now: site, title, channel,
    playing or paused, the video description and the subtitles on screen."""
    try:
        s = _bridge("/state", timeout=2)
    except Exception:
        return "The watch bridge is not running, so it is unknown what the user is watching."
    if not s.get("watching"):
        return "The user is not watching anything in the browser right now."

    lines = [f"Title: {_safe(s.get('title'))}"]
    if s.get("site"):
        lines.append(f"Site: {_safe(s['site'])}")
    if s.get("channel"):
        lines.append(f"Channel: {_safe(s['channel'])}")
    if s.get("paused") is not None:
        lines.append("Status: paused" if s["paused"] else "Status: playing")
    data = []
    if s.get("description"):
        data.append(f"Description: {_safe(s['description'])}")
    if s.get("subtitle"):
        data.append(f"Subtitles on screen (most recent last): {_safe(s['subtitle'])}")
    if data:
        lines += ["<video_data>", *data, "</video_data>"]
    else:
        lines.append("Subtitles: none (captions are off or nobody is talking).")
    age_min = s.get("age_seconds", 0) // 60
    if age_min >= 30:
        lines.append(f"(Last update was {age_min} minutes ago; they may have stopped watching.)")
    return "\n".join(lines)


@mcp.tool()
def control_video(action: str) -> str:
    """Control the video playing in the user's browser.
    action: "pause", "play" (start or resume what is already open), "next", "previous",
    "louder" (volume up) or "quieter" (volume down)."""
    if _system_turn():
        return BLOCKED
    action = (action or "").strip().lower()
    aliases = {"resume": "play", "continue": "play", "start": "play", "stop": "pause", "skip": "next",
               "back": "previous", "prev": "previous", "up": "louder", "volume_up": "louder",
               "down": "quieter", "volume_down": "quieter"}
    action = aliases.get(action, action)
    r, err = _send_command({"action": action})
    if err:
        return err
    result = _wait_result(r["id"], 12)
    return f"Result: {result}." if result else "The command was sent, but the browser did not confirm it yet."


@mcp.tool()
def play_on_youtube(query: str) -> str:
    """Search YouTube in the user's browser and play the first result.
    query: what to search, for example "artist name song title"."""
    if _system_turn():
        return BLOCKED
    query = " ".join((query or "").split())[:150]
    if not query:
        return "No search query was given."
    r, err = _send_command({"action": "search", "query": query})
    if err:
        return err
    result = _wait_result(r["id"], 30)
    return f"Result: {result}." if result else f"Searched YouTube for {query}, but the browser did not confirm what is playing yet."


if __name__ == "__main__":
    mcp.run()
