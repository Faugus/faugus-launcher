from faugus.language_config import *
from faugus.utils import atomic_write, load_json_file, save_json_file


class ConfigManager:
    def __init__(self):
        self.default_config = {
            'auto-close-on-launch': 'False',
            'default-prefix': PREFIXES_DIR,
            'mangohud': 'False',
            'gamemode': 'False',
            'sdl-enabled': 'False',
            'no-sleep-enabled': 'False',
            'default-runner': 'Proton-CachyOS Latest',
            'lossless-location': '',
            'discrete-gpu': 'False',
            'splash-window-enabled': 'True',
            'system-tray': 'False',
            'autostart-enabled': 'False',
            'mono-icon': 'False',
            'interface-mode': 'List',
            'labels-enabled': 'False',
            'logging-enabled': 'False',
            'wayland-driver': 'False',
            'wow64-enabled': 'False',
            'language': lang,
            'logging-warning': 'False',
            'show-hidden': 'False',
            'automatic-updates': 'True',
            'show-donate': 'True',
            'donate-last': '',
            'playtime': 0,
            'gamepad-navigation': 'False',
            'minimized-startup-enabled': 'False',
            'categories-and-sort-enabled': 'False',
            'backup-auto-enabled': 'False',
            'backup-frequency': 'daily',
            'backup-target-day': '0',
            'backup-dest-dir': '',
            'backup-last-date': '',
            'startup-window-size': 'None',
            'interface-theme': 'system',
            'accent-color': 'system',
            'steamgriddb-api-key': '',
            'background-mode': 'default',
            'banner-enabled': 'True',
            'width': '1280',
            'height': '720',
            'cover-size': '100',
            'sort': 'alpha',
            'category': 'all',
            'steam-user': 'all',
        }

        self.config = {}
        self.load_config()

    def load_config(self):
        self.config = load_json_file(CONFIG_FILE_DIR, default={})

        updated = False
        for key, default_value in self.default_config.items():
            if key not in self.config:
                self.config[key] = default_value
                updated = True

        if updated or not os.path.isfile(CONFIG_FILE_DIR):
            self.save_config()

    def save_config(self):
        save_json_file(self.config, CONFIG_FILE_DIR)

    def set_value(self, key, value):
        if key not in self.default_config:
            return

        self.config[key] = str(value)
