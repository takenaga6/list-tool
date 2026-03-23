$shell = New-Object -ComObject WScript.Shell
$startup = $shell.SpecialFolders("Startup")
$shortcut = $shell.CreateShortcut("$startup\ListTool_Daemon.lnk")
$shortcut.TargetPath = "C:\Users\user\list_tool\start_daemon.bat"
$shortcut.WorkingDirectory = "C:\Users\user\list_tool"
$shortcut.WindowStyle = 1
$shortcut.Description = "ListTool list-daemon"
$shortcut.Save()
Write-Host "OK: $startup\ListTool_Daemon.lnk"
