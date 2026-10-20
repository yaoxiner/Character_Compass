param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Destination,
    [string]$BuildDirectory = 'build/CharacterCompass',
    [string]$DependencyReport = 'dist/dependency-versions.txt',
    [string]$RuntimeLogs = ''
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $Destination | Out-Null
$destinationPath = (Resolve-Path $Destination).Path

# 只收集报告所在的三个层级，不递归拷贝安装目录里的 Qt 资源。
foreach ($relative in @('portable', 'installed', 'installed/app')) {
    $folder = Join-Path $Source $relative
    if (!(Test-Path -LiteralPath $folder)) { continue }
    $target = Join-Path $destinationPath $relative
    New-Item -ItemType Directory -Force $target | Out-Null
    Get-ChildItem -LiteralPath $folder -File | Where-Object {
        $_.Extension -in @('.json', '.png', '.log')
    } | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $target -Force }
}

$diagnostics = @{
    'dependency-versions.txt' = $DependencyReport
    'pyinstaller-warnings.txt' = (Join-Path $BuildDirectory 'warn-CharacterCompass.txt')
    'pyinstaller-dependencies.html' = (Join-Path $BuildDirectory 'xref-CharacterCompass.html')
}
foreach ($name in $diagnostics.Keys) {
    if (Test-Path -LiteralPath $diagnostics[$name] -PathType Leaf) {
        Copy-Item -LiteralPath $diagnostics[$name] -Destination (Join-Path $destinationPath $name) -Force
    }
}
if (!$RuntimeLogs -and $env:APPDATA) { $RuntimeLogs = Join-Path $env:APPDATA 'CharacterCompass/logs' }
if ($RuntimeLogs -and (Test-Path -LiteralPath $RuntimeLogs)) {
    $target = Join-Path $destinationPath 'runtime-logs'
    New-Item -ItemType Directory -Force $target | Out-Null
    Get-ChildItem -LiteralPath $RuntimeLogs -Filter 'desktop*.log*' -File |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $target -Force }
}
$count = @(Get-ChildItem -LiteralPath $destinationPath -Recurse -File).Count
Write-Host "Collected $count diagnostic files into $destinationPath"
