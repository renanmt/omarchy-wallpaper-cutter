import QtQuick
import Quickshell
import Quickshell.Io
ShellRoot {
    property int stage: 0
    WallpaperService { id: service; shell: ({}) }
    Process { id: hook; command: [Quickshell.env("XDG_CONFIG_HOME") + "/omarchy/hooks/theme-set.d/renan.wallpaper-cutter"] }
    Timer { interval: 2000; running: true; repeat: true; onTriggered: {
        if(stage === 0) {
            if(!service.wallpapers["test-monitor"]) { console.error("THEME_TEST_FAIL", "No initial wallpaper"); Qt.quit(); return; }
            hook.running=true; stage=1; return;
        }
        if(hook.running) return;
        if(Object.keys(service.wallpapers).length === 0) console.log("THEME_TEST_PASS");
        else console.error("THEME_TEST_FAIL", "Wallpaper overlay remained");
        Qt.quit();
    } }
}
