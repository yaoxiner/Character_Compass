param(
    [Parameter(Mandatory=$true)][string]$Executable,
    [Parameter(Mandatory=$true)][string]$Reports,
    [switch]$SkipPathCopy
)
$ErrorActionPreference = 'Stop'
if (!$IsWindows) { throw 'This validation must run on Windows.' }
$exe = (Resolve-Path $Executable).Path
New-Item -ItemType Directory -Force $Reports | Out-Null
$reportsPath = (Resolve-Path $Reports).Path
$copiedPath = $null
if (!$SkipPathCopy) {
    $target = Join-Path ([System.IO.Path]::GetTempPath()) ('CharacterCompass 中文路径 空格 ' + [guid]::NewGuid().ToString())
    $copiedPath = $target
    New-Item -ItemType Directory -Force $target | Out-Null
    Copy-Item (Join-Path (Split-Path $exe) '*') $target -Recurse -Force
    $exe = Join-Path $target 'CharacterCompass.exe'
}

function Invoke-AppCheck([string]$Flag, [string]$Name) {
    $report = Join-Path $reportsPath ($Name + '.json')
    $process = Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe) `
        -ArgumentList @($Flag, ('"' + $report + '"')) -PassThru
    if (!$process.WaitForExit(120000)) {
        $process.Kill($true)
        throw "Timed out: $Name"
    }
    if ($process.ExitCode -ne 0) { throw "Application failed ($($process.ExitCode)): $Name" }
    if (!(Test-Path $report)) { throw "Application did not produce report: $Name" }
    $result = Get-Content $report -Raw -Encoding utf8 | ConvertFrom-Json
    if (!$result.ok -or !$result.frozen -or $result.platform -ne 'win32') {
        throw "Application validation failed: $($result | ConvertTo-Json -Depth 8)"
    }
    $result.checks | ForEach-Object { Write-Host "PASS: $_" }
}

$oldScale = $env:QT_SCALE_FACTOR
$oldPlatform = $env:QT_QPA_PLATFORM
try {
    $env:QT_QPA_PLATFORM = 'windows'
    $env:QT_SCALE_FACTOR = '1'
    Invoke-AppCheck '--check-desktop' 'desktop'
    Invoke-AppCheck '--check-pet' 'pet-100-percent'
    $env:QT_SCALE_FACTOR = '2'
    Invoke-AppCheck '--check-pet' 'pet-200-percent'
} finally {
    $env:QT_SCALE_FACTOR = $oldScale
    $env:QT_QPA_PLATFORM = $oldPlatform
    if ($copiedPath) { Remove-Item $copiedPath -Recurse -Force -ErrorAction SilentlyContinue }
}
