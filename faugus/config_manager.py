from faugus.language_config import *
from faugus.utils import atomic_write, load_json_file, save_json_file


class ConfigManager:
    def __init__(self):
        self.default_config = {
            'close-onlaunch': 'False',
            'default-prefix': PREFIXES_DIR,
            'mangohud': 'False',
            'gamemode': 'False',
            'disable-hidraw': 'False',
            'prevent-sleep': 'False',
            'default-runner': 'Proton-CachyOS Latest',
            'lossless-location': '',
            'discrete-gpu': 'False',
            'splash-disable': 'False',
            'system-tray': 'False',
            'start-boot': 'False',
            'mono-icon': 'False',
            'interface-mode': 'List',
            'show-labels': 'False',
            'enable-logging': 'False',
            'wayland-driver': 'False',
            'enable-wow64': 'False',
            'language': lang,
            'logging-warning': 'False',
            'show-hidden': 'False',
            'disable-updates': 'False',
            'show-donate': 'True',
            'donate-last': '',
            'playtime': 0,
            'gamepad-navigation': 'False',
            'start-minimized': 'False',
            'show-categories': 'False',
            'backup-auto-enabled': 'False',
            'backup-frequency': 'daily',
            'backup-target-day': '0',
            'backup-dest-dir': '',
            'backup-last-date': '',
            'window-behavior': 'None',
            'interface-theme': 'system',
            'accent-color': 'system',
            'steamgriddb-api-key': '',
            'background-mode': 'default',
            'hero-enabled': 'True',
            'width': '1280',
            'height': '720',
            'banner-size': '100',
            'sort': 'alpha',
            'category': 'all',
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
