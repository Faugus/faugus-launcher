import os
import shutil
from pathlib import Path

import vdf

from faugus.path_manager import PathManager, APP_DIR, DESKTOP_DIR, ICONS_DIR, SHORTCUT_ICONS_DIR, COVERS_DIR, BANNERS_DIR, GAMES_JSON, CONFIG_FILE_DIR

_LEGACY_ICON_BASES = (
    PathManager.user_config('faugus-launcher/icons'),
    PathManager.user_config('faugus-launcher/icons-nolauncher'),
)
_NEW_ICON_BASES = (ICONS_DIR, SHORTCUT_ICONS_DIR)


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
    for directory in (APP_DIR, DESKTOP_DIR):
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


def _migrate_artwork_directory(old_dir, new_dir):
    old_path = Path(old_dir)
    new_path = Path(new_dir)
    if not old_path.is_dir() or old_path == new_path:
        return
    if not new_path.exists():
        old_path.rename(new_path)
        return
    for entry in old_path.iterdir():
        target = new_path / entry.name
        if not target.exists():
            shutil.move(str(entry), str(target))
    try:
        old_path.rmdir()
    except OSError:
        pass


def _migrate_artwork_directories():
    legacy_banners = PathManager.user_data('faugus-launcher/banners')
    legacy_heroes = PathManager.user_data('faugus-launcher/heroes')
    _migrate_artwork_directory(legacy_banners, COVERS_DIR)
    _migrate_artwork_directory(legacy_heroes, BANNERS_DIR)


def _migrate_games_json_fields():
    from faugus.utils import load_json_file, save_json_file

    games = load_json_file(GAMES_JSON, None)
    if games is None:
        return

    field_renames = {"banner": "cover", "disable_hidraw": "sdl_enabled", "prevent_sleep": "no_sleep"}

    changed = False
    for game in games:
        if not isinstance(game, dict):
            continue
        for old_field, new_field in field_renames.items():
            if old_field in game:
                game[new_field] = game.pop(old_field)
                changed = True

    if changed:
        save_json_file(games, GAMES_JSON)


def _migrate_config_json_values():
    from faugus.utils import load_json_file, save_json_file

    config = load_json_file(CONFIG_FILE_DIR, None)
    if config is None:
        return

    changed = False

    mode_renames = {"Blocks": "Grid", "Banners": "Covers"}
    mode = config.get('interface-mode')
    if mode in mode_renames:
        config['interface-mode'] = mode_renames[mode]
        changed = True

    key_renames = {
        "hero-enabled": "banner-enabled",
        "banner-size": "cover-size",
        "disable-hidraw": "sdl-enabled",
        "prevent-sleep": "no-sleep-enabled",
        "close-onlaunch": "auto-close-on-launch",
        "show-labels": "labels-enabled",
        "enable-logging": "logging-enabled",
        "start-boot": "autostart-enabled",
        "start-minimized": "minimized-startup-enabled",
        "show-categories": "categories-and-sort-enabled",
        "enable-wow64": "wow64-enabled",
        "window-behavior": "startup-window-size",
    }
    for old_key, new_key in key_renames.items():
        if old_key in config:
            config[new_key] = config.pop(old_key)
            changed = True

    inverted_key_renames = {"splash-disable": "splash-window-enabled", "disable-updates": "automatic-updates"}
    for old_key, new_key in inverted_key_renames.items():
        if old_key in config:
            old_value = config.pop(old_key)
            config[new_key] = 'False' if old_value == 'True' else 'True'
            changed = True

    if changed:
        save_json_file(config, CONFIG_FILE_DIR)


def fix_legacy_shortcut_icons():
    try:
        _fix_desktop_shortcuts()
    except Exception:
        pass
    try:
        _fix_steam_shortcuts()
    except Exception:
        pass
    try:
        from faugus.utils import update_games_json
        update_games_json()
    except Exception:
        pass
    try:
        _migrate_artwork_directories()
    except Exception:
        pass
    try:
        _migrate_games_json_fields()
    except Exception:
        pass
    try:
        _migrate_config_json_values()
    except Exception:
        pass
