"""从项目的几何标识绘制多尺寸 Windows ICO；构建时需要 Pillow。"""
from pathlib import Path

from PIL import Image, ImageDraw


def make_icon(destination: Path):
    size = 512
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=108, fill='#102b4e')
    draw.ellipse((80, 70, 432, 422), outline='#68d0df', width=13)
    draw.ellipse((113, 103, 399, 389), outline='#e7d5ae', width=4)
    draw.line((256, 48, 256, 87), fill='#e7d5ae', width=11)
    draw.line((256, 405, 256, 444), fill='#e7d5ae', width=11)
    draw.line((58, 246, 96, 246), fill='#e7d5ae', width=11)
    draw.line((416, 246, 454, 246), fill='#e7d5ae', width=11)
    draw.polygon([(256, 117), (294, 240), (256, 260), (218, 240)], fill='#75dce7')
    draw.polygon([(256, 374), (218, 260), (256, 240), (294, 260)], fill='#f4deb6')
    draw.ellipse((242, 230, 270, 258), fill='#fff7e3')
    draw.polygon([(130, 348), (180, 337), (256, 375), (332, 337), (382, 348),
                  (382, 401), (327, 390), (256, 426), (185, 390), (130, 401)], fill='#fff9e9')
    draw.line((256, 375, 256, 426), fill='#74cfdf', width=8)
    destination.parent.mkdir(parents=True, exist_ok=True)
    img.save(destination.with_suffix('.png'), format='PNG')
    img.save(destination, format='ICO', sizes=[(16, 16), (24, 24), (32, 32),
                                               (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == '__main__':
    make_icon(Path(__file__).resolve().parents[1] / 'web' / 'assets' / 'icon.ico')
