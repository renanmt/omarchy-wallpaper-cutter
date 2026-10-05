#!/usr/bin/env python3
"""Keep the plugin's desktop entry registered for its service lifetime."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import signal
import shlex
import socket
import sys
import tempfile
import uuid

NAME = 'renan.wallpaper-cutter.desktop'
OWNER = 'X-Wallpaper-Cutter-Owner='


def applications_dir():
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'applications'


@contextmanager
def locked(directory):
    directory.mkdir(parents=True, exist_ok=True)
    # All instances use the same lock, including across shell/plugin reloads.
    with (directory / '.renan.wallpaper-cutter.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def register(directory, template, owner, name=NAME, marker=OWNER, mode=0o644):
    path = directory / name
    content = template.rstrip() + '\n' + marker + owner + '\n'
    with locked(directory):
        if path.is_symlink():
            raise RuntimeError(f'Keeping existing launcher symlink: {path}')
        if path.exists():
            existing = path.read_text()
            # Accept our managed entries and the exact earlier manual copy.
            base = '\n'.join(line for line in existing.splitlines() if not line.startswith(marker))
            if base.strip() != template.strip():
                raise RuntimeError(f'Keeping customized launcher: {path}')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=directory, delete=False) as out:
                temporary = Path(out.name)
                out.write(content)
                os.fchmod(out.fileno(), mode)
            os.replace(temporary, path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
    return content


def unregister(directory, content, name=NAME):
    path = directory / name
    with locked(directory):
        # Never remove a newer instance's entry or a user's modified file.
        if path.is_file() and not path.is_symlink() and path.read_text() == content:
            path.unlink()


def stop(signum, frame):
    raise SystemExit(0)


def main():
    directory = applications_dir()
    template = Path(__file__).with_name(NAME).read_text()
    owner = uuid.uuid4().hex
    content = template.rstrip() + '\n' + OWNER + owner + '\n'
    hook_dir = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'omarchy/hooks/theme-set.d'
    hook_name = 'renan.wallpaper-cutter'
    helper = shlex.quote(str(Path(__file__).resolve().with_name('backend.py')))
    hook_template = '#!/bin/sh\nexec python3 ' + helper + ' theme-changed\n'
    hook_content = None
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        # A detached helper survives Quickshell destroying its QML objects long
        # enough to clean up. The private local socket is its lifetime lease:
        # unload/crash closes the peer, so no timer or desktop-wide polling runs.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as lease:
            lease.connect(sys.argv[1])
            hook_content = register(hook_dir, hook_template, owner, hook_name, '# Wallpaper-Cutter-Owner=', 0o755)
            register(directory, template, owner)
            lease.sendall(b'ready\n')
            while lease.recv(1):
                pass
    finally:
        unregister(directory, content)
        if hook_content:
            unregister(hook_dir, hook_content, hook_name)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
