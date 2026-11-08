"""OLV Watch-Along MCP server: get_watching, control_video, play_on_youtube.

Open-LLM-VTuber starts this file as a separate process (stdio) for each session.
No state is kept here; everything is read from the bridge (127.0.0.1:12450).
Note: stdout is the MCP channel, so never print() here.
"""
import json
import time
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP

BRIDGE_URL = "http://127.0.0.1:12450/state"
COMMAND_URL = "http://127.0.0.1:12450/command"
RESULT_URL = "http://127.0.0.1:12450/command/result"

# Ignore system proxy settings so local requests are not routed through a proxy.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

mcp = FastMCP("watch-along")


@mcp.tool()
def get_watching() -> str:
    """Get what the user is watching in their web browser right now: site, title, channel,
    playing or paused, the video description, and the subtitles currently on screen.
    Use this when the user asks what they are watching, or asks what you think about the video.
    Do not just repeat the title. Use the description, the subtitles and your own knowledge
    to say what the video is about and give your own short reaction or vibe check, in your
    usual style. No spoilers. Search the web only if you really do not recognize it or the user
    asks you to look it up: one search with max_results 3, and do not fetch pages unless they
    ask for details."""
    try:
        with _opener.open(BRIDGE_URL, timeout=2) as resp:
            s = json.load(resp)
    except Exception:
        return "The watch bridge is not running, so you don't know what the user is watching right now."

    if not s.get("watching"):
        return "The user is not watching anything in the browser right now."

    lines = [f"Title: {s.get('title')}"]
    if s.get("site"):
        lines.append(f"Site: {s['site']}")
    if s.get("channel"):
        lines.append(f"Channel: {s['channel']}")
    if s.get("paused") is not None:
        lines.append("Status: paused" if s["paused"] else "Status: playing")
    if s.get("description"):
        lines.append(f"Description: {s['description']}")
    if s.get("subtitle"):
        lines.append(f"Subtitles on screen (most recent last): {s['subtitle']}")
    else:
        lines.append("Subtitles: none (captions are off or nobody is talking).")

    age_min = s.get("age_seconds", 0) // 60
    if age_min >= 30:
        lines.append(f"(Last update was {age_min} minutes ago; they may have stopped watching.)")
    return "\n".join(lines)


@mcp.tool()
def control_video(action: str) -> str:
    """Control the YouTube video the user is watching in their browser.
    action must be one of: "pause", "play" (start or resume the video that is already open), "next" (skip to the next video), "previous", "louder" (turn the volume up), "quieter" (turn the volume down).
    Use this when the user asks you (in any language) to pause, play, start, resume, unpause, skip, go back, or turn the volume up or down. "Start the music/video" means action "play". IMPORTANT: every new request needs a new call to this tool, even if you did the same thing a moment ago. Never say you paused, played, skipped, went back or changed the volume unless you called this tool in this same reply; if you did not call it, nothing happened in the browser.
    After it returns, tell them in one short sentence what happened, in your usual style.
    If it did not work, say so honestly. Do not call it more than once per request."""
    action = (action or "").strip().lower()
    aliases = {"resume": "play", "continue": "play", "stop": "pause", "skip": "next",
               "back": "previous", "prev": "previous", "up": "louder", "volume_up": "louder", "down": "quieter", "volume_down": "quieter"}
    action = aliases.get(action, action)
    req = urllib.request.Request(COMMAND_URL, data=json.dumps({"action": action}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _opener.open(req, timeout=3) as resp:
            r = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            r = json.load(e)
        except Exception:
            return f"The watch bridge refused the command ({e.code})."
    except Exception:
        return "The watch bridge is not running, so you can't control the video right now."
    if not r.get("ok"):
        err = r.get("error", "")
        if "not connected" in err:
            return "The browser extension is not connected, so you couldn't control the video."
        return f"Could not send the command: {err}"
    for _ in range(12):                      # wait up to 6 s for the extension to confirm
        time.sleep(0.5)
        try:
            with _opener.open(f"{RESULT_URL}?id={r['id']}", timeout=2) as resp:
                result = json.load(resp).get("result")
        except Exception:
            result = None
        if result:
            return f"Result: {result}."
    return "The command was sent, but the browser did not confirm it yet."


@mcp.tool()
def play_on_youtube(query: str) -> str:
    """Search YouTube in the user's browser and play the first video result.
    Use this when the user asks you (in any language) to play or put on a song, artist or video,
    or when they say yes to a song you suggested. query: what to search, e.g. "artist name song title".
    Only use it when they clearly ask you to play or put on something (e.g. "play X", "put on X"). A sweet message, a compliment or a song name mentioned in conversation is NOT a request. To start, resume, pause or skip what is already open, use control_video instead. Call it once per request, and call it again for every new request even if you played something a moment ago. Never say something is playing unless you called this tool in this same reply,
    then tell them in one short sentence what is playing, in your usual style. If it failed, say so honestly."""
    query = (query or "").strip()[:150]
    if not query:
        return "No search query was given."
    req = urllib.request.Request(COMMAND_URL, data=json.dumps({"action": "search", "query": query}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _opener.open(req, timeout=3) as resp:
            r = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            r = json.load(e)
        except Exception:
            return f"The watch bridge refused the search ({e.code})."
    except Exception:
        return "The watch bridge is not running, so you can't play anything right now."
    if not r.get("ok"):
        err = r.get("error", "")
        if "not connected" in err:
            return "The browser extension is not connected, so you couldn't play it."
        return f"Could not send the search: {err}"
    for _ in range(30):                      # search + page load: wait up to 15 s
        time.sleep(0.5)
        try:
            with _opener.open(f"{RESULT_URL}?id={r['id']}", timeout=2) as resp:
                result = json.load(resp).get("result")
        except Exception:
            result = None
        if result:
            return f"Result: {result}."
    return f"Searched YouTube for {query}, but the browser did not confirm what is playing yet."


if __name__ == "__main__":
    mcp.run()