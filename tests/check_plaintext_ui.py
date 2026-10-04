import http.server
import json
import os
from pathlib import Path
import subprocess
import threading
import tempfile
import shutil

# Native regression check: opens two short-lived editor windows and uses a
# loopback-only server. The AutoText copy is the positive control.
source = Path(__file__).resolve().parents[1]
workspace = tempfile.TemporaryDirectory(prefix='cutter-plaintext-')
requests=[]
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        requests.append(self.path)
        self.send_response(204);self.end_headers()
    def log_message(self,*args): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    for variant in ['before','after']:
        requests.clear()
        directory=Path(workspace.name)/variant
        directory.mkdir()
        for pattern in ('*.qml', '*.js', 'backend.py'):
            for path in source.glob(pattern): shutil.copy2(path, directory/path.name)
        if variant == 'before':
            panel = directory/'Panel.qml'
            panel.write_text(panel.read_text().replace('textFormat: Text.PlainText', 'textFormat: Text.AutoText'))
        payload=f'<p>Decode failed: <img src="http://127.0.0.1:{server.server_port}/{variant}.png"></p>'
        qml='''import QtQuick
import Quickshell
ShellRoot {
    Panel { id: editor; Component.onCompleted: open("{}") }
    Timer { interval: 1000; running: true; onTriggered: { editor.error = true; editor.message = PAYLOAD; } }
    Timer { interval: 2300; running: true; onTriggered: {
        function search(item) {
            if (item.text === PAYLOAD) console.log("DIAGNOSTIC_FORMAT", item.textFormat === Text.PlainText ? "PLAIN" : "AUTO");
            if (item.children) for(var i=0;i<item.children.length;i++) search(item.children[i]);
        }
        search(editor.contentItem);
    } }
    Timer { interval: 3000; running: true; onTriggered: Qt.quit() }
}
'''.replace('PAYLOAD',json.dumps(payload))
        (directory/'preview.qml').write_text(qml)
        env={**os.environ,'XDG_CONFIG_HOME':str(directory/'config'),'XDG_STATE_HOME':str(directory/'state')}
        run=subprocess.run(['qs','-p',str(directory/'preview.qml')],env=env,capture_output=True,text=True,timeout=10)
        output=run.stdout+run.stderr
        assert run.returncode==0,output
        expected='PLAIN' if variant=='after' else 'AUTO'
        assert 'DIAGNOSTIC_FORMAT '+expected in output,output
        if variant=='before': assert requests, 'Positive control did not fetch its embedded image'
        else: assert not requests, f'Plain text still fetched: {requests}'
        print(f'{variant}: diagnostic {expected}, image requests={len(requests)}')
    print('PASS: exploit reproduced before fix; no image request after fix')
finally:
    server.shutdown()
    workspace.cleanup()
