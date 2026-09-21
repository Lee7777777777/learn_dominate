Option Explicit
Dim shell, fso, folder, entry, part, candidate, runner, arguments
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
entry = fso.BuildPath(folder, "start.pyw")
runner = ""
arguments = ""
For Each part In Split(shell.ExpandEnvironmentStrings("%PATH%"), ";")
    part = Replace(part, Chr(34), "")
    If Len(part) > 0 Then
        candidate = fso.BuildPath(part, "pythonw.exe")
        If fso.FileExists(candidate) Then
            runner = candidate
            Exit For
        End If
    End If
Next
If runner = "" Then
    candidate = shell.ExpandEnvironmentStrings("%WINDIR%\pyw.exe")
    If fso.FileExists(candidate) Then
        runner = candidate
        arguments = " -3"
    End If
End If
If runner = "" Then
    MsgBox "Python not found. Install Python 3.10+ with Tcl/Tk and add it to PATH.", 16, "Learning Map"
    WScript.Quit 1
End If
shell.CurrentDirectory = folder
shell.Run Chr(34) & runner & Chr(34) & arguments & " " & Chr(34) & entry & Chr(34), 1, False
