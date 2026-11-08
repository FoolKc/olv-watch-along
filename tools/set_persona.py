"""Replace persona_prompt in Open-LLM-VTuber's conf.yaml with the text of a persona file.

Usage: python -I set_persona.py <conf.yaml> <persona.txt>
- Saves the old persona as persona_old_<date>.txt next to the persona file.
- After writing, reads the YAML back the way Open-LLM-VTuber does; on any problem it restores the original.
"""
import sys
import time
from pathlib import Path

import yaml

conf_path, persona_path = Path(sys.argv[1]), Path(sys.argv[2])
original = conf_path.read_bytes().decode("utf-8")  # keep line endings as they are
nl = "\r\n" if "\r\n" in original else "\n"
persona = persona_path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()

lines = original.split(nl)
starts = [i for i, line in enumerate(lines) if line.startswith("  persona_prompt:")]
if len(starts) != 1:
    sys.exit(f"ERROR: found the 'persona_prompt' line {len(starts)} times, file not touched.")
start = starts[0]

end = start + 1
while end < len(lines):
    line = lines[end]
    if line.strip() and (len(line) - len(line.lstrip(" "))) <= 2:
        break
    end += 1
while end - 1 > start and not lines[end - 1].strip():
    end -= 1                                   # keep trailing blank lines

old_block = nl.join(lines[start:end])
backup = persona_path.parent / f"persona_old_{time.strftime('%Y%m%d_%H%M')}.txt"
backup.write_text(old_block, encoding="utf-8")

new_block = ["  persona_prompt: |"] + [("    " + l) if l.strip() else "" for l in persona.split("\n")]
updated = nl.join(lines[:start] + new_block + lines[end:])
conf_path.write_bytes(updated.encode("utf-8"))

try:
    data = yaml.safe_load(conf_path.read_text(encoding="utf-8"))
    loaded = data["character_config"]["persona_prompt"].strip()
    assert loaded == persona, "persona could not be read back or differs"
except Exception as e:
    conf_path.write_bytes(original.encode("utf-8"))
    sys.exit(f"ERROR: check failed ({e}). conf.yaml was restored.")

print(f"done: persona replaced ({len(persona.split())} words)")
print(f"old persona backup: {backup}")
print(f"new persona on lines {start + 1}-{start + len(new_block)}")