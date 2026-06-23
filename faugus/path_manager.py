#!/usr/bin/python3

import os
from pathlib import Path

IS_FLATPAK = 'FLATPAK_ID' in os.environ or os.path.exists('/.flatpak-info')

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
        xdg_state_home = Path(os.getenv('XDG_STATE_HOME', Path.home() / '.state'))
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
    def get_icon(icon_name):
        icon_paths = [
            PathManager.user_data('icons', icon_name),
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

faugus_launcher_dir = PathManager.user_config('faugus-launcher')
prefixes_dir = PathManager.user_home('Faugus')
config_file_dir = PathManager.user_config('faugus-launcher/config.ini')
logs_dir = PathManager.user_data('faugus-launcher/logs')
envar_dir = PathManager.user_config('faugus-launcher/envar.txt')
games_json = PathManager.user_data('faugus-launcher/games.json')
proton_cachyos = PathManager.system_data('steam/compatibilitytools.d/proton-cachyos-slr/')
umu_run = PathManager.user_data('faugus-launcher/umu-run')
compatibility_dir = Path(PathManager.get_compatibilitytools())
mangohud_dir = PathManager.find_binary('mangohud')
gamemoderun = PathManager.find_binary('gamemoderun')
launcher_path = PathManager.find_binary('faugus-launcher')
app_dir = Path(PathManager.get_applications())
desktop_dir = PathManager.user_desktop()
