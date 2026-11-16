' Qwen Image Studio - double click to start (no console window)
' ASCII only on purpose: VBScript reads .vbs as ANSI when there is no BOM.
'
' Order of attempts:
'   1) pythonw / python found along %PATH% (normal case)
'   2) absolute locations: Windows Store alias, C:\environment\python,
'      py launcher, %LOCALAPPDATA%\Programs\Python\*, C:\Python3xx, %ProgramFiles%\Python*
' The absolute probing is a safety net for machines whose PATH is broken.
Option Explicit

Dim fso, sh, base, appPy, cands, i, exe, mode, ok
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

base = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = base
appPy = base & "\app.py"

If Not fso.FileExists(appPy) Then
  MsgBox "app.py was not found next to this file:" & vbCrLf & base, 16, "Qwen Image Studio"
  WScript.Quit 1
End If

cands = Array( _
  FindOnPath("pythonw.exe"), _
  FindOnPath("python.exe"), _
  sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Microsoft\WindowsApps\pythonw.exe"), _
  sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe"), _
  "C:\environment\python\pythonw.exe", _
  sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Launcher\pyw.exe"), _
  sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Launcher\py.exe") )

ok = False
For i = 0 To UBound(cands)
  exe = cands(i)
  If exe <> "" Then
    mode = 1
    If LCase(Right(exe, 12)) = "pythonw.exe" Then mode = 0
    If LCase(Right(exe, 7)) = "pyw.exe" Then mode = 0
    On Error Resume Next
    Err.Clear
    If fso.FileExists(exe) Then
      sh.Run """" & exe & """ """ & appPy & """", mode, False
      If Err.Number = 0 Then
        ok = True
      End If
    End If
    On Error GoTo 0
    If ok Then Exit For
  End If
Next

If Not ok Then ok = TryScanned("pythonw.exe")

If Not ok Then
  MsgBox "Could not start the Python application." & vbCrLf & vbCrLf & _
         "Install Python 3.11+ from https://www.python.org/downloads/ " & _
         "and make sure it is on PATH, then try again.", 16, "Qwen Image Studio"
  WScript.Quit 1
End If
WScript.Quit 0

' ---------------------------------------------------------------- helpers
' WshShell.Run does NOT search PATH (it passes lpApplicationName to
' CreateProcess), so resolve the interpreter ourselves along %PATH%.
Function FindOnPath(fileName)
  Dim parts, p, full
  FindOnPath = ""
  parts = Split(sh.ExpandEnvironmentStrings("%PATH%"), ";")
  For Each p In parts
    p = Trim(Replace(p, """", ""))
    If p <> "" Then
      full = p & "\" & fileName
      If fso.FileExists(full) Then
        FindOnPath = full
        Exit Function
      End If
    End If
  Next
End Function

Function TryScanned(fileName)
  Dim roots, r, found
  roots = Array( _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python"), _
    "C:\", _
    sh.ExpandEnvironmentStrings("%ProgramFiles%"), _
    sh.ExpandEnvironmentStrings("%ProgramFiles(x86)%") )
  TryScanned = False
  For Each r In roots
    found = ScanPythonRoot(r, fileName)
    If found <> "" Then
      On Error Resume Next
      sh.Run """" & found & """ """ & appPy & """", 0, False
      If Err.Number = 0 Then
        TryScanned = True
        Exit Function
      End If
      On Error GoTo 0
    End If
  Next
End Function

Function ScanPythonRoot(root, fileName)
  Dim d, folderName, target
  ScanPythonRoot = ""
  If Not fso.FolderExists(root) Then Exit Function
  On Error Resume Next
  For Each d In fso.GetFolder(root).SubFolders
    folderName = LCase(d.Name)
    If Left(folderName, 6) = "python" Then
      target = d.Path & "\" & fileName
      If fso.FileExists(target) Then
        ScanPythonRoot = target
        Exit Function
      End If
    End If
  Next
  On Error GoTo 0
End Function
