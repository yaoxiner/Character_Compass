"""跨平台桌面入口；写作台与原生 Qt 桌宠分别运行。"""
from __future__ import annotations

import subprocess
import sys
import io
import logging
import os
from logging.handlers import RotatingFileHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread

# 写作台和原生同伴使用同一绑定，避免系统 QT_API 指向未打包的 PySide/Qt5。
os.environ['QT_API'] = 'pyqt6'
from app import DATA_ROOT, Handler, WEB, store


def configure_stdio(log_dir=None):
    """Windows 无控制台 exe 没有标准输出；诊断信息写入可轮转的本机日志。"""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    folder = Path(log_dir) if log_dir else DATA_ROOT.parent / 'logs'
    folder.mkdir(parents=True, exist_ok=True)
    name = 'desktop-pet.log' if sys.argv[1:2] == ['--pet'] else 'desktop.log'
    handler = RotatingFileHandler(folder / name, maxBytes=2_000_000,
                                  backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    logger = logging.getLogger('CharacterCompass.desktop')
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    class LogStream(io.TextIOBase):
        @property
        def encoding(self):
            return 'utf-8'

        def write(self, value):
            if value.strip():
                logger.info(value.rstrip())
            return len(value)

        def flush(self):
            handler.flush()

    if sys.stdout is None:
        sys.stdout = LogStream()
    if sys.stderr is None:
        sys.stderr = LogStream()
    return handler


def pet_command(base_url: str) -> list[str]:
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--pet', base_url]
    return [sys.executable, str(Path(__file__).resolve()), '--pet', base_url]


class DesktopBridge:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.pet_process: subprocess.Popen | None = None
        self.lock = Lock()

    def open_pet(self):
        with self.lock:
            if self.pet_process is None or self.pet_process.poll() is not None:
                options = {}
                if sys.platform == 'win32':
                    # 无控制台 exe 的标准句柄可能为空；对子进程显式提供有效句柄。
                    options = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000))
                self.pet_process = subprocess.Popen(pet_command(self.base_url), **options)
        return True

    def close_pet(self):
        with self.lock:
            process = self.pet_process
            self.pet_process = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        return True


def main(*, on_ready=None):
    if len(sys.argv) == 3 and sys.argv[1] == '--pet':
        from native_pet import run_pet
        return run_pet(sys.argv[2])

    if len(sys.argv) == 3 and sys.argv[1] in ('--check-desktop', '--check-pet'):
        from desktop_checks import run_check
        return run_check(sys.argv[1], Path(sys.argv[2]))

    if sys.argv[1:] == ['--check-package']:
        import webview
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from pet_assets import POSE_FILES, SHEET_FILES
        for resource in ('index.html', 'assets/icon.png',
                         *(f'assets/{filename}' for filename in
                           (*POSE_FILES.values(), *SHEET_FILES.values()))):
            if not (WEB / resource).is_file():
                raise SystemExit(f'打包资源缺失：{resource}')
        if sys.platform.startswith('linux'):
            import platform
            if platform.machine().lower() in ('x86_64', 'amd64'):
                cursor = WEB.parent / 'vendor/linux-x86_64/libxcb-cursor.so.0'
                if not cursor.is_file():
                    raise SystemExit('打包资源缺失：桌宠 XWayland 运行库')
        print('桌面包检查通过：写作窗口、Qt WebEngine 和角色资源均可加载。')
        return 0

    try:
        import webview
    except ImportError as exc:
        raise SystemExit(f'无法加载桌面窗口组件：{exc}。源码运行时请安装 requirements-desktop.txt。') from exc

    data_store = store()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    Thread(target=server.serve_forever, daemon=True, name='CharacterCompassHTTP').start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    bridge = DesktopBridge(base)
    webview.settings['ALLOW_DOWNLOADS'] = True
    window = webview.create_window('Character Compass · 长篇小说创作室', base + '/',
                          js_api=bridge, width=1180, height=800,
                          min_size=(780, 560), background_color='#f3f7f8')
    options = {'gui': 'qt'}
    icon = WEB / 'assets' / ('icon.ico' if sys.platform == 'win32' else 'icon.png')
    if icon.exists():
        options['icon'] = str(icon)
    print(f'Character Compass 桌面模式；作品目录：{data_store.root}')
    try:
        bridge.open_pet()
        if on_ready is None:
            webview.start(**options)
        else:
            webview.start(on_ready, (window, bridge), **options)
    finally:
        bridge.close_pet()
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    configure_stdio()
    raise SystemExit(main())
