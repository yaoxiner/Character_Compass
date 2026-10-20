"""桌宠图集：保留原素材细节的平滑渲染，以及原版像素渲染。"""
from __future__ import annotations

from pathlib import Path

FIGURE_WIDTH, FIGURE_HEIGHT = 128, 192
POSE_FILES = {
    'idle': 'companion.png',
    'blink': 'companion-blink.png',
    'think': 'companion-think.png',
    'read': 'companion-read.png',
}
SHEET_FILES = {name: f'companion-{name}-sequence.png'
               for name in ('drag', 'wave', 'cheer', 'stretch', 'recover')}
SHEET_FILES['drag'] = 'companion-drag-anime-v3.png'
SEQUENCES = {name: tuple(f'{name}_{i:02d}' for i in range(8)) for name in SHEET_FILES}
POSE_KEYS = frozenset(POSE_FILES) | frozenset(pose for frames in SEQUENCES.values()
                                            for pose in frames)


def isolate_character(image):
    """提取格子中完整的主体，去掉生成图集时落入格子的邻帧碎片。"""
    from PyQt6.QtGui import QImage

    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = rgba.width(), rgba.height()
    stride = rgba.bytesPerLine()
    pixels = bytearray(rgba.constBits().asstring(stride * height))
    alpha = bytearray(pixels[y * stride + x * 4 + 3]
                      for y in range(height) for x in range(width))
    visited = bytearray(width * height)
    largest = []
    for start, value in enumerate(alpha):
        if value < 64 or visited[start]:
            continue
        stack = [start]
        visited[start] = 1
        component = []
        while stack:
            index = stack.pop()
            component.append(index)
            x, y = index % width, index // width
            for ny in range(max(0, y - 1), min(height, y + 2)):
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = ny * width + nx
                    if not visited[neighbor] and alpha[neighbor] >= 64:
                        visited[neighbor] = 1
                        stack.append(neighbor)
        if len(component) > len(largest):
            largest = component
    if not largest:
        raise RuntimeError('桌面同伴动作格子中没有可见人物')
    keep = bytearray(width * height)
    # 给主体保留一像素的透明度过渡，避免把头发和衣服边缘切成锯齿。
    for index in largest:
        x, y = index % width, index // width
        for ny in range(max(0, y - 1), min(height, y + 2)):
            for nx in range(max(0, x - 1), min(width, x + 2)):
                keep[ny * width + nx] = 1
    for index, retained in enumerate(keep):
        if not retained:
            y, x = divmod(index, width)
            pixels[y * stride + x * 4 + 3] = 0
    return QImage(bytes(pixels), width, height, stride, QImage.Format.Format_RGBA8888).copy()


def load_pet_frames(assets: Path, *, quality: str = 'smooth', device_pixel_ratio: float = 1.0):
    from PyQt6.QtCore import QRect, QRectF, QSize, Qt
    from PyQt6.QtGui import QColor, QImage, QImageReader, QPainter, QPixmap

    if quality not in ('pixel', 'smooth'):
        raise ValueError('未知桌宠画质：' + str(quality))
    ratio = max(1.0, min(3.0, float(device_pixel_ratio))) if quality == 'smooth' else 1.0
    output_size = QSize(round(FIGURE_WIDTH * ratio), round(FIGURE_HEIGHT * ratio))

    def small_pixmap(image):
        small = image.scaled(64, 96, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        return QPixmap.fromImage(small).scaled(
            FIGURE_WIDTH, FIGURE_HEIGHT, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation)

    def smooth_pixmap(image, crop=None):
        target = QImage(output_size, QImage.Format.Format_ARGB32_Premultiplied)
        target.fill(QColor(0, 0, 0, 0))
        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(QRectF(target.rect()), image, crop or QRectF(image.rect()))
        painter.end()
        pixmap = QPixmap.fromImage(target)
        pixmap.setDevicePixelRatio(ratio)
        return pixmap

    def mask_source(source, clean):
        # 仍在旧版的 128×192 分析画布上隔离主体，避免提高精细度时带回邻帧碎片。
        # 只把保留区域作为蒙版，颜色和线条始终从原图读取。
        rgba = clean.convertToFormat(QImage.Format.Format_RGBA8888)
        stride = rgba.bytesPerLine()
        data = rgba.constBits().asstring(stride * rgba.height())
        mask_data = bytearray(len(data))
        for y in range(rgba.height()):
            for x in range(rgba.width()):
                i = y * stride + x * 4
                if data[i + 3]:
                    mask_data[i:i + 4] = b'\xff\xff\xff\xff'
        mask = QImage(bytes(mask_data), rgba.width(), rgba.height(), stride,
                      QImage.Format.Format_RGBA8888).copy()
        masked = source.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        painter = QPainter(masked)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.drawImage(QRectF(masked.rect()), mask, QRectF(mask.rect()))
        painter.end()
        return masked

    frames = {}
    for pose, filename in POSE_FILES.items():
        reader = QImageReader(str(assets / filename))
        reader.setScaledSize(QSize(64, 96) if quality == 'pixel' else output_size)
        image = reader.read()
        if image.isNull():
            raise RuntimeError(f'桌面同伴动作图片不存在：{filename}')
        frames[pose] = small_pixmap(image) if quality == 'pixel' else smooth_pixmap(image)

    for sequence, filename in SHEET_FILES.items():
        sheet = QImage(str(assets / filename)).convertToFormat(QImage.Format.Format_ARGB32)
        if sheet.isNull() or sheet.width() % 4 or sheet.height() % 2:
            raise RuntimeError(f'桌面同伴动作图集损坏：{filename}')
        width, height = sheet.width() // 4, sheet.height() // 2
        # 先限制在自己的格子中，再提取主体，邻帧的细小头发/衣角不进入输出。
        # 处理只在启动时进行，分析分辨率为显示分辨率，不对整张大图逐像素遍历。
        sources = [sheet.copy((i % 4) * width, (i // 4) * height, width, height)
                   for i in range(8)]
        cells = [isolate_character(source.scaled(
                                                 FIGURE_WIDTH, FIGURE_HEIGHT,
                                                 Qt.AspectRatioMode.IgnoreAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation))
                 for source in sources]
        width, height = FIGURE_WIDTH, FIGURE_HEIGHT
        # 整个动作共用同一裁切框与比例，避免逐帧自适应缩放造成身体忽大忽小。
        left, top, right, bottom = width, height, 0, 0
        step = max(1, min(width, height) // 96)
        for cell in cells:
            for y in range(0, height, step):
                for x in range(0, width, step):
                    if cell.pixel(x, y) >> 24 >= 80:
                        left, top = min(left, x), min(top, y)
                        right, bottom = max(right, x + step), max(bottom, y + step)
        if right <= left or bottom <= top:
            raise RuntimeError(f'桌面同伴动作图集没有可见角色：{filename}')
        padding = max(2, round(height * .02))
        crop_w = right - left + padding * 2
        crop_h = bottom - top + padding * 2
        crop_w = max(crop_w, round(crop_h * 2 / 3))
        crop_h = max(crop_h, round(crop_w * 3 / 2))
        crop = QRect(round((left + right - crop_w) / 2),
                     round((top + bottom - crop_h) / 2), crop_w, crop_h)
        for pose, cell, source in zip(SEQUENCES[sequence], cells, sources):
            if quality == 'pixel':
                frames[pose] = small_pixmap(cell.copy(crop))
            else:
                sx, sy = source.width() / FIGURE_WIDTH, source.height() / FIGURE_HEIGHT
                source_crop = QRectF(crop.x() * sx, crop.y() * sy,
                                     crop.width() * sx, crop.height() * sy)
                frames[pose] = smooth_pixmap(mask_source(source, cell), source_crop)
    return frames
