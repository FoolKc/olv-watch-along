#Requires AutoHotkey v2.0
#SingleInstance Force
; OLV Watch-Along: press F9 to turn spontaneous comments (and idle check-ins) on/off.
; The bridge (bridge.py) must be running on 127.0.0.1:12450.

BRIDGE := "http://127.0.0.1:12450/comments"

F9:: {
    try {
        ; 1) Read the current state (GET)
        http := ComObject("WinHttp.WinHttpRequest.5.1")
        http.Open("GET", BRIDGE, false)          ; false = wait for the reply
        http.SetTimeouts(2000, 2000, 2000, 2000) ; give up after 2 s if the bridge is down
        http.Send()
        if !RegExMatch(http.ResponseText, '"enabled"\s*:\s*(true|false)', &m) {
            Notify("Watch-Along: unexpected bridge reply")
            return
        }

        ; 2) Send the opposite (POST)
        newState := (m[1] = "true") ? "false" : "true"
        http.Open("POST", BRIDGE, false)
        http.SetRequestHeader("Content-Type", "application/json")
        http.Send('{"enabled": ' newState '}')

        ; 3) Show the state the bridge actually reports back
        if (http.Status = 200 && RegExMatch(http.ResponseText, '"enabled"\s*:\s*(true|false)', &m))
            Notify("Comments: " (m[1] = "true" ? "ON" : "OFF"))
        else
            Notify("Watch-Along: could not change it (HTTP " http.Status ")")
    } catch {
        Notify("Watch-Along: bridge is not running (12450)")
    }
}

; Small tooltip next to the mouse cursor for 2 seconds
Notify(text) {
    ToolTip(text)
    SetTimer(() => ToolTip(), -2000)  ; negative = run once
}
