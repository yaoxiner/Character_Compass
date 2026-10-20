$ErrorActionPreference = 'Stop'
if (!$IsWindows) { throw 'Windows shortcut regression checks require Windows.' }
. "$PSScriptRoot/../tools/windows_paths.ps1"
$root = Join-Path ([IO.Path]::GetTempPath()) ('CharacterCompass 路径检查 ' + [guid]::NewGuid().ToString())
$directory = Join-Path $root '中文 目录'
New-Item -ItemType Directory -Force $directory | Out-Null
try {
    $app = Join-Path $directory 'CharacterCompass.exe'
    $other = Join-Path $directory 'Other.exe'
    [IO.File]::WriteAllText($app, 'same bytes, distinct files')
    [IO.File]::WriteAllText($other, 'same bytes, distinct files')
    $expected = Resolve-WindowsFilePath $app
    foreach ($alias in @($app.Replace('\','/'), $app.ToUpperInvariant(), (Join-Path $directory './CharacterCompass.exe'))) {
        $resolved = Resolve-WindowsFilePath $alias
        if (![string]::Equals($expected, $resolved, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Equivalent path was rejected: $alias"
        }
    }
    if ([string]::Equals($expected, (Resolve-WindowsFilePath $other), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Different executable was accepted as the installed executable.'
    }
    Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
using System.Text;
public static class ShortcutPathTestNative {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
    public static extern uint GetShortPathNameW(string path, StringBuilder output, uint capacity);
}
'@
    $short = [Text.StringBuilder]::new(4096)
    $length = [ShortcutPathTestNative]::GetShortPathNameW($app, $short, [uint32]$short.Capacity)
    if ($length -eq 0 -or $length -ge $short.Capacity) { throw 'Failed to query Windows short path.' }
    $resolvedShort = Resolve-WindowsFilePath $short.ToString()
    if (![string]::Equals($expected, $resolvedShort, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Short and long executable paths did not resolve to the same file.'
    }
    foreach ($target in @($app, $short.ToString())) {
        $linkPath = Join-Path $root '中文 快捷方式.lnk'
        Write-WindowsShortcut -Path $linkPath -Target $target
        if (!(Test-Path -LiteralPath $linkPath)) { throw 'Unicode shortcut file was not created.' }
        $actual = Resolve-WindowsFilePath (Read-WindowsShortcutTarget $linkPath)
        if (![string]::Equals($expected, $actual, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Unicode shell shortcut did not resolve to the expected executable.'
        }
    }
    Write-WindowsShortcut -Path $linkPath -Target $other
    $wrong = Resolve-WindowsFilePath (Read-WindowsShortcutTarget $linkPath)
    if ([string]::Equals($expected, $wrong, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Shortcut to a different executable was incorrectly accepted.'
    }
    Write-Host 'PASS: Unicode shortcut filenames and targets, spaces, slash/case/dot aliases and short paths; different shortcut targets rejected.'
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force
}
