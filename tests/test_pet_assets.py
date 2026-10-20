"""图集中的邻帧碎片不得混进人物边缘；保持主体和透明度过渡。"""
import unittest
from pathlib import Path

try:
    from PyQt6.QtGui import QColor, QImage
    from PyQt6.QtWidgets import QApplication
except ImportError:
    QImage = None

from pet_assets import FIGURE_WIDTH, FIGURE_HEIGHT, POSE_KEYS, isolate_character, load_pet_frames


@unittest.skipIf(QImage is None, '需要可选的 Qt 桌面依赖')
class PetAssetTests(unittest.TestCase):
    def image(self):
        image = QImage(80, 120, QImage.Format.Format_RGBA8888)
        image.fill(QColor(0, 0, 0, 0))
        return image

    def fill(self, image, rect, color):
        x, y, width, height = rect
        for py in range(y, y + height):
            for px in range(x, x + width):
                image.setPixelColor(px, py, color)

    def test_neighbor_edges_removed_without_losing_body_or_feet(self):
        image = self.image()
        self.fill(image, (25, 10, 30, 95), QColor('#16558a'))
        self.fill(image, (25, 100, 12, 15), QColor('#101725'))
        self.fill(image, (43, 100, 12, 15), QColor('#101725'))
        self.fill(image, (0, 25, 5, 45), QColor('#e03131'))
        self.fill(image, (76, 10, 4, 40), QColor('#e03131'))
        self.fill(image, (0, 0, 10, 5), QColor('#e03131'))
        clean = isolate_character(image)
        self.assertEqual(clean.pixelColor(2, 40).alpha(), 0)
        self.assertEqual(clean.pixelColor(78, 20).alpha(), 0)
        self.assertEqual(clean.pixelColor(4, 2).alpha(), 0)
        self.assertEqual(clean.pixelColor(40, 50), image.pixelColor(40, 50))
        self.assertEqual(clean.pixelColor(30, 113), image.pixelColor(30, 113))
        self.assertEqual(clean.pixelColor(50, 113), image.pixelColor(50, 113))

    def test_body_antialiasing_kept_but_distant_noise_removed(self):
        image = self.image()
        self.fill(image, (24, 19, 32, 82), QColor(50, 130, 190, 30))
        self.fill(image, (25, 20, 30, 80), QColor(50, 130, 190, 255))
        image.setPixelColor(2, 40, QColor(50, 130, 190, 30))
        clean = isolate_character(image)
        self.assertEqual(clean.pixelColor(24, 50).alpha(), 30)
        self.assertEqual(clean.pixelColor(2, 40).alpha(), 0)


@unittest.skipIf(QImage is None, '需要可选的 Qt 桌面依赖')
class PetQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(['pet-quality-tests', '-platform', 'offscreen'])
        assets = Path(__file__).resolve().parents[1] / 'web/assets'
        cls.pixel = load_pet_frames(assets, quality='pixel')
        cls.smooth = load_pet_frames(assets, quality='smooth')
        cls.retina = load_pet_frames(assets, quality='smooth', device_pixel_ratio=2)

    def test_quality_keeps_all_frames_and_logical_dimensions(self):
        for frames in (self.pixel, self.smooth, self.retina):
            self.assertEqual(set(frames), POSE_KEYS)
            for frame in frames.values():
                size = frame.deviceIndependentSize()
                if frames is self.pixel:
                    # 旧版保持纵横比时，部分动作实际宽 126；回退必须保留这一行为。
                    self.assertLessEqual(size.width(), FIGURE_WIDTH)
                    self.assertLessEqual(size.height(), FIGURE_HEIGHT)
                else:
                    self.assertEqual(size.width(), FIGURE_WIDTH)
                    self.assertEqual(size.height(), FIGURE_HEIGHT)
        self.assertEqual(self.retina['idle'].width(), 256)
        self.assertEqual(self.retina['idle'].height(), 384)

    def test_higher_detail_preserves_transparent_edges_and_feet(self):
        for frames in (self.smooth, self.retina):
            for pose, frame in frames.items():
                if '_' not in pose:
                    continue
                image = frame.toImage()
                w, h = image.width(), image.height()
                edge = [(x, y) for y in range(h) for x in (0, w-1)]
                edge += [(x, y) for x in range(w) for y in (0, h-1)]
                self.assertTrue(all(image.pixelColor(x, y).alpha() == 0 for x, y in edge), pose)
                self.assertTrue(any(image.pixelColor(x,y).alpha() > 180
                    for y in range(h*3//4,h) for x in range(w)), pose)

    def test_high_quality_restores_detail_instead_of_nearest_neighbor_blocks(self):
        # 像素版的每个 2×2 色块相同；高清版应确实增加独立像素。
        def block_differences(frame):
            image = frame.toImage()
            return sum(image.pixel(x,y) != image.pixel(x+1,y)
                       for y in range(image.height()) for x in range(0,image.width()-1,2))
        for name in ('idle', 'drag_03', 'wave_03'):
            self.assertEqual(block_differences(self.pixel[name]), 0)
            self.assertGreater(block_differences(self.smooth[name]), 200)


if __name__ == '__main__':
    unittest.main()
