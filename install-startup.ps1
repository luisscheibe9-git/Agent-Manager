param(
    [string]$Pythonw
)
$ErrorActionPreference = 'Stop'
$appDirectory = $PSScriptRoot
if (-not $Pythonw) {
    $commonDirectory = & git -C $appDirectory rev-parse --path-format=absolute --git-common-dir 2>$null
    $dataDirectory = if ($LASTEXITCODE -eq 0) { Split-Path -Parent $commonDirectory } else { $appDirectory }
    $Pythonw = Join-Path $dataDirectory '.venv\Scripts\pythonw.exe'
}
$pythonExecutable = (Resolve-Path -LiteralPath $Pythonw).Path
$startupDirectory = [Environment]::GetFolderPath('Startup')
$shortcutFile = Join-Path $startupDirectory 'Agent Manager.lnk'
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut($shortcutFile)
$shortcut.TargetPath = $pythonExecutable
$shortcut.Arguments = '"' + (Join-Path $appDirectory 'black_launcher.py') + '"'
$shortcut.WorkingDirectory = $appDirectory
$shortcut.IconLocation = (Join-Path $appDirectory 'inbox.ico') + ',0'
$shortcut.Description = 'Start Agent Manager and restore the saved chat list at sign-in'
$shortcut.WindowStyle = 7
$shortcut.Save()
Write-Output "Installed startup shortcut: $shortcutFile"
