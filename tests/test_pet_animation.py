"""拖动期间的动作优先级与松手后的状态恢复。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pet_animation import AnimationModel, CLIPS


class AnimationModelTests(unittest.TestCase):
    def test_repeated_drag_start_preserves_frame_progress(self):
        model = AnimationModel()
        model.begin_drag()
        first = model.current_frame
        model.advance(110)
        second = model.current_frame
        model.begin_drag()
        self.assertNotEqual(first, second)
        self.assertEqual(model.current_frame, second)
        model.advance(110)
        self.assertNotEqual(model.current_frame, second)

    def test_drag_flails_then_recovers_to_latest_task(self):
        model = AnimationModel()
        model.set_task('draft')
        model.play('greet')
        model.begin_drag()
        self.assertEqual(model.current_clip, 'drag')
        first = model.current_frame
        model.advance(110)
        self.assertNotEqual(model.current_frame, first)
        model.set_task('plan')
        model.end_drag()
        self.assertEqual(model.current_clip, 'recover')
        model.advance(CLIPS['recover'].duration_ms)
        self.assertEqual((model.current_clip, model.current_frame), ('thinking', 'think'))

    def test_drag_cannot_be_interrupted_by_background_completion(self):
        model = AnimationModel()
        model.begin_drag()
        model.play('cheer')
        model.set_task(None)
        self.assertEqual(model.current_clip, 'drag')
        model.end_drag()
        model.advance(CLIPS['recover'].duration_ms)
        self.assertEqual(model.current_clip, 'idle')

    def test_click_and_stretch_return_to_base(self):
        model = AnimationModel()
        model.set_task('analyze')
        model.play('greet')
        model.advance(CLIPS['greet'].duration_ms)
        self.assertEqual(model.current_clip, 'thinking')
        model.play('stretch')
        model.advance(CLIPS['stretch'].duration_ms)
        self.assertEqual(model.current_clip, 'thinking')


if __name__ == '__main__':
    unittest.main()
