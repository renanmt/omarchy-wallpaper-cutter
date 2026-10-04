import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
import subprocess
import struct
from unittest.mock import patch

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
        self.source = self.path / 'source.ppm'
        self.source.write_bytes(b'P6\n400 100\n255\n' + (bytes((255,0,0))*200 + bytes((0,0,255))*200)*100)

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
        self.assertEqual(self.size(paths[0]), (200, 100))
        self.assertEqual(self.size(paths[1]), (400, 200))
        self.assertEqual(self.pixel(paths[0], 100, 50), (255, 0, 0))
        self.assertEqual(self.pixel(paths[1], 200, 100), (0, 0, 255))
        self.assertFalse((backend.STATE / 'applied.json').exists())

    def test_gap_discards_hidden_pixels(self):
        req = self.request()
        req['frames'][1].update(x=120, width=180)
        result = backend.render(req)
        self.assertEqual(self.pixel(sorted(Path(result['directory']).glob('*.png'))[1], 0, 50), (0, 0, 255))

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
        self.source = self.path / 'portrait.jpg'
        subprocess.run(['magick', '-size', '100x200', 'xc:red', str(self.source)], check=True)
        # Real EXIF orientation tag, built with stdlib rather than an imaging library.
        tiff = b'II' + struct.pack('<HIH', 42, 8, 1) + struct.pack('<HHIHHI', 274, 3, 1, 6, 0, 0)
        payload = b'Exif\x00\x00' + tiff
        jpeg = self.source.read_bytes()
        self.source.write_bytes(jpeg[:2] + b'\xff\xe1' + struct.pack('>H', len(payload)+2) + payload + jpeg[2:])
        result = backend.inspect(str(self.source))
        self.assertEqual((result['width'], result['height']), (200, 100))
        self.assertEqual(self.size(Path(result['preview'].removeprefix('file://'))), (200, 100))

    def size(self, path):
        return tuple(map(int, subprocess.check_output(['magick', 'identify', '-format', '%w %h', str(path)]).split()))

    def pixel(self, path, x, y):
        return tuple(subprocess.check_output(['magick', str(path), '-crop', f'1x1+{x}+{y}', '-depth', '8', 'rgb:-']))

    def test_literal_filename_with_brackets_and_colons(self):
        special = self.path / 'image [0]: sunset.ppm'
        special.write_bytes(self.source.read_bytes())
        result = backend.inspect(special)
        self.assertEqual((result['width'], result['height']), (400, 100))

    def test_first_frame_only(self):
        source = self.path / 'animation.gif'
        subprocess.run(['magick', '-size', '20x10', 'xc:red', 'xc:blue', str(source)], check=True)
        result = backend.inspect(source)
        self.assertEqual((result['width'], result['height']), (20, 10))
        self.assertGreater(self.pixel(Path(result['preview'].removeprefix('file://')), 5, 5)[0], 245)

    def test_fractional_crop_matches_source_coordinates(self):
        self.source.write_bytes(b'P6\n256 100\n255\n' + b''.join(bytes((x,x,x)) for x in range(256))*100)
        req = self.request()
        req.update(imageX=0, imageY=0)
        req['frames'] = [dict(name='DP-1', x=10.75, y=0, width=100, height=100, pixelWidth=200, pixelHeight=100)]
        result = backend.render(req)
        path = next(Path(result['directory']).glob('*.png'))
        # Output pixel 80 samples source edge-coordinate 51.0, pixel-coordinate 50.5.
        self.assertLessEqual(abs(self.pixel(path, 80, 50)[0] - 51), 1)

    def test_processing_failure_preserves_applied_state(self):
        req = self.request(); req['apply'] = True
        backend.render(req)
        before = (backend.STATE / 'applied.json').read_bytes()
        original = backend.magick
        def fail_export(args, stdin=None):
            if '-distort' in args: raise RuntimeError('simulated export failure')
            return original(args, stdin)
        with patch.object(backend, 'magick', side_effect=fail_export):
            with self.assertRaises(RuntimeError): backend.render(req)
        self.assertEqual((backend.STATE / 'applied.json').read_bytes(), before)
        self.assertEqual(len(list((backend.STATE / 'exports').iterdir())), 1)

    def test_missing_imagemagick_has_clear_error(self):
        with patch.object(backend.subprocess, 'run', side_effect=FileNotFoundError):
            with self.assertRaisesRegex(RuntimeError, 'ImageMagick.*missing'): backend.inspect(self.source)

if __name__ == '__main__': unittest.main()
