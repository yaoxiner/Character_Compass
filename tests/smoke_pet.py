"""运行 Qt 事件循环测试拖动、持续动画、脚部可见性与屏幕边缘。

QT_QPA_PLATFORM=offscreen python tests/smoke_pet.py
PET_REAL_MOUSE=1 python tests/smoke_pet.py  # X11/XWayland，短暂操作真实鼠标
"""
import ctypes
import os
import sys
import time
import traceback
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt, QTimer
from PyQt6.QtGui import QCursor, QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

from native_pet import FIGURE_HEIGHT, FIGURE_WIDTH, run_pet
from pet_assets import POSE_KEYS
from pet_animation import AnimationModel, CLIPS


class MouseDriver:
    def __init__(self, widget):
        self.widget = widget
        self.point = QPoint()
        self.held = False

    def send(self, kind):
        button = (Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else
                  Qt.MouseButton.LeftButton)
        event = QMouseEvent(kind, QPointF(self.widget.mapFromGlobal(self.point)),
                            QPointF(self.point), button,
                            Qt.MouseButton.LeftButton if self.held else Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(self.widget, event)

    def move(self, point):
        self.point = point
        self.send(QEvent.Type.MouseMove)

    def press(self):
        self.held = True
        self.send(QEvent.Type.MouseButtonPress)

    def release(self):
        self.held = False
        self.send(QEvent.Type.MouseButtonRelease)

    def close(self):
        if self.held:
            self.release()


class XTestMouseDriver(MouseDriver):
    def __init__(self, widget):
        super().__init__(widget)
        assert QApplication.platformName() == 'xcb', '真实鼠标检查需要 X11/XWayland'
        self.original = QCursor.pos()
        self.xlib = ctypes.CDLL('libX11.so.6')
        self.xtest = ctypes.CDLL('libXtst.so.6')
        self.xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.xlib.XOpenDisplay.restype = ctypes.c_void_p
        self.xlib.XFlush.argtypes = [ctypes.c_void_p]
        self.xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.xtest.XTestFakeMotionEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        self.xtest.XTestFakeButtonEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        self.display = self.xlib.XOpenDisplay(None)
        assert self.display, 'XTest 无法连接桌面'

    def move(self, point):
        self.point = point
        scale = self.widget.devicePixelRatioF()
        self.xtest.XTestFakeMotionEvent(self.display, -1,
                                       round(point.x() * scale), round(point.y() * scale), 0)
        self.xlib.XFlush(self.display)

    def press(self):
        self.held = True
        self.xtest.XTestFakeButtonEvent(self.display, 1, 1, 0)
        self.xlib.XFlush(self.display)

    def release(self):
        self.held = False
        self.xtest.XTestFakeButtonEvent(self.display, 1, 0, 0)
        self.xlib.XFlush(self.display)

    def close(self):
        super().close()
        self.move(self.original)
        self.xlib.XCloseDisplay(self.display)


original_show = QWidget.show
captured = {'ok': False, 'driver': None}


def later(milliseconds, callback):
    def checked():
        try:
            callback()
        except Exception:
            traceback.print_exc()
            if captured['driver']:
                captured['driver'].close()
                captured['driver'] = None
            QApplication.instance().exit(1)
    QTimer.singleShot(milliseconds, checked)


def snapshot(widget):
    return widget.grab().toImage().scaled(widget.size())


def show_and_check(widget):
    original_show(widget)
    if widget.windowTitle() != '故事海同伴':
        return
    samples = []
    state = {}

    def check_feet():
        picture = snapshot(widget)
        frame = widget.frames[widget.animation.current_frame].toImage().scaled(FIGURE_WIDTH, FIGURE_HEIGHT)
        x, y = widget.pose_position()
        assert widget.rect().contains(QRect(x, y, frame.width(), frame.height()))
        count = 0
        for sy in range(frame.height() * 3 // 4, frame.height()):
            for sx in range(frame.width()):
                if frame.pixelColor(sx, sy).alpha() > 180:
                    assert picture.pixelColor(x + sx, y + sy).alpha() > 160, (
                        '脚部被裁掉', widget.animation.current_clip, sx, sy)
                    count += 1
        assert count > 0, '角色帧没有脚部像素'

    def initial():
        assert set(widget.frames) == POSE_KEYS
        assert widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        assert widget.mask().isEmpty(), '角色仍在使用会裁切动画的窗口 mask'
        area = widget.screen().availableGeometry()
        widget.move(area.topLeft() + QPoint(60, 60))
        widget.motion_timer.stop()
        seen = set()
        for name, clip in CLIPS.items():
            for index, pose in enumerate(clip.frames):
                if pose in seen:
                    continue
                widget.animation = AnimationModel()
                widget.animation.overlay = name
                widget.animation.frame_index = index
                widget.repaint()
                check_feet()
                seen.add(pose)
        assert seen == POSE_KEYS
        for pose, frame in widget.frames.items():
            if '_' not in pose:
                continue
            image = frame.toImage()
            edge = [(x, y) for y in range(image.height()) for x in (0, image.width() - 1)]
            edge += [(x, y) for x in range(image.width()) for y in (0, image.height() - 1)]
            assert all(image.pixelColor(x, y).alpha() == 0 for x, y in edge), (
                '动作帧边缘没有透明隔离，可能混入邻帧碎片', pose)
        widget.animation = AnimationModel()
        # 画质切换不改变当前帧、动作进度、窗口位置和抓取位置。
        widget.animation.begin_drag()
        widget.animation.advance(200)
        progress = (widget.animation.current_frame, widget.animation.elapsed_ms)
        position, size = widget.pos(), widget.size()
        widget.set_quality('pixel')
        assert (widget.animation.current_frame, widget.animation.elapsed_ms) == progress
        widget.set_quality('smooth')
        assert widget.quality == 'smooth'
        assert (widget.animation.current_frame, widget.animation.elapsed_ms) == progress
        assert widget.pos() == position and widget.size() == size
        widget.animation = AnimationModel()
        deadline = widget._next_stretch
        assert 250 < deadline - time.monotonic() <= 300, '启动后过早打哈欠'
        with patch('native_pet.time.monotonic', return_value=deadline - .01):
            widget.animate()
        assert widget.animation.current_clip == 'idle'
        with patch('native_pet.time.monotonic', return_value=deadline):
            widget.animate()
        assert widget.animation.current_clip == 'stretch'
        assert widget._next_stretch == deadline + 300
        widget.animation.advance(CLIPS['stretch'].duration_ms)
        with patch('native_pet.time.monotonic', return_value=deadline + 299.99):
            widget.animate()
        assert widget.animation.current_clip == 'idle', '两次自动打哈欠不足五分钟'
        widget._writing = True
        widget.animation.set_task('draft')
        with patch('native_pet.time.monotonic', return_value=deadline + 300):
            widget.animate()
        assert widget.animation.current_clip == 'working', '工作时插入了打哈欠'
        widget._writing = False
        widget._last_tick = time.monotonic()
        widget._next_stretch = widget._last_tick + 300
        assert snapshot(widget).pixelColor(0, 0).alpha() == 0
        widget.animation = AnimationModel()
        widget.motion_timer.start()
        cls = XTestMouseDriver if os.environ.get('PET_REAL_MOUSE') == '1' else MouseDriver
        driver = cls(widget)
        captured['driver'] = driver
        state['driver'] = driver
        state['local'] = QPoint(widget.figure_x + FIGURE_WIDTH // 2, widget.figure_y + 65)
        state['position'] = widget.pos()
        driver.move(widget.mapToGlobal(state['local']))
        later(80, driver.press)
        later(140, driver.release)
        later(240, clicked)

    def clicked():
        assert widget._card_title, '点击角色没有打开对话卡片'
        assert widget.pos() == state['position'], '弹出卡片时角色位置改变'
        assert widget.size().height() == 300
        assert widget.mask().isEmpty()
        card = snapshot(widget)
        color = card.pixelColor(176, 20)
        assert color.alpha() > 240 and min(color.red(), color.green(), color.blue()) > 235
        if os.environ.get('CAPTURE_PET_PREVIEW') == '1':
            card.save(str(Path(__file__).resolve().parents[1] / 'docs/native-pet-preview.png'))
        driver = state['driver']
        state['press'] = widget.mapToGlobal(state['local'])
        driver.move(state['press'])
        later(60, driver.press)
        for i in range(7):
            point = state['press'] + QPoint(25 + i * 4, 20 + i * 3)
            later(120 + i * 80, lambda point=point: driver.move(point))
            later(160 + i * 80, held_sample)
        later(820, driver.release)
        later(900, released)

    def held_sample():
        assert widget.animation.current_clip == 'drag', '按住拖动时动作提前结束'
        assert widget.pos() == state['driver'].point - state['local'], (
            '拖动抓取点发生偏移', widget.pos(), state['driver'].point - state['local'])
        assert widget.mask().isEmpty()
        assert not widget._card_title
        check_feet()
        samples.append(widget.animation.current_frame)

    def released():
        assert len(set(samples)) >= 4, ('拖动时没有播放足够的中间帧', samples)
        assert widget.animation.current_clip == 'recover'
        assert widget._drag_origin is None
        assert not widget._card_title, '松手时误触发对话'
        check_feet()
        later(1150, recovered)

    def recovered():
        assert widget.animation.current_clip == 'idle', '松手后没有恢复待机'
        check_feet()
        driver = state['driver']
        area = widget.screen().availableGeometry()
        driver.move(widget.mapToGlobal(state['local']))
        later(60, driver.press)
        later(120, lambda: driver.move(QPoint(area.center().x(), area.bottom() - 2)))
        later(210, driver.release)
        later(320, edge_checked)

    def edge_checked():
        area = widget.screen().availableGeometry()
        assert area.contains(widget.frameGeometry()), (
            '松手后窗口仍超出屏幕，脚部会不可见', area, widget.frameGeometry())
        check_feet()
        state['driver'].close()
        captured['driver'] = None
        captured['ok'] = True
        print('平台：' + QApplication.platformName() + '；拖动帧：' + ', '.join(samples))
        widget.close()
        QApplication.instance().quit()

    later(180, initial)


QWidget.show = show_and_check
run_pet('http://127.0.0.1:48631')
assert captured['ok'], '桌面同伴交互检查失败'
print('点击、连续拖动、松手恢复、所有动作脚部可见性与屏幕边缘检查通过。')
