import QtQuick
import Quickshell
ShellRoot {
    property int step: 0
    property var appEntries: DesktopEntries.applications.values
    Loader { id: loader; active: true; sourceComponent: WallpaperService { shell: ({}) } }
    Timer {
        interval: 2000; running: true; repeat: true
        onTriggered: {
            var found=appEntries.some(function(entry) { return entry.name === "Wallpaper Cutter"; });
            console.log("LAUNCHER_STEP",step,"found",found);
            if (found !== (step % 2 === 0)) { console.error("LAUNCHER_TEST_FAIL",step); Qt.quit(); return; }
            if(step===0) loader.active=false;
            if(step===1) loader.active=true;
            if(step===2) loader.active=false;
            if(step===3) { console.log("LAUNCHER_TEST_PASS"); Qt.quit(); }
            step++;
        }
    }
}
