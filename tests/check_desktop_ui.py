"""Native checks; requires a running Wayland session and Quickshell."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

source = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="cutter-desktop-") as workspace:
    directory = Path(workspace)
    for pattern in ("*.qml", "*.js", "*.py", "*.desktop"):
        for path in source.glob(pattern):
            shutil.copy2(path, directory / path.name)
    env = dict(os.environ)
    for key in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME"):
        env[key] = str(directory / key.lower())
    (Path(env["XDG_DATA_HOME"]) / "applications").mkdir(parents=True)
    state = Path(env["XDG_STATE_HOME"]) / "omarchy-wallpaper-cutter"
    state.mkdir(parents=True)
    (state / "applied.json").write_text(json.dumps({"test-monitor": "file:///unused.png"}))
    for name, marker in (("launcher", "LAUNCHER_TEST_PASS"), ("theme", "THEME_TEST_PASS")):
        shutil.copy2(source / "tests" / (name + ".qml"), directory / "check.qml")
        run = subprocess.run(["qs", "-p", str(directory / "check.qml")],
                             env=env, capture_output=True, text=True, timeout=20)
        output = run.stdout + run.stderr
        assert run.returncode == 0 and marker in output and "TEST_FAIL" not in output, output
        assert "Unable to assign" not in output and "ReferenceError" not in output, output
        print(marker)
