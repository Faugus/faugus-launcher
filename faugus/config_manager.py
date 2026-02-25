from faugus.language_config import *

faugus_launcher_dir = PathManager.user_config('faugus-launcher')
prefixes_dir = str(Path.home() / 'Faugus')

class ConfigManager:
    def __init__(self):
        self.default_config = {
            'close-onlaunch': 'False',
            'default-prefix': prefixes_dir,
            'mangohud': 'False',
            'gamemode': 'False',
            'disable-hidraw': 'False',
            'prevent-sleep': 'False',
            'default-runner': 'GE-Proton',
            'lossless-location': '',
            'discrete-gpu': 'False',
            'splash-disable': 'False',
            'system-tray': 'False',
            'start-boot': 'False',
            'mono-icon': 'False',
            'interface-mode': 'List',
            'start-maximized': 'False',
            'start-fullscreen': 'False',
            'show-labels': 'False',
            'smaller-banners': 'False',
            'enable-logging': 'False',
            'wayland-driver': 'False',
            'enable-hdr': 'False',
            'enable-wow64': 'False',
            'language': lang,
            'logging-warning': 'False',
            'show-hidden': 'False',
            'show-donate': 'True',
            'donate-last': '',
        }

        self.config = {}
        self.load_config()

    def load_config(self):
        if os.path.isfile(config_file_dir):
            with open(config_file_dir, 'r') as f:
                for line in f.read().splitlines():
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"')
                        self.config[key] = value

        updated = False
        for key, default_value in self.default_config.items():
            if key not in self.config:
                self.config[key] = default_value
                updated = True

        if updated or not os.path.isfile(config_file_dir):
            self.save_config()

    def save_config(self):
        if not os.path.exists(faugus_launcher_dir):
            os.makedirs(faugus_launcher_dir)

        with open(config_file_dir, 'w') as f:
            for key, value in self.config.items():
                if key in ['default-prefix', 'default-runner']:
                    f.write(f'{key}="{value}"\n')
                else:
                    f.write(f'{key}={value}\n')

    def save_with_values(self, *args):
        keys = list(self.default_config.keys())
        for key, value in zip(keys, args):
            self.config[key] = str(value)
        self.save_config()

    def set_value(self, key, value):
        if key not in self.default_config:
            return

        self.config[key] = str(value)
        self.save_config()
