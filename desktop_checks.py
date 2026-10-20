"""发布前用实际打包程序检查写作窗口和透明桌宠；只操作临时作品。"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import time
import traceback

from storage import Store, write_json


def run_check(mode: str, report: Path) -> int:
    report = report.resolve()
    result = {'ok': False, 'platform': sys.platform,
              'frozen': bool(getattr(sys, 'frozen', False)), 'checks': []}
    with tempfile.TemporaryDirectory(prefix='CharacterCompass 中文测试 ') as temporary:
        try:
            root = Path(temporary)
            os.environ['CHARACTER_COMPASS_PET_SETTINGS'] = str(root / 'pet.ini')
            os.environ['CHARACTER_COMPASS_PET_QUALITY'] = 'smooth'
            if mode == '--check-desktop':
                check_desktop(root, report, result)
            else:
                check_pet(report, result)
        except Exception:
            result['ok'] = False
            result['error'] = traceback.format_exc()
        write_json(report, result)
    return 0 if result['ok'] else 1


def check_desktop(root, report, result):
    import app
    from desktop import main

    app._store = Store(root / '作品库')
    app.ENV_FILE = root / '.env'
    os.environ['CHARACTER_COMPASS_ENV_FILE'] = str(app.ENV_FILE)
    os.environ['DEEPSEEK_API_KEY'] = ''
    novel = app._store.create_novel('桌面验收 · 中文小说', '')
    app._store.create_chapter(novel['id'], 1, '第一章', '这里是验收用的临时正文。', '临时章节记忆。')

    def wait_for(predicate, seconds=35):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.1)
        raise AssertionError('写作窗口验收超时。')

    def ready(window, bridge):
        try:
            wait_for(lambda: window.evaluate_js("typeof state !== 'undefined' && !!state.novel && !state.busy"))
            assert window.evaluate_js("document.getElementById('chapter-body').value") == '这里是验收用的临时正文。'
            assert window.evaluate_js("!!document.querySelector('[data-tab=memories]')")
            assert window.evaluate_js("document.getElementById('outline').previousElementSibling.textContent.includes('不发送给 AI')")
            result['checks'].append('Qt WebEngine 加载完整写作界面和中文章节')
            window.evaluate_js("""(() => {
              for (const [id,text] of [['worldbuilding','施法消耗记忆，禁止复活。'],['scene','本章在书店相遇。']]) {
                const field=document.getElementById(id); field.value=text;
                field.dispatchEvent(new Event('input'));
              }
              document.getElementById('save-all').click(); return true;
            })()""")
            wait_for(lambda: app._store.novel_state(novel['id'], full=False)['scene_brief'] == '本章在书店相遇。')
            saved = app._store.novel_state(novel['id'], full=False)
            assert saved['worldbuilding'] == '施法消耗记忆，禁止复活。'
            result['checks'].append('界面调用本机 API 保存世界观和章节要求，中文路径读写正确')
            assert bridge.pet_process is not None and bridge.pet_process.poll() is None
            result['checks'].append('写作窗口成功启动独立桌宠进程')
            result['ok'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        finally:
            write_json(report, result)
            window.destroy()

    # 防止再次进入命令行分派；调用的仍是正常桌面启动与关闭流程。
    sys.argv = [sys.argv[0]]
    main(on_ready=ready)


def check_pet(report, result):
    from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt, QTimer
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication
    from native_pet import run_pet
    from pet_animation import AnimationModel, CLIPS
    from pet_assets import FIGURE_WIDTH, FIGURE_HEIGHT, POSE_KEYS

    state = {'samples': []}

    def ready(pet):
        state['pet'] = pet

        def guarded(callback):
            def run():
                try:
                    callback()
                except Exception:
                    result['error'] = traceback.format_exc()
                    write_json(report, result)
                    pet.close()
                    QApplication.instance().quit()
            return run

        def after(milliseconds, callback):
            QTimer.singleShot(milliseconds, guarded(callback))

        def mouse(kind, point, held):
            button = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
            event = QMouseEvent(kind, QPointF(pet.mapFromGlobal(point)), QPointF(point), button,
                Qt.MouseButton.LeftButton if held else Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(pet, event)

        def feet():
            frame = pet.frames[pet.animation.current_frame]
            x, y = pet.pose_position()
            assert pet.rect().contains(QRect(x, y, FIGURE_WIDTH, FIGURE_HEIGHT))
            picture = pet.grab().toImage().scaled(pet.size())
            image = frame.toImage().scaled(FIGURE_WIDTH, FIGURE_HEIGHT)
            visible = [(sx, sy) for sy in range(FIGURE_HEIGHT*3//4, FIGURE_HEIGHT)
                       for sx in range(FIGURE_WIDTH) if image.pixelColor(sx,sy).alpha() > 180]
            assert visible, '素材缺少脚部。'
            assert all(picture.pixelColor(x+sx,y+sy).alpha() > 160 for sx,sy in visible), '脚部被裁切。'

        def initial():
            assert set(pet.frames) == POSE_KEYS
            assert pet.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
            assert pet.windowFlags() & Qt.WindowType.FramelessWindowHint
            assert pet.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            assert pet.mask().isEmpty()
            pet.motion_timer.stop()
            seen = set()
            for name, clip in CLIPS.items():
                for index, pose in enumerate(clip.frames):
                    if pose in seen:
                        continue
                    pet.animation = AnimationModel()
                    pet.animation.overlay, pet.animation.frame_index = name, index
                    feet()
                    seen.add(pose)
            result['checks'].append('44 张高清姿势完整，透明无边框窗口置顶，脚部均可见')
            pet.animation = AnimationModel()
            position = pet.pos()
            pet.animation.begin_drag()
            pet.animation.advance(200)
            progress = (pet.animation.current_frame, pet.animation.elapsed_ms)
            for quality in ('pixel', 'smooth'):
                pet.set_quality(quality)
                assert pet.quality == quality
                assert (pet.animation.current_frame, pet.animation.elapsed_ms) == progress
                assert pet.pos() == position and pet.size().width() == 190 and pet.size().height() == 300
            result['checks'].append('高清和像素切换保留窗口位置、大小及动作进度')
            pet.animation = AnimationModel()
            pet._last_tick = time.monotonic()
            pet.motion_timer.start()
            local = QPoint(pet.figure_x+64, pet.figure_y+65)
            state['local'], state['origin'] = local, pet.pos()
            point = pet.mapToGlobal(local)
            mouse(QEvent.Type.MouseButtonPress, point, True)
            mouse(QEvent.Type.MouseButtonRelease, point, False)
            assert pet._card_title
            color = pet.grab().toImage().scaled(pet.size()).pixelColor(176,20)
            assert color.alpha() > 240 and min(color.red(),color.green(),color.blue()) > 235
            pet.grab().save(str(report.with_suffix('.png')))
            result['checks'].append('点击弹出白色对话卡片')
            mouse(QEvent.Type.MouseButtonPress, point, True)
            state['pointer'] = point-QPoint(50,40)
            mouse(QEvent.Type.MouseMove, state['pointer'], True)
            for i in range(1,7):
                after(i*90, sample)
            after(680, release)

        def sample():
            assert pet.animation.current_clip == 'drag'
            assert pet.pos() == state['pointer']-state['local'], '拖动抓取偏移。'
            assert not pet._card_title
            feet()
            state['samples'].append(pet.animation.current_frame)

        def release():
            assert len(set(state['samples'])) >= 4, '拖动时没有连续切帧。'
            mouse(QEvent.Type.MouseButtonRelease, state['pointer'], False)
            assert pet.animation.current_clip == 'recover'
            after(1250, finished)

        def finished():
            assert pet.animation.current_clip == 'idle'
            assert pet.screen().availableGeometry().contains(pet.frameGeometry())
            feet()
            result['checks'].append('连续拖动切帧、抓取位置、松手恢复和屏幕边界正确')
            result['ok'] = True
            write_json(report, result)
            pet.close()
            QApplication.instance().quit()

        after(150, initial)
        after(25000, lambda: (_ for _ in ()).throw(AssertionError('桌宠验收超时。')))

    run_pet('http://127.0.0.1:1', on_ready=ready)
