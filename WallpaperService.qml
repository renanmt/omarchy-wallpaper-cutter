import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

Item {
    id: root
    property var wallpapers: ({})
    readonly property string stateHome: Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state"
    FileView {
        id: state
        path: root.stateHome + "/omarchy-wallpaper-cutter/applied.json"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: { try { root.wallpapers = JSON.parse(text()); } catch (e) { console.warn(e); } }
        onLoadFailed: root.wallpapers = ({})
    }
    Timer { interval: 1500; running: true; repeat: true; onTriggered: state.reload() }
    Variants {
        model: Quickshell.screens
        PanelWindow {
            required property var modelData
            screen: modelData
            visible: !!root.wallpapers[modelData.name]
            anchors { top: true; right: true; bottom: true; left: true }
            exclusionMode: ExclusionMode.Ignore
            WlrLayershell.namespace: "wallpaper-cutter"
            WlrLayershell.layer: WlrLayer.Bottom
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
            color: "transparent"
            mask: Region {}
            Image { anchors.fill: parent; source: root.wallpapers[modelData.name] || ""; fillMode: Image.Stretch; cache: false }
        }
    }
}
