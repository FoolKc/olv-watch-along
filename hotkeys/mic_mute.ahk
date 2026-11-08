#Requires AutoHotkey v2.0
#SingleInstance Force
; Press F8 to mute/unmute the microphone for Open-LLM-VTuber (e.g. while on a call).
; Needs tools/patch_mute.py applied to Open-LLM-VTuber once.
; While muted, voice input is dropped before it reaches speech recognition or the LLM.
; Typed messages and watch-along comments are not affected.

olvDir := "C:\path\to\Open-LLM-VTuber"   ; <- change to your Open-LLM-VTuber folder
flag := olvDir "\mic_muted.flag"
useBeep := false   ; set to true for a short beep

if FileExist(flag)
    FileDelete(flag)   ; always start in listening mode

ShowState(text) {
    ToolTip(text)
    SetTimer(() => ToolTip(), -1500)
}

F8:: {
    if FileExist(flag) {
        FileDelete(flag)
        ShowState("Mic: LISTENING")
        if useBeep
            SoundBeep(1000, 60)
    } else {
        FileAppend("", flag)
        ShowState("Mic: MUTED")
        if useBeep
            SoundBeep(500, 60)
    }
    KeyWait("F8")
}
