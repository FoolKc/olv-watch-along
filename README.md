# OLV Watch-Along

[![Firefox Add-on](https://img.shields.io/amo/v/olv-watch-along?label=Firefox%20add-on)](https://addons.mozilla.org/firefox/addon/olv-watch-along/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Watch YouTube together with your [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) character.
It sees what you are watching (including Shorts and long music mixes), comments on it with you,
and controls playback when you ask by voice or text.

![The character comments on a video that just started](docs/demo.gif)

*The character comments on its own when a new video starts.*

> "Can you skip this song?" → the character skips it.
> "Turn it down a bit" → the character lowers the volume and tells you the new level.
> "Play some lo-fi" → the character searches YouTube and starts the first real video.
> "What song is this?" → in a long mix, the character knows which song is playing right now.
> You open a new video → 15 seconds later the character says something about it.

This is an add-on: it does **not** include Open-LLM-VTuber itself.

## Features

**Watching together**
- Knows what you are watching: title, channel, playing or paused, description and the captions on screen.
- Knows where you are in the video: the current position and, in videos with chapters, the chapter playing now (in a long music mix, the current song).
- YouTube Shorts: sees the Short you stop on (scrolling past quickly does not trigger comments).
- Comments on its own: one short comment on each new video, and now and then on new captions, with cooldowns and a daily cap.
- Idle check-in: after a long silence the character checks in on you (optional).

**Control**
- Pause, play, next, previous, volume up and down (on Shorts: pause, play and volume).
- "Play X": searches YouTube and opens the first real result (not ads or Shorts), then tells you the actual title.
- With several YouTube tabs open, commands go to the tab you are looking at.
- Hotkeys (Windows, optional): F9 turns comments on and off, F8 mutes the microphone.

**Privacy**
- Runs on your PC only: the bridge listens on `127.0.0.1`. No accounts, no cloud service of its own.
- Video titles, descriptions and captions are treated as data, so text inside a video cannot make the character act on its own.

## Which one should I use?

| | OLV Watch-Along (this project) | [OLV Desktop Companion](https://github.com/FoolKc/olv-desktop-companion) |
|---|---|---|
| Watch YouTube together | Yes | Yes (same extension) |
| Look at your screen, open apps, notes, Spotify | No | Yes |
| Operating system | Tested on Windows (`setup.bat` and hotkeys are Windows-only) | Windows only |
| Best for | Just watching together, smallest setup | A character that also helps on your desktop |

Use one of them, not both: they share the same browser extension and the same port.

## Quick setup (Windows)

No coding needed.

**Before you start, you need:**
- A working Open-LLM-VTuber, installed with `uv` as in [its quick start](https://open-llm-vtuber.github.io/docs/quick-start), and a model that supports tool calling (for example DeepSeek).
- Firefox or a Firefox-based browser such as Zen.

**Steps:**
1. **Download this project:** on GitHub, click **Code → Download ZIP** and unzip it anywhere (for example in Documents).
2. **Close Open-LLM-VTuber**, then double-click **`setup.bat`** in the unzipped folder. Drag your Open-LLM-VTuber folder into the window, press Enter and answer the question.
   It backs up and edits `conf.yaml` and `mcp_servers.json` for you, adds the rules to the end of your persona, and creates `start_bridge.bat`.
3. **Install the browser extension:** [OLV Watch-Along on addons.mozilla.org](https://addons.mozilla.org/firefox/addon/olv-watch-along/). Then, on youtube.com, click the icon left of the address bar and set **Autoplay → Allow Audio and Video**.
4. **Start Open-LLM-VTuber.** In its settings, change the WebSocket URL to `ws://127.0.0.1:12393/proxy-ws` (only once).
5. **Double-click `start_bridge.bat`** and keep that window open. Start a **new chat**.

**Check that it works:** open a YouTube video and wait about 15 seconds: the character should say something about it. Then say "pause": the video should stop.

From then on, you only start Open-LLM-VTuber and `start_bridge.bat`.

**Good to know**
- `setup.bat --dry-run` (in a terminal in this folder) shows what setup would change, without changing anything.
- `undo_setup.bat` removes it again.
- After updating this project, run `setup.bat` again; it updates the rules instead of adding them twice.

## Troubleshooting

**The character never comments on videos.**
Check that the `start_bridge.bat` window is open and shows no errors, and that the WebSocket URL in the Open-LLM-VTuber settings is `ws://127.0.0.1:12393/proxy-ws`. Comments also pause for 45 seconds after you talk, after F9 (comments off), and after the daily cap of 60.

**"Play X" opens the video, but it does not start.**
The browser blocks autoplay. On youtube.com, set **Autoplay → Allow Audio and Video** (step 3).

**The character says "done", but nothing happens.**
Open-LLM-VTuber's chat memory keeps only the text of replies, not the tool calls. After a few commands the model can see "skip the song" → "Skipped." in the history and start copying it without calling the tool. The rules from setup already tell it not to; if it still happens, start a new chat.

**Windows will not run `setup.bat`.**
Files from a downloaded ZIP can be blocked. Right-click the ZIP before unzipping → **Properties** → tick **Unblock**, then unzip again.

**Setup stops with "STOPPED".**
Nothing was changed. The message says why (often an unusual `conf.yaml` layout). Follow the [manual setup](#manual-setup) below, and feel free to open an issue with the message.

**The bridge window shows an error that the port is already in use.**
Another bridge is already running, for example the one from OLV Desktop Companion. Close it; only one can run at a time.

## Privacy and security

- The bridge listens on `127.0.0.1` only and rejects requests coming from websites (Origin check)
  and requests with a foreign `Host` header (DNS rebinding). Commands can only be fetched with
  the extension's custom header.
- Video titles, descriptions and captions are written by strangers. The bridge and the MCP server
  clean them so they cannot fake an event or close the `<video_data>` block, and `prompts/system_rules.txt`
  tells the character to treat them as information only.
- While the character is reacting to an event (a turn you did not start), `control_video` and
  `play_on_youtube` refuse to run, so text inside a video cannot make the character act on its own.
  This is enforced in code, not only in the prompt.
- The extension reads only YouTube `/watch`, `/shorts/` and search pages: title, channel, description, chapter, position and on-screen captions.
  It does not read comments, your account or other sites.
- Everything the character sees is sent to the LLM you configured in Open-LLM-VTuber.
  If that is a cloud API, your watch history goes there too.
- Recommended: set **Run in Private Windows → Don't Allow** for the extension in `about:addons`.

## Known limitations

- YouTube only, Firefox-based browsers only.
- YouTube changes its page layout from time to time; selectors in `extension/adapters/` may need updates.
- On Shorts, "next" and "previous" are not supported (just scroll). The channel name may be empty there.
- If you close the tab you are watching, the character forgets the video; another open YouTube tab is picked up when you click on it.
- State lives in memory; restarting the bridge resets it (and the daily cap).

---

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

- **extension/**: reads the YouTube page and carries out playback commands. Each site has its own small adapter in `extension/adapters/` (YouTube watch pages, YouTube Shorts); `content.js` is the shared core.
- **bridge/bridge.py**: small local server. Stores the current state in memory, sends short `[EVENT ...]` messages (new video, new captions, idle) through Open-LLM-VTuber's proxy, and queues commands for the extension. It contains no personality text: how the character reacts is up to your prompt.
- **mcp/watch_mcp.py**: MCP server that gives the character three tools: `get_watching`, `control_video`, `play_on_youtube`.
- **prompts/**: rules to add to your character's prompt: how to react to events, how to treat outside text, and how to use the tools.
- **tools/setup.py**: the setup wizard behind `setup.bat`. It edits `conf.yaml` as text (your comments stay), then reads it back and restores the original if anything else changed.

Each spontaneous comment is one LLM request; each playback command is usually two.

## Manual setup

Use this instead of `setup.bat` if you want to do each step yourself, or if you are not on Windows.

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

### 3. Add the rules to your prompt

The bridge sends events like `[EVENT new_video]`, and the character needs to know what they mean.
Add the two files in `prompts/` after your own persona. `tools/set_persona.py` can do it for you
(close Open-LLM-VTuber first; it backs up the old persona and checks the YAML afterwards):

```
C:/path/to/Open-LLM-VTuber/.venv/Scripts/python.exe -I tools/set_persona.py C:/path/to/Open-LLM-VTuber/conf.yaml my_persona.txt prompts/system_rules.txt prompts/tool_rules.txt
```

You can edit both files freely, for example to give the idle check-in your character's own flavor.
Start a new chat afterwards.

### 4. Start the bridge

```
C:/path/to/Open-LLM-VTuber/.venv/Scripts/python.exe bridge/bridge.py
```

Optional environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `WATCH_USER_NAME` | `the user` | How events refer to you, e.g. your name |
| `OLV_DIR` | current folder | Open-LLM-VTuber folder (only used for the F8 mute flag) |

### 5. Load the extension

- **Easiest:** install it from [addons.mozilla.org](https://addons.mozilla.org/firefox/addon/olv-watch-along/).
- **For testing:** open `about:debugging#/runtime/this-firefox` → **Load Temporary Add-on** → pick `extension/manifest.json`. Temporary add-ons are removed when the browser closes.
- **Permanent, your own build:** Firefox only installs signed extensions. Change the `id` in `manifest.json` to your own, zip the contents of the `extension` folder (`manifest.json`, `background.js`, `content.js`, `adapters/`, `icons/`) so that `manifest.json` sits at the top level of the zip, and sign it as an unlisted ("On your own") add-on on [addons.mozilla.org](https://addons.mozilla.org/developers/). Then install the signed `.xpi` from `about:addons`.
- Allow **Autoplay → Allow Audio and Video** for youtube.com, otherwise "play X" opens the video but it does not start.

### 6. Hotkeys (optional, Windows)

Needs [AutoHotkey v2](https://www.autohotkey.com/).

- `hotkeys/comments_toggle.ahk`: **F9** turns spontaneous comments and idle check-ins on/off. Shows a small tooltip.
- `hotkeys/mic_mute.ahk`: **F8** mutes/unmutes the microphone. Needs a one-time patch: run `tools/patch_mute.py` from the Open-LLM-VTuber folder (it keeps a `.bak` backup). Set `olvDir` at the top of the script.

Without AutoHotkey you can toggle comments from PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:12450/comments -ContentType 'application/json' -Body '{"enabled":false}'
```

## Requirements (details)

- [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) (tested with v1.2.1) and an LLM that supports tool calling.
- Firefox or a Firefox-based browser (tested with Zen). The extension is Manifest V2.
- Python packages `aiohttp` and `mcp` (both already in Open-LLM-VTuber's virtual environment).
- Optional: [AutoHotkey v2](https://www.autohotkey.com/) for the hotkeys (Windows).

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

## Contributing

This is my first public project, so there is surely room to improve.
Issues, ideas and pull requests are very welcome, and so are reports of what worked or failed on your setup.
Feel free to fork it and shape it to your own setup.

## Credits

- [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) (MIT): the VTuber framework this add-on is built for.
- `tools/patch_mute.py` modifies Open-LLM-VTuber's `websocket_handler.py` on your machine; that file remains under Open-LLM-VTuber's license.

Designed and built by **foolkc**, with AI-assisted coding.

## License

MIT, see [LICENSE](LICENSE).
