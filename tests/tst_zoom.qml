import QtQuick
import QtTest
import ".."
Item {
    width: 420; height: 100
    ZoomSlider { id: slider; width: 400; value: 1 }
    TestCase {
        name: "ZoomMouseInteraction"
        when: windowShown
        function test_click_and_drag() {
            verify(slider.height >= 30);
            mouseClick(slider, 300, slider.height/2);
            verify(slider.value > 2.5);
            mousePress(slider, 300, slider.height/2);
            mouseMove(slider, 60, slider.height/2, 50);
            verify(slider.value < 1.2, "Dragging must update zoom before release");
            mouseRelease(slider, 60, slider.height/2);
        }
    }
}
