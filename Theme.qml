import QtQuick
import Quickshell
import Quickshell.Io

QtObject {
    id: root
    property color background: "#101315"
    property color foreground: "#cacccc"
    property color accent: "#8caaee"
    property color muted: Qt.alpha(foreground, 0.55)
    property color surface: Qt.tint(background, Qt.alpha(foreground, 0.045))
    property color border: Qt.alpha(foreground, 0.14)
    property string font: "monospace"
    property FileView palette: FileView {
        path: Quickshell.env("HOME") + "/.local/state/omarchy/current/theme/colors.toml"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            var lines = text().split("\n");
            lines.forEach(function(line) {
                var m = line.match(/^\s*(background|foreground|accent)\s*=\s*"(#[0-9a-fA-F]+)"/);
                if (m) root[m[1]] = m[2];
            });
        }
    }
    property Timer refresh: Timer { interval: 3000; running: true; repeat: true; onTriggered: root.palette.reload() }
}
