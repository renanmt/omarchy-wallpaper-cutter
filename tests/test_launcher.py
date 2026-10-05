import importlib.util
import os
from pathlib import Path
import subprocess
import socket
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('launcher', ROOT / 'launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'applications'
        self.template = (ROOT / launcher.NAME).read_text()
        self.path = self.directory / launcher.NAME

    def test_registration_and_cleanup(self):
        content = launcher.register(self.directory, self.template, 'first')
        self.assertIn('Name=Wallpaper Cutter', self.path.read_text())
        launcher.unregister(self.directory, content)
        self.assertFalse(self.path.exists())

    def test_old_instance_cannot_remove_reloaded_entry(self):
        old = launcher.register(self.directory, self.template, 'old')
        new = launcher.register(self.directory, self.template, 'new')
        launcher.unregister(self.directory, old)
        self.assertEqual(self.path.read_text(), new)
        launcher.unregister(self.directory, new)
        self.assertFalse(self.path.exists())

    def test_customized_entry_is_preserved(self):
        self.directory.mkdir()
        self.path.write_text('[Desktop Entry]\nName=My custom cutter\n')
        with self.assertRaises(RuntimeError): launcher.register(self.directory, self.template, 'owner')
        self.assertIn('My custom cutter', self.path.read_text())

    def test_user_edits_after_registration_are_preserved(self):
        content = launcher.register(self.directory, self.template, 'owner')
        self.path.write_text(content + 'Comment=User modified\n')
        launcher.unregister(self.directory, content)
        self.assertTrue(self.path.exists())

    def test_legacy_manual_copy_is_adopted(self):
        self.directory.mkdir()
        self.path.write_text(self.template)
        content = launcher.register(self.directory, self.template, 'owner')
        launcher.unregister(self.directory, content)
        self.assertFalse(self.path.exists())

    def test_socket_close_and_termination_cleanup(self):
        for terminate in (False, True):
            socket_path = str(Path(self.temp.name)/('lease-'+str(terminate)+'.sock'))
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(socket_path); server.listen(); server.settimeout(3)
                proc = subprocess.Popen(['python3', str(ROOT / 'launcher.py'), socket_path],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    env={**os.environ, 'XDG_DATA_HOME': self.temp.name, 'XDG_CONFIG_HOME': str(Path(self.temp.name)/'config'), 'XDG_STATE_HOME': str(Path(self.temp.name)/'state')})
                try:
                    client, _ = server.accept()
                    client.settimeout(3)
                    self.assertEqual(client.recv(32), b'ready\n')
                    self.assertTrue(self.path.exists())
                    hook = Path(self.temp.name)/'config/omarchy/hooks/theme-set.d/renan.wallpaper-cutter'
                    self.assertTrue(hook.stat().st_mode & 0o111)
                    subprocess.run([str(hook)], check=True, capture_output=True, env={**os.environ, 'XDG_STATE_HOME': str(Path(self.temp.name)/'state')})
                    self.assertTrue((Path(self.temp.name)/'state/omarchy-wallpaper-cutter/applied.json').exists())
                    if terminate: proc.terminate()
                    client.close()
                    self.assertEqual(proc.wait(timeout=3), 0)
                    self.assertFalse(self.path.exists())
                    self.assertFalse(hook.exists())
                finally:
                    if proc.poll() is None: proc.kill(); proc.wait()
                    proc.stdout.close(); proc.stderr.close()


if __name__ == '__main__': unittest.main()
