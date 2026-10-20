param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$Reports
)
$ErrorActionPreference = 'Stop'
if (!$IsWindows) { throw 'Installer validation must run on Windows.' }
$setup = (Resolve-Path $Installer).Path
New-Item -ItemType Directory -Force $Reports | Out-Null
$reportsPath = (Resolve-Path $Reports).Path
$installPath = Join-Path $reportsPath '中文安装路径 空格\CharacterCompass'
$installLog = Join-Path $reportsPath 'install.log'
$process = Start-Process $setup -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-',
    ('/DIR="' + $installPath + '"'), ('/LOG="' + $installLog + '"')) -PassThru
if (!$process.WaitForExit(180000)) { $process.Kill($true); throw 'Installer timed out.' }
if ($process.ExitCode -ne 0) { throw "Installer failed: $($process.ExitCode)" }
$app = Join-Path $installPath 'CharacterCompass.exe'
if (!(Test-Path $app)) { throw 'Installed executable is missing.' }
$shell = New-Object -ComObject WScript.Shell
$shortcutPaths = @(
    (Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'Character Compass.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'Character Compass.lnk')
)
foreach ($path in $shortcutPaths) {
    if (!(Test-Path $path)) { throw "Shortcut missing: $path" }
    $shortcut = $shell.CreateShortcut($path)
    if ($shortcut.TargetPath -ine $app) { throw "Shortcut points to the wrong executable: $path" }
}
$shortcutReport = @{ok=$true; executable=$app; shortcuts=$shortcutPaths}
$shortcutReport | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $reportsPath 'installer.json') -Encoding utf8
& "$PSScriptRoot/check_windows_package.ps1" -Executable $app -Reports (Join-Path $reportsPath 'app') -SkipPathCopy
if (!$?) { throw 'Installed application validation failed.' }

$uninstaller = Join-Path $installPath 'unins000.exe'
if (!(Test-Path $uninstaller)) { throw 'Uninstaller is missing.' }
$uninstallLog = Join-Path $reportsPath 'uninstall.log'
$uninstall = Start-Process $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',
    ('/LOG="' + $uninstallLog + '"')) -PassThru
if (!$uninstall.WaitForExit(120000)) { $uninstall.Kill($true); throw 'Uninstaller timed out.' }
if ($uninstall.ExitCode -ne 0) { throw "Uninstaller failed: $($uninstall.ExitCode)" }
if (Test-Path $app) { throw 'Uninstall did not remove the executable.' }
Write-Host 'PASS: setup exe installation, desktop/start menu shortcuts, installed application, and uninstall.'
