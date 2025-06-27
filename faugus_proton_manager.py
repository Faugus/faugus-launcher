#!/usr/bin/env python3

import requests
import gi
import os
import tarfile
import shutil
import gettext
import locale
from pathlib import Path

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gio, GLib

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
        return icon_paths[-1]

IS_FLATPAK = 'FLATPAK_ID' in os.environ or os.path.exists('/.flatpak-info')
if IS_FLATPAK:
    faugus_png = PathManager.get_icon('io.github.Faugus.faugus-launcher.png')
    STEAM_COMPATIBILITY_PATH = Path(os.path.expanduser("~/.local/share/Steam/compatibilitytools.d"))
else:
    faugus_png = PathManager.get_icon('faugus-launcher.png')
    STEAM_COMPATIBILITY_PATH = Path(PathManager.user_data("Steam/compatibilitytools.d"))

config_file_dir = PathManager.user_config('faugus-launcher/config.ini')
faugus_launcher_dir = PathManager.user_config('faugus-launcher')

def get_system_locale():
    lang = os.environ.get('LANG') or os.environ.get('LC_MESSAGES')
    if lang:
        return lang.split('.')[0]

    try:
        return locale.getdefaultlocale()[0] or 'en_US'
    except Exception:
        return 'en_US'

def get_language_from_config():
    if os.path.exists(config_file_dir):
        with open(config_file_dir, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('language='):
                    return line.split('=', 1)[1].strip()
    return None

lang = get_language_from_config() or get_system_locale()

LOCALE_DIR = (
    PathManager.system_data('locale')
    if os.path.isdir(PathManager.system_data('locale'))
    else os.path.join(os.path.dirname(__file__), 'locale')
)

try:
    translation = gettext.translation('faugus-proton-manager', localedir=LOCALE_DIR, languages=[lang])
    translation.install()
    _ = translation.gettext
except FileNotFoundError:
    gettext.install('faugus-proton-manager', localedir=LOCALE_DIR)
    _ = gettext.gettext

class ConfigManager:
    def __init__(self):
        self.default_config = {
            'language': lang,
        }
        self.config = {}
        self.load_config()

    def load_config(self):
        if os.path.isfile(config_file_dir):
            with open(config_file_dir, 'r') as f:
                for line in f.read().splitlines():
                    if '=' in line:
                        key, value = line.split('=', 1)
                        self.config[key.strip()] = value.strip().strip('"')

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
                f.write(f'{key}={value}\n')

class ProtonDownloader(Gtk.Dialog):
    def __init__(self):
        super().__init__(title=_("Faugus Proton Manager"))
        self.set_resizable(False)
        self.set_modal(True)
        self.set_icon_from_file(faugus_png)

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

        self.notebook = Gtk.Notebook()
        self.notebook.set_halign(Gtk.Align.FILL)
        self.notebook.set_valign(Gtk.Align.FILL)
        self.notebook.set_vexpand(True)
        self.notebook.set_hexpand(True)
        frame.add(self.notebook)

        # Tab 1: GE-Proton
        self.grid_ge = Gtk.Grid()
        self.grid_ge.set_hexpand(True)
        self.grid_ge.set_row_spacing(5)
        self.grid_ge.set_column_spacing(10)
        scroll_ge = Gtk.ScrolledWindow()
        scroll_ge.set_size_request(400, 400)
        scroll_ge.set_margin_top(10)
        scroll_ge.set_margin_bottom(10)
        scroll_ge.set_margin_start(10)
        scroll_ge.set_margin_end(10)
        scroll_ge.add(self.grid_ge)

        tab_box_ge = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tab_label_ge = Gtk.Label(label="GE-Proton")
        tab_label_ge.set_width_chars(15)
        tab_label_ge.set_xalign(0.5)
        tab_box_ge.pack_start(tab_label_ge, True, True, 0)
        tab_box_ge.set_hexpand(True)
        tab_box_ge.show_all()
        self.notebook.append_page(scroll_ge, tab_box_ge)

        # Tab 2: Proton-EM
        self.grid_em = Gtk.Grid()
        self.grid_em.set_hexpand(True)
        self.grid_em.set_row_spacing(5)
        self.grid_em.set_column_spacing(10)
        scroll_em = Gtk.ScrolledWindow()
        scroll_em.set_size_request(400, 400)
        scroll_em.set_margin_top(10)
        scroll_em.set_margin_bottom(10)
        scroll_em.set_margin_start(10)
        scroll_em.set_margin_end(10)
        scroll_em.add(self.grid_em)

        tab_box_em = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tab_label_em = Gtk.Label(label="Proton-EM")
        tab_label_em.set_width_chars(15)
        tab_label_em.set_xalign(0.5)
        tab_box_em.pack_start(tab_label_em, True, True, 0)
        tab_box_em.set_hexpand(True)
        tab_box_em.show_all()
        self.notebook.append_page(scroll_em, tab_box_em)

        self.load_config()
        self.get_releases()
        self.show_all()
        self.progress_bar.set_visible(False)
        self.progress_label.set_visible(False)

    def load_config(self):
        cfg = ConfigManager()
        self.language = cfg.config.get('language', '')

    def get_releases(self):
        self.fetch_releases_from_url(
            "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases",
            self.grid_ge
        )
        self.fetch_releases_from_url(
            "https://api.github.com/repos/Etaash-mathamsetty/Proton/releases",
            self.grid_em
        )

    def fetch_releases_from_url(self, url, grid):
        page = 1
        releases = []
        while True:
            response = requests.get(url, params={"page": page, "per_page": 100})
            if response.status_code == 200:
                page_releases = response.json()
                if not page_releases:
                    break
                releases.extend(page_releases)
                page += 1
            else:
                break

        for release in releases:
            tag_name = release["tag_name"]

            if "GloriousEggroll" in url:
                # Esperado: GE-Proton8-1
                if not tag_name.startswith("GE-Proton"):
                    continue
                try:
                    version_str = tag_name.replace("GE-Proton", "")
                    major, minor = map(int, version_str.split("-"))
                    if (major, minor) < (8, 1):
                        continue
                except Exception:
                    continue

            elif "Etaash-mathamsetty" in url:
                # Esperado: EM-10.0-4
                if not tag_name.startswith("EM-"):
                    continue
                try:
                    version_str = tag_name.replace("EM-", "")
                    part1, part2 = version_str.split("-")
                    major, minor = map(int, part1.split("."))
                    patch = int(part2)
                    if (major, minor, patch) < (10, 0, 4):
                        continue
                except Exception:
                    continue

            self.add_release_to_grid(release, grid)

    def add_release_to_grid(self, release, grid):
        tag_name = release["tag_name"]
        display_tag_name = f"proton-{tag_name}" if tag_name.startswith("EM-") else tag_name

        row_index = len(grid.get_children()) // 2

        label = Gtk.Label(label=display_tag_name, xalign=0)
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        grid.attach(label, 0, row_index, 1, 1)

        version_path = self.get_installed_path(display_tag_name)
        is_installed = os.path.exists(version_path)

        button = Gtk.Button(label=_("Remove") if is_installed else _("Download"))
        button.connect("clicked", self.on_button_clicked, release)
        button.set_size_request(120, -1)
        grid.attach(button, 1, row_index, 1, 1)

    def get_installed_path(self, tag_name):
        if not STEAM_COMPATIBILITY_PATH.exists():
            return None

        tag_lower = tag_name.lower()
        for folder in STEAM_COMPATIBILITY_PATH.iterdir():
            folder_name_lower = folder.name.lower()
            if folder_name_lower.endswith(tag_lower):
                return folder
            if tag_lower.startswith("proton-"):
                if folder_name_lower.endswith(tag_lower[len("proton-"):]):
                    return folder

        return STEAM_COMPATIBILITY_PATH / tag_name

    def update_button(self, button, new_label):
        button.set_label(new_label)
        button.set_sensitive(True)

    def on_button_clicked(self, widget, release):
        tag_name = release["tag_name"]
        if tag_name.startswith("EM-"):
            tag_name = f"proton-{tag_name}"

        version_path = self.get_installed_path(tag_name)

        if os.path.exists(version_path):
            self.on_remove_clicked(widget, release)
        else:
            self.progress_bar.set_visible(True)
            self.progress_label.set_visible(True)
            self.on_download_clicked(widget, release)

    def disable_all_buttons(self):
        for grid in (self.grid_ge, self.grid_em):
            for child in grid.get_children():
                if isinstance(child, Gtk.Button):
                    child.set_sensitive(False)

    def enable_all_buttons(self):
        for grid in (self.grid_ge, self.grid_em):
            for child in grid.get_children():
                if isinstance(child, Gtk.Button):
                    child.set_sensitive(True)

    def on_download_clicked(self, widget, release):
        self.disable_all_buttons()
        for asset in release["assets"]:
            if asset["name"].endswith((".tar.gz", ".tar.xz")):
                self.download_and_extract(
                    asset["browser_download_url"],
                    asset["name"],
                    release["tag_name"],
                    widget
                )
                break

    def download_and_extract(self, url, filename, tag_name, button):
        button.set_label(_("Downloading..."))
        display_tag_name = f"proton-{tag_name}" if tag_name.startswith("EM-") else tag_name
        self.progress_label.set_text(_("Downloading {tag}...").format(tag=display_tag_name))
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

        self.extract_tar_and_update_button(tar_file_path, tag_name, button)

    def extract_tar_and_update_button(self, tar_file_path, tag_name, button):
        button.set_label(_("Extracting..."))
        display_tag_name = f"proton-{tag_name}" if tag_name.startswith("EM-") else tag_name
        self.progress_label.set_text(_("Extracting {tag}...").format(tag=display_tag_name))
        Gtk.main_iteration_do(False)

        mode = 'r:xz' if tar_file_path.endswith('.tar.xz') else 'r:gz'

        with tarfile.open(tar_file_path, mode) as tar:
            temp_dir = os.path.join(STEAM_COMPATIBILITY_PATH, f"temp_{tag_name}")
            os.makedirs(temp_dir, exist_ok=True)
            tar.extractall(path=temp_dir)

            extracted_dir = None
            for item in os.listdir(temp_dir):
                item_path = os.path.join(temp_dir, item)
                if os.path.isdir(item_path):
                    extracted_dir = item_path
                    break

            if extracted_dir:
                final_dir = os.path.join(STEAM_COMPATIBILITY_PATH, os.path.basename(extracted_dir))
                if os.path.exists(final_dir):
                    shutil.rmtree(final_dir)
                shutil.move(extracted_dir, STEAM_COMPATIBILITY_PATH)

            shutil.rmtree(temp_dir)

        os.remove(tar_file_path)

        self.update_button(button, _("Remove"))
        self.progress_bar.set_visible(False)
        self.progress_label.set_visible(False)
        self.enable_all_buttons()
        button.set_sensitive(True)

    def on_remove_clicked(self, widget, release):
        version_path = self.get_installed_path(release["tag_name"])
        if version_path and os.path.exists(version_path):
            try:
                shutil.rmtree(version_path)
                self.update_button(widget, _("Download"))
            except Exception:
                pass

def apply_dark_theme():
    if IS_FLATPAK:
        if (os.environ.get("XDG_CURRENT_DESKTOP")) == "KDE":
            Gtk.Settings.get_default().set_property("gtk-theme-name", "Breeze")
        try:
            proxy = Gio.DBusProxy.new_sync(
                Gio.bus_get_sync(Gio.BusType.SESSION, None), 0, None,
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.Settings", None)
            is_dark = proxy.call_sync(
                "Read", GLib.Variant("(ss)", ("org.freedesktop.appearance", "color-scheme")),
                0, -1, None).unpack()[0] == 1
        except:
            is_dark = False
        Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", is_dark)
    else:
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
