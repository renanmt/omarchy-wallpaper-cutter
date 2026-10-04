# Preview assets

- `../preview.png`: screenshot of the real QML editor, using a sample three-display layout. No personal wallpaper or desktop contents are included.
- `demo-wallpaper.png`: original artwork generated with the built-in OpenAI image generation tool for this project, used inside the editor screenshot.
- `hero.svg`: original vector illustration from the initial release.

The generated wallpaper and project preview assets are distributed under the project MIT license.

## Generation prompt

Use case: stylized-concept. Asset type: original wallpaper used inside a real multi-monitor wallpaper editor screenshot for an open-source Omarchy plugin marketplace. Primary request: a striking panoramic landscape of sculptural dark mountains, a tiny glowing coral sun and flowing luminous teal mist crossing the whole scene. Premium editorial digital art, restrained dark charcoal, muted teal and warm coral palette, fine natural texture, elegant cinematic light. Very wide landscape composition, 3:1 aspect ratio if possible, continuous interesting detail across left, center and right so cropping into three monitors still looks cohesive. No UI, no monitor frames, no text, logos, watermarks, people or brands. This is only the wallpaper artwork; the actual application will supply the screenshot UI. Save the generated artifact for project use.

## Screenshot composition

Open `demo-wallpaper.png` in the editor with a 1080×1920 portrait display on each side of a 2560×1440 landscape display. Position the landscape display 200 logical pixels below the portrait tops, set seam compensation to 28, and use Fill layout. The captured editor window is 1440×900. The marketplace discovers the root `preview.png` automatically and generates optimized versions.
