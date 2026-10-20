"""在 X11/XWayland 上只操作本脚本启动的打包桌宠，验证真实窗口与鼠标拖动。"""
import ctypes as C
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time


class XImage(C.Structure):
    _fields_ = [
        ('width', C.c_int), ('height', C.c_int), ('xoffset', C.c_int),
        ('format', C.c_int), ('data', C.c_void_p), ('byte_order', C.c_int),
        ('bitmap_unit', C.c_int), ('bitmap_bit_order', C.c_int),
        ('bitmap_pad', C.c_int), ('depth', C.c_int), ('bytes_per_line', C.c_int),
        ('bits_per_pixel', C.c_int), ('red_mask', C.c_ulong),
        ('green_mask', C.c_ulong), ('blue_mask', C.c_ulong),
        ('obdata', C.c_void_p)]


x = C.CDLL('libX11.so.6')
t = C.CDLL('libXtst.so.6')
s = C.CDLL('libXext.so.6')
Display = C.c_void_p
Window = C.c_ulong
IntPtr = C.POINTER(C.c_int)
UIntPtr = C.POINTER(C.c_uint)
x.XOpenDisplay.argtypes = [C.c_char_p]
x.XOpenDisplay.restype = Display
x.XDefaultRootWindow.argtypes = [Display]
x.XDefaultRootWindow.restype = Window
x.XQueryTree.argtypes = [Display, Window, C.POINTER(Window), C.POINTER(Window),
                        C.POINTER(C.POINTER(Window)), UIntPtr]
x.XFetchName.argtypes = [Display, Window, C.POINTER(C.c_void_p)]
x.XInternAtom.argtypes = [Display, C.c_char_p, C.c_int]
x.XInternAtom.restype = C.c_ulong
x.XGetWindowProperty.argtypes = [Display, Window, C.c_ulong, C.c_long, C.c_long,
                                C.c_int, C.c_ulong, C.POINTER(C.c_ulong), IntPtr,
                                C.POINTER(C.c_ulong), C.POINTER(C.c_ulong),
                                C.POINTER(C.c_void_p)]
x.XFree.argtypes = [C.c_void_p]
x.XGetGeometry.argtypes = [Display, Window, C.POINTER(Window), IntPtr, IntPtr,
                          UIntPtr, UIntPtr, UIntPtr, UIntPtr]
x.XTranslateCoordinates.argtypes = [Display, Window, Window, C.c_int, C.c_int,
                                    IntPtr, IntPtr, C.POINTER(Window)]
x.XQueryPointer.argtypes = [Display, Window, C.POINTER(Window), C.POINTER(Window),
                           IntPtr, IntPtr, IntPtr, IntPtr, UIntPtr]
x.XFlush.argtypes = [Display]
x.XCloseDisplay.argtypes = [Display]
x.XGetImage.argtypes = [Display, Window, C.c_int, C.c_int, C.c_uint,
                       C.c_uint, C.c_ulong, C.c_int]
x.XGetImage.restype = C.POINTER(XImage)
x.XDestroyImage.argtypes = [C.POINTER(XImage)]
t.XTestFakeMotionEvent.argtypes = [Display, C.c_int, C.c_int, C.c_int, C.c_ulong]
t.XTestFakeButtonEvent.argtypes = [Display, C.c_uint, C.c_int, C.c_ulong]
s.XShapeQueryExtents.argtypes = [Display, Window, IntPtr, IntPtr, IntPtr, UIntPtr,
                                UIntPtr, IntPtr, IntPtr, IntPtr, UIntPtr, UIntPtr]


def find_named(display, parent, excluded=()):
    name, actual, fmt, length, rest = C.c_void_p(), C.c_ulong(), C.c_int(), C.c_ulong(), C.c_ulong()
    atom = x.XInternAtom(display, b'_NET_WM_NAME', 0)
    x.XGetWindowProperty(display, parent, atom, 0, 256, 0, 0, C.byref(actual),
                         C.byref(fmt), C.byref(length), C.byref(rest), C.byref(name))
    if name.value:
        title = C.string_at(name, length.value).decode('utf-8', errors='replace')
        x.XFree(name)
        if title == '故事海同伴' and parent not in excluded:
            return parent
    root, owner, count = Window(), Window(), C.c_uint()
    children = C.POINTER(Window)()
    if x.XQueryTree(display, parent, C.byref(root), C.byref(owner),
                    C.byref(children), C.byref(count)):
        ids = [children[i] for i in range(count.value)]
        if children:
            x.XFree(children)
        for child in ids:
            found = find_named(display, child, excluded)
            if found:
                return found
    return None


def geometry(display, window, root):
    r, child = Window(), Window()
    ax, ay, gx, gy = C.c_int(), C.c_int(), C.c_int(), C.c_int()
    width, height, border, depth = [C.c_uint() for _ in range(4)]
    assert x.XGetGeometry(display, window, C.byref(r), C.byref(ax), C.byref(ay),
                          C.byref(width), C.byref(height), C.byref(border), C.byref(depth))
    x.XTranslateCoordinates(display, window, root, 0, 0,
                            C.byref(gx), C.byref(gy), C.byref(child))
    return gx.value, gy.value, width.value, height.value


def capture(display, window, width, height):
    image = x.XGetImage(display, window, 0, 0, width, height, C.c_ulong(-1).value, 2)
    assert image
    try:
        obj = image.contents
        assert obj.depth == 32 and obj.bits_per_pixel == 32
        data = C.string_at(obj.data, obj.bytes_per_line * obj.height)
        return data, obj.bytes_per_line, obj.byte_order
    finally:
        x.XDestroyImage(image)


def main():
    display = x.XOpenDisplay(None)
    assert display, '需要 X11/XWayland 桌面'
    root = x.XDefaultRootWindow(display)
    r, child = Window(), Window()
    ox, oy, lx, ly, buttons = C.c_int(), C.c_int(), C.c_int(), C.c_int(), C.c_uint()
    x.XQueryPointer(display, root, C.byref(r), C.byref(child), C.byref(ox), C.byref(oy),
                     C.byref(lx), C.byref(ly), C.byref(buttons))
    process = None
    held = False

    def motion(px, py):
        t.XTestFakeMotionEvent(display, -1, px, py, 0)
        x.XFlush(display)
        time.sleep(.07)

    def button(down):
        nonlocal held
        held = down
        t.XTestFakeButtonEvent(display, 1, int(down), 0)
        x.XFlush(display)
        time.sleep(.07)

    try:
        existing = set()
        while previous := find_named(display, root, existing):
            existing.add(previous)
        executable = str(Path(sys.argv[1]).resolve())
        env = dict(os.environ)
        env.pop('QT_QPA_PLATFORM', None)
        process = subprocess.Popen([executable, '--pet', 'http://127.0.0.1:48631'], env=env)
        deadline = time.monotonic() + 6
        window = None
        while time.monotonic() < deadline:
            assert process.poll() is None, '打包桌宠提前退出'
            window = find_named(display, root, existing)
            if window:
                break
            time.sleep(.08)
        assert window, '默认平台未能创建 X11/XWayland 桌宠窗口'
        time.sleep(.2)
        px, py, width, height = geometry(display, window, root)
        scale = width / 190
        assert abs(height - 300 * scale) < 2
        anchor_x, anchor_y = round(95 * scale), round(150 * scale)
        motion(px + anchor_x, py + anchor_y)
        button(True)
        button(False)
        data, stride, order = capture(display, window, width, height)
        offset = round(20 * scale) * stride + round(176 * scale) * 4
        assert all(c > 235 for c in data[offset:offset + 4]), '打包窗口的白色对话卡片没有显示'
        assert geometry(display, window, root) == (px, py, width, height), '点击时窗口跳动'
        button(True)
        for i in range(1, 5):
            motion(px + anchor_x - i * 20, py + anchor_y - i * 15)
        hashes = set()
        for _ in range(6):
            data, stride, order = capture(display, window, width, height)
            hashes.add(hashlib.sha256(data).hexdigest())
            time.sleep(.12)
        assert len(hashes) >= 4, '打包版拖动时没有播放足够的中间动作'
        actual = geometry(display, window, root)
        assert actual[:2] == (px - 80, py - 60), ('打包版抓取点偏移', actual)
        button(False)
        time.sleep(1.2)
        data, stride, order = capture(display, window, width, height)
        alpha_index = 3 if order == 0 else 0
        feet = sum(data[y * stride + xx * 4 + alpha_index] > 160
                   for y in range(round(228 * scale), round(276 * scale))
                   for xx in range(round(31 * scale), round(159 * scale)))
        assert feet > 20, '打包版松手后的脚部不可见'
        bounds, bx, by, bw, bh = C.c_int(), C.c_int(), C.c_int(), C.c_uint(), C.c_uint()
        clip, cx, cy, cw, ch = C.c_int(), C.c_int(), C.c_int(), C.c_uint(), C.c_uint()
        s.XShapeQueryExtents(display, window, C.byref(bounds), C.byref(bx), C.byref(by),
                            C.byref(bw), C.byref(bh), C.byref(clip), C.byref(cx),
                            C.byref(cy), C.byref(cw), C.byref(ch))
        assert not bounds.value and not clip.value, '系统仍在裁切角色画布'
        print(f'打包版真实鼠标检查通过：拖动位移 (-80, -60)，{len(hashes)} 张不同画面，脚部 {feet} 像素，画布无系统裁切。')
    finally:
        if held:
            button(False)
        if process is not None:
            process.terminate()
            process.wait(timeout=4)
        motion(ox.value, oy.value)
        x.XCloseDisplay(display)


if __name__ == '__main__':
    main()
