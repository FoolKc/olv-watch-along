"""Patch Open-LLM-VTuber so the F8 hotkey (hotkeys/mic_mute.ahk) can mute the microphone.

Run once from the Open-LLM-VTuber folder:  python tools/patch_mute.py
(or copy this file there first). While the file mic_muted.flag exists in that folder,
incoming voice audio is dropped and no LLM request is made. A backup of the original
file is saved as websocket_handler.py.bak. Re-run after updating Open-LLM-VTuber.
"""
import shutil

p = "src/open_llm_vtuber/websocket_handler.py"
raw = open(p, encoding="utf-8", newline="").read()
nl = "\r\n" if "\r\n" in raw else "\n"


def fix(s):
    return s.replace("\n", nl)


a1 = fix('''        """Handle incoming audio data"""
        audio_data = data.get("audio", [])
''')
b1 = fix('''        """Handle incoming audio data"""
        from pathlib import Path as _P
        if (_P(__file__).resolve().parents[2] / "mic_muted.flag").exists():
            return
        audio_data = data.get("audio", [])
''')
a2 = fix('''        """Handle triggers that start a conversation"""
        await handle_conversation_trigger(
''')
b2 = fix('''        """Handle triggers that start a conversation"""
        if data.get("type") == "mic-audio-end":
            from pathlib import Path as _P
            if (_P(__file__).resolve().parents[2] / "mic_muted.flag").exists():
                self.received_data_buffers[client_uid] = np.array([])
                await websocket.send_text(
                    json.dumps({"type": "control", "text": "conversation-chain-end"})
                )
                return
        await handle_conversation_trigger(
''')

for a in (a1, a2):
    assert raw.count(a) == 1, "Expected code not found exactly once (already patched, or Open-LLM-VTuber changed). Nothing was modified."

shutil.copy(p, p + ".bak")
raw = raw.replace(a1, b1).replace(a2, b2)
with open(p, "w", encoding="utf-8", newline="") as f:
    f.write(raw)
print("Done. Backup: " + p + ".bak")