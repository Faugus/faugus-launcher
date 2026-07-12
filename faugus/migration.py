import os
from pathlib import Path

import vdf

from faugus.path_manager import PathManager, app_dir, desktop_dir, icons_dir, shortcut_icons_dir

_LEGACY_ICON_BASES = (
    PathManager.user_config('faugus-launcher/icons'),
    PathManager.user_config('faugus-launcher/icons-nolauncher'),
)
_NEW_ICON_BASES = (icons_dir, shortcut_icons_dir)


def _rewrite_icon_path(value):
    if not value:
        return None
    for old_base, new_base in zip(_LEGACY_ICON_BASES, _NEW_ICON_BASES):
        if value == old_base:
            return new_base
        if value.startswith(old_base + os.sep):
            return new_base + value[len(old_base):]
    return None


def _fix_desktop_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except OSError:
        return

    changed = False
    for i, line in enumerate(lines):
        if line.startswith('Icon='):
            new_value = _rewrite_icon_path(line[len('Icon='):].rstrip('\n'))
            if new_value is not None:
                lines[i] = f'Icon={new_value}\n'
                changed = True

    if changed:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
        except OSError:
            pass


def _fix_desktop_shortcuts():
    for directory in (app_dir, desktop_dir):
        d = Path(directory)
        if not d.is_dir():
            continue
        for entry in d.glob('*.desktop'):
            _fix_desktop_file(entry)


def _fix_steam_shortcuts():
    from faugus.steam_setup import get_all_shortcut_paths

    for path in get_all_shortcut_paths():
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'rb') as f:
                shortcuts = vdf.binary_load(f)
        except (SyntaxError, OSError):
            continue

        if "shortcuts" not in shortcuts:
            continue

        changed = False
        for game_info in shortcuts["shortcuts"].values():
            if not isinstance(game_info, dict):
                continue
            new_value = _rewrite_icon_path(game_info.get("icon"))
            if new_value is not None:
                game_info["icon"] = new_value
                changed = True

        if changed:
            try:
                with open(path, 'wb') as f:
                    vdf.binary_dump(shortcuts, f)
            except OSError:
                pass


def fix_legacy_shortcut_icons():
    try:
        _fix_desktop_shortcuts()
    except Exception:
        pass
    try:
        _fix_steam_shortcuts()
    except Exception:
        pass
