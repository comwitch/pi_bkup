#!/usr/bin/env python3
"""Portable, allowlisted Pi configuration backup (Python 3.9+, no dependencies)."""
import argparse
import hashlib
import json
import ntpath
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
from datetime import datetime, timezone
import zipfile

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    'settings.json', 'keybindings.json', 'mcp.json', 'models.json',
    'AGENTS.override.md', 'AGENTS.md', 'AGENTS.MD', 'CLAUDE.md', 'CLAUDE.MD',
    'SYSTEM.md', 'APPEND_SYSTEM.md',
}
DIRS = {'extensions', 'skills', 'prompts', 'themes'}
SKIP = {'node_modules', '.git', '__pycache__', '.DS_Store'}
MACHINE_KEYS = {'shellPath', 'shellCommandPrefix', 'externalEditor', 'sessionDir',
                'npmCommand', 'httpProxy'}
MAX_SIZE = 256 * 1024 * 1024


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def allowed(name):
    parts = PurePosixPath(name).parts
    return (bool(parts) and not any(p in SKIP for p in parts)
            and ((len(parts) == 1 and name in FILES)
                 or (len(parts) > 1 and parts[0] in DIRS)))


def valid_path(name):
    parts = name.split('/')
    return (not ntpath.splitdrive(name)[0] and '\\' not in name
            and all(p not in ('', '.', '..') and ':' not in p for p in parts)
            and not any(p.endswith((' ', '.')) for p in parts)
            and not any(p.split('.')[0].upper() in
                        {'CON', 'PRN', 'AUX', 'NUL', *('COM%d' % n for n in range(1, 10)),
                         *('LPT%d' % n for n in range(1, 10))} for p in parts))


def collect(agent, portable):
    result = {}
    candidates = []
    # Use actual directory entries to avoid case-insensitive filename aliases.
    for path in sorted(agent.iterdir(), key=lambda p: p.name):
        name = path.name
        if name not in FILES | DIRS:
            continue
        if path.is_symlink():
            raise ValueError('Symlink not supported: %s (copy actual resources here first)' % path)
        if path.is_file():
            candidates.append(path)
        elif path.is_dir() and name in DIRS:
            for base, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = sorted(d for d in dirs if d not in SKIP)
                for entry in dirs + files:
                    p = Path(base) / entry
                    if p.is_symlink() and entry not in SKIP:
                        raise ValueError('Symlink not supported: %s' % p)
                candidates.extend(Path(base) / f for f in sorted(files) if f not in SKIP)
    for path in candidates:
        name = path.relative_to(agent).as_posix()
        if not valid_path(name) or not allowed(name):
            raise ValueError('Non-portable resource path: ' + name)
        data = path.read_bytes()
        if name == 'settings.json' and portable:
            settings = json.loads(data)
            if not isinstance(settings, dict):
                raise ValueError('settings.json must contain an object')
            removed = sorted(MACHINE_KEYS & settings.keys())
            for key in removed:
                del settings[key]
            if removed:
                print('Omitted machine-specific settings: ' + ', '.join(removed))
            data = (json.dumps(settings, ensure_ascii=False, indent=2) + '\n').encode()
        result[name] = (data, stat.S_IMODE(path.stat().st_mode) & 0o777)
    if sum(len(data) for data, _ in result.values()) > MAX_SIZE:
        raise ValueError('Configuration exceeds 256 MiB limit')
    return result


def save_archive(output, entries):
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError('Refusing to overwrite archive: ' + str(output))
    manifest = {'format': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'mode': mode}
                          for name, (data, mode) in entries.items()}}
    fd, temp = tempfile.mkstemp(dir=output.parent, prefix='.pi-backup-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('manifest.json', json.dumps(manifest, indent=2))
                for name, (data, _) in sorted(entries.items()):
                    archive.writestr('agent/' + name, data)
        os.replace(temp, output)
        output.chmod(0o600)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    print('Archive: %s (%d files)' % (output, len(entries)))


def load_archive(path):
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or sum(i.file_size for i in infos) > MAX_SIZE:
            raise ValueError('Duplicate entries or archive exceeds 256 MiB limit')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format') != 1 or not isinstance(manifest.get('files'), dict):
            raise ValueError('Unsupported backup format')
        if set(names) != {'manifest.json', *('agent/' + n for n in manifest['files'])}:
            raise ValueError('Unexpected archive entries')
        entries = {}
        case_names = set()
        for name, meta in manifest['files'].items():
            if not valid_path(name) or not allowed(name) or name.casefold() in case_names:
                raise ValueError('Unsafe or case-colliding archive path: ' + name)
            case_names.add(name.casefold())
            data = archive.read('agent/' + name)
            if hashlib.sha256(data).hexdigest() != meta['sha256']:
                raise ValueError('Checksum mismatch: ' + name)
            mode = meta.get('mode', 0o600)
            if not isinstance(mode, int) or not 0 <= mode <= 0o777:
                raise ValueError('Invalid permissions: ' + name)
            entries[name] = (data, mode)
        return entries


def target_for(agent, name):
    target = agent.joinpath(*name.split('/'))
    for part in [target, *target.parents]:
        if part.is_symlink():
            raise ValueError('Refusing symlink destination: ' + str(part))
    if target.exists() and not target.is_file():
        raise ValueError('Destination is not a file: ' + str(target))
    for parent in target.parents:
        if parent.exists() and not parent.is_dir():
            raise ValueError('Destination parent is not a directory: ' + str(parent))
    return target


def put(target, data, mode):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix='.pi-restore-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.chmod(temp, mode)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def restore(args, agent):
    # Resolve the selected root (macOS /var and /tmp are system symlinks).
    # Resource paths below this root must still never traverse symlinks.
    agent = agent.resolve()
    entries = load_archive(args.archive)
    targets = {name: target_for(agent, name) for name in entries}
    print('Destination: ' + str(agent))
    for name in sorted(entries):
        print(('overwrite ' if targets[name].exists() else 'create    ') + name)
    print('Other files, credentials and sessions are left untouched.')
    if args.dry_run:
        return
    if not args.yes and input('Restore these files? [y/N] ').strip().lower() != 'y':
        print('Cancelled.')
        return
    previous = {name: (target.read_bytes(), stat.S_IMODE(target.stat().st_mode) & 0o777)
                for name, target in targets.items() if target.exists()}
    rollback = args.rollback_dir / ('before-restore-' + stamp() + '.zip')
    save_archive(rollback, previous)
    changed = []
    try:
        for name, (data, mode) in entries.items():
            put(targets[name], data, mode)
            changed.append(name)
    except Exception:
        for name in reversed(changed):
            if name in previous:
                put(targets[name], *previous[name])
            else:
                targets[name].unlink()
        raise
    print('Restored. Restart Pi, log in on this machine, then run pi update --extensions.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent-dir', type=Path,
                        default=Path(os.environ.get('PI_CODING_AGENT_DIR', '~/.pi/agent')).expanduser())
    sub = parser.add_subparsers(dest='command', required=True)
    backup = sub.add_parser('backup')
    backup.add_argument('--output', type=Path)
    backup.add_argument('--keep-machine-settings', action='store_true')
    restore_parser = sub.add_parser('restore')
    restore_parser.add_argument('--archive', type=Path, required=True)
    restore_parser.add_argument('--yes', action='store_true')
    restore_parser.add_argument('--dry-run', action='store_true')
    restore_parser.add_argument('--rollback-dir', type=Path, default=ROOT / 'backups' / 'rollback')
    args = parser.parse_args()
    agent = args.agent_dir.expanduser().absolute()
    if args.command == 'backup':
        if not agent.is_dir():
            raise ValueError('Agent directory not found: ' + str(agent))
        entries = collect(agent, not args.keep_machine_settings)
        if not entries:
            raise ValueError('No configuration files found')
        # Check portability and path collisions before publishing the archive.
        if len({n.casefold() for n in entries}) != len(entries):
            raise ValueError('Case-colliding filenames cannot be shared across OSes')
        save_archive(args.output or ROOT / 'backups' / ('pi-config-' + stamp() + '.zip'), entries)
        print('Warning: models.json, mcp.json and custom resources may contain secrets. Review before sharing.')
    else:
        restore(args, agent)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, EOFError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        sys.exit(1)
