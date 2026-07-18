import os
import shlex
import shutil
import tempfile
from datetime import date
from pathlib import Path

import vdf

from faugus.path_manager import PathManager, APP_DIR, DESKTOP_DIR, ICONS_DIR, SHORTCUT_ICONS_DIR, COVERS_DIR, BANNERS_DIR, GAMES_JSON, CONFIG_FILE_DIR, FILECHOOSER_FOLDERS_FILE, FAUGUS_LAUNCHER_DIR, FAUGUS_LAUNCHER_SHARE_DIR, FAUGUS_LAUNCHER_STATE_DIR

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


def _rewrite_desktop_lines(lines):
    changed = False
    new_lines = list(lines)
    for i, line in enumerate(new_lines):
        if line.startswith('Icon='):
            new_value = _rewrite_icon_path(line[len('Icon='):].rstrip('\n'))
            if new_value is not None:
                new_lines[i] = f'Icon={new_value}\n'
                changed = True
    return changed, new_lines


def _fix_desktop_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except OSError:
        return

    changed, new_lines = _rewrite_desktop_lines(lines)

    if changed:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
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
        return False
    if not new_path.exists():
        shutil.move(str(old_path), str(new_path))
        return True
    moved = False
    for entry in old_path.iterdir():
        target = new_path / entry.name
        if not target.exists():
            shutil.move(str(entry), str(target))
            moved = True
    try:
        old_path.rmdir()
    except OSError:
        pass
    return moved


def _migrate_artwork_directories():
    legacy_banners = PathManager.user_config('faugus-launcher/banners')
    legacy_heroes_config = PathManager.user_config('faugus-launcher/heroes')
    legacy_heroes_data = PathManager.user_data('faugus-launcher/heroes')
    migrated = False
    migrated |= _migrate_artwork_directory(legacy_banners, COVERS_DIR)
    migrated |= _migrate_artwork_directory(legacy_heroes_config, BANNERS_DIR)
    migrated |= _migrate_artwork_directory(legacy_heroes_data, BANNERS_DIR)
    return migrated


def _migrate_games_json_fields():
    from faugus.utils import load_json_file, save_json_file

    games = load_json_file(GAMES_JSON, None)
    if games is None:
        return

    field_renames = {
        "banner": "cover",
        "disable_hidraw": "sdl_enabled",
        "prevent_sleep": "no_sleep",
        "pre_launch_command": "pre_launch",
        "post_launch_command": "post_launch",
        "addapp_checkbox": "addapp_enabled",
    }

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


def _migrate_filechooser_folder_keys():
    from faugus.utils import load_json_file, save_json_file

    folders = load_json_file(FILECHOOSER_FOLDERS_FILE, None)
    if folders is None:
        return

    key_renames = {"pre_launch_command": "pre_launch", "post_launch_command": "post_launch"}

    changed = False
    for old_key, new_key in key_renames.items():
        if old_key in folders:
            folders[new_key] = folders.pop(old_key)
            changed = True

    if changed:
        save_json_file(folders, FILECHOOSER_FOLDERS_FILE)


def _collect_desktop_backups():
    entries = []
    for directory, subdir in ((DESKTOP_DIR, "desktop-shortcuts"), (APP_DIR, "appmenu-shortcuts")):
        d = Path(directory)
        if not d.is_dir():
            continue
        for entry in d.glob('*.desktop'):
            entries.append((entry, subdir, entry.name))
    return entries


def _collect_steam_shortcut_backups():
    from faugus.steam_setup import get_all_shortcut_paths

    entries = []
    for path in get_all_shortcut_paths():
        path = Path(path)
        if path.exists():
            account_id = path.parent.parent.name
            entries.append((path, "steam-shortcuts", f"{account_id}-shortcuts.vdf"))
    return entries


def _restore_action_dir(original, backup_rel):
    quoted_dir = shlex.quote(original)
    quoted_src = shlex.quote('/' + backup_rel)
    return (
        f'DIR={quoted_dir}\n'
        f'if [ -L "$DIR" ]; then DIR=$(readlink -f "$DIR"); fi\n'
        f'if [ -d "$DIR" ]; then find "$DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {{}} +; else mkdir -p "$DIR"; fi\n'
        f'cp -a "$SCRIPT_DIR"{quoted_src}/. "$DIR/"\n'
        f'printf \'Restored %s\\n\' {quoted_dir}'
    )


def _restore_action_file(original, backup_rel):
    quoted_dst = shlex.quote(original)
    quoted_dst_dir = shlex.quote(os.path.dirname(original))
    quoted_src = shlex.quote('/' + backup_rel)
    return (
        f'mkdir -p {quoted_dst_dir}\n'
        f'cp -a "$SCRIPT_DIR"{quoted_src} {quoted_dst}\n'
        f'printf \'Restored %s\\n\' {quoted_dst}'
    )


def _clear_action(original):
    quoted_dir = shlex.quote(original)
    return (
        f'DIR={quoted_dir}\n'
        f'if [ -L "$DIR" ]; then DIR=$(readlink -f "$DIR"); fi\n'
        f'if [ -d "$DIR" ]; then find "$DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {{}} +; else mkdir -p "$DIR"; fi\n'
        f'printf \'Cleared %s\\n\' {quoted_dir}'
    )


def _build_restore_script(dir_snapshots, file_snapshots, clear_only_dirs):
    preview = []
    actions = []

    for entry in dir_snapshots:
        preview.append(f'printf \'  %s\\n\' {shlex.quote(entry["original"] + "/")}')
        actions.append(_restore_action_dir(entry["original"], entry["backup"]))

    for entry in file_snapshots:
        preview.append(f'printf \'  %s\\n\' {shlex.quote(entry["original"])}')
        actions.append(_restore_action_file(entry["original"], entry["backup"]))

    for original in clear_only_dirs:
        preview.append(f'printf \'  %s (cleared)\\n\' {shlex.quote(original + "/")}')
        actions.append(_clear_action(original))

    preview_block = "\n".join(preview)
    actions_block = "\n\n".join(actions)

    return f'''#!/bin/sh
set -e

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

echo "This restores Faugus Launcher's data to exactly how it was"
echo "before the migration ran, replacing the current contents of:"
{preview_block}

printf 'Proceed? [y/N] '
read ANSWER
case "$ANSWER" in
    y|Y) ;;
    *) echo "Cancelled."; exit 0 ;;
esac

{actions_block}

echo "Done. Restart Faugus Launcher for the changes to take effect."
'''


def _backup_before_migration():
    backup_root = Path(PathManager.user_home('Faugus Backup'))
    zip_path = backup_root / f"faugus-migration-backup-{date.today().isoformat()}.zip"
    if zip_path.exists():
        return

    staging_dir = Path(tempfile.mkdtemp(prefix="faugus-migration-backup-"))

    dir_snapshots = []
    for label, src in (
        ("config", FAUGUS_LAUNCHER_DIR),
        ("data", FAUGUS_LAUNCHER_SHARE_DIR),
    ):
        real_src = os.path.realpath(src) if os.path.islink(src) else src
        if os.path.isdir(real_src):
            shutil.copytree(real_src, staging_dir / label)
            dir_snapshots.append({"backup": label, "original": str(src)})

    file_snapshots = []
    for src_path, subdir, basename in _collect_desktop_backups() + _collect_steam_shortcut_backups():
        target_dir = staging_dir / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        backup_path = target_dir / basename
        shutil.copy2(src_path, backup_path)
        file_snapshots.append({"backup": str(backup_path.relative_to(staging_dir)), "original": str(src_path)})

    script_text = _build_restore_script(dir_snapshots, file_snapshots, [str(FAUGUS_LAUNCHER_STATE_DIR)])
    restore_script = staging_dir / "restore.sh"
    restore_script.write_text(script_text, encoding="utf-8")
    restore_script.chmod(0o755)

    backup_root.mkdir(parents=True, exist_ok=True)
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", root_dir=str(staging_dir))
    shutil.rmtree(staging_dir)


def fix_legacy_shortcut_icons():
    artwork_migrated = False

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
        artwork_migrated = _migrate_artwork_directories()
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
    try:
        _migrate_filechooser_folder_keys()
    except Exception:
        pass

    return artwork_migrated
