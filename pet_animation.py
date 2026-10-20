"""桌面同伴的纯状态机；Qt 窗口只负责显示当前帧。"""
from __future__ import annotations

from dataclasses import dataclass
from pet_assets import SEQUENCES


@dataclass(frozen=True)
class Clip:
    frames: tuple[str, ...]
    frame_ms: int
    loop: bool = False

    @property
    def duration_ms(self) -> int:
        return len(self.frames) * self.frame_ms


CLIPS = {
    'idle': Clip(('idle',) * 40 + ('blink',) * 2 + ('idle',) * 12, 85, True),
    'thinking': Clip(('think',), 150, True),
    'working': Clip(('read',), 150, True),
    'greet': Clip(SEQUENCES['wave'], 140),
    'stretch': Clip(SEQUENCES['stretch'][:5] + (SEQUENCES['stretch'][4],) * 2 +
                    SEQUENCES['stretch'][5:], 160),
    'cheer': Clip(SEQUENCES['cheer'], 145),
    # 下摆到上摆之间补一次水平经过姿势，避免从身侧直接跳到头顶。
    'drag': Clip(tuple(SEQUENCES['drag'][i] for i in (0, 1, 2, 1, 3, 4, 5, 6, 7)),
                 80, True),
    'recover': Clip(SEQUENCES['recover'], 140),
}


class AnimationModel:
    def __init__(self):
        self.base = 'idle'
        self.overlay: str | None = None
        self.frame_index = 0
        self.elapsed_ms = 0

    @property
    def current_clip(self) -> str:
        return self.overlay or self.base

    @property
    def current_frame(self) -> str:
        return CLIPS[self.current_clip].frames[self.frame_index]

    def set_task(self, task: str | None) -> None:
        base = ('thinking' if task in ('analyze', 'plan') else
                'working' if task else 'idle')
        if base != self.base:
            self.base = base
            if self.overlay is None:
                self.frame_index = 0
                self.elapsed_ms = 0

    def play(self, clip: str) -> None:
        if clip not in ('greet', 'stretch', 'cheer', 'recover'):
            raise ValueError(f'不是可播放的临时动作：{clip}')
        if self.overlay == 'drag':
            return
        self.overlay = clip
        self.frame_index = 0
        self.elapsed_ms = 0

    def begin_drag(self) -> None:
        if self.overlay == 'drag':
            return
        self.overlay = 'drag'
        self.frame_index = 0
        self.elapsed_ms = 0

    def end_drag(self) -> None:
        if self.overlay == 'drag':
            self.overlay = 'recover'
            self.frame_index = 0
            self.elapsed_ms = 0

    def advance(self, milliseconds: int) -> None:
        remaining = max(0, milliseconds)
        while remaining:
            clip = CLIPS[self.current_clip]
            until_next = clip.frame_ms - self.elapsed_ms
            step = min(remaining, until_next)
            self.elapsed_ms += step
            remaining -= step
            if self.elapsed_ms < clip.frame_ms:
                break
            self.elapsed_ms = 0
            self.frame_index += 1
            if self.frame_index >= len(clip.frames):
                self.frame_index = 0
                if not clip.loop:
                    self.overlay = None
