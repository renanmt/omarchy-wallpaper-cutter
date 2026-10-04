import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image

spec = importlib.util.spec_from_file_location('backend', Path(__file__).parents[1] / 'backend.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

class CutterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        backend.STATE = self.path / 'state'
        backend.CONFIG = self.path / 'config'
        self.source = self.path / 'source.png'
        image = Image.new('RGB', (400, 100), 'red')
        image.paste('blue', (200, 0, 400, 100))
        image.save(self.source)

    def test_settings_saved_without_export_or_image(self):
        expected = backend.save_settings({'gap': 32, 'adjustments': {'DP-1': {'x': -12, 'y': 8}}})
        self.assertEqual(backend.load_settings(), expected)
        self.assertTrue((backend.CONFIG / 'settings.json').exists())
        self.assertFalse(backend.STATE.exists())

    def test_invalid_settings_do_not_overwrite_valid_settings(self):
        expected = backend.save_settings({'gap': 24})
        with self.assertRaises(ValueError): backend.save_settings({'gap': float('nan')})
        self.assertEqual(backend.load_settings(), expected)

    def test_settings_migration_and_precedence(self):
        backend.atomic_json(backend.STATE / 'session.json', {'gap': 10, 'adjustments': {'DP-2': {'x': 3, 'y': 5}}})
        self.assertEqual(backend.load_settings()['gap'], 10)
        backend.save_settings({'gap': 40})
        self.assertEqual(backend.load_settings()['gap'], 40)

    def test_reset_settings_persists(self):
        backend.save_settings({'gap': 25})
        backend.save_settings({'gap': 0, 'adjustments': {}})
        self.assertEqual(backend.load_settings()['gap'], 0)

    def request(self):
        return dict(image={'path': str(self.source)}, imageScale=1, imageX=-100, imageY=-20,
                    frames=[dict(name='DP-1', x=-100, y=-20, width=200, height=100, pixelWidth=200, pixelHeight=100),
                            dict(name='DP-2', x=100, y=-20, width=200, height=100, pixelWidth=400, pixelHeight=200)])

    def test_rotation_scale_negative_origin_and_mirror(self):
        raw = [dict(name='DP-1', width=1920, height=1080, x=-720, y=-100, transform=3, scale=1.5),
               dict(name='mirror', width=1920, height=1080, x=0, y=0, mirrorOf='DP-1')]
        m = backend.monitors(raw)[0]
        self.assertEqual((m['width'], m['height']), (720, 1280))
        self.assertEqual((m['pixelWidth'], m['pixelHeight']), (1080, 1920))
        self.assertEqual(m['x'], -720)

    def test_crops_match_preview_coordinates_and_native_resolution(self):
        result = backend.render(self.request())
        paths = sorted(Path(result['directory']).glob('*.png'))
        with Image.open(paths[0]) as first, Image.open(paths[1]) as second:
            self.assertEqual(first.size, (200, 100))
            self.assertEqual(second.size, (400, 200))
            self.assertEqual(first.getpixel((100, 50)), (255, 0, 0))
            self.assertEqual(second.getpixel((200, 100)), (0, 0, 255))
        self.assertFalse((backend.STATE / 'applied.json').exists())

    def test_gap_discards_hidden_pixels(self):
        req = self.request()
        req['frames'][1].update(x=120, width=180)
        result = backend.render(req)
        with Image.open(sorted(Path(result['directory']).glob('*.png'))[1]) as im:
            self.assertEqual(im.getpixel((0, 50)), (0, 0, 255))

    def test_out_of_bounds_preserves_applied_state(self):
        req = self.request(); req['apply'] = True
        backend.render(req)
        before = (backend.STATE / 'applied.json').read_bytes()
        req['imageX'] = 0
        with self.assertRaises(ValueError): backend.render(req)
        self.assertEqual((backend.STATE / 'applied.json').read_bytes(), before)

    def test_nonfinite_rejected(self):
        req = self.request(); req['imageScale'] = float('nan')
        with self.assertRaises(ValueError): backend.render(req)

    def test_unique_exports(self):
        self.assertNotEqual(backend.render(self.request())['directory'], backend.render(self.request())['directory'])

    def test_exif_orientation_used_for_preview(self):
        image = Image.new('RGB', (100, 200))
        exif = image.getexif(); exif[274] = 6
        image.save(self.source, exif=exif)
        result = backend.inspect(str(self.source))
        self.assertEqual((result['width'], result['height']), (200, 100))

if __name__ == '__main__': unittest.main()
