import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import "Geometry.js" as Geometry

Item {
    id: root
    property alias contentItem: appContent
    property bool opened: false
    property var monitors: []
    property var adjustments: ({})
    property real gap: 0
    property int selected: 0
    property var picture: null
    property real zoom: 1
    property real panX: 0
    property real panY: 0
    property string message: "Choose an image to begin. Your display layout is detected automatically."
    property bool error: false
    property string job: ""
    property bool sessionLoaded: false
    property bool loadSessionNext: false
    property string exportDirectory: ""
    property string exportName: ""
    readonly property bool busy: worker.running || picker.running
    readonly property var frames: Geometry.frames(monitors, gap, adjustments)
    readonly property var bounds: Geometry.bounds(frames)
    readonly property real baseScale: picture ? Math.max(bounds.width/picture.width, bounds.height/picture.height) : 1
    readonly property real imageScale: baseScale * zoom
    readonly property real imageX: bounds.x + (bounds.width-(picture ? picture.width*imageScale : 0))/2 + panX
    readonly property real imageY: bounds.y + (bounds.height-(picture ? picture.height*imageScale : 0))/2 + panY
    readonly property bool covered: picture && frames.length > 0 && frames.every(function(m) {
        return m.x >= imageX-0.001 && m.y >= imageY-0.001 && m.x+m.width <= imageX+picture.width*imageScale+0.001 && m.y+m.height <= imageY+picture.height*imageScale+0.001;
    })
    readonly property string helper: decodeURIComponent(Qt.resolvedUrl("backend.py").toString().replace("file://", ""))
    property bool settingsReady: false
    property string pendingSettings: ""
    property string settingsStatus: "Loading saved adjustments…"
    readonly property bool settingsBusy: settingsReader.running || settingsWriter.running || pendingSettings !== ""
    onOpenedChanged: if (!opened) picker.running = false
    onGapChanged: saveSettings()
    onAdjustmentsChanged: saveSettings()

    function saveSettings() {
        if (!settingsReady) return;
        pendingSettings = JSON.stringify({gap: gap, adjustments: adjustments});
        flushSettings();
    }
    function flushSettings() {
        if (settingsWriter.running || !pendingSettings) return;
        settingsWriter.command = ["python3", helper, "save-settings", pendingSettings];
        pendingSettings = "";
        settingsStatus = "Saving adjustments…";
        settingsWriter.running = true;
    }
    Process {
        id: settingsReader
        command: ["python3", root.helper, "load-settings"]
        running: true
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var result = JSON.parse(text);
                    if (!result.ok) throw new Error(result.error);
                    root.gap = result.data.gap;
                    root.adjustments = result.data.adjustments;
                    root.settingsReady = true;
                    root.settingsStatus = "Adjustments saved automatically";
                } catch (e) { root.error = true; root.message = "Could not load settings: " + e; root.settingsStatus = "Settings unavailable"; }
            }
        }
    }
    Process {
        id: settingsWriter
        onExited: Qt.callLater(root.flushSettings)
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var result = JSON.parse(text);
                    if (!result.ok) throw new Error(result.error);
                    root.settingsStatus = "Adjustments saved automatically";
                } catch (e) { root.error = true; root.message = "Could not save settings: " + e; root.settingsStatus = "Settings not saved"; }
            }
        }
    }
    Theme { id: theme }

    function open(payload) { opened = true; if (!monitors.length) run("monitors", []); }
    function close() { opened = false; }
    function run(command, args) {
        if (busy) return;
        job = command; error = false;
        worker.command = ["python3", helper, command].concat(args);
        worker.running = true;
    }
    function fit() { zoom = 1; panX = 0; panY = 0; }
    function offset(axis, value) {
        if (!frames[selected]) return;
        var next = JSON.parse(JSON.stringify(adjustments));
        var name = frames[selected].name;
        if (!next[name]) next[name] = {x:0,y:0};
        next[name][axis] = value; adjustments = next;
    }
    function currentOffset(axis) {
        var m = frames[selected];
        return m && adjustments[m.name] ? adjustments[m.name][axis] : 0;
    }
    function beginExport() {
        var filename = picture.name || picture.path.slice(picture.path.lastIndexOf("/") + 1);
        exportName = "cut-" + filename.replace(/\.[^.]+$/, "");
        choosePath("export");
    }
    function exportImages(apply) {
        var data = {image: picture, frames: frames, imageScale:imageScale, imageX:imageX, imageY:imageY,
            gap:gap, adjustments:adjustments, zoom:zoom, panX:panX, panY:panY, apply:apply, directory:exportDirectory, exportName:apply ? "" : exportName};
        run("export", [JSON.stringify(data)]);
        message = apply ? "Cutting and applying wallpapers…" : "Exporting full-resolution PNGs…";
    }
    Process {
        id: worker
        onExited: { if (root.loadSessionNext) { root.loadSessionNext = false; Qt.callLater(function() { root.run("session", []); }); } }
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var result = JSON.parse(text);
                    if (!result.ok) { root.error = true; root.message = result.error; return; }
                    if (root.job === "monitors") {
                        root.monitors = result.data; root.selected = 0;
                        if (!root.sessionLoaded) { root.sessionLoaded = true; root.loadSessionNext = true; }
                        root.message = result.data.length + " displays detected. Choose an image or adjust your composition.";
                    } else if (root.job === "session" && result.data) {
                        var saved = result.data;
                        root.picture = saved.image;
                        root.zoom = saved.zoom || 1; root.panX = saved.panX || 0; root.panY = saved.panY || 0;
                        root.message = "Last exported composition restored. Display layout refreshed.";
                    } else if (root.job === "import") {
                        var imported = result.data;
                        root.picture = imported.image;
                        root.gap = imported.gap; root.adjustments = imported.adjustments;
                        root.zoom = imported.zoom; root.panX = imported.panX; root.panY = imported.panY;
                        root.message = "Cut imported. Review it on your current displays, then apply.";
                    } else if (root.job === "inspect" || root.job === "omarchy-wallpaper") {
                        root.picture = result.data; root.fit();
                        root.message = (root.job === "omarchy-wallpaper" ? "Active Omarchy wallpaper loaded. " : "") + "Drag the image to compose. Scroll to zoom. Arrow keys for precise movement.";
                    } else if (root.job === "export") {
                        root.message = (result.data.themeChanged ? "Theme changed; kept the theme wallpaper. Export saved to " : result.data.applied ? "Applied. PNGs saved to " : "Exported to ") + result.data.directory;
                    } else if (root.job === "restore") root.message = "Omarchy wallpaper restored.";
                } catch (e) { root.error = true; root.message = "Unable to read helper response: " + e; }
            }
        }
        stderr: StdioCollector { onStreamFinished: if (text.trim()) { root.error = true; root.message = text.trim(); } }
    }
    function choosePath(mode) {
        if (busy) return;
        picker.mode = mode;
        picker.reply = null;
        var start = mode === "image" && picture ? picture.path.slice(0, picture.path.lastIndexOf("/")) : exportDirectory;
        picker.environment = {WALLPAPER_CUTTER_PICKER_MODE: mode, WALLPAPER_CUTTER_EXPORT_NAME: exportName,
            WALLPAPER_CUTTER_PICKER_FOLDER: start ? "file://" + encodeURI(start).replace(/#/g, "%23").replace(/\?/g, "%3F") : ""};
        picker.running = true;
    }
    Process {
        id: picker
        property string mode: ""
        onStarted: console.log("Wallpaper Cutter native picker PID:", processId)
        property var reply: null
        command: ["qs", "--no-color", "--log-rules", "qml.debug=true", "-p", root.helper.slice(0, root.helper.lastIndexOf("/")) + "/Picker.qml"]
        function readReply(text) {
            var marker = "WALLPAPER_CUTTER_PICKER_RESULT ";
            text.split("\n").forEach(function(line) {
                var index = line.indexOf(marker);
                if (index >= 0) {
                    try { reply = JSON.parse(line.slice(index + marker.length)); } catch(e) {}
                }
            });
        }
        stdout: StdioCollector { onStreamFinished: picker.readReply(text) }
        stderr: StdioCollector { onStreamFinished: picker.readReply(text) }
        onExited: Qt.callLater(function() {
            if (!root.opened) return;
            if (!picker.reply || typeof picker.reply.url !== "string") {
                root.error = true;
                root.message = "The file picker closed unexpectedly. Please try again.";
                return;
            }
            var url = picker.reply.url;
            if (!url) return; // Cancellation leaves the composition untouched.
            if (url.indexOf("file://") !== 0) {
                root.error = true; root.message = "Choose a local file or folder."; return;
            }
            var path = decodeURIComponent(url.slice(7));
            if (picker.mode === "image") root.run("inspect", [path]);
            else if (picker.mode === "import") root.run("import", [path]);
            else if (picker.mode === "export") {
                root.exportDirectory = path.slice(0, path.lastIndexOf("/")) || "/";
                root.exportName = path.slice(path.lastIndexOf("/") + 1);
                root.exportImages(false);
            }
        })
    }

    component Copy: Text {
        // Diagnostics and filenames are untrusted text, never HTML/resources.
        textFormat: Text.PlainText
        color: theme.foreground
        font.family: theme.font
        font.pixelSize: 12
        elide: Text.ElideRight
    }
    component Action: Button {
        id: button
        property bool primary: false
        implicitHeight: 36
        implicitWidth: label.implicitWidth + 28
        hoverEnabled: true
        contentItem: Copy { id: label; text: button.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: button.primary ? theme.background : theme.foreground; opacity: button.enabled ? 1 : 0.35 }
        background: Rectangle { color: button.primary ? theme.accent : button.hovered ? Qt.alpha(theme.foreground,0.1) : "transparent"; border.width: 1; border.color: button.activeFocus ? theme.accent : theme.border; opacity: button.enabled ? 1 : 0.4 }
    }
    component Value: SpinBox {
        id: spin
        from: -5000; to: 5000; editable: true
        implicitWidth: 118; implicitHeight: 34
        palette.text: theme.foreground
        palette.base: theme.surface
        contentItem: TextInput {
            text: spin.textFromValue(spin.value, spin.locale)
            color: theme.foreground; font.family: theme.font; font.pixelSize: 12
            horizontalAlignment: Qt.AlignHCenter; verticalAlignment: Qt.AlignVCenter
            validator: spin.validator; readOnly: !spin.editable
            selectByMouse: true; selectionColor: theme.accent
        }
        background: Rectangle { color: theme.surface; border.color: spin.activeFocus ? theme.accent : theme.border }
        up.indicator: Rectangle { x: spin.width-width; width: 26; height: spin.height; color: spin.up.pressed ? theme.border : "transparent"; Copy { anchors.centerIn: parent; text: "+" } }
        down.indicator: Rectangle { width: 26; height: spin.height; color: spin.down.pressed ? theme.border : "transparent"; Copy { anchors.centerIn: parent; text: "−" } }
    }
    component Rule: Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.border }

    FloatingWindow {
        id: window
        visible: root.opened
        title: "Wallpaper Cutter"
        implicitWidth: 1180; implicitHeight: 780
        minimumSize: Qt.size(850, 640)
        color: theme.background
        onVisibleChanged: if (!visible) root.opened = false

        Rectangle {
            id: appContent
            anchors.fill: parent; color: theme.background
        ColumnLayout {
            anchors.fill: parent; spacing: 0
            RowLayout {
                Layout.fillWidth: true; Layout.margins: 24; spacing: 14
                Rectangle { width: 36; height: 36; color: theme.accent
                    Copy { anchors.centerIn: parent; text: "▥"; color: theme.background; font.pixelSize: 25 }
                }
                ColumnLayout { spacing: 3
                    Copy { text: "WALLPAPER CUTTER"; font.pixelSize: 16; font.bold: true; font.letterSpacing: 1.5 }
                    Copy { text: "One image. Every display."; color: theme.muted }
                }
                Item { Layout.fillWidth: true }
                Copy { text: root.monitors.length + " DISPLAYS"; color: theme.accent; font.pixelSize: 10; font.letterSpacing: 1 }
                Action { text: "Import cut…"; enabled: !root.busy; onClicked: root.choosePath("import") }
                Action { text: "Use Omarchy wallpaper"; enabled: !root.busy; onClicked: root.run("omarchy-wallpaper", []) }
                Action { text: "Choose image"; enabled: !root.busy; onClicked: root.choosePath("image") }
            }
            Rule {}
            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
                ColumnLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.margins: 24; spacing: 16
                    RowLayout {
                        Layout.fillWidth: true
                        Copy { text: "COMPOSITION"; color: theme.muted; font.pixelSize: 10; font.letterSpacing: 1.5 }
                        Item { Layout.fillWidth: true }
                        Copy { text: root.picture ? root.picture.width + " × " + root.picture.height + " SOURCE" : "LIVE PREVIEW"; color: theme.muted; font.pixelSize: 10 }
                    }
                    Rectangle {
                        id: canvas
                        Layout.fillWidth: true; Layout.fillHeight: true
                        color: Qt.tint(theme.background, "#07000000"); border.color: theme.border; clip: true
                        readonly property real ratio: Math.min((width-80)/root.bounds.width, (height-100)/root.bounds.height)
                        readonly property real originX: (width-root.bounds.width*ratio)/2-root.bounds.x*ratio
                        readonly property real originY: (height-root.bounds.height*ratio)/2-root.bounds.y*ratio
                        Canvas {
                            id: dots
                            anchors.fill: parent
                            onPaint: {
                                var ctx = getContext("2d"); ctx.reset(); ctx.fillStyle = Qt.alpha(theme.foreground,0.12);
                                for (var x=16;x<width;x+=24) for(var y=16;y<height;y+=24) ctx.fillRect(x,y,1,1);
                            }
                            Connections { target: theme; function onForegroundChanged() { dots.requestPaint(); } }
                        }
                        Image {
                            visible: !!root.picture
                            source: root.picture ? root.picture.preview : ""
                            x: canvas.originX+root.imageX*canvas.ratio; y: canvas.originY+root.imageY*canvas.ratio
                            width: root.picture ? root.picture.width*root.imageScale*canvas.ratio : 0
                            height: root.picture ? root.picture.height*root.imageScale*canvas.ratio : 0
                            opacity: 0.14
                        }
                        Repeater {
                            model: root.frames
                            delegate: Item {
                                id: frame
                                required property var modelData
                                required property int index
                                x: canvas.originX+modelData.x*canvas.ratio; y: canvas.originY+modelData.y*canvas.ratio
                                width: modelData.width*canvas.ratio; height: modelData.height*canvas.ratio
                                Rectangle {
                                    anchors.fill: parent; color: theme.surface; clip: true
                                    Image {
                                        source: root.picture ? root.picture.preview : ""
                                        x: (root.imageX-frame.modelData.x)*canvas.ratio; y: (root.imageY-frame.modelData.y)*canvas.ratio
                                        width: root.picture ? root.picture.width*root.imageScale*canvas.ratio : 0
                                        height: root.picture ? root.picture.height*root.imageScale*canvas.ratio : 0
                                    }
                                    Rectangle { anchors.fill: parent; color: "transparent"; border.width: root.selected === frame.index ? 2 : 1; border.color: root.selected === frame.index ? theme.accent : theme.foreground }
                                    Rectangle { x: 10; y: 10; width: badge.implicitWidth+14; height: 25; color: Qt.alpha(theme.background,0.85)
                                        Copy { id: badge; anchors.centerIn: parent; text: (frame.index+1)+" / "+frame.modelData.name; font.pixelSize: 10; color: root.selected === frame.index ? theme.accent : theme.foreground }
                                    }
                                    Copy { anchors.centerIn: parent; visible: !root.picture; text: frame.modelData.pixelWidth+" × "+frame.modelData.pixelHeight; color: theme.muted; font.pixelSize: 10 }
                                }
                                Copy { anchors.top: parent.bottom; anchors.topMargin: 10; anchors.horizontalCenter: parent.horizontalCenter; text: frame.modelData.name; color: theme.muted; font.pixelSize: 10 }
                            }
                        }
                        MouseArea {
                            id: drag
                            anchors.fill: parent; focus: true; hoverEnabled: true
                            cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                            property real lastX: 0; property real lastY: 0
                            onPressed: function(mouse) {
                                forceActiveFocus(); lastX=mouse.x; lastY=mouse.y;
                                var x=(mouse.x-canvas.originX)/canvas.ratio, y=(mouse.y-canvas.originY)/canvas.ratio;
                                root.frames.forEach(function(m,i) { if(x>=m.x && x<=m.x+m.width && y>=m.y && y<=m.y+m.height) root.selected=i; });
                            }
                            onPositionChanged: function(mouse) {
                                if(pressed && root.picture) { root.panX+=(mouse.x-lastX)/canvas.ratio; root.panY+=(mouse.y-lastY)/canvas.ratio; lastX=mouse.x; lastY=mouse.y; }
                            }
                            onWheel: function(wheel) { if(root.picture) root.zoom=Math.max(0.25,Math.min(4, root.zoom*Math.pow(1.001,wheel.angleDelta.y))); }
                            Keys.onPressed: function(event) {
                                var step = event.modifiers & Qt.ShiftModifier ? 10 : 1;
                                if(event.key===Qt.Key_Left) root.panX-=step;
                                else if(event.key===Qt.Key_Right) root.panX+=step;
                                else if(event.key===Qt.Key_Up) root.panY-=step;
                                else if(event.key===Qt.Key_Down) root.panY+=step;
                                else if(event.key===Qt.Key_0) root.fit();
                                else return;
                                event.accepted=true;
                            }
                        }
                        Rectangle {
                            visible: !root.picture
                            anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 24
                            width: emptyText.implicitWidth+28; height: 34; color: theme.background; border.color: theme.border
                            Copy { id: emptyText; anchors.centerIn: parent; text: "Choose an image to start composing"; color: theme.muted; font.pixelSize: 11 }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 12
                        Copy { text: "ZOOM"; color: theme.muted; font.pixelSize: 10 }
                        ZoomSlider {
                            id: zoomSlider
                            Layout.fillWidth: true; from: 0.25; to: 4; value: root.zoom; enabled: !!root.picture
                            onMoved: root.zoom=value
                            accentColor: theme.accent
                            trackColor: theme.border
                        }
                        Copy { text: Math.round(root.zoom*100)+"%"; Layout.preferredWidth: 40 }
                        Action { text: "Fill layout"; enabled: !!root.picture; onClicked: root.fit() }
                    }
                    Copy { text: "DRAG to compose    SCROLL to zoom    ↑↓←→ to nudge    SHIFT for 10 px"; color: theme.muted; font.pixelSize: 10; Layout.fillWidth: true }
                }
                Rectangle { Layout.fillHeight: true; implicitWidth: 1; color: theme.border }
                ScrollView {
                    Layout.preferredWidth: 292; Layout.fillHeight: true; clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width; spacing: 16
                        Item { implicitHeight: 8 }
                        ColumnLayout {
                            Layout.fillWidth: true; Layout.leftMargin: 20; Layout.rightMargin: 20; spacing: 14
                            RowLayout {
                                Copy { text: "YOUR DISPLAYS"; color: theme.muted; font.pixelSize: 10; font.letterSpacing: 1 }
                                Item { Layout.fillWidth: true }
                                ToolButton { text: "↻"; palette.buttonText: theme.accent; enabled: !root.busy; onClicked: root.run("monitors", []); ToolTip.visible: hovered; ToolTip.text: "Refresh monitor layout" }
                            }
                            Repeater {
                                model: root.frames
                                delegate: Rectangle {
                                    required property var modelData
                                    required property int index
                                    Layout.fillWidth: true; implicitHeight: 64
                                    color: root.selected===index ? Qt.alpha(theme.accent,0.08) : "transparent"
                                    border.color: root.selected===index ? theme.accent : theme.border
                                    ColumnLayout { anchors.fill: parent; anchors.margins: 12; spacing: 5
                                        Copy { text: (index+1)+"   "+modelData.name; color: root.selected===index ? theme.accent : theme.foreground }
                                        Copy { text: modelData.pixelWidth+" × "+modelData.pixelHeight+"  ·  "+modelData.scale+"× scale"; color: theme.muted; font.pixelSize: 10 }
                                    }
                                    MouseArea { anchors.fill: parent; onClicked: root.selected=index; cursorShape: Qt.PointingHandCursor }
                                }
                            }
                            Rule {}
                            Copy { text: "BEZEL COMPENSATION"; color: theme.muted; font.pixelSize: 10; font.letterSpacing: 1 }
                            RowLayout {
                                Copy { text: "Gap at each seam"; Layout.fillWidth: true; font.pixelSize: 11 }
                                Value { enabled: root.settingsReady; from: 0; to: 500; value: root.gap; onValueModified: root.gap=value }
                            }
                            Copy { text: "Logical pixels between touching displays.\nThe image behind each gap is omitted."; color: theme.muted; font.pixelSize: 10; lineHeight: 1.5; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                            Rule {}
                            Copy { text: (root.frames[root.selected] ? root.frames[root.selected].name : "DISPLAY")+" ALIGNMENT"; color: theme.muted; font.pixelSize: 10; font.letterSpacing: 1 }
                            RowLayout { Copy { text: "Horizontal"; Layout.fillWidth: true; font.pixelSize: 11 } Value { enabled: root.settingsReady; value: root.currentOffset("x"); onValueModified: root.offset("x",value) } }
                            RowLayout { Copy { text: "Vertical"; Layout.fillWidth: true; font.pixelSize: 11 } Value { enabled: root.settingsReady; value: root.currentOffset("y"); onValueModified: root.offset("y",value) } }
                            Copy { text: "Fine-tune the selected screen’s crop.\nYour desktop layout stays unchanged."; color: theme.muted; font.pixelSize: 10; lineHeight: 1.5; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                            Action { text: "Reset adjustments"; enabled: root.settingsReady; Layout.fillWidth: true; onClicked: { root.gap=0; root.adjustments=({}); root.fit(); } }
                            Copy { text: root.settingsStatus; color: theme.muted; font.pixelSize: 10; Layout.fillWidth: true }
                            Rule {}
                            Copy { text: "OUTPUT"; color: theme.muted; font.pixelSize: 10; font.letterSpacing: 1 }
                            Copy { text: "PNG · native display resolution\nPortrait & scaled displays supported"; color: theme.muted; font.pixelSize: 10; lineHeight: 1.5; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                            Action { text: "Restore Omarchy wallpaper"; Layout.fillWidth: true; enabled: !root.busy; onClicked: root.run("restore", []) }
                        }
                        Item { implicitHeight: 12 }
                    }
                }
            }
            Rule {}
            RowLayout {
                Layout.fillWidth: true; Layout.margins: 20; spacing: 12
                Rectangle { width: 6; height: 6; radius: 3; color: root.error ? "#e78284" : theme.accent }
                Copy { Layout.fillWidth: true; text: root.picture && !root.covered ? "Image does not cover every display. Use Fill layout or adjust the composition." : root.message; color: root.error ? "#e78284" : theme.muted; font.pixelSize: 11; wrapMode: Text.WordWrap; maximumLineCount: 3 }
                Action { text: "Export…"; enabled: root.covered && !root.busy; onClicked: root.beginExport() }
                Action { text: root.busy ? "Working…" : "Apply wallpapers"; primary: true; enabled: root.covered && !root.busy; onClicked: { root.exportDirectory=""; root.exportImages(true); } }
            }
        }
        }
        Shortcut { sequence: "Ctrl+O"; onActivated: if(!root.busy) root.choosePath("image") }
        Shortcut { sequence: "Escape"; onActivated: root.close() }
    }
}
