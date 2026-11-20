"""Setup wizard: connects OLV Watch-Along to an existing Open-LLM-VTuber install.

Normally you do not run this file yourself: double-click setup.bat instead.
Manual use (with Open-LLM-VTuber's Python):
    <Open-LLM-VTuber>/.venv/Scripts/python.exe -I tools/setup.py <Open-LLM-VTuber folder> [--dry-run | --undo]

What it changes (each file is backed up first, as <name>.before_setup, the first time only):
- mcp_servers.json: adds the "watch-along" MCP server.
- conf.yaml: turns on the proxy and MCP tools, enables the "watch-along" server,
  and adds the rules from prompts/ to the end of your persona (between two marker lines,
  so running setup again updates them instead of adding them twice).
- start_bridge.bat in this folder: double-click it to start the bridge.

--dry-run  shows what would change and writes nothing.
--undo     removes the server, the server name and the rules again (proxy and MCP stay on).

conf.yaml is edited as text, so your comments and layout stay as they are. Afterwards the
file is read back the way Open-LLM-VTuber reads it and compared with what was expected;
if anything else changed, the original is restored.
"""
import copy
import json
import re
import shutil
import socket
import sys
from pathlib import Path

import yaml

# ---------------- project settings ----------------
PROJECT = "watch-along"
SERVER = "watch-along"
OTHER_SERVER = "desktop-companion"     # the sister project's server; it has the same watch tools
MCP_SCRIPT = "mcp/watch_mcp.py"
BRIDGE_SCRIPT = "bridge/bridge.py"
USER_NAME_VAR = "WATCH_USER_NAME"
COMPANION = False
RULE_FILES = ["prompts/system_rules.txt", "prompts/tool_rules.txt"]
EXTENSION_URL = "https://addons.mozilla.org/firefox/addon/olv-watch-along/"
# ---------------------------------------------------

REPO = Path(__file__).resolve().parent.parent
def markers(project: str):
    return (f"[{project} rules: start. Added by setup.py; run it with --undo to remove]",
            f"[{project} rules: end]")


BEGIN, END = markers(PROJECT)
OTHER_BEGIN, OTHER_END = markers(OTHER_SERVER)
OLV_PORT = 12393


def fwd(p: Path) -> str:
    return str(p).replace("\\", "/")


def say(text: str = "") -> None:
    print(text, flush=True)


def ask(question: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    try:
        answer = input(f"{question}{hint}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def yes(question: str, default: bool) -> bool:
    answer = ask(question + (" (Y/n)" if default else " (y/N)")).lower()
    return default if not answer else answer.startswith("y")


def stop(msg: str) -> None:
    say()
    say("STOPPED: " + msg)
    say("Nothing was changed by this step.")
    sys.exit(1)


def backup(path: Path, dry: bool) -> None:
    target = path.with_name(path.name + ".before_setup")
    if not dry and path.exists() and not target.exists():
        shutil.copyfile(path, target)


# ---------------- mcp_servers.json ----------------
def edit_mcp_servers(olv: Path, entry: dict, undo: bool, dry: bool) -> list:
    path = olv / "mcp_servers.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"mcp_servers": {}}
    servers = data.setdefault("mcp_servers", {})
    notes = []
    if undo:
        if SERVER in servers:
            del servers[SERVER]
            notes.append(f'mcp_servers.json: removed "{SERVER}"')
    elif servers.get(SERVER) != entry:
        notes.append(f'mcp_servers.json: {"updated" if SERVER in servers else "added"} "{SERVER}"')
        servers[SERVER] = entry
    if notes and not dry:
        backup(path, dry)
        path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    return notes


# ---------------- conf.yaml (text edits) ----------------
def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def split_comment(value: str):
    """'["a", "b"] # x' -> ('["a", "b"]', ' # x'). Good enough for these simple values."""
    m = re.search(r"\s+#", value)
    return (value[:m.start()], value[m.start():]) if m else (value, "")


def find_section(lines, name: str, indent: int, start: int = 0, end: int = None):
    """(first, last+1) line range of a mapping key at this indent, or None."""
    end = len(lines) if end is None else end
    for i in range(start, end):
        if indent_of(lines[i]) == indent and lines[i].strip().startswith(name + ":"):
            j = i + 1
            while j < end and (not lines[j].strip() or indent_of(lines[j]) > indent):
                j += 1
            while j > i + 1 and not lines[j - 1].strip():
                j -= 1                     # trailing blank lines belong to what follows
            return i, j
    return None


def set_key(lines, section, key: str, value: str, insert_after_header: bool = True) -> bool:
    """Sets 'key: value' directly inside section. Returns True if something changed."""
    first, last = section
    child = None
    for i in range(first + 1, last):
        if lines[i].strip() and not lines[i].lstrip().startswith("#"):
            child = indent_of(lines[i])
            break
    if child is None:
        return False
    for i in range(first + 1, last):
        if indent_of(lines[i]) == child and lines[i].strip().startswith(key + ":"):
            old, comment = split_comment(lines[i].split(":", 1)[1])
            if old.strip().lower() == value.lower():
                return False
            lines[i] = " " * child + f"{key}: {value}" + comment
            return True
    lines.insert(first + 1, " " * child + f"{key}: {value}")
    return True


def edit_conf_text(text: str, rules: str, undo: bool):
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    notes = []

    # 1) system_config.enable_proxy
    if not undo:
        sec = find_section(lines, "system_config", 0)
        if not sec:
            stop("conf.yaml has no 'system_config' section. Is this Open-LLM-VTuber's conf.yaml?")
        if set_key(lines, sec, "enable_proxy", "true"):
            notes.append("conf.yaml: proxy turned on (enable_proxy: true)")

    # 2) basic_memory_agent: use_mcpp + mcp_enabled_servers
    char = find_section(lines, "character_config", 0)
    if not char:
        stop("conf.yaml has no 'character_config' section.")
    agent = None
    for ind in range(2, 13, 2):
        agent = find_section(lines, "basic_memory_agent", ind, char[0], char[1])
        if agent:
            break
    if not agent:
        stop("conf.yaml has no 'basic_memory_agent' settings.")
    if not undo and set_key(lines, agent, "use_mcpp", "True"):
        notes.append("conf.yaml: MCP tools turned on (use_mcpp: True)")
        agent = find_section(lines, "basic_memory_agent", indent_of(lines[agent[0]]), agent[0])
    idx = [i for i in range(agent[0] + 1, agent[1]) if lines[i].strip().startswith("mcp_enabled_servers:")]
    if len(idx) != 1:
        stop("could not find one 'mcp_enabled_servers:' line under basic_memory_agent.\n"
             f'Add "{SERVER}" to it by hand, like: mcp_enabled_servers: ["time", "{SERVER}"]')
    i = idx[0]
    key, rest = lines[i].split(":", 1)
    value, comment = split_comment(rest)
    try:
        servers = yaml.safe_load(value) if value.strip() else []
    except yaml.YAMLError:
        servers = None
    if not isinstance(servers, list) or not all(isinstance(s, str) for s in servers):
        stop("'mcp_enabled_servers' is not written as a list in one line, like [\"time\", \"ddg-search\"].\n"
             f'Add "{SERVER}" to it by hand.')
    new = [s for s in servers if s != SERVER]
    if not undo:
        if OTHER_SERVER in new:
            new.remove(OTHER_SERVER)
            notes.append(f'conf.yaml: removed "{OTHER_SERVER}" from the enabled servers '
                         f"({SERVER} has the same watch tools; using both would duplicate them)")
        new.append(SERVER)
    if new != servers:
        lines[i] = f"{key}: " + json.dumps(new) + comment
        notes.append(f'conf.yaml: removed "{SERVER}" from mcp_enabled_servers' if undo
                     else f'conf.yaml: enabled "{SERVER}" in mcp_enabled_servers')

    # 3) persona_prompt: rules between the two marker lines at the end
    char = find_section(lines, "character_config", 0)
    child = next((indent_of(l) for l in lines[char[0] + 1:char[1]]
                  if l.strip() and not l.lstrip().startswith("#")), 2)
    p = find_section(lines, "persona_prompt", child, char[0], char[1])
    if not p:
        stop("conf.yaml has no 'persona_prompt' under character_config.")
    header = lines[p[0]]
    style = header.split(":", 1)[1].strip()
    if not style.startswith("|"):
        stop("your persona_prompt is not written as a block (persona_prompt: | followed by indented lines).\n"
             "Add the files in prompts/ to the end of your persona by hand, or use tools/set_persona.py.")
    first, last = p[0] + 1, p[1]
    while last > first and not lines[last - 1].strip():
        last -= 1
    body = lines[first:last]
    pind = min((indent_of(l) for l in body if l.strip()), default=indent_of(header) + 2)
    plain = [l[pind:] if l.strip() else "" for l in body]

    def cut(plain, begin, end):
        if begin not in plain:
            return None, plain
        b = plain.index(begin)
        e = plain.index(end, b) + 1 if end in plain[b:] else len(plain)
        if b > 0 and not plain[b - 1].strip():
            b -= 1
        return plain[b:e], plain[:b] + plain[e:]

    old_block, plain = cut(plain, BEGIN, END)
    if not undo:
        other_block, plain = cut(plain, OTHER_BEGIN, OTHER_END)
        if other_block:
            notes.append(f"conf.yaml: removed the {OTHER_SERVER} rules from your persona (these rules include them)")
    if not undo:
        block = ["", BEGIN] + rules.split("\n") + [END]
        plain = plain + block
        if old_block != block:
            notes.append("conf.yaml: rules from prompts/ " + ("updated" if old_block else "added") +
                         " at the end of your persona")
    elif old_block is not None:
        notes.append("conf.yaml: rules removed from your persona")
    new_body = [(" " * pind + l) if l.strip() else "" for l in plain]
    lines[first:last] = new_body
    return nl.join(lines), notes


def expected(data: dict, rules: str, undo: bool) -> dict:
    """What conf.yaml should contain after the edit (to compare with the real result)."""
    d = copy.deepcopy(data)
    agent = d["character_config"]["agent_config"]["agent_settings"]["basic_memory_agent"]
    servers = [s for s in (agent.get("mcp_enabled_servers") or []) if s != SERVER]
    persona = d["character_config"]["persona_prompt"] or ""
    for begin, end in [(BEGIN, END)] + ([] if undo else [(OTHER_BEGIN, OTHER_END)]):
        if begin in persona:
            b = persona.index(begin)
            e = persona.index(end, b) + len(end) if end in persona[b:] else len(persona)
            persona = persona[:b].rstrip("\n") + ("\n" + persona[e:].lstrip("\n") if persona[e:].strip() else "")
    if not undo:
        d["system_config"]["enable_proxy"] = True
        agent["use_mcpp"] = True
        if OTHER_SERVER in servers:
            servers.remove(OTHER_SERVER)
        servers.append(SERVER)
        persona = (persona.rstrip("\n") + "\n\n" if persona.strip() else "\n") + BEGIN + "\n" + rules + "\n" + END + "\n"
    agent["mcp_enabled_servers"] = servers
    d["character_config"]["persona_prompt"] = persona
    return d


def normalize(d: dict) -> dict:
    d = copy.deepcopy(d)
    text = "\n".join(l.rstrip() for l in (d["character_config"].get("persona_prompt") or "").split("\n"))
    d["character_config"]["persona_prompt"] = re.sub(r"\n{3,}", "\n\n", text).strip()   # blank lines may move
    return d


def edit_conf(olv: Path, undo: bool, dry: bool) -> list:
    path = olv / "conf.yaml"
    if not path.exists():
        stop(f"{path} not found. Run Open-LLM-VTuber once so it creates conf.yaml, then try again.")
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        stop("conf.yaml is not saved as UTF-8. Save it as UTF-8 in your editor and run setup again.")
    rules = "\n\n".join((REPO / f).read_text(encoding="utf-8").replace("\r\n", "\n").strip() for f in RULE_FILES)
    before = yaml.safe_load(text)
    new_text, notes = edit_conf_text(text, rules, undo)
    try:
        after = yaml.safe_load(new_text)
        ok = normalize(after) == normalize(expected(before, rules, undo))
    except Exception:
        ok = False
    if not ok:
        stop("the edited conf.yaml did not read back as expected, so it was not saved.\n"
             "Please follow the manual setup in the README and open an issue with your Open-LLM-VTuber version.")
    if notes and not dry:
        backup(path, dry)
        path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + new_text.encode("utf-8"))
    return notes


# ---------------- companion extras ----------------
def companion_steps(olv: Path, dry: bool) -> tuple:
    """Returns (env for the MCP server, notes)."""
    notes = []
    card = REPO / "prompts" / "user_card.md"
    if not card.exists():
        notes.append("prompts/user_card.md created from the example (open it and write a few lines about yourself)")
        if not dry:
            shutil.copyfile(REPO / "prompts" / "user_card.example.md", card)
    env = {"COMPANION_CARD": fwd(card)}

    say()
    say("Screenshots: the character can look at your screen when you ask (\"look at my screen\").")
    say("Your model must accept images (for example DeepSeek's chat model with the patch below), and")
    say("the screenshot is sent to the LLM you use. You can turn this off later in mcp_servers.json.")
    if yes("Turn on screenshots?", False):
        env["COMPANION_SCREENSHOT"] = "1"

    say()
    say("The Open-LLM-VTuber patch adds the live user card, a sliding chat window and screenshots for")
    say("OpenAI-compatible models. It adds a few lines to two Open-LLM-VTuber files (backed up first).")
    if yes("Apply the patch? (recommended)", True):
        target = olv / "src" / "open_llm_vtuber"
        if dry:
            notes.append("would apply olv_patch to " + fwd(target))
        else:
            files = [target / "agent" / "agents" / "basic_memory_agent.py", target / "mcpp" / "tool_executor.py",
                     target / "agent" / "agents" / "companion_patch.py"]
            state = [f.read_bytes() if f.exists() else b"" for f in files]
            sys.path.insert(0, str(REPO / "olv_patch"))
            import patch_olv
            sys.argv = ["patch_olv.py", str(target)]
            patch_olv.main()
            patched = files[2]
            src = patched.read_text(encoding="utf-8")
            src2 = re.sub(r'^CARD_PATH = os\.environ\.get\("COMPANION_CARD", r"[^"]*"\)',
                          lambda m: f'CARD_PATH = os.environ.get("COMPANION_CARD", r"{card}")', src, count=1, flags=re.M)
            if src2 != src:
                patched.write_text(src2, encoding="utf-8")
            if [f.read_bytes() for f in files] != state:
                notes.append("Open-LLM-VTuber patch applied, user card connected")
    return env, notes


# ---------------- start_bridge.bat ----------------
def write_start_bat(olv: Path, python: Path, user_name: str, dry: bool) -> list:
    path = REPO / "start_bridge.bat"
    content = "\r\n".join([
        "@echo off",
        f"rem Starts the {PROJECT} bridge. Made by setup.py; run setup again to update it.",
        f"title {PROJECT} bridge",
        'cd /d "%~dp0"',
        f'set "OLV_DIR={olv}"',
        f'set "{USER_NAME_VAR}={user_name}"',
        f'"{python}" {BRIDGE_SCRIPT}',
        "pause",
        "",
    ])
    if path.exists() and path.read_text(encoding="utf-8", errors="replace") == content.replace("\r\n", "\n"):
        return []
    if not dry:
        path.write_bytes(content.encode("utf-8"))
    return ["start_bridge.bat written (double-click it to start the bridge)"]


# ---------------- main ----------------
def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    undo, dry = "--undo" in sys.argv, "--dry-run" in sys.argv
    say(f"=== {PROJECT} setup" + (" (dry run: nothing will be written)" if dry else "") + (" (undo)" if undo else "") + " ===")
    say()
    olv = Path(args[0] if args else ask("Open-LLM-VTuber folder (you can drag the folder here)").strip('"')).expanduser()
    olv = olv.resolve()
    python = olv / ".venv" / "Scripts" / "python.exe"
    if not (olv / "conf.yaml").exists() and not (olv / "run_server.py").exists():
        stop(f"{olv} does not look like an Open-LLM-VTuber folder (no conf.yaml or run_server.py).")
    if not python.exists():
        python = Path(sys.executable)
    say(f"Open-LLM-VTuber: {olv}")

    with socket.socket() as s:
        s.settimeout(0.5)
        running = s.connect_ex(("127.0.0.1", OLV_PORT)) == 0
    if running and not dry:
        say()
        say("Open-LLM-VTuber seems to be running. Close it first (it would overwrite or ignore the changes).")
        ask("Press Enter when it is closed")

    notes = []
    if undo:
        notes += edit_mcp_servers(olv, {}, True, dry)
        notes += edit_conf(olv, True, dry)
    else:
        say()
        user_name = ask("What should the character call you in event messages?", "the user")
        env = {}
        if COMPANION:
            env, extra = companion_steps(olv, dry)
            notes += extra
        entry = {"command": fwd(python), "args": [fwd(REPO / MCP_SCRIPT)]}
        if env:
            entry["env"] = env
        notes += edit_mcp_servers(olv, entry, False, dry)
        notes += edit_conf(olv, False, dry)
        notes += write_start_bat(olv, python, user_name, dry)

    say()
    say("Would change:" if dry else "Done:")
    for n in notes or ["nothing to change, everything is already set up"]:
        say("  - " + n)
    if not dry and notes:
        say("  Backups: files ending in .before_setup next to the originals (made only the first time).")
    if not undo:
        say()
        say("What is left (only once):")
        say(f"  1. Install the browser extension: {EXTENSION_URL}")
        say("  2. Start Open-LLM-VTuber, open its settings in the web page and set the WebSocket URL to")
        say("     ws://127.0.0.1:12393/proxy-ws")
        say("  3. Double-click start_bridge.bat (keep that window open), then start a NEW chat.")
        if COMPANION:
            say("  4. Write a few lines about yourself in prompts/user_card.md.")
    else:
        say()
        say("The proxy and MCP tools were left on (other tools may use them).")
        if COMPANION:
            say("To remove the Open-LLM-VTuber patch, copy back the .companion_backup files in")
            say("src/open_llm_vtuber/agent/agents and src/open_llm_vtuber/mcpp.")


if __name__ == "__main__":
    main()
