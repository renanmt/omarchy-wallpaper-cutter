import QtQuick
import QtQuick.Dialogs
import Quickshell

// Native dialogs belong to this short-lived process, never the desktop shell.
ShellRoot {
    id: root
    property bool finished: false
    property string mode: Quickshell.env("WALLPAPER_CUTTER_PICKER_MODE")
    property string initialFolder: Quickshell.env("WALLPAPER_CUTTER_PICKER_FOLDER") || "file://" + Quickshell.env("HOME") + "/Pictures"
    function finish(url) {
        if (finished) return;
        finished = true;
        console.log("WALLPAPER_CUTTER_PICKER_RESULT " + JSON.stringify({url: url.toString()}));
        Qt.quit();
    }
    FileDialog {
        id: imageDialog
        title: "Choose a wallpaper"
        currentFolder: root.initialFolder
        nameFilters: ["Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"]
        onAccepted: root.finish(selectedFile)
        onRejected: root.finish("")
    }
    FileDialog {
        id: importDialog
        title: "Import an exported cut"
        currentFolder: root.initialFolder
        nameFilters: ["Wallpaper cut (layout.json)"]
        onAccepted: root.finish(selectedFile)
        onRejected: root.finish("")
    }
    FileDialog {
        id: exportDialog
        title: "Export wallpapers"
        fileMode: FileDialog.SaveFile
        acceptLabel: "Export"
        // Existing cuts are preserved using a numbered folder name.
        options: FileDialog.DontConfirmOverwrite
        currentFolder: root.initialFolder
        selectedFile: root.initialFolder.replace(/\/$/, "") + "/" + encodeURIComponent(Quickshell.env("WALLPAPER_CUTTER_EXPORT_NAME") || "cut-wallpaper")
        onAccepted: root.finish(selectedFile)
        onRejected: root.finish("")
    }
    Component.onCompleted: {
        if (mode === "image") imageDialog.open();
        else if (mode === "export") exportDialog.open();
        else if (mode === "import") importDialog.open();
        else Qt.quit();
    }
}
