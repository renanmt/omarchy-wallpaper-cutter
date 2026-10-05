"""End-to-end named export and import using temporary state and native dialogs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

source = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='cutter-roundtrip-') as workspace:
    directory = Path(workspace)
    for pattern in ('*.qml', '*.js', 'backend.py'):
        for path in source.glob(pattern): shutil.copy2(path, directory / path.name)
    export = directory / 'My sunset cut'
    panel = directory / 'Panel.qml'
    panel.write_text(panel.read_text().replace('picker.environment = {', 'picker.environment = {XDG_CONFIG_HOME: ' + json.dumps(os.environ.get('XDG_CONFIG_HOME') or str(Path.home()/'.config')) + ', '))
    picker = directory / 'Picker.qml'
    text = picker.read_text()
    text = text.replace('exportDialog.open();', '{ exportDialog.selectedFile = ' + json.dumps(export.as_uri()) + '; exportDialog.open(); }')
    text = text.replace('importDialog.open();', '{ importDialog.selectedFile = ' + json.dumps((export/'layout.json').as_uri()) + '; importDialog.open(); }')
    text = text.rstrip()[:-1] + '\nTimer { interval: 1200; running: true; onTriggered: { if(root.mode === "export") exportDialog.accept(); else importDialog.accept(); } }\n}\n'
    picker.write_text(text)
    harness = '''import QtQuick
import Quickshell
ShellRoot {
    property int stage: 0
    Panel { id: editor; Component.onCompleted: open("{}") }
    function fail(message) { console.error("ROUNDTRIP_FAIL", message); Qt.quit(); }
    Timer { interval: 400; running: true; repeat: true; onTriggered: {
        if(editor.busy || !editor.settingsReady) return;
        if(editor.error) { fail(editor.message); return; }
        if(stage === 0) { editor.run("inspect", [IMAGE]); stage++; return; }
        if(stage === 1) {
            editor.gap = 17; editor.adjustments = {"DP-1": {x: 0, y: 5}};
            editor.beginExport();
            if(editor.exportName !== "cut-demo-wallpaper") { fail("Wrong default name: " + editor.exportName); return; }
            stage=3; return;
        }
        if(stage === 3) {
            if(editor.message.indexOf("Exported to ") !== 0) { fail(editor.message); return; }
            editor.gap=0; editor.adjustments=({}); editor.picture=null;
            editor.choosePath("import"); stage++; return;
        }
        if(stage === 4) {
            if(editor.picture && editor.gap===17 && editor.adjustments["DP-1"].y===5 && editor.message.indexOf("Cut imported")===0)
                console.log("ROUNDTRIP_PASS");
            else fail("Composition was not restored");
            Qt.quit();
        }
    } }
}
'''.replace('IMAGE', json.dumps(str(source/'docs/demo-wallpaper.png')))
    (directory/'check.qml').write_text(harness)
    env = {**os.environ, 'XDG_CONFIG_HOME': str(directory/'config'), 'XDG_STATE_HOME': str(directory/'state')}
    run = subprocess.run(['qs', '-p', str(directory/'check.qml')], env=env, capture_output=True, text=True, timeout=45)
    output = run.stdout + run.stderr
    assert run.returncode == 0 and 'ROUNDTRIP_PASS' in output, output
    assert (export/'layout.json').exists()
    assert (export/'source.png').exists()
    assert not (directory/'state/omarchy-wallpaper-cutter/applied.json').exists()
    print('PASS: default name, native Save dialog, custom name, export, native import, restored adjustments; no wallpaper applied')
