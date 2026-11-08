# OLV Watch-Along

A watch-along add-on for [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber).
Your AI character sees what you are watching on YouTube, comments on it with you,
and controls playback when you ask by voice or text.

> "Can you skip this song?" → the character skips it.
> "Play some lo-fi" → the character searches YouTube and starts the first real video.
> You open a new video → 15 seconds later the character says something about it.

This project does **not** include Open-LLM-VTuber itself. You need a working
Open-LLM-VTuber setup first; this add-on plugs into it.

## Features

- **Knows what you are watching:** title, channel, playing/paused, description and the captions on screen.
- **Comments on its own:** one short comment on each new video, and now and then on new captions (with cooldowns and a daily cap).
- **Playback control:** pause, play, next, previous.
- **"Play X":** searches YouTube and opens the first real result (not ads or Shorts), then tells you the actual title.
- **Idle check-in:** after a long silence the character checks in on you (optional).
- **Hotkeys (Windows, optional):** F9 turns comments on/off, F8 mutes the mic.
- **Local only:** the bridge listens on `127.0.0.1` only. YouTube only. No accounts, no cloud service of its own.

## How it works

```
 Firefox / Zen                     bridge.py (127.0.0.1:12450)              Open-LLM-VTuber
┌──────────────┐  POST /update   ┌──────────────────────────┐  text-input   ┌──────────────────┐
│  extension   │ ──────────────► │ keeps "now watching"     │ ────────────► │ /proxy-ws        │
│ content.js   │                 │ decides when to comment  │  (comments)   │                  │
│ background.js│ ◄────────────── │ command queue            │               │  LLM + MCP tools │
└──────────────┘  GET /command   └──────────────────────────┘               └────────┬─────────┘
                                          ▲  GET /state, POST /command               │ stdio
                                          └──────────────────────────── watch_mcp.py ◄┘
```

- **extension/**: reads the YouTube page and carries out playback commands.
- **bridge/bridge.py**: small local server. Stores the current state in memory, sends spontaneous comments through Open-LLM-VTuber's proxy, and queues commands for the extension.
- **mcp/watch_mcp.py**: MCP server that gives the character three tools: `get_watching`, `control_video`, `play_on_youtube`.

## Requirements

- A working [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) install (tested with v1.2.1) and an LLM that supports tool calling.
- Firefox or a Firefox-based browser (tested with Zen). The extension is Manifest V2.
- Python packages `aiohttp` and `mcp` (both already in Open-LLM-VTuber's virtual environment).
- Optional: [AutoHotkey v2](https://www.autohotkey.com/) for the hotkeys (Windows).

## Setup

### 1. Turn on the Open-LLM-VTuber proxy

In `conf.yaml`, under `system_config`:

```yaml
  enable_proxy: true
```

Then, in the Open-LLM-VTuber frontend settings, change the WebSocket URL to
`ws://127.0.0.1:12393/proxy-ws`. The proxy lets the bridge and the frontend share one session,
so the character's comments appear and are spoken in your frontend.

### 2. Register the MCP server

In `mcp_servers.json` (Open-LLM-VTuber project root), add an entry inside `"mcp_servers"`:

```json
"watch-along": {
  "command": "C:/path/to/Open-LLM-VTuber/.venv/Scripts/python.exe",
  "args": ["C:/path/to/olv-watch-along/mcp/watch_mcp.py"]
}
```

In `conf.yaml`, under `agent_settings` → `basic_memory_agent`, make sure tools are on and add the server:

```yaml
      use_mcpp: True
      mcp_enabled_servers: ["time", "ddg-search", "watch-along"]
```

Restart Open-LLM-VTuber after changing these files.

### 3. Start the bridge

```
C:/path/to/Open-LLM-VTuber/.venv/Scripts/python.exe bridge/bridge.py
```

Optional environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `WATCH_USER_NAME` | `the user` | How the system notes refer to you, e.g. your name |
| `OLV_DIR` | current folder | Open-LLM-VTuber folder (only used for the F8 mute flag) |

### 4. Load the extension

- **For testing:** open `about:debugging#/runtime/this-firefox` → **Load Temporary Add-on** → pick `extension/manifest.json`. Temporary add-ons are removed when the browser closes.
- **Permanent:** Firefox only installs signed extensions. Change the `id` in `manifest.json` to your own, zip the three files, and sign it as an unlisted ("On your own") add-on on [addons.mozilla.org](https://addons.mozilla.org/developers/). Then install the signed `.xpi` from `about:addons`.
- Allow **Autoplay → Allow Audio and Video** for youtube.com, otherwise "play X" opens the video but it does not start.
- Recommended: set **Run in Private Windows → Don't Allow** for the extension.

### 5. Hotkeys (optional, Windows)

- `hotkeys/comments_toggle.ahk`: **F9** turns spontaneous comments and idle check-ins on/off. Shows a small tooltip.
- `hotkeys/mic_mute.ahk`: **F8** mutes/unmutes the microphone. Needs a one-time patch: run `tools/patch_mute.py` from the Open-LLM-VTuber folder (it keeps a `.bak` backup). Set `olvDir` at the top of the script.

Without AutoHotkey you can toggle comments from PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:12450/comments -ContentType 'application/json' -Body '{"enabled":false}'
```

## Settings

At the top of `bridge/bridge.py`:

| Setting | Default | Meaning |
|---|---|---|
| `NEW_VIDEO_SETTLE_S` | 15 | Seconds after a new video opens before the character comments |
| `COOLDOWN_S` | 300 | Minimum seconds between caption comments on the same video |
| `QUIET_AFTER_USER_S` | 45 | No spontaneous comments for this long after you talk |
| `DAILY_CAP` | 60 | Maximum spontaneous comments and check-ins per day |
| `CHECKINS_ENABLED` | True | Idle check-ins on/off |
| `IDLE_CHECKIN_S` | 600 | Silence before a check-in |
| `RESPECT_MUTE` | False | If True, no comments while the F8 mute is on |

Each spontaneous comment is one LLM request; each playback command is usually two.

## Tip: when the character says "done" but nothing happens

Open-LLM-VTuber's chat memory stores only the text of replies, not the tool calls.
After a few commands the model can see "skip the song" → "Skipped." in the history
without any tool call and start copying that, answering without actually calling the tool.
The tool descriptions already warn against this. If it still happens, add a line like this
to your persona:

```
Video control: every time the user asks you to pause, play, skip, go back or open something,
call control_video or play_on_youtube in that same reply, even if you did the same thing a
moment ago. The chat history does not show your earlier tool calls, but they happened, so
never answer a request like that with words only. If you did not call the tool, nothing
happened, so do not say it is done.
```

`tools/set_persona.py` can write a persona text file into `conf.yaml` safely
(it backs up the old persona and checks the YAML afterwards). Starting a new chat also helps.

## Privacy and security

- The bridge listens on `127.0.0.1` only and rejects requests coming from websites (Origin check).
  Commands can only be fetched with the extension's custom header.
- The extension reads only YouTube `/watch` and search pages: title, channel, description and on-screen captions.
  It does not read comments, your account or other tabs.
- Everything the character sees is sent to the LLM you configured in Open-LLM-VTuber.
  If that is a cloud API, your watch history goes there too.

## Known limitations

- YouTube only, Firefox-based browsers only.
- YouTube changes its page layout from time to time; selectors in `content.js` may need updates.
- State lives in memory; restarting the bridge resets it (and the daily cap).

## Contributing

This is my first public project, so there is surely room to improve.
Issues, ideas and pull requests are very welcome. Feel free to fork it
and shape it to your own setup.

## Credits

- [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) (MIT): the VTuber framework this add-on is built for.
- `tools/patch_mute.py` modifies Open-LLM-VTuber's `websocket_handler.py` on your machine; that file remains under Open-LLM-VTuber's license.

Designed and built by **foolkc**, with AI-assisted coding.

## License

MIT, see [LICENSE](LICENSE).
