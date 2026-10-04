#!/usr/bin/env python3
"""Local image I/O and Hyprland discovery. No server or shell interpolation."""
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager

STATE = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'omarchy-wallpaper-cutter'

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')) / 'omarchy-wallpaper-cutter'

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
        json.dump(value, f)
        temporary = f.name
    os.replace(temporary, path)


def monitors(raw=None):
    if raw is None:
        raw = json.loads(subprocess.check_output(['hyprctl', 'monitors', '-j'], timeout=5))
    result = []
    for m in raw:
        if m.get('disabled') or m.get('mirrorOf', 'none') not in ('none', '', None):
            continue
        w, h = int(m['width']), int(m['height'])
        if int(m.get('transform', 0)) % 2:
            w, h = h, w
        scale = float(m.get('scale', 1))
        result.append(dict(name=m['name'], description=m.get('description', m['name']),
                           x=m['x'], y=m['y'], width=w / scale, height=h / scale,
                           pixelWidth=w, pixelHeight=h, scale=scale,
                           transform=m.get('transform', 0)))
    if not result:
        raise ValueError('No active independent displays found. Start this app in a Hyprland session.')
    return sorted(result, key=lambda m: (m['x'], m['y'], m['name']))


def magick(arguments, stdin=None):
    try:
        result = subprocess.run(['magick', *map(str, arguments)], stdin=stdin,
                                capture_output=True, timeout=120, check=True)
    except FileNotFoundError as error:
        raise RuntimeError('ImageMagick (magick) is missing. It is included with standard Omarchy installations.') from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('Image processing timed out after 120 seconds.') from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(error.stderr.decode(errors='replace').strip() or 'ImageMagick could not process this image.') from error
    return result.stdout.decode().strip()


@contextmanager
def normalized_image(path):
    # Read an actual local file through stdin, so brackets/colons in filenames
    # cannot be interpreted as ImageMagick selectors or pseudo-image operators.
    with tempfile.TemporaryDirectory(prefix='wallpaper-cutter-') as temporary:
        normalized = Path(temporary) / 'source.miff'
        with Path(path).expanduser().open('rb') as source:
            dimensions = magick(['-[0]', '-auto-orient', '-colorspace', 'sRGB',
                                 '-background', 'black', '-alpha', 'remove', '-alpha', 'off',
                                 '+repage', '-strip', '-write', normalized,
                                 '-format', '%w %h', 'info:'], stdin=source)
        width, height = map(int, dimensions.split())
        yield normalized, width, height


def inspect(path):
    STATE.mkdir(parents=True, exist_ok=True)
    preview = STATE / ('preview-' + uuid.uuid4().hex + '.jpg')
    try:
        with normalized_image(path) as (normalized, width, height):
            magick([normalized, '-filter', 'Lanczos', '-resize', '3840x3840>',
                    '-quality', '93', preview])
    except Exception:
        preview.unlink(missing_ok=True)
        raise
    return dict(path=str(Path(path).expanduser().resolve()), preview=preview.as_uri(),
                width=width, height=height)


def number(value, minimum=-1000000, maximum=1000000):
    value = float(value)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError('An adjustment is outside the supported range.')
    return value


def validate_settings(data):
    if not isinstance(data, dict) or not isinstance(data.get('adjustments', {}), dict):
        raise ValueError('Settings must contain a monitor adjustment object.')
    adjustments = {}
    for name, value in data.get('adjustments', {}).items():
        if not isinstance(name, str) or not isinstance(value, dict):
            raise ValueError('Invalid monitor adjustment.')
        adjustments[name] = dict(x=number(value.get('x', 0), -5000, 5000),
                                 y=number(value.get('y', 0), -5000, 5000))
    return dict(version=1, gap=number(data.get('gap', 0), 0, 500), adjustments=adjustments)


def save_settings(data):
    settings = validate_settings(data)
    atomic_json(CONFIG / 'settings.json', settings)
    return settings


def load_settings():
    path = CONFIG / 'settings.json'
    if path.exists():
        return validate_settings(json.loads(path.read_text()))
    # Migrate old export-dependent settings even if the source image is gone.
    session = STATE / 'session.json'
    if session.exists():
        return save_settings(json.loads(session.read_text()))
    return validate_settings({})


def render(request):
    with normalized_image(request['image']['path']) as (image, width, height):
        return render_normalized(request, image, width, height)


def render_normalized(request, image, width, height):
    scale = number(request['imageScale'], 0.00001, 10000)
    ix, iy = number(request['imageX']), number(request['imageY'])
    frames = request['frames']
    if not frames or len(frames) > 32:
        raise ValueError('Choose between 1 and 32 displays.')
    crops = []
    names = set()
    for m in frames:
        name = m['name']
        if name in names:
            raise ValueError('Duplicate display name.')
        names.add(name)
        x, y = number(m['x']), number(m['y'])
        w, h = number(m['width'], 1), number(m['height'], 1)
        pw, ph = int(number(m['pixelWidth'], 1, 16384)), int(number(m['pixelHeight'], 1, 16384))
        box = ((x-ix)/scale, (y-iy)/scale, (x+w-ix)/scale, (y+h-iy)/scale)
        if box[0] < -0.01 or box[1] < -0.01 or box[2] > width+0.01 or box[3] > height+0.01:
            raise ValueError('The image must cover every display. Choose Fill layout or move the image back inside the frames.')
        box = (max(0, box[0]), max(0, box[1]), min(width, box[2]), min(height, box[3]))
        crops.append((m, box, (pw, ph)))
    # A unique directory avoids overwriting previous exports, even on failure.
    directory = Path(request.get('directory') or STATE / 'exports').expanduser() / ('cut-' + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True, exist_ok=False)
    outputs = {}
    try:
        for i, (m, box, size) in enumerate(crops):
            name = re.sub(r'[^A-Za-z0-9_.-]', '_', m['name'])
            path = directory / f'{i+1:02d}-{name}-{size[0]}x{size[1]}.png'
            # Affine mapping keeps fractional source edges; integer -crop would
            # round away small alignment/zoom changes. Viewport fixes output size.
            sx, sy = size[0] / (box[2] - box[0]), size[1] / (box[3] - box[1])
            matrix = f'{sx},0,0,{sy},{-box[0]*sx},{-box[1]*sy}'
            magick([image, '-virtual-pixel', 'edge', '-filter', 'Lanczos',
                    '-define', f'distort:viewport={size[0]}x{size[1]}+0+0',
                    '-distort', 'AffineProjection', matrix, '+repage',
                    '-depth', '8', '-strip', 'PNG24:' + str(path)])
            outputs[m['name']] = path.as_uri()
        atomic_json(directory / 'layout.json', request)
        atomic_json(STATE / 'session.json', request)
        if request.get('apply'):
            atomic_json(STATE / 'applied.json', outputs)
    except Exception:
        for path in directory.iterdir():
            path.unlink()
        directory.rmdir()
        raise
    return dict(directory=str(directory), outputs=outputs, applied=bool(request.get('apply')))


def main():
    command = sys.argv[1]
    if command == 'load-settings':
        return load_settings()
    if command == 'save-settings':
        return save_settings(json.loads(sys.argv[2]))
    if command == 'monitors':
        return monitors()
    if command == 'inspect':
        return inspect(sys.argv[2])
    if command == 'export':
        return render(json.loads(sys.argv[2]))
    if command == 'restore':
        atomic_json(STATE / 'applied.json', {})
        return {'restored': True}
    if command == 'session':
        path = STATE / 'session.json'
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        if not Path(data['image']['path']).is_file():
            return None
        data['image'] = inspect(data['image']['path'])
        return data
    raise ValueError('Unknown command')


if __name__ == '__main__':
    try:
        print(json.dumps({'ok': True, 'data': main()}))
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        sys.exit(1)
