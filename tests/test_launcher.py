import importlib.util
import json
import os
from pathlib import Path
import subprocess
import socket
import shlex
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

    def test_template_upgrade_requires_unmodified_managed_entry(self):
        for existing in ('old template\n', 'old template\n# Owner=first\n# Custom edit\n'):
            self.directory.mkdir(exist_ok=True)
            self.path.write_text(existing)
            with self.assertRaises(RuntimeError):
                launcher.register(self.directory, 'new template', 'second', marker='# Owner=',
                                  previous_templates=('old template',))
            self.assertEqual(self.path.read_text(), existing)

    def test_old_instance_cannot_remove_upgraded_hook(self):
        old = launcher.register(self.directory, 'old template', 'first', marker='# Owner=')
        new = launcher.register(self.directory, 'new template', 'second', marker='# Owner=',
                                previous_templates=('old template',))
        launcher.unregister(self.directory, old)
        self.assertEqual(self.path.read_text(), new)
        launcher.unregister(self.directory, new)
        self.assertFalse(self.path.exists())

    def test_socket_close_and_termination_cleanup(self):
        for terminate in (False, True):
            socket_path = str(Path(self.temp.name)/('lease-'+str(terminate)+'.sock'))
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(socket_path); server.listen(); server.settimeout(3)
                env = {**os.environ, 'HOME': self.temp.name, 'XDG_DATA_HOME': self.temp.name,
                       'XDG_CONFIG_HOME': str(Path(self.temp.name)/'config'),
                       'XDG_STATE_HOME': str(Path(self.temp.name)/'state')}
                theme = Path(self.temp.name)/'.local/state/omarchy/current/theme.name'
                theme.parent.mkdir(parents=True, exist_ok=True)
                theme.write_text('tokyo-night\n')
                source = Path(self.temp.name)/'source.ppm'
                source.write_bytes(b'P6\n1 1\n255\n\xff\x00\x00')
                request = dict(image={'path': str(source)}, imageScale=1, imageX=0, imageY=0,
                               apply=True, frames=[dict(name='DP-1', x=0, y=0, width=1, height=1,
                                                       pixelWidth=1, pixelHeight=1)])
                subprocess.run(['python3', str(ROOT/'backend.py'), 'export', json.dumps(request)],
                               env=env, check=True, capture_output=True)
                applied = Path(env['XDG_STATE_HOME'])/'omarchy-wallpaper-cutter/applied.json'
                expected = applied.read_bytes()
                hook = Path(env['XDG_CONFIG_HOME'])/'omarchy/hooks/theme-set.d/renan.wallpaper-cutter'
                old_template = '#!/bin/sh\nexec python3 ' + shlex.quote(str(ROOT/'backend.py')) + ' theme-changed\n'
                launcher.register(hook.parent, old_template, 'old', hook.name, '# Wallpaper-Cutter-Owner=', 0o755)
                proc = subprocess.Popen(['python3', str(ROOT / 'launcher.py'), socket_path],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    env=env)
                try:
                    client, _ = server.accept()
                    client.settimeout(3)
                    self.assertEqual(client.recv(32), b'ready\n')
                    self.assertTrue(self.path.exists())
                    self.assertTrue(hook.stat().st_mode & 0o111)
                    subprocess.run([str(hook), 'tokyo-night'], check=True, capture_output=True, env=env)
                    self.assertEqual(applied.read_bytes(), expected)
                    # Leave theme.name unchanged: this must use the hook argument.
                    subprocess.run([str(hook), 'nord'], check=True, capture_output=True, env=env)
                    self.assertEqual(json.loads(applied.read_text()), {})
                    if terminate: proc.terminate()
                    client.close()
                    self.assertEqual(proc.wait(timeout=3), 0)
                    self.assertFalse(self.path.exists())
                    self.assertFalse(hook.exists())
                finally:
                    if proc.poll() is None: proc.kill(); proc.wait()
                    proc.stdout.close(); proc.stderr.close()


if __name__ == '__main__': unittest.main()
