# 通过文件句柄解析最终路径，兼容 8.3 短路径、路径分隔符及目录联接。
if (!('CharacterCompass.WindowsFilePath' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;
namespace CharacterCompass {
    public static class WindowsFilePath {
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
        private static extern uint GetFinalPathNameByHandleW(
            SafeFileHandle handle, StringBuilder buffer, uint size, uint flags);
        public static string Resolve(string path) {
            using (var stream = File.Open(path, FileMode.Open, FileAccess.Read,
                                           FileShare.ReadWrite | FileShare.Delete)) {
                var buffer = new StringBuilder(512);
                while (true) {
                    // FILE_NAME_NORMALIZED | VOLUME_NAME_NT：不依赖盘符别名。
                    uint length = GetFinalPathNameByHandleW(stream.SafeFileHandle,
                        buffer, (uint)buffer.Capacity, 2);
                    if (length == 0) throw new Win32Exception(Marshal.GetLastWin32Error());
                    if (length < buffer.Capacity) return buffer.ToString();
                    buffer.Capacity = checked((int)length + 1);
                }
            }
        }
    }
}
'@
}

function Resolve-WindowsFilePath([string]$Path) {
    if (!$IsWindows) { throw 'Windows file path resolution requires Windows.' }
    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'Shortcut target is empty.' }
    $expanded = [Environment]::ExpandEnvironmentVariables($Path.Trim('"'))
    return [CharacterCompass.WindowsFilePath]::Resolve($expanded)
}
