import os
import json
import re
import subprocess
from PIL import Image
from faugus.path_manager import PathManager, IS_FLATPAK, games_json
from gi.repository import Gtk, Gdk, Gio, GLib, GdkPixbuf

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

class HiDpiMixin:
    def new_surface_from_image(self: Gtk.Window, path, width=None, height=None, keep_aspect_ratio=False):
        scale = self.get_scale_factor()
        if width and height:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, int(width * scale), int(height * scale), keep_aspect_ratio)
        else:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)

        surface = Gdk.cairo_surface_create_from_pixbuf(pixbuf, scale, None)
        return surface

def ensure_parent_dir(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

def load_json_file(filepath, default=None):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []

def save_json_file(data, filepath, indent=4):
    ensure_parent_dir(filepath)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)

def format_title(title):
    title = title.strip().lower()
    title = re.sub(r"[^\w\s-]", "", title)
    title = re.sub(r"\s+", "-", title)
    return title

def add_windows_file_filters(filechooser):
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

def add_image_file_filters(filechooser, include_ico=True):
    image_filter = Gtk.FileFilter()
    image_filter.set_name(_("Image files"))
    image_filter.add_pattern("*.png")
    image_filter.add_pattern("*.jpg")
    image_filter.add_pattern("*.jpeg")
    image_filter.add_pattern("*.jxl")
    image_filter.add_pattern("*.bmp")
    image_filter.add_pattern("*.gif")
    image_filter.add_pattern("*.svg")
    if include_ico:
        image_filter.add_pattern("*.ico")
    filechooser.add_filter(image_filter)
    
_FAUGUS_NOTIFICATION = PathManager.system_data('faugus-launcher/faugus-notification.ogg')

def play_notification_sound():
    subprocess.Popen(["canberra-gtk-play", "-f", _FAUGUS_NOTIFICATION])

def build_lossless_env(lossless_enabled, lossless_multiplier, lossless_flow,
                       lossless_performance, lossless_hdr, lossless_present):
    parts = []
    if not lossless_enabled:
        return parts
    parts.append("LSFG_LEGACY=1")
    parts.append("LSFGVK_ENV=1")
    if lossless_multiplier:
        parts.append(f"LSFG_MULTIPLIER={lossless_multiplier}")
        parts.append(f"LSFGVK_MULTIPLIER={lossless_multiplier}")
    if lossless_flow:
        parts.append(f"LSFG_FLOW_SCALE={lossless_flow/100}")
        parts.append(f"LSFGVK_FLOW_SCALE={lossless_flow/100}")
    if lossless_performance:
        parts.append("LSFG_PERFORMANCE_MODE=1")
        parts.append("LSFGVK_PERFORMANCE_MODE=1")
    else:
        parts.append("LSFG_PERFORMANCE_MODE=0")
        parts.append("LSFGVK_PERFORMANCE_MODE=0")
    if lossless_hdr:
        parts.append("LSFG_HDR_MODE=1")
    else:
        parts.append("LSFG_HDR_MODE=0")
    if lossless_present:
        parts.append(f"LSFG_EXPERIMENTAL_PRESENT_MODE={lossless_present}")
    return parts
    
def is_valid_image(file_path):
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(file_path)
        return pixbuf is not None
    except Exception:
        return False

def on_entry_changed(widget, entry):
    if entry.get_text():
        entry.get_style_context().remove_class("entry")

def on_entry_query_tooltip(widget, x, y, keyboard_mode, tooltip):
    current_text = widget.get_text()
    if current_text.strip():
        tooltip.set_text(current_text)
    else:
        tooltip.set_text(widget.get_tooltip_text())
    return True

def find_largest_resolution(directory):
    largest_image = None
    largest_resolution = (0, 0)
    valid_image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff'}
    for file_name in os.listdir(directory):
        file_path = os.path.join(directory, file_name)
        if os.path.isfile(file_path):
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

def on_button_search_protonfix_clicked(widget):
    import webbrowser
    webbrowser.open("https://umu.openwinecomponents.org/")

def on_button_kofi_clicked(widget):
    import webbrowser
    webbrowser.open("https://ko-fi.com/K3K210EMDU")

def on_button_paypal_clicked(widget):
    import webbrowser
    webbrowser.open("https://www.paypal.com/donate/?business=57PP9DVD3VWAN&no_recurring=0&currency_code=USD")

def update_games_json():
    games = load_json_file(games_json, None)
    if games is None:
        return

    changed = False

    icons_dir = PathManager.user_config('faugus-launcher/icons')

    for game in games:
        if game.get("runner") == "Proton-CachyOS":
            game["runner"] = "Proton-CachyOS (System)"
            changed = True

        if "favorite" in game:
            if game["favorite"] == True:
                game["category"] = False

            game.pop("favorite")
            changed = True

        game_id = game.get("gameid")

        if game_id:
            new_icon_path = os.path.join(icons_dir, f"{game_id}.ico")

            if game.get("icon") != new_icon_path:
                game["icon"] = new_icon_path
                changed = True

    if changed:
        save_json_file(games, games_json)

GAME_FIELDS = [
    "gameid", "title", "path", "prefix",
    "launch_arguments", "game_arguments",
    "mangohud", "gamemode", "disable_hidraw",
    "protonfix", "runner",
    "addapp_checkbox", "addapp", "addapp_bat", "addapp_delay", "addapp_first",
    "banner",
    "lossless_enabled", "lossless_multiplier", "lossless_flow",
    "lossless_performance", "lossless_hdr", "lossless_present",
    "playtime", "hidden", "prevent_sleep", "category", "icon",
]

def game_to_dict(game):
    return {field: getattr(game, field) for field in GAME_FIELDS}

def game_to_save_dict(game, hidden=None):
    d = {**game_to_dict(game),
         "mangohud": True if game.mangohud else "",
         "gamemode": True if game.gamemode else "",
         "disable_hidraw": True if game.disable_hidraw else "",
         "addapp_checkbox": "addapp_enabled" if game.addapp_checkbox else ""}
    if hidden is not None:
        d["hidden"] = hidden
    return d

def prepare_game_kwargs(data):
    defaults = {f: "" for f in GAME_FIELDS}
    defaults.update({"playtime": 0, "hidden": False, "prevent_sleep": False,
                     "category": False, "icon": ""})
    return {f: data.get(f, defaults[f]) for f in GAME_FIELDS}
