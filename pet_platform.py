"""桌宠的平台配置与输入区域；输入区域不参与画面裁切。"""
from __future__ import annotations

import ctypes
import os
import platform
import sys
from pathlib import Path


def configure_pet_platform() -> None:
    if not sys.platform.startswith('linux'):
        return
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    if platform.machine().lower() in ('x86_64', 'amd64'):
        cursor = root / 'vendor/linux-x86_64/libxcb-cursor.so.0'
        if cursor.is_file():
            try:
                ctypes.CDLL(str(cursor), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass
    if os.environ.get('DISPLAY') and not os.environ.get('QT_QPA_PLATFORM'):
        # XWayland 支持绝对定位与自由拖动；纯 Wayland 作为后备。
        os.environ['QT_QPA_PLATFORM'] = 'xcb;wayland'


class X11InputShape:
    """仅设置 X11 ShapeInput，避免 QWidget.setMask 把动作画面裁掉。"""

    class Rectangle(ctypes.Structure):
        _fields_ = [('x', ctypes.c_short), ('y', ctypes.c_short),
                    ('width', ctypes.c_ushort), ('height', ctypes.c_ushort)]

    def __init__(self, window_id: int):
        self.window_id = window_id
        self.xlib = ctypes.CDLL('libX11.so.6')
        self.shape = ctypes.CDLL('libXext.so.6')
        self.xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.xlib.XOpenDisplay.restype = ctypes.c_void_p
        self.xlib.XFlush.argtypes = [ctypes.c_void_p]
        self.xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.shape.XShapeCombineRectangles.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(self.Rectangle), ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.display = self.xlib.XOpenDisplay(None)
        if not self.display:
            raise OSError('无法连接 X11 桌面')

    def set_rectangles(self, rectangles: list[tuple[int, int, int, int]]) -> None:
        array = (self.Rectangle * len(rectangles))(
            *(self.Rectangle(*rect) for rect in rectangles))
        # ShapeInput=2，ShapeSet=0，Unsorted=0；不改变 Bounding/Clip。
        self.shape.XShapeCombineRectangles(self.display, self.window_id, 2, 0, 0,
                                          array, len(array), 0, 0)
        self.xlib.XFlush(self.display)

    def close(self) -> None:
        if self.display:
            self.xlib.XCloseDisplay(self.display)
            self.display = None
