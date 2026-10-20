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
. "$PSScriptRoot/windows_paths.ps1"
$resolvedApp = Resolve-WindowsFilePath $app
$shortcutPaths = @(
    (Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'Character Compass.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Programs')) 'Character Compass.lnk')
)
$shortcutDetails = @()
$shortcutErrors = @()
foreach ($path in $shortcutPaths) {
    $detail = [ordered]@{shortcut=$path; expected=$app; expectedResolved=$resolvedApp; target=$null; targetResolved=$null; ok=$false; error=$null}
    try {
        if (!(Test-Path -LiteralPath $path)) { throw "Shortcut missing: $path" }
        $shortcut = $shell.CreateShortcut($path)
        $detail.target = $shortcut.TargetPath
        $detail.targetResolved = Resolve-WindowsFilePath $shortcut.TargetPath
        $detail.ok = [string]::Equals($detail.targetResolved, $resolvedApp, [StringComparison]::OrdinalIgnoreCase)
        if (!$detail.ok) { throw "Shortcut target mismatch: actual='$($detail.target)' expected='$app'" }
    } catch {
        $detail.error = $_.Exception.Message
        $shortcutErrors += $detail.error
    }
    $shortcutDetails += $detail
}
$shortcutReport = @{ok=($shortcutErrors.Count -eq 0); executable=$app; shortcuts=$shortcutDetails}
$shortcutReport | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $reportsPath 'installer.json') -Encoding utf8
if ($shortcutErrors.Count) { throw ($shortcutErrors -join '; ') }
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
