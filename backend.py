#!/usr/bin/env python3
"""Local image I/O and Hyprland discovery. No server or shell interpolation."""
import json
import fcntl
import shutil
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
                width=width, height=height, name=Path(path).name)


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


@contextmanager
def wallpaper_lock():
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / '.wallpaper.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def theme_generation():
    path = STATE / 'theme-generation.json'
    return path.read_text() if path.exists() else ''


def restore(theme_changed=False):
    with wallpaper_lock():
        if theme_changed:
            atomic_json(STATE / 'theme-generation.json', uuid.uuid4().hex)
        atomic_json(STATE / 'applied.json', {})
    return {'restored': True}


def export_name(request):
    name = request.get('exportName')
    if name is None or name == '':
        stem = re.sub(r'[\\/\x00-\x1f\x7f]', '_', Path(request['image'].get('name') or request['image']['path']).stem)
        name = 'cut-' + stem.encode('utf-8')[:140].decode('utf-8', errors='ignore')
    if not isinstance(name, str):
        raise ValueError('Enter a name for the export.')
    name = name.strip()
    if not name or name in ('.', '..') or re.search(r'[\\/\x00-\x1f\x7f]', name) or len(name.encode('utf-8')) > 180:
        raise ValueError('Use a folder name up to 180 bytes, without slashes or control characters.')
    return name


def export_directory(parent, name):
    parent.mkdir(parents=True, exist_ok=True)
    for index in range(1, 10000):
        path = parent / (name if index == 1 else f'{name}-{index}')
        try:
            path.mkdir()
            return path
        except FileExistsError:
            continue
    raise ValueError('Too many exports with this name. Choose a different name.')


def import_layout(path):
    path = Path(path).expanduser().resolve()
    if path.is_dir():
        path /= 'layout.json'
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('This layout file is too large.')
    data = json.loads(path.read_text())
    settings = validate_settings(data)
    zoom = number(data.get('zoom', 1), 0.25, 4)
    pan_x, pan_y = number(data.get('panX', 0)), number(data.get('panY', 0))
    if data.get('sourceImage'):
        source_name = data['sourceImage']
        if not isinstance(source_name, str) or Path(source_name).name != source_name or source_name in ('.', '..'):
            raise ValueError('Invalid source image in this export.')
        image_path = (path.parent / source_name).resolve()
        if image_path.parent != path.parent:
            raise ValueError('The source image must be inside the exported folder.')
    else:
        image_path = Path(data['image']['path']).expanduser()
    if not image_path.is_file():
        raise ValueError('The original image is missing. Keep the source image with the exported layout.')
    image = inspect(image_path)
    image['name'] = str(data['image'].get('name') or Path(data['image']['path']).name)
    return dict(image=image, gap=settings['gap'], adjustments=settings['adjustments'],
                zoom=zoom, panX=pan_x, panY=pan_y)


def render(request):
    name = export_name(request)
    generation = theme_generation()
    with normalized_image(request['image']['path']) as (image, width, height):
        return render_normalized(request, image, width, height, name, generation)


def render_normalized(request, image, width, height, directory_name, generation):
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
    directory = export_directory(Path(request.get('directory') or STATE / 'exports').expanduser(), directory_name)
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
        source = Path(request['image']['path']).expanduser()
        source_name = 'source' + source.suffix
        shutil.copyfile(source, directory / source_name)
        layout = dict(request, sourceImage=source_name, version=1)
        atomic_json(directory / 'layout.json', layout)
        atomic_json(STATE / 'session.json', request)
        applied = False
        if request.get('apply'):
            with wallpaper_lock():
                if theme_generation() == generation:
                    atomic_json(STATE / 'applied.json', outputs)
                    applied = True
    except Exception:
        for path in directory.iterdir():
            path.unlink()
        directory.rmdir()
        raise
    return dict(directory=str(directory), outputs=outputs, applied=applied, themeChanged=bool(request.get('apply')) and not applied)


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
    if command == 'import':
        return import_layout(sys.argv[2])
    if command in ('restore', 'theme-changed'):
        return restore(command == 'theme-changed')
    if command == 'session':
        path = STATE / 'session.json'
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        if not Path(data['image']['path']).is_file():
            return None
        original_name = data['image'].get('name')
        data['image'] = inspect(data['image']['path'])
        if original_name:
            data['image']['name'] = original_name
        return data
    raise ValueError('Unknown command')


if __name__ == '__main__':
    try:
        print(json.dumps({'ok': True, 'data': main()}))
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        sys.exit(1)
