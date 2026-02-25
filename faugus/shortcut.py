#!/usr/bin/python3

import sys
sys.dont_write_bytecode = True

import gi
import gettext
import shutil
import subprocess
import re
import webbrowser
import unicodedata

gi.require_version("Gtk", "3.0")
gi.require_version('Gdk', '3.0')

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from PIL import Image
from faugus.dark_theme import *
from faugus.config_manager import *

IS_FLATPAK = 'FLATPAK_ID' in os.environ or os.path.exists('/.flatpak-info')
if IS_FLATPAK:
    app_dir = str(Path.home() / '.local/share/applications')
    faugus_png = PathManager.get_icon('io.github.Faugus.faugus-launcher.png')
    lsfgvk_possible_paths = [
        Path("/usr/lib/extensions/vulkan/lsfgvk/lib/liblsfg-vk.so"), # Deprecated in LSFG-VK v2.0
        Path(os.path.expanduser('~/.local/lib/liblsfg-vk.so')), # Deprecated in LSFG-VK v2.0
        Path("/usr/lib/extensions/vulkan/lsfgvk/lib/liblsfg-vk-layer.so"),
        Path(os.path.expanduser('~/.local/lib/liblsfg-vk-layer.so')),
    ]
    lsfgvk_path = next((p for p in lsfgvk_possible_paths if p.exists()), lsfgvk_possible_paths[-1])
else:
    app_dir = PathManager.user_data('applications')
    faugus_png = PathManager.get_icon('faugus-launcher.png')
    lsfgvk_possible_paths = [
        Path("/usr/lib/liblsfg-vk.so"), # Deprecated in LSFG-VK v2.0
        Path("/usr/lib64/liblsfg-vk.so"), # Deprecated in LSFG-VK v2.0
        Path(os.path.expanduser('~/.local/lib/liblsfg-vk.so')), # Deprecated in LSFG-VK v2.0
        Path("/usr/lib/liblsfg-vk-layer.so"),
        Path("/usr/lib64/liblsfg-vk-layer.so"),
        Path(os.path.expanduser('~/.local/lib/liblsfg-vk-layer.so'))
    ]
    lsfgvk_path = next((p for p in lsfgvk_possible_paths if p.exists()), lsfgvk_possible_paths[-1])
icons_dir = PathManager.user_config('faugus-launcher/icons')
config_file_dir = PathManager.user_config('faugus-launcher/config.ini')
prefixes_dir = str(Path.home() / 'Faugus')
mangohud_dir = PathManager.find_binary('mangohud')
gamemoderun = PathManager.find_binary('gamemoderun')
umu_run = PathManager.user_data('faugus-launcher/umu-run')
faugus_run = PathManager.find_binary('faugus-run')
faugus_launcher_dir = PathManager.user_config('faugus-launcher')
faugus_notification = PathManager.system_data('faugus-launcher/faugus-notification.ogg')

def get_desktop_dir():
    try:
        desktop_dir = subprocess.check_output(['xdg-user-dir', 'DESKTOP'], text=True).strip()
        return desktop_dir
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("xdg-user-dir not found or failed; falling back to ~/Desktop")
        return str(Path.home() / 'Desktop')

desktop_dir = get_desktop_dir()

def find_lossless_dll():
    possible_common_locations = [
        Path.home() / '.local' / 'share' / 'Steam' / 'steamapps' / 'common',
        Path.home() / '.steam' / 'steam' / 'steamapps' / 'common',
        Path.home() / '.steam' / 'root' / 'steamapps' / 'common',
        Path.home() / 'SteamLibrary' / 'steamapps' / 'common',
        Path(os.path.expanduser('~/.var/app/com.valvesoftware.Steam/.steam/steamapps/common/'))
    ]

    for location in possible_common_locations:
        dll_candidate = location / 'Lossless Scaling' / 'Lossless.dll'
        if dll_candidate.exists():
            return str(dll_candidate)

    return ""

def get_system_locale():
    lang = os.environ.get('LANG') or os.environ.get('LC_MESSAGES')
    if lang:
        return lang.split('.')[0]

    try:
        loc = locale.getdefaultlocale()[0]
        if loc:
            return loc
    except Exception:
        pass

    return 'en_US'

def get_language_from_config():
    if os.path.exists(config_file_dir):
        with open(config_file_dir, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('language='):
                    return line.split('=', 1)[1].strip()
    return None

lang = get_language_from_config()
if not lang:
    lang = get_system_locale()

LOCALE_DIR = (
    PathManager.system_data('locale')
    if os.path.isdir(PathManager.system_data('locale'))
    else os.path.join(os.path.dirname(__file__), 'locale')
)

try:
    translation = gettext.translation(
        'faugus-launcher',
        localedir=LOCALE_DIR,
        languages=[lang] if lang else ['en_US']
    )
    translation.install()
    globals()['_'] = translation.gettext
except FileNotFoundError:
    gettext.install('faugus-launcher', localedir=LOCALE_DIR)
    globals()['_'] = gettext.gettext

def format_title(title):
    title = title.strip().lower()
    title = re.sub(r"['’]", "", title)
    title = re.sub(r"[^a-z0-9]+", "-", title)
    title = title.strip("-")
    return title

def _validate_text(entry):
    text = entry.get_text()
    for i, c in enumerate(text):
        if c.isalpha() and "LATIN" not in unicodedata.name(c, ""):
            new_text = text[:i] + text[i+1:]
            entry.set_text(new_text)
            entry.set_position(i)
            break

class CreateShortcut(Gtk.Window):
    def __init__(self, file_path):
        super().__init__(title="Faugus Launcher")
        self.file_path = file_path
        self.set_resizable(False)
        self.set_icon_from_file(faugus_png)

        game_title = os.path.basename(file_path)
        self.set_title(game_title)
        print(self.file_path)

        self.icon_directory = f"{icons_dir}/icon_temp/"

        if not os.path.exists(self.icon_directory):
            os.makedirs(self.icon_directory)

        self.icons_path = icons_dir
        self.icon_extracted = os.path.expanduser(f'{self.icons_path}/icon_temp/icon.ico')
        self.icon_converted = os.path.expanduser(f'{self.icons_path}/icon_temp/icon.png')
        self.icon_temp = f'{self.icons_path}/icon_temp.ico'

        self.default_prefix = ""

        self.lossless_enabled = False
        self.lossless_multiplier = 1
        self.lossless_flow = 100
        self.lossless_performance = False
        self.lossless_hdr = False
        self.lossless_present = False

        self.label_title = Gtk.Label(label=_("Title"))
        self.label_title.set_halign(Gtk.Align.START)
        self.entry_title = Gtk.Entry()
        self.entry_title.connect("changed", self.on_entry_changed, self.entry_title)
        self.entry_title.connect("changed", _validate_text)
        self.entry_title.set_tooltip_text(_("Game Title"))

        self.label_protonfix = Gtk.Label(label="Protonfix")
        self.label_protonfix.set_halign(Gtk.Align.START)
        self.entry_protonfix = Gtk.Entry()
        self.entry_protonfix.set_tooltip_text("UMU ID")
        self.button_search_protonfix = Gtk.Button()
        self.button_search_protonfix.set_image(
            Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.button_search_protonfix.connect("clicked", self.on_button_search_protonfix_clicked)
        self.button_search_protonfix.set_size_request(50, -1)

        self.label_launch_arguments = Gtk.Label(label=_("Launch Arguments"))
        self.label_launch_arguments.set_halign(Gtk.Align.START)
        self.entry_launch_arguments = Gtk.Entry()
        self.entry_launch_arguments.set_tooltip_text(_("e.g.: PROTON_USE_WINED3D=1 gamescope -W 2560 -H 1440"))

        self.label_game_arguments = Gtk.Label(label=_("Game Arguments"))
        self.label_game_arguments.set_halign(Gtk.Align.START)
        self.entry_game_arguments = Gtk.Entry()
        self.entry_game_arguments.set_tooltip_text(_("e.g.: -d3d11 -fullscreen"))

        self.button_lossless = Gtk.Button(label=_("Lossless Scaling Frame Generation"))
        self.button_lossless.connect("clicked", self.on_button_lossless_clicked)

        self.label_addapp = Gtk.Label(label=_("Additional Application"))
        self.label_addapp.set_halign(Gtk.Align.START)
        self.entry_addapp = Gtk.Entry()
        self.entry_addapp.set_tooltip_text(_("/path/to/the/app"))
        self.button_search_addapp = Gtk.Button()
        self.button_search_addapp.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.button_search_addapp.connect("clicked", self.on_button_search_addapp_clicked)
        self.button_search_addapp.set_size_request(50, -1)

        self.button_shortcut_icon = Gtk.Button()
        self.button_shortcut_icon.set_size_request(120, -1)
        self.button_shortcut_icon.set_tooltip_text(_("Select an icon for the shortcut"))
        self.button_shortcut_icon.connect("clicked", self.on_button_shortcut_icon_clicked)

        self.checkbox_mangohud = Gtk.CheckButton(label="MangoHud")
        self.checkbox_mangohud.set_tooltip_text(
            _("Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more."))
        self.checkbox_gamemode = Gtk.CheckButton(label="GameMode")
        self.checkbox_gamemode.set_tooltip_text(_("Tweaks your system to improve performance."))
        self.checkbox_disable_hidraw = Gtk.CheckButton(label=_("Disable Hidraw"))
        self.checkbox_disable_hidraw.set_tooltip_text(
            _("May fix controller issues with some games. Only works with GE-Proton10 or Proton-EM-10."))
        self.checkbox_prevent_sleep = Gtk.CheckButton(label=_("Prevent Sleep"))

        # Button Cancel
        self.button_cancel = Gtk.Button(label=_("Cancel"))
        self.button_cancel.connect("clicked", self.on_cancel_clicked)
        self.button_cancel.set_size_request(150, -1)

        # Button Ok
        self.button_ok = Gtk.Button(label=_("Ok"))
        self.button_ok.connect("clicked", self.on_ok_clicked)
        self.button_ok.set_size_request(150, -1)

        css_provider = Gtk.CssProvider()
        css = """
        .entry {
            border-color: Red;
        }
        """
        css_provider.load_from_data(css.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css_provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_USER)

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.box.set_margin_start(0)
        self.box.set_margin_end(0)
        self.box.set_margin_top(0)
        self.box.set_margin_bottom(0)

        frame = Gtk.Frame()
        frame.set_margin_start(10)
        frame.set_margin_end(10)
        frame.set_margin_top(10)
        frame.set_margin_bottom(10)

        self.grid_title = Gtk.Grid()
        self.grid_title.set_row_spacing(10)
        self.grid_title.set_column_spacing(10)
        self.grid_title.set_margin_start(10)
        self.grid_title.set_margin_end(10)
        self.grid_title.set_margin_top(10)

        self.grid_protonfix = Gtk.Grid()
        self.grid_protonfix.set_row_spacing(10)
        self.grid_protonfix.set_column_spacing(10)
        self.grid_protonfix.set_margin_start(10)
        self.grid_protonfix.set_margin_end(10)
        self.grid_protonfix.set_margin_top(10)

        self.grid_launch_arguments = Gtk.Grid()
        self.grid_launch_arguments.set_row_spacing(10)
        self.grid_launch_arguments.set_column_spacing(10)
        self.grid_launch_arguments.set_margin_start(10)
        self.grid_launch_arguments.set_margin_end(10)
        self.grid_launch_arguments.set_margin_top(10)

        self.grid_game_arguments = Gtk.Grid()
        self.grid_game_arguments.set_row_spacing(10)
        self.grid_game_arguments.set_column_spacing(10)
        self.grid_game_arguments.set_margin_start(10)
        self.grid_game_arguments.set_margin_end(10)
        self.grid_game_arguments.set_margin_top(10)

        self.grid_lossless = Gtk.Grid()
        self.grid_lossless.set_row_spacing(10)
        self.grid_lossless.set_column_spacing(10)
        self.grid_lossless.set_margin_start(10)
        self.grid_lossless.set_margin_end(10)
        self.grid_lossless.set_margin_top(10)

        self.grid_addapp = Gtk.Grid()
        self.grid_addapp.set_row_spacing(10)
        self.grid_addapp.set_column_spacing(10)
        self.grid_addapp.set_margin_start(10)
        self.grid_addapp.set_margin_end(10)
        self.grid_addapp.set_margin_top(10)

        self.grid_title.attach(self.label_title, 0, 0, 4, 1)
        self.grid_title.attach(self.entry_title, 0, 1, 4, 1)
        self.entry_title.set_hexpand(True)

        self.grid_protonfix.attach(self.label_protonfix, 0, 0, 1, 1)
        self.grid_protonfix.attach(self.entry_protonfix, 0, 1, 3, 1)
        self.entry_protonfix.set_hexpand(True)
        self.grid_protonfix.attach(self.button_search_protonfix, 3, 1, 1, 1)

        self.grid_launch_arguments.attach(self.label_launch_arguments, 0, 0, 4, 1)
        self.grid_launch_arguments.attach(self.entry_launch_arguments, 0, 1, 4, 1)
        self.entry_launch_arguments.set_hexpand(True)

        self.grid_game_arguments.attach(self.label_game_arguments, 0, 0, 4, 1)
        self.grid_game_arguments.attach(self.entry_game_arguments, 0, 1, 4, 1)
        self.entry_game_arguments.set_hexpand(True)

        self.grid_addapp.attach(self.label_addapp, 0, 0, 1, 1)
        self.grid_addapp.attach(self.entry_addapp, 0, 1, 3, 1)
        self.entry_addapp.set_hexpand(True)
        self.grid_addapp.attach(self.button_search_addapp, 3, 1, 1, 1)

        self.grid_lossless.attach(self.button_lossless, 0, 0, 1, 1)
        self.button_lossless.set_hexpand(True)

        self.grid_tools = Gtk.Grid(orientation=Gtk.Orientation.VERTICAL)
        self.grid_tools.set_row_spacing(10)
        self.grid_tools.set_column_spacing(10)
        self.grid_tools.set_margin_start(10)
        self.grid_tools.set_margin_end(10)
        self.grid_tools.set_margin_top(10)
        self.grid_tools.set_margin_bottom(10)

        self.grid_shortcut_icon = Gtk.Grid(orientation=Gtk.Orientation.VERTICAL)
        self.grid_shortcut_icon.set_row_spacing(10)
        self.grid_shortcut_icon.set_column_spacing(10)
        self.grid_shortcut_icon.set_margin_start(10)
        self.grid_shortcut_icon.set_margin_end(10)
        self.grid_shortcut_icon.set_margin_top(10)
        self.grid_shortcut_icon.set_margin_bottom(10)

        self.grid_tools.add(self.checkbox_mangohud)
        self.grid_tools.add(self.checkbox_gamemode)
        self.grid_tools.add(self.checkbox_prevent_sleep)
        self.grid_tools.add(self.checkbox_disable_hidraw)

        self.grid_shortcut_icon.add(self.button_shortcut_icon)
        self.grid_shortcut_icon.set_valign(Gtk.Align.CENTER)

        self.box_tools = Gtk.Box()
        self.box_tools.pack_start(self.grid_tools, False, False, 0)
        self.box_tools.pack_end(self.grid_shortcut_icon, False, False, 0)

        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_box.set_margin_start(10)
        bottom_box.set_margin_end(10)
        # botton_box.set_margin_top(10)
        bottom_box.set_margin_bottom(10)

        self.button_cancel.set_hexpand(True)
        self.button_ok.set_hexpand(True)

        bottom_box.pack_start(self.button_cancel, True, True, 0)
        bottom_box.pack_start(self.button_ok, True, True, 0)

        self.main_grid = Gtk.Grid(orientation=Gtk.Orientation.VERTICAL)
        self.main_grid.add(self.grid_title)
        self.main_grid.add(self.grid_protonfix)
        self.main_grid.add(self.grid_launch_arguments)
        self.main_grid.add(self.grid_game_arguments)
        self.main_grid.add(self.grid_addapp)
        self.main_grid.add(self.grid_lossless)
        self.main_grid.add(self.box_tools)

        self.load_config()

        self.mangohud_enabled = os.path.exists(mangohud_dir)
        if not self.mangohud_enabled:
            self.checkbox_mangohud.set_sensitive(False)
            self.checkbox_mangohud.set_active(False)
            self.checkbox_mangohud.set_tooltip_text(
                _("Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more. NOT INSTALLED."))

        self.gamemode_enabled = os.path.exists(gamemoderun) or os.path.exists("/usr/games/gamemoderun")
        if not self.gamemode_enabled:
            self.checkbox_gamemode.set_sensitive(False)
            self.checkbox_gamemode.set_active(False)
            self.checkbox_gamemode.set_tooltip_text(_("Tweaks your system to improve performance. NOT INSTALLED."))

        lossless_dll_path = find_lossless_dll()
        if os.path.exists(lsfgvk_path):
            if lossless_dll_path or os.path.exists(self.lossless_location):
                self.button_lossless.set_sensitive(True)
            else:
                self.button_lossless.set_sensitive(False)
                self.button_lossless.set_tooltip_text(_("Lossless.dll NOT FOUND. If it's installed, go to Faugus Launcher's settings and set the location."))
        else:
            self.button_lossless.set_sensitive(False)
            self.button_lossless.set_tooltip_text(_("Lossless Scaling Vulkan Layer NOT INSTALLED."))

        frame.add(self.main_grid)
        self.box.add(frame)
        self.box.add(bottom_box)
        self.add(self.box)

        if not os.path.exists(self.icon_directory):
            os.makedirs(self.icon_directory)

        try:
            # Attempt to extract the icon
            command = f'icoextract "{file_path}" "{self.icon_extracted}"'
            result = subprocess.run(command, shell=True, text=True, capture_output=True)

            # Check if there was an error in executing the command
            if result.returncode != 0:
                if "NoIconsAvailableError" in result.stderr or "PEFormatError" in result.stderr:
                    print("The file does not contain icons.")
                    self.button_shortcut_icon.set_image(self.set_image_shortcut_icon())
                else:
                    print(f"Error extracting icon: {result.stderr}")
            else:
                # Convert the extracted icon to PNG
                command_magick = shutil.which("magick") or shutil.which("convert")
                os.system(f'{command_magick} "{self.icon_extracted}" "{self.icon_converted}"')
                if os.path.isfile(self.icon_extracted):
                    os.remove(self.icon_extracted)

                largest_image = self.find_largest_resolution(self.icon_directory)
                shutil.move(largest_image, os.path.expanduser(self.icon_temp))

                pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.icon_temp)
                scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)
                image = Gtk.Image.new_from_file(self.icon_temp)
                image.set_from_pixbuf(scaled_pixbuf)

                self.button_shortcut_icon.set_image(image)

        except Exception as e:
            print(f"An error occurred: {e}")

        shutil.rmtree(self.icon_directory)

        # Connect the destroy signal to Gtk.main_quit
        self.connect("destroy", Gtk.main_quit)

    def on_button_lossless_clicked(self, widget):
        dialog = Gtk.Dialog(title=_("Lossless Scaling Frame Generation"), parent=self, flags=0)
        dialog.set_resizable(False)
        dialog.set_icon_from_file(faugus_png)

        frame = Gtk.Frame()
        frame.set_margin_start(10)
        frame.set_margin_end(10)
        frame.set_margin_top(10)
        frame.set_margin_bottom(10)

        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_margin_top(10)
        grid.set_margin_bottom(10)
        grid.set_margin_start(10)
        grid.set_margin_end(10)

        enabled = val if (val := getattr(self, "lossless_enabled", False)) != "" else False
        multiplier = val if (val := getattr(self, "lossless_multiplier", 1)) != "" else 1
        flow = val if (val := getattr(self, "lossless_flow", 100)) != "" else 100
        performance = val if (val := getattr(self, "lossless_performance", False)) != "" else False
        hdr = val if (val := getattr(self, "lossless_hdr", False)) != "" else False
        present = val if (val := getattr(self, "lossless_present", False)) != "" else "VSync/FIFO (default)"

        checkbox_enable = Gtk.CheckButton(label="Enable")
        checkbox_enable.set_active(enabled)
        checkbox_enable.set_halign(Gtk.Align.START)

        label_multiplier = Gtk.Label(label=_("Multiplier"))
        label_multiplier.set_halign(Gtk.Align.START)
        spin_multiplier = Gtk.SpinButton()
        spin_multiplier.set_adjustment(Gtk.Adjustment(value=multiplier, lower=1, upper=20, step_increment=1))
        spin_multiplier.set_numeric(True)
        spin_multiplier.set_tooltip_text(_("Multiply the FPS."))

        label_flow = Gtk.Label(label=_("Flow Scale"))
        label_flow.set_halign(Gtk.Align.START)
        adjustment = Gtk.Adjustment(value=flow, lower=25, upper=100, step_increment=1)
        scale_flow = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
        scale_flow.set_digits(0)
        scale_flow.set_hexpand(True)
        scale_flow.set_value_pos(Gtk.PositionType.RIGHT)
        scale_flow.set_tooltip_text(_("Lower the internal motion estimation resolution."))

        checkbox_performance = Gtk.CheckButton(label=_("Performance Mode"))
        checkbox_performance.set_tooltip_text(_("Massively improve performance at the cost of quality."))
        checkbox_performance.set_active(performance)

        checkbox_hdr = Gtk.CheckButton(label=_("HDR Mode"))
        checkbox_hdr.set_tooltip_text(_("Enable special HDR-only behavior."))
        checkbox_hdr.set_active(hdr)

        label_present = Gtk.Label(label=_("Present Mode (Experimental)"))
        label_present.set_halign(Gtk.Align.START)

        combobox_present = Gtk.ComboBoxText()
        combobox_present.set_tooltip_text(_("Override the present mode."))

        options = [
            "VSync/FIFO (default)",
            "Mailbox",
            "Immediate",
        ]

        for opt in options:
            combobox_present.append_text(opt)

        mapping = {
            "fifo": "VSync/FIFO (default)",
            "mailbox": "Mailbox",
            "immediate": "Immediate",
        }

        ui_value = mapping.get(present, "VSync/FIFO (default)")
        combobox_present.set_active(options.index(ui_value))

        def on_enable_toggled(cb):
            active = cb.get_active()
            label_multiplier.set_sensitive(active)
            spin_multiplier.set_sensitive(active)
            label_flow.set_sensitive(active)
            scale_flow.set_sensitive(active)
            checkbox_performance.set_sensitive(active)
            checkbox_hdr.set_sensitive(active)
            label_present.set_sensitive(active)
            combobox_present.set_sensitive(active)

        checkbox_enable.connect("toggled", on_enable_toggled)
        on_enable_toggled(checkbox_enable)

        grid.attach(checkbox_enable,        0, 0, 1, 1)
        grid.attach(label_multiplier,       0, 1, 1, 1)
        grid.attach(spin_multiplier,        0, 2, 1, 1)
        grid.attach(label_flow,             0, 3, 1, 1)
        grid.attach(scale_flow,             0, 4, 1, 1)
        grid.attach(checkbox_performance,   0, 5, 1, 1)
        grid.attach(checkbox_hdr,           0, 6, 1, 1)
        grid.attach(label_present,          0, 7, 1, 1)
        grid.attach(combobox_present,       0, 8, 1, 1)

        frame.add(grid)

        button_cancel = Gtk.Button(label=_("Cancel"))
        button_cancel.set_size_request(150, -1)
        button_cancel.set_hexpand(True)
        button_cancel.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.CANCEL))

        button_ok = Gtk.Button(label=_("Ok"))
        button_ok.set_size_request(150, -1)
        button_ok.set_hexpand(True)
        button_ok.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.OK))

        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_box.set_margin_start(10)
        bottom_box.set_margin_end(10)
        bottom_box.set_margin_bottom(10)
        bottom_box.pack_start(button_cancel, True, True, 0)
        bottom_box.pack_start(button_ok, True, True, 0)

        content_area = dialog.get_content_area()
        content_area.pack_start(frame, True, True, 0)
        content_area.pack_start(bottom_box, False, False, 0)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            self.lossless_enabled = checkbox_enable.get_active()
            self.lossless_multiplier = spin_multiplier.get_value_as_int()
            self.lossless_flow = scale_flow.get_value()
            self.lossless_performance = checkbox_performance.get_active()
            self.lossless_hdr = checkbox_hdr.get_active()

            present = combobox_present.get_active_text()

            mapping = {
                "VSync/FIFO (default)": "fifo",
                "Mailbox": "mailbox",
                "Immediate": "immediate",
            }

            self.lossless_present = mapping.get(present, "fifo")

        dialog.destroy()
        return response

    def on_button_search_addapp_clicked(self, widget):
        filechooser = Gtk.FileChooserNative(
            title=_("Select an additional application"),
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Open"),
            cancel_label=_("Cancel"),
        )

        filechooser.set_current_folder(os.path.expanduser("~/"))

        windows_filter = Gtk.FileFilter()
        windows_filter.set_name(_("Windows files"))
        windows_filter.add_pattern("*.exe")
        windows_filter.add_pattern("*.msi")
        windows_filter.add_pattern("*.bat")
        windows_filter.add_pattern("*.lnk")
        windows_filter.add_pattern("*.reg")

        all_files_filter = Gtk.FileFilter()
        all_files_filter.set_name(_("All files"))
        all_files_filter.add_pattern("*")

        filechooser.add_filter(windows_filter)
        filechooser.add_filter(all_files_filter)
        filechooser.set_filter(windows_filter)

        response = filechooser.run()

        if response == Gtk.ResponseType.ACCEPT:
            self.entry_addapp.set_text(filechooser.get_filename())

        filechooser.destroy()

    def find_largest_resolution(self, directory):
        largest_image = None
        largest_resolution = (0, 0)  # (width, height)

        # Define a set of valid image extensions
        valid_image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff'}

        for file_name in os.listdir(directory):
            file_path = os.path.join(directory, file_name)
            if os.path.isfile(file_path):
                # Check if the file has a valid image extension
                if os.path.splitext(file_name)[1].lower() in valid_image_extensions:
                    try:
                        with Image.open(file_path) as img:
                            width, height = img.size
                            if width * height > largest_resolution[0] * largest_resolution[1]:
                                largest_resolution = (width, height)
                                largest_image = file_path
                    except IOError:
                        print(f"Unable to open {file_path}")

        return largest_image

    def on_button_search_protonfix_clicked(self, widget):
        webbrowser.open("https://umu.openwinecomponents.org/")

    def load_config(self):
        cfg = ConfigManager()

        self.default_prefix = cfg.config.get('default-prefix', '').strip('"')
        mangohud = cfg.config.get('mangohud', 'False') == 'True'
        gamemode = cfg.config.get('gamemode', 'False') == 'True'
        disable_hidraw = cfg.config.get('disable-hidraw', 'False') == 'True'
        prevent_sleep = cfg.config.get('prevent-sleep', 'False') == 'True'
        self.default_runner = cfg.config.get('default-runner', '').strip('"')
        self.lossless_location = cfg.config.get('lossless-location', '')

        self.checkbox_mangohud.set_active(mangohud)
        self.checkbox_gamemode.set_active(gamemode)
        self.checkbox_disable_hidraw.set_active(disable_hidraw)
        self.checkbox_prevent_sleep.set_active(prevent_sleep)

    def on_cancel_clicked(self, widget):
        if os.path.isfile(self.icon_temp):
            os.remove(self.icon_temp)
        if os.path.isdir(self.icon_directory):
            shutil.rmtree(self.icon_directory)
        self.destroy()

    def on_ok_clicked(self, widget):

        validation_result = self.validate_fields()
        if not validation_result:
            self.set_sensitive(True)
            return

        title = self.entry_title.get_text()
        title_formatted = format_title(title)

        addapp = self.entry_addapp.get_text()
        addapp_bat = f"{os.path.dirname(self.file_path)}/faugus-{title_formatted}.bat"

        if self.entry_addapp.get_text():
            with open(addapp_bat, "w") as bat_file:
                bat_file.write(f'start "" "z:{addapp}"\n')
                bat_file.write(f'start "" "z:{self.file_path}"\n')

        if os.path.isfile(os.path.expanduser(self.icon_temp)):
            os.rename(os.path.expanduser(self.icon_temp), f'{self.icons_path}/{title_formatted}.ico')

        # Check if the icon file exists
        new_icon_path = f"{icons_dir}/{title_formatted}.ico"
        if not os.path.exists(new_icon_path):
            new_icon_path = faugus_png

        protonfix = self.entry_protonfix.get_text()
        launch_arguments = self.entry_launch_arguments.get_text()
        game_arguments = self.entry_game_arguments.get_text()
        lossless_enabled = self.lossless_enabled
        lossless_multiplier = self.lossless_multiplier
        lossless_flow = self.lossless_flow
        lossless_performance = self.lossless_performance
        lossless_hdr = self.lossless_hdr
        lossless_present = self.lossless_present

        mangohud = True if self.checkbox_mangohud.get_active() else ""
        gamemode = True if self.checkbox_gamemode.get_active() else ""
        disable_hidraw = True if self.checkbox_disable_hidraw.get_active() else ""
        prevent_sleep = True if self.checkbox_prevent_sleep.get_active() else ""

        # Get the directory containing the executable
        game_directory = os.path.dirname(self.file_path)

        command_parts = []

        # Add command parts if they are not empty
        if disable_hidraw:
            command_parts.append("PROTON_DISABLE_HIDRAW=1")
        if prevent_sleep:
            command_parts.append("PREVENT_SLEEP=1")
        if protonfix:
            command_parts.append(f'GAMEID={protonfix}')
        else:
            command_parts.append(f'GAMEID={title_formatted}')
        if launch_arguments:
            command_parts.append(launch_arguments)
        if lossless_enabled:
            command_parts.append("LSFG_LEGACY=1") # Deprecated in LSFG-VK v2.0
            command_parts.append("LSFGVK_ENV=1")
            if lossless_multiplier:
                command_parts.append(f"LSFG_MULTIPLIER={lossless_multiplier}") # Deprecated in LSFG-VK v2.0
                command_parts.append(f"LSFGVK_MULTIPLIER={lossless_multiplier}")
            if lossless_flow:
                command_parts.append(f"LSFG_FLOW_SCALE={lossless_flow/100}") # Deprecated in LSFG-VK v2.0
                command_parts.append(f"LSFGVK_FLOW_SCALE={lossless_flow/100}")
            if lossless_performance:
                command_parts.append("LSFG_PERFORMANCE_MODE=1") # Deprecated in LSFG-VK v2.0
                command_parts.append("LSFGVK_PERFORMANCE_MODE=1")
            else:
                command_parts.append("LSFG_PERFORMANCE_MODE=0") # Deprecated in LSFG-VK v2.0
                command_parts.append("LSFGVK_PERFORMANCE_MODE=0")
            if lossless_hdr: # HDR mode env is deprecated in LSFG-VK v2.0
                command_parts.append("LSFG_HDR_MODE=1")
            else:
                command_parts.append("LSFG_HDR_MODE=0")
            if lossless_present: # Experimental present mode env is deprecated in LSFG-VK v2.0
                command_parts.append(f"LSFG_EXPERIMENTAL_PRESENT_MODE={lossless_present}")
        if gamemode:
            command_parts.append("gamemoderun")
        if mangohud:
            command_parts.append("mangohud")
        # Add the fixed command and remaining arguments
        command_parts.append(f"'{umu_run}'")
        if self.entry_addapp.get_text():
            escaped_addapp_bat = addapp_bat.replace("'", "'\\''")
            command_parts.append(f"'{escaped_addapp_bat}'")
        elif self.file_path:
            escaped_file_path = self.file_path.replace("'", "'\\''")
            command_parts.append(f"'{escaped_file_path}'")
        if game_arguments:
            command_parts.append(f"{game_arguments}")

        # Join all parts into a single command
        command = ' '.join(command_parts)

        # Create a .desktop file
        if IS_FLATPAK:
            desktop_file_content = (
                f'[Desktop Entry]\n'
                f'Name={title}\n'
                f'Exec=flatpak run --command={faugus_run} io.github.Faugus.faugus-launcher "{command}"\n'
                f'Icon={new_icon_path}\n'
                f'Type=Application\n'
                f'Categories=Game;\n'
                f'Path={game_directory}\n'
            )
        else:
            desktop_file_content = (
                f'[Desktop Entry]\n'
                f'Name={title}\n'
                f'Exec={faugus_run} "{command}"\n'
                f'Icon={new_icon_path}\n'
                f'Type=Application\n'
                f'Categories=Game;\n'
                f'Path={game_directory}\n'
            )

        # Check if the destination directory exists and create if it doesn't
        applications_directory = app_dir
        if not os.path.exists(applications_directory):
            os.makedirs(applications_directory)

        desktop_directory = desktop_dir
        if not os.path.exists(desktop_directory):
            os.makedirs(desktop_directory)

        applications_shortcut_path = f"{app_dir}/{title_formatted}.desktop"

        with open(applications_shortcut_path, 'w') as desktop_file:
            desktop_file.write(desktop_file_content)

        # Make the .desktop file executable
        os.chmod(applications_shortcut_path, 0o755)

        # Copy the shortcut to Desktop
        desktop_shortcut_path = f"{desktop_dir}/{title_formatted}.desktop"
        shutil.copyfile(applications_shortcut_path, desktop_shortcut_path)
        os.chmod(desktop_shortcut_path, 0o755)

        if os.path.isfile(self.icon_temp):
            os.remove(self.icon_temp)
        if os.path.isdir(self.icon_directory):
            shutil.rmtree(self.icon_directory)
        self.destroy()

    def on_entry_changed(self, widget, entry):
        if entry.get_text():
            entry.get_style_context().remove_class("entry")

    def set_image_shortcut_icon(self):
        image_path = faugus_png

        pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
        scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)

        image = Gtk.Image.new_from_pixbuf(scaled_pixbuf)
        return image

    def on_button_shortcut_icon_clicked(self, widget):
        self.set_sensitive(False)

        path = self.file_path

        if not os.path.exists(self.icon_directory):
            os.makedirs(self.icon_directory)

        try:
            command = f'icoextract "{path}" "{self.icon_extracted}"'
            result = subprocess.run(command, shell=True, text=True, capture_output=True)

            if result.returncode != 0:
                if "NoIconsAvailableError" in result.stderr or "PEFormatError" in result.stderr:
                    print("The file does not contain icons.")
                    self.button_shortcut_icon.set_image(self.set_image_shortcut_icon())
                else:
                    print(f"Error extracting icon: {result.stderr}")
            else:
                command_magick = shutil.which("magick") or shutil.which("convert")
                os.system(f'{command_magick} "{self.icon_extracted}" "{self.icon_converted}"')
                if os.path.isfile(self.icon_extracted):
                    os.remove(self.icon_extracted)

        except Exception as e:
            print(f"An error occurred: {e}")

        def is_valid_image(file_path):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(file_path)
                return pixbuf is not None
            except Exception:
                return False

        filechooser = Gtk.FileChooserNative.new(
            _("Select an icon for the shortcut"),
            self,
            Gtk.FileChooserAction.OPEN,
            _("Open"),
            _("Cancel")
        )

        filter_ico = Gtk.FileFilter()
        filter_ico.set_name(_("Image files"))
        filter_ico.add_pattern("*.png")
        filter_ico.add_pattern("*.jpg")
        filter_ico.add_pattern("*.jpeg")
        filter_ico.add_pattern("*.jxl")
        filter_ico.add_pattern("*.bmp")
        filter_ico.add_pattern("*.gif")
        filter_ico.add_pattern("*.svg")
        filter_ico.add_pattern("*.ico")
        filechooser.add_filter(filter_ico)

        filechooser.set_current_folder(self.icon_directory)

        response = filechooser.run()
        if response == Gtk.ResponseType.ACCEPT:
            file_path = filechooser.get_filename()
            if not file_path or not is_valid_image(file_path):
                dialog_image = Gtk.Dialog(title="Faugus Launcher", transient_for=self, modal=True)
                dialog_image.set_resizable(False)
                dialog_image.set_icon_from_file(faugus_png)
                subprocess.Popen(["canberra-gtk-play", "-f", faugus_notification])

                label = Gtk.Label()
                label.set_label(_("The selected file is not a valid image."))
                label.set_halign(Gtk.Align.CENTER)

                label2 = Gtk.Label()
                label2.set_label(_("Please choose another one."))
                label2.set_halign(Gtk.Align.CENTER)

                button_yes = Gtk.Button(label=_("Ok"))
                button_yes.set_size_request(150, -1)
                button_yes.connect("clicked", lambda x: dialog_image.response(Gtk.ResponseType.YES))

                content_area = dialog_image.get_content_area()
                content_area.set_border_width(0)
                content_area.set_halign(Gtk.Align.CENTER)
                content_area.set_valign(Gtk.Align.CENTER)
                content_area.set_vexpand(True)
                content_area.set_hexpand(True)

                box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
                box_top.set_margin_start(20)
                box_top.set_margin_end(20)
                box_top.set_margin_top(20)
                box_top.set_margin_bottom(20)

                box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                box_bottom.set_margin_start(10)
                box_bottom.set_margin_end(10)
                box_bottom.set_margin_bottom(10)

                box_top.pack_start(label, True, True, 0)
                box_top.pack_start(label2, True, True, 0)
                box_bottom.pack_start(button_yes, True, True, 0)

                content_area.add(box_top)
                content_area.add(box_bottom)

                dialog_image.show_all()
                dialog_image.run()
                dialog_image.destroy()
            else:
                shutil.copyfile(file_path, self.icon_temp)
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.icon_temp)
                scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)
                image = Gtk.Image.new_from_file(self.icon_temp)
                image.set_from_pixbuf(scaled_pixbuf)
                self.button_shortcut_icon.set_image(image)

        filechooser.destroy()

        if os.path.isdir(self.icon_directory):
            shutil.rmtree(self.icon_directory)
        self.set_sensitive(True)

    def update_preview(self, dialog):
        if file_path := dialog.get_preview_filename():
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(file_path)
                max_width = 400
                max_height = 400
                width = pixbuf.get_width()
                height = pixbuf.get_height()

                if width > max_width or height > max_height:
                    ratio = min(max_width / width, max_height / height)
                    new_width = int(width * ratio)
                    new_height = int(height * ratio)
                    pixbuf = pixbuf.scale_simple(new_width, new_height, GdkPixbuf.InterpType.BILINEAR)

                image = Gtk.Image.new_from_pixbuf(pixbuf)
                dialog.set_preview_widget(image)
                dialog.set_preview_widget_active(True)
                dialog.get_preview_widget().set_size_request(max_width, max_height)
            except GLib.Error:
                dialog.set_preview_widget_active(False)
        else:
            dialog.set_preview_widget_active(False)

    def validate_fields(self):

        title = self.entry_title.get_text()

        self.entry_title.get_style_context().remove_class("entry")

        if not title:
            self.entry_title.get_style_context().add_class("entry")
            return False

        return True

def main():
    os.environ["GTK_USE_PORTAL"] = "1"
    apply_dark_theme()
    exec_path = sys.argv[1]

    win = CreateShortcut(exec_path)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
