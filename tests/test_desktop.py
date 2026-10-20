import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from desktop import DesktopBridge, configure_stdio, pet_command


class FakeProcess:
    def __init__(self):
        self.running = True
        self.terminated = False

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.terminated = True
        self.running = False

    def wait(self, timeout=None):
        return 0


class DesktopTests(unittest.TestCase):
    def test_windowed_windows_exe_writes_diagnostics_without_console(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('desktop.sys.stdout', None), patch('desktop.sys.stderr', None):
                import desktop
                handler = configure_stdio(folder)
                desktop.sys.stdout.write('中文启动检查\n')
                desktop.sys.stderr.write('错误诊断\n')
                desktop.sys.stderr.flush()
                handler.close()
                import logging
                logging.getLogger('CharacterCompass.desktop').removeHandler(handler)
            log = (Path(folder) / 'desktop.log').read_text(encoding='utf-8')
            self.assertIn('中文启动检查', log)
            self.assertIn('错误诊断', log)

    def test_pet_button_reuses_running_process_and_can_reopen(self):
        spawned = []

        def fake_popen(command, **_kwargs):
            spawned.append(command)
            return FakeProcess()

        bridge = DesktopBridge('http://127.0.0.1:12345')
        with patch('desktop.subprocess.Popen', side_effect=fake_popen):
            bridge.open_pet()
            bridge.open_pet()
            self.assertEqual(len(spawned), 1)
            first = bridge.pet_process
            bridge.close_pet()
            self.assertTrue(first.terminated)
            bridge.open_pet()
            self.assertEqual(len(spawned), 2)
            bridge.close_pet()

    def test_packaged_pet_uses_same_desktop_executable(self):
        with patch('desktop.sys.frozen', True, create=True), \
             patch('desktop.sys.executable', '/package/CharacterCompass'):
            self.assertEqual(pet_command('http://127.0.0.1:12'),
                             ['/package/CharacterCompass', '--pet', 'http://127.0.0.1:12'])

    def test_windows_pet_process_does_not_depend_on_console_handles(self):
        import subprocess
        bridge = DesktopBridge('http://127.0.0.1:12345')
        with patch('desktop.sys.platform', 'win32'), patch('desktop.subprocess.Popen', return_value=FakeProcess()) as spawn:
            bridge.open_pet()
        self.assertEqual(spawn.call_args.kwargs['stdin'], subprocess.DEVNULL)
        self.assertEqual(spawn.call_args.kwargs['stdout'], subprocess.DEVNULL)
        self.assertEqual(spawn.call_args.kwargs['stderr'], subprocess.DEVNULL)
        self.assertTrue(spawn.call_args.kwargs['creationflags'] & 0x08000000)


if __name__ == '__main__':
    unittest.main()
