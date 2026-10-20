"""原生透明桌面同伴：单角色窗口、拖动动作与白色对话卡片。"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

from pet_animation import AnimationModel
from pet_assets import FIGURE_WIDTH, FIGURE_HEIGHT, load_pet_frames
from pet_platform import X11InputShape, configure_pet_platform

WEB = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'web'
STRETCH_INTERVAL_SECONDS = 5 * 60

TASK_NAMES = {
    'analyze': '正在整理人物性格…',
    'plan': '正在推演人物弧线…',
    'draft': '正在写场景草稿…',
    'draft_pro': '正在写重点场景…',
    'summarize': '正在记录章节记忆…',
}

def run_pet(base_url: str, *, on_ready=None) -> int:
    if not base_url.startswith('http://127.0.0.1:'):
        raise ValueError('桌面同伴只能连接本机写作台。')

    configure_pet_platform()

    from PyQt6.QtCore import QPoint, QRect, QSettings, Qt, QTimer, QUrl
    from PyQt6.QtGui import QColor, QFont, QPainter, QPen
    from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
    from PyQt6.QtWidgets import QApplication, QMenu, QWidget

    class Pet(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle('故事海同伴')
            self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                                Qt.WindowType.WindowStaysOnTopHint)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setFixedSize(190, 300)
            self.setCursor(Qt.CursorShape.OpenHandCursor)

            self.animation = AnimationModel()
            self._phase = 0.0
            self._last_tick = time.monotonic()
            self._next_stretch = self._last_tick + STRETCH_INTERVAL_SECONDS
            self._drag_origin: QPoint | None = None
            self._press_global: QPoint | None = None
            self._did_drag = False
            self._native_drag = False
            self._input_shape = None
            self._balance = '尚未查询'
            self._writing = False
            self._task = ''
            self._card_title = ''
            self._card_detail = ''
            self.card_rect = QRect(5, 5, 180, 66)
            self.card_timer = QTimer(self)
            self.card_timer.setSingleShot(True)
            self.card_timer.timeout.connect(self.hide_card)

            settings_file = os.environ.get('CHARACTER_COMPASS_PET_SETTINGS')
            self.settings = (QSettings(settings_file, QSettings.Format.IniFormat) if settings_file
                             else QSettings('CharacterCompass', 'DesktopCompanion'))
            requested = os.environ.get('CHARACTER_COMPASS_PET_QUALITY') or self.settings.value('quality', 'smooth')
            self.quality = requested if requested in ('pixel', 'smooth') else 'smooth'
            self._frame_cache = {}
            self.frames = self.quality_frames(self.quality)
            self.figure_x = (self.width() - FIGURE_WIDTH) // 2
            self.figure_y = 84

            screen = QApplication.primaryScreen()
            if screen:
                area = screen.availableGeometry()
                self.move(area.right() - self.width() - 16,
                          area.bottom() - self.height() - 8)

            self.network = QNetworkAccessManager(self)
            self.activity_timer = QTimer(self)
            self.activity_timer.timeout.connect(self.fetch_activity)
            self.activity_timer.start(2500)
            self.balance_timer = QTimer(self)
            self.balance_timer.timeout.connect(self.fetch_balance)
            self.balance_timer.start(60000)
            self.motion_timer = QTimer(self)
            self.motion_timer.timeout.connect(self.animate)
            self.motion_timer.start(40)
            self.fetch_activity()
            self.fetch_balance()

        def quality_frames(self, quality):
            ratio = self.devicePixelRatioF() if quality == 'smooth' else 1.0
            key = (quality, ratio)
            if key not in self._frame_cache:
                self._frame_cache[key] = load_pet_frames(WEB / 'assets', quality=quality,
                                                       device_pixel_ratio=ratio)
            return self._frame_cache[key]

        def set_quality(self, quality):
            # 先完整准备帧，再切换；不移动窗口、不重置动作，也不需要重启。
            try:
                frames = self.quality_frames(quality)
            except (OSError, RuntimeError, ValueError):
                self.show_card('画质切换失败', '已保留原画质，可继续使用。')
                return
            self.frames = frames
            self.quality = quality
            self.settings.setValue('quality', quality)
            self.update()

        def pose_position(self) -> tuple[int, int]:
            clip = self.animation.current_clip
            if clip in ('drag', 'greet', 'cheer', 'stretch', 'recover'):
                return self.figure_x, self.figure_y
            bob = round(math.sin(self._phase) * 3)
            return self.figure_x, self.figure_y + bob

        def showEvent(self, event):
            super().showEvent(event)
            if QApplication.platformName() == 'xcb' and self._input_shape is None:
                try:
                    self._input_shape = X11InputShape(int(self.winId()))
                except (OSError, AttributeError):
                    pass
            self.update_input_region()

        def update_input_region(self):
            if self._input_shape is None:
                return
            # 输入区域与可见画布分离；切帧时不向系统提交新的裁切形状。
            rectangles = [(self.figure_x - 5, self.figure_y - 12,
                           FIGURE_WIDTH + 10, FIGURE_HEIGHT + 28)]
            if self._card_title:
                r = self.card_rect
                rectangles.append((r.x(), r.y(), r.width(), r.height()))
            scale = self.devicePixelRatioF()
            self._input_shape.set_rectangles([
                tuple(round(value * scale) for value in rect) for rect in rectangles])

        def closeEvent(self, event):
            if self._input_shape is not None:
                self._input_shape.close()
                self._input_shape = None
            super().closeEvent(event)

        def show_card(self, title: str, detail: str, duration_ms: int = 7500):
            self._card_title = title[:20]
            self._card_detail = detail[:45]
            self.card_timer.start(duration_ms)
            self.update_input_region()
            self.update()

        def hide_card(self):
            self.card_timer.stop()
            self._card_title = ''
            self._card_detail = ''
            self.update_input_region()
            self.update()

        def show_dialogue(self):
            self.animation.play('greet')
            if self._writing:
                detail = TASK_NAMES.get(self._task, '正在和你一起创作…')
            else:
                detail = 'DeepSeek 余额：' + self._balance
            self.show_card('嗨，我在这里陪你写故事', detail)

        def animate(self):
            now = time.monotonic()
            elapsed_ms = max(1, min(250, round((now - self._last_tick) * 1000)))
            self._last_tick = now
            self.animation.advance(elapsed_ms)
            if now >= self._next_stretch and self.animation.current_clip == 'idle':
                self.stretch()
            self._phase += elapsed_ms / 320
            self.update()

        def stretch(self):
            if self._writing or self.animation.current_clip == 'drag':
                return
            self.animation.play('stretch')
            self._next_stretch = time.monotonic() + STRETCH_INTERVAL_SECONDS

        def request_json(self, path: str, callback):
            reply = self.network.get(QNetworkRequest(QUrl(base_url + path)))

            def finished():
                try:
                    payload = json.loads(bytes(reply.readAll()).decode('utf-8'))
                    if isinstance(payload, dict):
                        callback(payload)
                except (ValueError, UnicodeDecodeError):
                    pass
                finally:
                    reply.deleteLater()

            reply.finished.connect(finished)

        def fetch_activity(self):
            self.request_json('/api/activity', self.got_activity)

        def got_activity(self, data: dict):
            writing = data.get('state') == 'writing'
            task = str(data.get('task', '')) if writing else ''
            if self._writing and not writing:
                self.animation.play('cheer')
            self._writing = writing
            self._task = task
            self.animation.set_task(task if writing else None)

        def fetch_balance(self):
            self.request_json('/api/balance', self.got_balance)

        def got_balance(self, data: dict):
            if 'error' in data:
                self._balance = str(data['error'])[:35]
            else:
                balances = data.get('balance_infos') or []
                self._balance = ' · '.join(
                    f"{item.get('currency', '')} {item.get('total_balance', '')}"
                    for item in balances if isinstance(item, dict)) or '暂无余额信息'
            if self._card_title and not self._writing:
                self._card_detail = 'DeepSeek 余额：' + self._balance
                self.update()

        def paintEvent(self, _event):
            painter = QPainter(self)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.quality == 'smooth')
            x, y = self.pose_position()
            painter.drawPixmap(x, y, self.frames[self.animation.current_frame])
            if self._card_title:
                rect = self.card_rect
                painter.setPen(QPen(QColor('#c8dee3'), 1))
                painter.setBrush(QColor('#ffffff'))
                painter.drawRoundedRect(rect, 13, 13)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor('#64c7cf'))
                painter.drawEllipse(15, 17, 7, 7)
                title_font = QFont()
                title_font.setPointSize(9)
                title_font.setBold(True)
                painter.setFont(title_font)
                painter.setPen(QColor('#19364b'))
                painter.drawText(QRect(29, 10, 151, 22),
                                 Qt.AlignmentFlag.AlignVCenter, self._card_title)
                detail_font = QFont()
                detail_font.setPointSize(8)
                painter.setFont(detail_font)
                painter.setPen(QColor('#3b5666'))
                painter.drawText(QRect(15, 32, 160, 34),
                                 Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
                                 self._card_detail)
            painter.end()

        def mousePressEvent(self, event):
            if event.button() != Qt.MouseButton.LeftButton:
                return
            if self._card_title and self.card_rect.contains(event.position().toPoint()):
                self.hide_card()
                event.accept()
                return
            self.raise_()
            self._press_global = event.globalPosition().toPoint()
            # 保存按下点在固定窗口中的偏移；角色换姿势不会改变抓取位置。
            self._drag_origin = event.position().toPoint()
            self._did_drag = False
            self._native_drag = False
            event.accept()

        def mouseMoveEvent(self, event):
            if self._drag_origin is None:
                return
            if not event.buttons() & Qt.MouseButton.LeftButton:
                self.finish_press()
                return
            global_pos = event.globalPosition().toPoint()
            if self._press_global is None:
                return
            if (global_pos - self._press_global).manhattanLength() > 6:
                if not self._did_drag:
                    self._did_drag = True
                    self.animation.begin_drag()
                    self.hide_card()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    if QApplication.platformName().startswith('wayland'):
                        handle = self.windowHandle()
                        self._native_drag = bool(handle and handle.startSystemMove())
            if self._did_drag and not QApplication.platformName().startswith('wayland'):
                self.move(global_pos - self._drag_origin)
            event.accept()

        def finish_press(self, global_pos: QPoint | None = None):
            if self._drag_origin is None:
                return
            moved = self._did_drag
            if global_pos is not None and self._press_global is not None:
                moved |= (global_pos - self._press_global).manhattanLength() > 6
            self._drag_origin = None
            self._press_global = None
            native_drag = self._native_drag
            self._native_drag = False
            self._did_drag = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.animation.end_drag()
            if not moved:
                self.show_dialogue()
            elif not native_drag and not QApplication.platformName().startswith('wayland'):
                self.keep_on_screen(global_pos)
            self.update()

        def keep_on_screen(self, pointer: QPoint | None = None):
            screen = QApplication.screenAt(pointer or self.frameGeometry().center())
            screen = screen or self.screen()
            if screen is None:
                return
            area = screen.availableGeometry()
            left = area.left()
            top = area.top()
            right = max(left, area.right() - self.width() + 1)
            bottom = max(top, area.bottom() - self.height() + 1)
            self.move(max(left, min(right, self.x())), max(top, min(bottom, self.y())))

        def mouseReleaseEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                self.finish_press(event.globalPosition().toPoint())
                event.accept()

        def contextMenuEvent(self, event):
            menu = QMenu(self)
            menu.addAction('和同伴说话', self.show_dialogue)
            menu.addAction('查看 DeepSeek 余额', lambda: self.show_card(
                'DeepSeek 余额', self._balance))
            menu.addAction('刷新余额', self.fetch_balance)
            menu.addAction('伸个懒腰', self.stretch)
            quality_menu = menu.addMenu('显示画质')
            for quality, label in (('smooth', '高清 · 原素材细节'), ('pixel', '像素 · 恢复上一版效果')):
                action = quality_menu.addAction(label)
                action.setCheckable(True)
                action.setChecked(self.quality == quality)
                action.triggered.connect(lambda _checked=False, quality=quality: self.set_quality(quality))
            menu.addSeparator()
            menu.addAction('暂时收起同伴', self.close)
            menu.exec(event.globalPos())

    app = QApplication([])
    app.setQuitOnLastWindowClosed(True)
    pet = Pet()
    pet.show()
    pet.raise_()
    if on_ready is not None:
        QTimer.singleShot(0, lambda: on_ready(pet))
    return app.exec()
