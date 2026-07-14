#!/usr/bin/python3

import os
from pathlib import Path

IS_FLATPAK = 'FLATPAK_ID' in os.environ or os.path.exists('/.flatpak-info')

faugus_source_root = str(Path(__file__).resolve().parent.parent)


def subprocess_env():
    env = os.environ.copy()
    existing = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = faugus_source_root + (os.pathsep + existing if existing else '')
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
        source_path = os.path.join(faugus_source_root, 'assets', filename)
        if os.path.exists(source_path):
            return source_path
        return PathManager.system_data('faugus-launcher', filename)

    @staticmethod
    def get_icon(icon_name):
        icon_paths = [
            os.path.join(faugus_source_root, 'assets', icon_name),
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


lsfgvk_flatpak_paths = [
    Path("/usr/lib/extensions/vulkan/lsfgvk/lib/liblsfg-vk.so"),
    Path(os.path.expanduser('~/.local/lib/liblsfg-vk.so')),
    Path("/usr/lib/extensions/vulkan/lsfgvk/lib/liblsfg-vk-layer.so"),
    Path(os.path.expanduser('~/.local/lib/liblsfg-vk-layer.so')),
]
lsfgvk_native_paths = [
    Path("/usr/lib/liblsfg-vk.so"),
    Path("/usr/lib64/liblsfg-vk.so"),
    Path("/usr/local/lib/liblsfg-vk.so"),
    Path(os.path.expanduser('~/.local/lib/liblsfg-vk.so')),
    Path("/usr/lib/liblsfg-vk-layer.so"),
    Path("/usr/lib64/liblsfg-vk-layer.so"),
    Path(os.path.expanduser('~/.local/lib/liblsfg-vk-layer.so')),
]

_lsfgvk_candidates = lsfgvk_flatpak_paths if IS_FLATPAK else lsfgvk_native_paths
lsfgvk_path = next((p for p in _lsfgvk_candidates if p.exists()), _lsfgvk_candidates[-1])

faugus_png = PathManager.get_icon('io.github.Faugus.faugus-launcher.svg') if IS_FLATPAK else PathManager.get_icon('faugus-launcher.svg')

faugus_notification = PathManager.get_asset('faugus-notification.ogg')
faugus_banner = PathManager.get_asset('faugus-banner.png')
faugus_png_raster = PathManager.get_asset('faugus-launcher-raster.png')
banners_dir = PathManager.user_data('faugus-launcher/banners')
backup_dir = PathManager.user_data("faugus-launcher/games-backup")
faugus_mono_icon = PathManager.get_icon('faugus-mono.svg')
eac_dir = PathManager.user_data("faugus-launcher/components/eac")
be_dir = PathManager.user_data("faugus-launcher/components/be")
DOWNLOAD_DIR = PathManager.user_data('faugus-launcher/components')
shortcut_icons_dir = PathManager.user_data('faugus-launcher/icons-nolauncher')
faugus_launcher_dir = PathManager.user_config('faugus-launcher')
prefixes_dir = PathManager.user_home('Faugus')
config_file_dir = PathManager.user_config('faugus-launcher/config.ini')
logs_dir = PathManager.user_data('faugus-launcher/logs')
envar_dir = PathManager.user_config('faugus-launcher/envar.txt')
games_json = PathManager.user_data('faugus-launcher/games.json')
presets_file = PathManager.user_data('faugus-launcher/presets.json')
latest_games = PathManager.user_state('faugus-launcher/latest-games.txt')
categories_file = PathManager.user_data('faugus-launcher/categories.txt')
custom_order = PathManager.user_data('faugus-launcher/custom-order.json')
faugus_launcher_share_dir = PathManager.user_data('faugus-launcher')
faugus_launcher_state_dir = PathManager.user_state('faugus-launcher')
faugus_temp = PathManager.user_state('faugus-launcher/faugus_temp')
running_games = PathManager.user_state('faugus-launcher/running_games.json')
icons_dir = PathManager.user_data('faugus-launcher/icons')
proton_cachyos = PathManager.system_data('steam/compatibilitytools.d/proton-cachyos-slr/')
umu_run = PathManager.user_data('faugus-launcher/umu-run')
compatibility_dir = Path(PathManager.get_compatibilitytools())
mangohud_dir = PathManager.find_binary('mangohud')
gamemoderun = PathManager.find_binary('gamemoderun')
launcher_path = PathManager.find_binary('faugus-launcher')
app_dir = Path(PathManager.get_applications())
desktop_dir = PathManager.user_desktop()

BACKUP_ITEMS = {
    "banners": banners_dir,
    "games-backup": backup_dir,
    "icons": icons_dir,
    "config.ini": config_file_dir,
    "envar.txt": envar_dir,
    "games.json": games_json,
    "latest-games.txt": latest_games,
    "categories.txt": categories_file,
    "custom-order.json": custom_order,
    "presets.json": presets_file,
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

    for name in ('games.json', 'icons', 'icons-nolauncher', 'banners',
                 'games-backup', 'categories.txt', 'custom-order.json',
                 'presets.json', 'logs', 'components'):
        _migrate_legacy_item(
            os.path.join(legacy_config, name),
            os.path.join(faugus_launcher_share_dir, name),
        )

    _migrate_legacy_item(
        os.path.join(legacy_config, 'latest-games.txt'),
        latest_games,
    )

    for name in ('running_games.json', 'faugus_temp'):
        _migrate_legacy_item(
            os.path.join(legacy_data, name),
            os.path.join(faugus_launcher_state_dir, name),
        )


_migrate_legacy_paths()
