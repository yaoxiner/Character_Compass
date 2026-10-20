# 通过文件句柄解析最终路径，兼容 8.3 短路径、路径分隔符及目录联接。
if (!('CharacterCompass.WindowsFilePath' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
using Microsoft.Win32.SafeHandles;
namespace CharacterCompass {
    // IShellLinkW 的方法顺序必须与 Windows COM vtable 一致。
    [ComImport, Guid("000214F9-0000-0000-C000-000000000046"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    internal interface IShellLinkW {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path,
                     int capacity, IntPtr findData, uint flags);
        void GetIDList(out IntPtr idList);
        void SetIDList(IntPtr idList);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder value, int capacity);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string value);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder value, int capacity);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string value);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder value, int capacity);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string value);
        void GetHotkey(out short hotkey);
        void SetHotkey(short hotkey);
        void GetShowCmd(out int command);
        void SetShowCmd(int command);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path,
                             int capacity, out int index);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string path, int index);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string path, uint reserved);
        void Resolve(IntPtr window, uint flags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string path);
    }

    public static class WindowsShellLink {
        private static object Create() {
            Type type = Type.GetTypeFromCLSID(new Guid("00021401-0000-0000-C000-000000000046"), true);
            return Activator.CreateInstance(type);
        }

        public static void Save(string shortcut, string target) {
            object instance = Create();
            try {
                ((IShellLinkW)instance).SetPath(Path.GetFullPath(target));
                // .NET 的 IPersistFile 使用 LPWStr，文件名不经过 ANSI 代码页。
                ((IPersistFile)instance).Save(Path.GetFullPath(shortcut), true);
            } finally {
                Marshal.FinalReleaseComObject(instance);
            }
        }

        public static string ReadTarget(string shortcut) {
            object instance = Create();
            try {
                ((IPersistFile)instance).Load(Path.GetFullPath(shortcut), 0);
                var target = new StringBuilder(32768);
                // SLGP_RAWPATH：读取已保存的目标，不启动 UI 或自动改指到其它文件。
                ((IShellLinkW)instance).GetPath(target, target.Capacity, IntPtr.Zero, 4);
                if (target.Length == 0) throw new InvalidOperationException("Shortcut target is empty.");
                return target.ToString();
            } finally {
                Marshal.FinalReleaseComObject(instance);
            }
        }
    }

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

function Write-WindowsShortcut([string]$Path, [string]$Target) {
    if (!$IsWindows) { throw 'Shell shortcuts require Windows.' }
    [CharacterCompass.WindowsShellLink]::Save($Path, $Target)
}

function Read-WindowsShortcutTarget([string]$Path) {
    if (!$IsWindows) { throw 'Shell shortcuts require Windows.' }
    return [CharacterCompass.WindowsShellLink]::ReadTarget($Path)
}
