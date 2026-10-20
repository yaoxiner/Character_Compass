$ErrorActionPreference = 'Stop'
$root = Join-Path ([IO.Path]::GetTempPath()) ('cc-report-test-' + [guid]::NewGuid().ToString())
$fixture = @{
    'source/portable/desktop.json' = '{"ok":true}'
    'source/installed/installer.json' = '{"ok":false,"target":"SHORT~1"}'
    'source/installed/install.log' = 'failed install diagnostics'
    'source/installed/app/pet-200-percent.png' = 'preview'
    'source/installed/中文安装路径 空格/CharacterCompass/_internal/asset.png' = 'exclude bundled asset'
    'source/installed/中文安装路径 空格/CharacterCompass/_internal/resource.json' = 'exclude bundled resource'
    'build/warn-CharacterCompass.txt' = 'build warnings'
    'build/xref-CharacterCompass.html' = 'build dependencies'
    'versions.txt' = 'versions'
    'logs/desktop.log.1' = 'rotated runtime log'
}
try {
    foreach ($relative in $fixture.Keys) {
        $path = Join-Path $root $relative
        New-Item -ItemType Directory -Force (Split-Path $path) | Out-Null
        [IO.File]::WriteAllText($path, $fixture[$relative])
    }
    $output = Join-Path $root 'workspace/dist/windows-checks'
    & "$PSScriptRoot/../tools/collect_windows_reports.ps1" -Source "$root/source" -Destination $output `
        -BuildDirectory "$root/build" -DependencyReport "$root/versions.txt" -RuntimeLogs "$root/logs"
    if (@(Get-ChildItem -LiteralPath $output -File -Recurse).Count -ne 8) {
        throw 'Report collection lost diagnostics or included installed program resources.'
    }
    foreach ($relative in @('portable/desktop.json','installed/installer.json','installed/install.log',
        'installed/app/pet-200-percent.png','dependency-versions.txt','pyinstaller-warnings.txt',
        'pyinstaller-dependencies.html','runtime-logs/desktop.log.1')) {
        if (!(Test-Path -LiteralPath (Join-Path $output $relative))) { throw "Missing diagnostic: $relative" }
    }
    if ([IO.File]::ReadAllText((Join-Path $output 'installed/install.log')) -ne 'failed install diagnostics') {
        throw 'Failed-run diagnostic content was changed.'
    }
    Write-Host 'PASS: failed-run reports and build/runtime logs collected in one workspace directory; installed Qt assets excluded.'
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force
}
