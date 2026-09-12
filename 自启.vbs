' Desktop Tidy autostart launcher
' Waits for the system to be ready, then starts the app and logs what happened.
Option Explicit
Dim sh, fso, wmi, procs, p, exePath, scriptPath, logPath, f, i
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
exePath = "C:\Program Files\Python312\pythonw.exe"
scriptPath = "D:\GitHub\desktop-tidy\main.py"
logPath = "C:\Users\stwh8\AppData\Roaming\DesktopTidy\tray.log"

WScript.Sleep 12000

' ??????????
On Error Resume Next
Set wmi = GetObject("winmgmts:\\.\root\cimv2")
Set procs = wmi.ExecQuery("SELECT CommandLine FROM Win32_Process WHERE Name='pythonw.exe'")
For Each p In procs
    If InStr(p.CommandLine, "main.py") > 0 Then
        WriteLog "autostart: already running, skipped"
        WScript.Quit 0
    End If
Next
On Error Goto 0

' ???/??????????? 6 ?
For i = 1 To 6
    If fso.FileExists(exePath) And fso.FileExists(scriptPath) Then
        sh.Run Chr(34) & exePath & Chr(34) & " " & Chr(34) & scriptPath & Chr(34), 0, False
        WriteLog "autostart: started the app (attempt " & i & ")"
        WScript.Quit 0
    End If
    WScript.Sleep 10000
Next
WriteLog "autostart: FAILED - pythonw.exe or main.py was not found"

Sub WriteLog(msg)
    On Error Resume Next
    Set f = fso.OpenTextFile(logPath, 8, True)
    f.WriteLine Year(Now) & "-" & Right("0" & Month(Now), 2) & "-" & Right("0" & Day(Now), 2) & " " & _
        Right("0" & Hour(Now), 2) & ":" & Right("0" & Minute(Now), 2) & ":" & Right("0" & Second(Now), 2) & _
        "  [launcher] " & msg
    f.Close
End Sub
