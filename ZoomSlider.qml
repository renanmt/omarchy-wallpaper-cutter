import QtQuick
import QtQuick.Controls

Slider {
    id: control
    property color accentColor: "#8caaee"
    property color trackColor: "#444444"
    implicitWidth: 240
    implicitHeight: 36
    from: 0.25
    to: 4
    live: true
    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + control.availableHeight / 2 - height / 2
        implicitWidth: 200
        implicitHeight: 2
        width: control.availableWidth
        height: implicitHeight
        color: control.trackColor
        Rectangle { width: control.visualPosition * parent.width; height: parent.height; color: control.accentColor }
    }
    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        implicitWidth: 12
        implicitHeight: 18
        color: control.accentColor
        border.width: control.activeFocus ? 1 : 0
        border.color: "white"
    }
}
