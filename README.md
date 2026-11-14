# OLV Watch-Along

A watch-along add-on for [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber).
Your AI character sees what you are watching on YouTube (including Shorts), comments on it with you,
and controls playback when you ask by voice or text.

![The character comments on a video that just started](docs/demo.gif)

*The character comments on its own when a new video starts. Playback control (pause, play, skip, volume, "play X") works by voice or text; see Features below.*

> "Can you skip this song?" → the character skips it.
> "Turn it down a bit" → the character lowers the volume and tells you the new level.
> "Play some lo-fi" → the character searches YouTube and starts the first real video.
> You open a new video → 15 seconds later the character says something about it.

This project does **not** include Open-LLM-VTuber itself. You need a working
Open-LLM-VTuber setup first; this add-on plugs into it.

## Features

- **Knows what you are watching:** title, channel, playing/paused, description and the captions on screen.
- **YouTube Shorts:** sees the Short you stop on (scrolling past quickly does not trigger comments); pause, play and volume work there too.
- **Comments on its own:** one short comment on each new video, and now and then on new captions (with cooldowns and a daily cap).
- **Playback control:** pause, play, next, previous, volume up/down.
- **"Play X":** searches YouTube and opens the first real result (not ads or Shorts), then tells you the actual title.
- **Idle check-in:** after a long silence the character checks in on you (optional).
- **Hotkeys (Windows, optional):** F9 turns comments on/off, F8 mutes the mic.
- **Local only:** the bridge listens on `127.0.0.1` only. YouTube only. No accounts, no cloud service of its own.
- **Prompt-injection aware:** video titles, descriptions and captions are treated as data, and the playback tools are locked while the character reacts to a video on its own.

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

- **For testing:** open `about:debugging#/runtime/this-firefox` → **Load Temporary Add-on** → pick `extension/manifest.json`. Temporary add-ons are removed when the browser closes.
- **Permanent:** Firefox only installs signed extensions. Change the `id` in `manifest.json` to your own, zip the contents of the `extension` folder (`manifest.json`, `background.js`, `content.js`, `adapters/`, `icons/`) so that `manifest.json` sits at the top level of the zip, and sign it as an unlisted ("On your own") add-on on [addons.mozilla.org](https://addons.mozilla.org/developers/). Then install the signed `.xpi` from `about:addons`.
- Allow **Autoplay → Allow Audio and Video** for youtube.com, otherwise "play X" opens the video but it does not start.
- Recommended: set **Run in Private Windows → Don't Allow** for the extension.

### 6. Hotkeys (optional, Windows)

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
`prompts/tool_rules.txt` already contains a rule against this (setup step 3). If it still
happens, make sure the rules are in your prompt and start a new chat.

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
- The extension reads only YouTube `/watch`, `/shorts/` and search pages: title, channel, description and on-screen captions.
  It does not read comments, your account or other tabs.
- Everything the character sees is sent to the LLM you configured in Open-LLM-VTuber.
  If that is a cloud API, your watch history goes there too.

## Known limitations

- YouTube only, Firefox-based browsers only.
- YouTube changes its page layout from time to time; selectors in `extension/adapters/` may need updates.
- On Shorts, "next" and "previous" are not supported (just scroll). The channel name may be empty there.
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
