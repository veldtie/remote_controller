Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = ""

If WScript.Arguments.Count > 0 Then
  exePath = WScript.Arguments(0)
Else
  exePath = fso.BuildPath(baseDir, "dist\\RemoteControllerClient.exe")
End If

If fso.FileExists(exePath) Then
  shell.Run Chr(34) & exePath & Chr(34), 0
End If
