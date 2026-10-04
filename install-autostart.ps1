# Start Career OS silently every time you log in to Windows (so the 07:30 / 17:30 scouts run).
# Undo: delete "Career OS.lnk" from shell:startup
$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "Career OS.lnk"
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = "powershell.exe"
$s.Arguments = "-NoProfile -WindowStyle Minimized -ExecutionPolicy Bypass -File `"$PSScriptRoot\start.ps1`" -NoBrowser"
$s.WorkingDirectory = $PSScriptRoot
$s.WindowStyle = 7
$s.Save()
Write-Host "Career OS will start automatically when you log in. Shortcut: $lnk"
