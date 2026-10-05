"""Exercise the actual child picker and parent response handling on Wayland."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

source = Path(__file__).resolve().parents[1]
image = source / 'docs/demo-wallpaper.png'
if not image.exists():
    image = next((source / 'docs').glob('*.png'))
with tempfile.TemporaryDirectory(prefix='cutter-picker-') as workspace:
    for case in (sys.argv[1:] or ('accept', 'cancel', 'failure', 'close', 'export')):
        directory = Path(workspace) / case
        directory.mkdir()
        for pattern in ('*.qml', '*.js', 'backend.py'):
            for path in source.glob(pattern):
                shutil.copy2(path, directory / path.name)
        panel = directory / 'Panel.qml'
        panel.write_text(panel.read_text().replace('onStreamFinished: picker.readReply(text)', 'onStreamFinished: { console.log("CHILD_LOG", text); picker.readReply(text); }'))
        panel.write_text(panel.read_text().replace('picker.environment = {', 'picker.environment = {XDG_CONFIG_HOME: ' + json.dumps(os.environ.get('XDG_CONFIG_HOME') or str(Path.home()/'.config')) + ', '))
        picker = directory / 'Picker.qml'
        qml = picker.read_text()
        qml = qml.replace('imageDialog.open();', ' { imageDialog.selectedFile = ' + json.dumps(image.as_uri()) + '; imageDialog.open(); }')
        action = {'accept': 'imageDialog.accept()', 'cancel': 'imageDialog.reject()',
                  'failure': 'Qt.quit()', 'close': 'imageDialog.reject()', 'export': 'exportDialog.accept()'}[case]
        qml = qml.rstrip()[:-1] + '\nTimer { interval: 1500; running: true; onTriggered: ' + action + ' }\n}\n'
        qml = qml.replace('exportDialog.open();', ' { exportDialog.currentFolder = ' + json.dumps(directory.as_uri()) + '; exportDialog.selectedFile = ' + json.dumps((directory/'test cut').as_uri()) + '; exportDialog.open(); }')
        picker.write_text(qml)
        expected = {'accept': 'editor.picture !== null && !editor.error',
                    'cancel': 'editor.picture === null && !editor.error',
                    'failure': 'editor.error && editor.message.indexOf("unexpectedly") >= 0',
                    'close': '!editor.opened && !editor.busy',
                    'export': '!editor.error && editor.message.indexOf("Exported to ") === 0'}[case]
        close = 'editor.opened = false;' if case == 'close' else ''
        harness = '''import QtQuick
import Quickshell
ShellRoot {
    property int stage: 0
    Panel { id: editor; Component.onCompleted: open("{}") }
    Timer { interval: 400; running: true; repeat: true; onTriggered: {
        if (stage === 0) {
            if (!editor.settingsReady || editor.busy) return;
            editor.choosePath("image"); stage = 1; return;
        }
        if (stage === 1) { CLOSE stage = 2; }
        if (editor.busy) return;
        if (EXPECTED) console.log("PICKER_TEST_PASS");
        else console.error("PICKER_TEST_FAIL", editor.message);
        Qt.quit();
    } }
}
'''.replace('EXPECTED', expected).replace('CLOSE', close)
        if case == 'export':
            harness = harness.replace('!editor.error && editor.message', 'editor.exportDirectory === ' + json.dumps(str(directory)) + ' && !editor.error && editor.message')
            harness = harness.replace('editor.choosePath("image"); stage = 1;', 'editor.run("inspect", [' + json.dumps(str(image)) + ']); stage = 10;')
            harness = harness.replace('if (stage === 1)', 'if (stage === 10) { if(editor.busy) return; editor.beginExport(); stage = 1; return; }\n        if (stage === 1)')
        (directory / 'check.qml').write_text(harness)
        env = {**os.environ, 'XDG_CONFIG_HOME': str(directory / 'config'),
               'XDG_STATE_HOME': str(directory / 'state')}
        run = subprocess.run(['qs', '-p', str(directory / 'check.qml')], env=env,
                             capture_output=True, text=True, timeout=20)
        output = run.stdout + run.stderr
        assert run.returncode == 0 and 'PICKER_TEST_PASS' in output, output
        print(case + ': PASS', flush=True)
