#!/usr/bin/python3

import json
import os
import sys
from pathlib import Path

IS_FLATPAK = 'FLATPAK_ID' in os.environ or os.path.exists('/.flatpak-info')

FAUGUS_SOURCE_ROOT = str(Path(__file__).resolve().parent.parent)


def subprocess_env():
    env = os.environ.copy()
    existing = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = FAUGUS_SOURCE_ROOT + (os.pathsep + existing if existing else '')
    return env


class PathManager:
    @staticmethod
    def user_home(*relative_paths):
        if IS_FLATPAK:
            home_dir = Path(os.getenv('HOST_HOME', Path.home()))
        else:
            home_dir = Path(os.getenv('HOME', Path.home()))
        return str(home_dir.joinpath(*relative_paths))

    @staticmethod
    def system_data(*relative_paths):
        xdg_data_dirs = os.getenv('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':')
        for data_dir in xdg_data_dirs:
            path = Path(data_dir).joinpath(*relative_paths)
            if path.exists():
                return str(path)
        return str(Path(xdg_data_dirs[0]).joinpath(*relative_paths))

    @staticmethod
    def user_data(*relative_paths):
        xdg_data_home = Path(os.getenv('XDG_DATA_HOME', Path.home() / '.local/share'))
        return str(xdg_data_home.joinpath(*relative_paths))

    @staticmethod
    def user_config(*relative_paths):
        xdg_config_home = Path(os.getenv('XDG_CONFIG_HOME', Path.home() / '.config'))
        return str(xdg_config_home.joinpath(*relative_paths))

    @staticmethod
    def user_state(*relative_paths):
        xdg_state_home = Path(os.getenv('XDG_STATE_HOME', Path.home() / '.local/state'))
        return str(xdg_state_home.joinpath(*relative_paths))

    @staticmethod
    def find_binary(binary_name):
        paths = os.getenv('PATH', '').split(':')
        for path in paths:
            binary_path = Path(path) / binary_name
            if binary_path.exists():
                return str(binary_path)
        return ""

    @staticmethod
    def get_asset(filename):
        source_path = os.path.join(FAUGUS_SOURCE_ROOT, 'assets', filename)
        if os.path.exists(source_path):
            return source_path
        return PathManager.system_data('faugus-launcher', filename)

    @staticmethod
    def get_icon(icon_name):
        icon_paths = [
            os.path.join(FAUGUS_SOURCE_ROOT, 'assets', icon_name),
            PathManager.user_data('icons', icon_name),
            PathManager.system_data('icons/hicolor/scalable/actions', icon_name),
            PathManager.system_data('icons/hicolor/scalable/apps', icon_name),
            PathManager.system_data('icons', icon_name)
        ]
        for path in icon_paths:
            if Path(path).exists():
                return path
        return icon_paths[-1]

    @staticmethod
    def get_compatibilitytools():
        base_dir = Path(os.getenv('HOST_XDG_DATA_HOME', Path.home() / '.local' / 'share'))
        compatibilitytools_folder = base_dir / 'Steam' / 'compatibilitytools.d'
        return str(compatibilitytools_folder)

    @staticmethod
    def get_applications():
        base_dir = Path(os.getenv('HOST_XDG_DATA_HOME', Path.home() / '.local' / 'share'))
        compatibilitytools_folder = base_dir / 'applications'
        return str(compatibilitytools_folder)

    @staticmethod
    def user_desktop():
        config_file = Path(PathManager.user_config('user-dirs.dirs'))

        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('XDG_DESKTOP_DIR='):
                        value = line.split('=', 1)[1].strip().strip('"')

                        if value.startswith('$HOME/'):
                            relative_path = value.replace('$HOME/', '')
                            return PathManager.user_home(relative_path)
                        elif value == '$HOME':
                            return PathManager.user_home()

                        return value

        return PathManager.user_home('Desktop')


LSFGVK_FLATPAK_PATHS = [
    Path("/usr/lib/extensions/vulkan/lsfgvk/lib/liblsfg-vk.so"),
    Path(os.path.expanduser('~/.local/lib/liblsfg-vk.so')),
    Path("/usr/lib/extensions/vulkan/lsfgvk/lib/liblsfg-vk-layer.so"),
    Path(os.path.expanduser('~/.local/lib/liblsfg-vk-layer.so')),
]
LSFGVK_NATIVE_PATHS = [
    Path("/usr/lib/liblsfg-vk.so"),
    Path("/usr/lib64/liblsfg-vk.so"),
    Path("/usr/local/lib/liblsfg-vk.so"),
    Path(os.path.expanduser('~/.local/lib/liblsfg-vk.so')),
    Path("/usr/lib/liblsfg-vk-layer.so"),
    Path("/usr/lib64/liblsfg-vk-layer.so"),
    Path(os.path.expanduser('~/.local/lib/liblsfg-vk-layer.so')),
]

_LSFGVK_CANDIDATES = LSFGVK_FLATPAK_PATHS if IS_FLATPAK else LSFGVK_NATIVE_PATHS
LSFGVK_PATH = next((p for p in _LSFGVK_CANDIDATES if p.exists()), _LSFGVK_CANDIDATES[-1])

FAUGUS_PNG = PathManager.get_icon('io.github.Faugus.faugus-launcher.svg') if IS_FLATPAK else PathManager.get_icon('faugus-launcher.svg')

FAUGUS_NOTIFICATION = PathManager.get_asset('faugus-notification.ogg')
FAUGUS_PNG_RASTER = PathManager.get_asset('faugus-launcher-raster.png')
COVERS_DIR = PathManager.user_data('faugus-launcher/covers')
BANNERS_DIR = PathManager.user_data('faugus-launcher/banners')
BACKUP_DIR = PathManager.user_data("faugus-launcher/games-backup")
FAUGUS_MONO_ICON = PathManager.get_icon('faugus-mono.svg')
EAC_DIR = PathManager.user_data("faugus-launcher/components/eac")
BE_DIR = PathManager.user_data("faugus-launcher/components/be")
DOWNLOAD_DIR = PathManager.user_data('faugus-launcher/components')
SHORTCUT_ICONS_DIR = PathManager.user_data('faugus-launcher/icons-nolauncher')
FAUGUS_LAUNCHER_DIR = PathManager.user_config('faugus-launcher')
PREFIXES_DIR = PathManager.user_home('Faugus')
CONFIG_FILE_DIR = PathManager.user_config('faugus-launcher/config.json')
LOGS_DIR = PathManager.user_data('faugus-launcher/logs')
ENVAR_DIR = PathManager.user_config('faugus-launcher/envar.json')
GAMES_JSON = PathManager.user_data('faugus-launcher/games.json')
PRESETS_FILE = PathManager.user_data('faugus-launcher/presets.json')
LATEST_GAMES = PathManager.user_state('faugus-launcher/latest-games.json')
CATEGORIES_FILE = PathManager.user_data('faugus-launcher/categories.json')
CUSTOM_ORDER = PathManager.user_data('faugus-launcher/custom-order.json')
FAUGUS_LAUNCHER_SHARE_DIR = PathManager.user_data('faugus-launcher')
FAUGUS_LAUNCHER_STATE_DIR = PathManager.user_state('faugus-launcher')
FAUGUS_TEMP = PathManager.user_state('faugus-launcher/faugus_temp')
RUNNING_GAMES = PathManager.user_state('faugus-launcher/running-games.json')
FILECHOOSER_FOLDERS_FILE = PathManager.user_state('faugus-launcher/filechooser_folders.json')
ICONS_DIR = PathManager.user_data('faugus-launcher/icons')
PROTON_CACHYOS = PathManager.system_data('steam/compatibilitytools.d/proton-cachyos-slr/')
UMU_RUN = PathManager.user_data('faugus-launcher/umu-run')
COMPATIBILITY_DIR = Path(PathManager.get_compatibilitytools())
MANGOHUD_DIR = PathManager.find_binary('mangohud')
GAMEMODERUN = PathManager.find_binary('gamemoderun')
LAUNCHER_PATH = PathManager.find_binary('faugus-launcher')
if LAUNCHER_PATH:
    LAUNCHER_MODULE_ARGS = ""
else:
    LAUNCHER_PATH = sys.executable
    LAUNCHER_MODULE_ARGS = "-m faugus.launcher "
APP_DIR = Path(PathManager.get_applications())
DESKTOP_DIR = PathManager.user_desktop()

BACKUP_ITEMS = {
    "covers": COVERS_DIR,
    "banners": BANNERS_DIR,
    "games-backup": BACKUP_DIR,
    "icons": ICONS_DIR,
    "config.json": CONFIG_FILE_DIR,
    "envar.json": ENVAR_DIR,
    "games.json": GAMES_JSON,
    "latest-games.json": LATEST_GAMES,
    "categories.json": CATEGORIES_FILE,
    "custom-order.json": CUSTOM_ORDER,
    "presets.json": PRESETS_FILE,
    "filechooser_folders.json": FILECHOOSER_FOLDERS_FILE,
}

LEGACY_BACKUP_DIR_ITEMS = {
    "heroes": BANNERS_DIR,
}


def _migrate_legacy_item(old_path, new_path):
    old = Path(old_path)
    new = Path(new_path)
    if old == new or not old.exists() or new.exists():
        return
    try:
        new.parent.mkdir(parents=True, exist_ok=True)
        try:
            old.rename(new)
        except OSError:
            import shutil as _shutil
            _shutil.move(str(old), str(new))
    except OSError:
        pass


def _migrate_legacy_paths():
    legacy_config = PathManager.user_config('faugus-launcher')
    legacy_data = PathManager.user_data('faugus-launcher')

    for name in ('games.json', 'icons', 'icons-nolauncher', 'covers',
                 'games-backup', 'categories.txt', 'custom-order.json',
                 'presets.json', 'logs', 'components'):
        _migrate_legacy_item(
            os.path.join(legacy_config, name),
            os.path.join(FAUGUS_LAUNCHER_SHARE_DIR, name),
        )

    _migrate_legacy_item(
        os.path.join(legacy_config, 'latest-games.txt'),
        os.path.join(FAUGUS_LAUNCHER_STATE_DIR, 'latest-games.txt'),
    )

    _migrate_legacy_item(
        os.path.join(legacy_data, 'running_games.json'),
        RUNNING_GAMES,
    )
    _migrate_legacy_item(
        os.path.join(FAUGUS_LAUNCHER_STATE_DIR, 'running_games.json'),
        RUNNING_GAMES,
    )
    _migrate_legacy_item(
        os.path.join(legacy_data, 'faugus_temp'),
        os.path.join(FAUGUS_LAUNCHER_STATE_DIR, 'faugus_temp'),
    )


def _parse_kv_file(path):
    data = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f.read().splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    data[key.strip()] = value.strip().strip('"')
    except OSError:
        pass
    return data


def _parse_lines_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except OSError:
        return []


def _write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    os.replace(tmp_path, path)


LEGACY_FORMAT_ITEMS = {
    'config.ini': (CONFIG_FILE_DIR, 'kv'),
    'envar.txt': (ENVAR_DIR, 'lines'),
    'latest-games.txt': (LATEST_GAMES, 'lines'),
    'categories.txt': (CATEGORIES_FILE, 'lines'),
}


def convert_legacy_format_file(old_path, new_path, kind):
    data = _parse_kv_file(old_path) if kind == 'kv' else _parse_lines_file(old_path)
    _write_json_atomic(new_path, data)


def _migrate_legacy_formats():
    for old_name, (new_path, kind) in LEGACY_FORMAT_ITEMS.items():
        old_path = os.path.join(os.path.dirname(new_path), old_name)
        if os.path.isfile(old_path) and not os.path.isfile(new_path):
            try:
                convert_legacy_format_file(old_path, new_path, kind)
                os.remove(old_path)
            except OSError:
                pass


def _backup_before_legacy_migration():
    try:
        from faugus.migration import _backup_before_migration
        _backup_before_migration()
    except Exception:
        pass


_backup_before_legacy_migration()
_migrate_legacy_paths()
_migrate_legacy_formats()
