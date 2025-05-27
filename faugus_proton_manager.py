#!/usr/bin/env python3

import requests
import gi
import os
import tarfile
import shutil
import sys
import gettext
import locale
from pathlib import Path

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio

class PathManager:
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
    def get_icon(icon_name):
        icon_paths = [
            PathManager.user_data('icons', icon_name),
            PathManager.system_data('icons/hicolor/256x256/apps', icon_name),
            PathManager.system_data('icons', icon_name)
        ]
        for path in icon_paths:
            if Path(path).exists():
                return path
        return icon_paths[-1]  # Fallback

GITHUB_API_URL = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases"
STEAM_COMPATIBILITY_PATH = PathManager.user_data("Steam/compatibilitytools.d")

faugus_png = PathManager.get_icon('faugus-launcher.png')
config_file_dir = PathManager.user_config('faugus-launcher/config.ini')

faugus_session = False

if "session" in sys.argv:
    faugus_session = True

LOCALE_DIR = (
    PathManager.system_data('locale')
    if os.path.isdir(PathManager.system_data('locale'))
    else os.path.join(os.path.dirname(__file__), 'locale')
)

locale.setlocale(locale.LC_ALL, '')
lang = locale.getlocale()[0]
if os.path.exists(config_file_dir):
    with open(config_file_dir, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('language='):
                lang = line.split('=', 1)[1].strip()
                break
try:
    translation = gettext.translation(
        'faugus-proton-manager',
        localedir=LOCALE_DIR,
        languages=[lang]
    )
    translation.install()
    globals()['_'] = translation.gettext
except FileNotFoundError:
    gettext.install('faugus-proton-manager', localedir=LOCALE_DIR)
    globals()['_'] = gettext.gettext

class ProtonDownloader(Gtk.Dialog):
    def __init__(self):
        super().__init__(title=_("Faugus GE-Proton Manager"))
        self.set_resizable(False)
        self.set_modal(True)
        self.set_icon_from_file(faugus_png)
        if faugus_session:
            self.fullscreen()

        frame = Gtk.Frame()
        frame.set_margin_start(10)
        frame.set_margin_end(10)
        frame.set_margin_top(10)
        frame.set_margin_bottom(10)

        self.content_area = self.get_content_area()
        self.content_area.set_border_width(0)
        self.content_area.set_halign(Gtk.Align.CENTER)
        self.content_area.set_valign(Gtk.Align.CENTER)
        self.content_area.set_vexpand(True)
        self.content_area.set_hexpand(True)
        self.content_area.add(frame)

        self.progress_label = Gtk.Label(label="")
        self.progress_label.set_margin_start(10)
        self.progress_label.set_margin_end(10)
        self.progress_label.set_margin_bottom(10)
        self.content_area.add(self.progress_label)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_margin_start(10)
        self.progress_bar.set_margin_end(10)
        self.progress_bar.set_margin_bottom(10)
        self.content_area.add(self.progress_bar)

        # Scrolled window to hold the Grid
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_size_request(400, 400)
        self.scrolled_window.set_margin_start(10)
        self.scrolled_window.set_margin_end(10)
        self.scrolled_window.set_margin_top(10)
        self.scrolled_window.set_margin_bottom(10)

        # Grid for releases
        self.grid = Gtk.Grid()
        self.scrolled_window.add(self.grid)

        frame.add(self.scrolled_window)

        # Set row and column spacing
        self.grid.set_row_spacing(5)
        self.grid.set_column_spacing(10)

        self.load_config()

        # Fetch and populate releases in the Grid
        self.releases = []
        self.get_releases()
        self.show_all()
        self.progress_bar.set_visible(False)
        self.progress_label.set_visible(False)

    def load_config(self):
        config_file = config_file_dir

        if os.path.isfile(config_file):
            with open(config_file, 'r') as f:
                config_dict = {}
                for line in f.read().splitlines():
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"')
                        config_dict[key] = value

            self.language = config_dict.get('language', '')
        else:
            self.save_config(False, '', "False", "False", "False", "GE-Proton", "True", "False", "False", "False", "List", "False", "False", "False", "False", "False", "False", lang)
            self.default_runner = "GE-Proton"

    def save_config(self, checkbox_state, default_prefix, mangohud_state, gamemode_state, disable_hidraw_state, default_runner, checkbox_discrete_gpu_state, checkbox_splash_disable, checkbox_system_tray, checkbox_start_boot, combo_box_interface, checkbox_start_maximized, checkbox_start_fullscreen, checkbox_gamepad_navigation, checkbox_enable_logging, checkbox_wayland_driver, checkbox_enable_hdr, language):
        config_file = config_file_dir

        config_path = faugus_launcher_dir
        if not os.path.exists(config_path):
            os.makedirs(config_path)

        default_prefix = prefixes_dir
        self.default_prefix = prefixes_dir

        default_runner = (f'"{default_runner}"')

        config = {}

        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                for line in f:
                    key, value = line.strip().split('=', 1)
                    config[key] = value.strip('"')

        config['close-onlaunch'] = checkbox_state
        config['default-prefix'] = default_prefix
        config['mangohud'] = mangohud_state
        config['gamemode'] = gamemode_state
        config['disable-hidraw'] = disable_hidraw_state
        config['default-runner'] = default_runner
        config['discrete-gpu'] = checkbox_discrete_gpu_state
        config['splash-disable'] = checkbox_splash_disable
        config['system-tray'] = checkbox_system_tray
        config['start-boot'] = checkbox_start_boot
        config['interface-mode'] = combo_box_interface
        config['start-maximized'] = checkbox_start_maximized
        config['start-fullscreen'] = checkbox_start_fullscreen
        config['gamepad-navigation'] = checkbox_gamepad_navigation
        config['enable-logging'] = checkbox_enable_logging
        config['wayland-driver'] = checkbox_wayland_driver
        config['enable-hdr'] = checkbox_enable_hdr
        config['language'] = language

        with open(config_file, 'w') as f:
            for key, value in config.items():
                if key == 'default-prefix':
                    f.write(f'{key}="{value}"\n')
                else:
                    f.write(f'{key}={value}\n')

    def filter_releases(self):
        filtered_releases = []
        for release in self.releases:
            filtered_releases.append(release)
            if release["tag_name"] == "GE-Proton8-1":
                break
        return filtered_releases

    def get_releases(self):
        page = 1
        while True:
            response = requests.get(GITHUB_API_URL, params={"page": page, "per_page": 100})
            if response.status_code == 200:
                releases = response.json()
                if not releases:
                    break
                self.releases.extend(releases)
                page += 1
            else:
                print(_("Error fetching releases:"), response.status_code)
                break

        self.releases = self.filter_releases()

        for release in self.releases:
            self.add_release_to_grid(release)

    def add_release_to_grid(self, release):
        row_index = len(self.grid.get_children()) // 2

        label = Gtk.Label(label=release["tag_name"], xalign=0)
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        self.grid.attach(label, 0, row_index, 1, 1)

        version_path = os.path.join(STEAM_COMPATIBILITY_PATH, release["tag_name"])
        button = Gtk.Button(label=_("Remove") if os.path.exists(version_path) else _("Download"))
        button.connect("clicked", self.on_button_clicked, release)
        button.set_size_request(120, -1)

        self.grid.attach(button, 1, row_index, 1, 1)

    def on_button_clicked(self, widget, release):
        version_path = os.path.join(STEAM_COMPATIBILITY_PATH, release["tag_name"])

        if os.path.exists(version_path):
            self.on_remove_clicked(widget, release)
        else:
            self.progress_bar.set_visible(True)
            self.progress_label.set_visible(True)
            self.on_download_clicked(widget, release)

    def disable_all_buttons(self):
        for child in self.grid.get_children():
            if isinstance(child, Gtk.Button):
                child.set_sensitive(False)

    def enable_all_buttons(self):
        for child in self.grid.get_children():
            if isinstance(child, Gtk.Button):
                child.set_sensitive(True)

    def on_download_clicked(self, widget, release):
        self.disable_all_buttons()
        for asset in release["assets"]:
            if asset["name"].endswith(".tar.gz"):
                download_url = asset["browser_download_url"]
                self.download_and_extract(download_url, asset["name"], release["tag_name"], widget)
                break

    def download_and_extract(self, url, filename, tag_name, button):
        dialog = Gtk.Dialog(title=_("Downloading"), parent=self, modal=True)
        dialog.set_resizable(False)

        button.set_label(_("Downloading..."))
        self.progress_label.set_text(_("Downloading {tag}...").format(tag=tag_name))
        button.set_sensitive(False)

        if not os.path.exists(STEAM_COMPATIBILITY_PATH):
            os.makedirs(STEAM_COMPATIBILITY_PATH)

        response = requests.get(url, stream=True)
        total_size = int(response.headers.get("content-length", 0))
        downloaded_size = 0

        tar_file_path = os.path.join(os.getcwd(), filename)
        with open(tar_file_path, "wb") as file:
            for data in response.iter_content(1024):
                file.write(data)
                downloaded_size += len(data)
                progress = downloaded_size / total_size
                self.progress_bar.set_fraction(progress)
                self.progress_bar.set_text(f"{int(progress * 100)}%")
                Gtk.main_iteration_do(False)

        dialog.destroy()

        self.extract_tar_and_update_button(tar_file_path, tag_name, button)

    def extract_tar_and_update_button(self, tar_file_path, tag_name, button):
        button.set_label(_("Extracting..."))
        self.progress_label.set_text(_("Extracting {tag}...").format(tag=tag_name))
        Gtk.main_iteration_do(False)

        self.extract_tar(tar_file_path, STEAM_COMPATIBILITY_PATH, self.progress_bar)

        os.remove(tar_file_path)

        self.update_button(button, _("Remove"))
        self.progress_bar.set_visible(False)
        self.progress_label.set_visible(False)
        self.enable_all_buttons()
        button.set_sensitive(True)

    def extract_tar(self, tar_file_path, extract_to, progress_bar):
        try:
            with tarfile.open(tar_file_path, "r:gz") as tar:
                members = tar.getmembers()
                total_members = len(members)
                for index, member in enumerate(members, start=1):
                    tar.extract(member, path=extract_to)
                    progress = index / total_members
                    progress_bar.set_fraction(progress)
                    progress_bar.set_text(_("Extracting... {percent}%").format(percent=int(progress * 100)))
                    Gtk.main_iteration_do(False)
        except Exception as e:
            print(_("Failed to extract {tar_file_path}: {error}").format(tar_file_path=tar_file_path, error=e))

    def on_remove_clicked(self, widget, release):
        version_path = os.path.join(STEAM_COMPATIBILITY_PATH, release["tag_name"])
        if os.path.exists(version_path):
            try:
                shutil.rmtree(version_path)
                self.update_button(widget, _("Download"))
            except Exception as e:
                print(_("Failed to remove {version_path}: {error}").format(version_path=version_path, error=e))

    def update_button(self, button, new_label):
        button.set_label(new_label)

def apply_dark_theme():
    desktop_env = Gio.Settings.new("org.gnome.desktop.interface")
    try:
        is_dark_theme = desktop_env.get_string("color-scheme") == "prefer-dark"
    except Exception:
        is_dark_theme = "-dark" in desktop_env.get_string("gtk-theme")
    if is_dark_theme:
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)

def main():
    apply_dark_theme()
    win = ProtonDownloader()
    win.connect("destroy", Gtk.main_quit)
    Gtk.main()

if __name__ == "__main__":
    main()
