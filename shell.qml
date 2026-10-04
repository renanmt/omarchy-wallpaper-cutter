import QtQuick
import Quickshell
ShellRoot {
    Panel { id: editor; Component.onCompleted: open("{}") }
    // Standalone owns this process; installed panels never quit the shared shell.
    Timer {
        interval: 50
        running: !editor.opened && !editor.busy && !editor.settingsBusy
        onTriggered: Qt.quit()
    }
    WallpaperService {}
}
