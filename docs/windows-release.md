# Windows 安装包与验收

## 安装产物

Windows 构建生成 `CharacterCompass-Setup.exe`，内含 Python、Qt WebEngine、写作页面和高清桌面同伴。安装程序创建桌面与开始菜单快捷方式，默认安装到当前用户目录。小说与 Key 单独保存在 `%APPDATA%\CharacterCompass\`。

安装目标为 Windows 10 1809 及以上、Windows 11 的 x64 环境，依据 [Qt 6.11 的 Windows 支持范围](https://doc.qt.io/qt-6.11/windows.html)配置安装程序最低版本。当前工作流生成 x64 包。桌面依赖固定为本机已验证的 pywebview 6.2.1、PyQt6 6.11.0、Qt WebEngine 6.11.0 和 QtPy 2.4.3，避免首次构建意外换用不同主版本。

## 从 GitHub 获取 exe

1. 上传完整源码，包含 `.github/workflows/`。推送到 `main` 或 `master` 会自动执行 **Build Windows desktop app**；也可在 Actions 中手动运行，或推送 `v*` 标签。
2. 等待工作流通过。它会构建程序、启动验收、编译安装包、静默安装并再次验收，随后检查卸载。
3. 打开本次运行的 Artifacts，下载 **CharacterCompass-Windows-Setup**。
4. 解压下载的压缩包，双击里面的 **CharacterCompass-Setup.exe**，安装后通过桌面快捷方式启动。

另有 **CharacterCompass-Windows** 便携包，需保留整个目录。验收报告位于 **CharacterCompass-Windows-Checks**。

## Windows 工作流的验收内容

- 安装桌面依赖后运行全部单元测试，确保 Qt 检查实际执行。
- 生成多尺寸 ICO，打包 Python、Qt WebEngine、网页和角色资源。
- 将便携包放在带中文与空格的路径，实际启动打包后的写作窗口。
- 通过页面调用本机 API 保存中文世界观和本次章节要求，确认独立桌宠子进程可启动。
- 使用 Windows 原生 Qt 平台检查 100% 和 200% 缩放：44 张高清姿势、透明无边框置顶窗口、白色卡片、连续拖动、脚部完整性、松手恢复，以及高清／像素切换。
- 静默安装 `CharacterCompass-Setup.exe` 到中文路径，检查桌面与开始菜单快捷方式的目标，再对安装后的程序执行同一套验收。
- 执行卸载，确认程序文件移除。

任何一道验收失败，本次工作流不会上传正式安装包；失败报告和打包诊断文件仍会保存。

## 本次上传前的验证范围

2026-10-20：本机为 Linux，没有 Windows、Wine 或 Windows 虚拟机。本机已验证单元测试、源码启动与打包后的 Qt 写作窗口和桌宠验收入口；**这不代表 Windows 实机验收已通过**。Windows exe 的实际构建、运行、安装和卸载结果，以第一次 Windows Actions 运行报告为准。

Windows 无控制台程序的错误会保存到 `%APPDATA%\CharacterCompass\logs\desktop.log`，日志自动轮转。处理方式依据 [PyInstaller 关于 Windows 无控制台程序标准输出的说明](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#sys-stdin-sys-stdout-and-sys-stderr-in-noconsole-windowed-applications-windows-only)。

## 上传源码

运行 `python tools/package_source.py` 生成 `dist/CharacterCompass-GitHub-source.zip`。解压后上传里面的源码目录，包含 `.github` 文件夹。此包排除本机 `.env`、小说、依赖、构建目录和回退安装包；如果发现源码中包含当前本机 Key，会停止生成。

在 Windows 构建环境使用 PowerShell 7（pwsh）也可单独运行验收：

```powershell
./tools/check_windows_package.ps1 -Executable dist/CharacterCompass/CharacterCompass.exe -Reports dist/windows-checks
./tools/check_windows_installer.ps1 -Installer dist/installer/CharacterCompass-Setup.exe -Reports dist/installer-checks
```
