import os
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from faugus.path_manager import PathManager, IS_FLATPAK, games_json, compatibility_dir, proton_cachyos
from gi.repository import Gtk, Gdk, Gio, GLib, GdkPixbuf, Pango

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

def write_addapp_bat(bat_path, exe_path, addapp, addapp_delay, addapp_first, game_arguments):
    with open(bat_path, "w") as f:
        f.write('@echo off\n')
        if not addapp_first:
            if game_arguments:
                f.write(f'start "" "z:{exe_path}" {game_arguments}\n')
            else:
                f.write(f'start "" "z:{exe_path}"\n')
            if addapp_delay:
                f.write(f'ping -n {addapp_delay} 127.0.0.1 >nul\n')
            f.write(f'start "" "z:{addapp}"\n')
        else:
            f.write(f'start "" "z:{addapp}"\n')
            if addapp_delay:
                f.write(f'ping -n {addapp_delay} 127.0.0.1 >nul\n')
            if game_arguments:
                f.write(f'start "" "z:{exe_path}" {game_arguments}\n')
            else:
                f.write(f'start "" "z:{exe_path}"\n')

def is_valid_image(file_path):
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(file_path)
        return pixbuf is not None
    except Exception:
        return False

def show_invalid_image_dialog():
    dialog = Gtk.Dialog(title="Faugus Launcher")
    dialog.set_modal(True)
    dialog.set_resizable(False)
    play_notification_sound()

    label = Gtk.Label()
    label.set_label(_("The selected file is not a valid image."))
    label.set_halign(Gtk.Align.CENTER)

    label2 = Gtk.Label()
    label2.set_label(_("Please choose another one."))
    label2.set_halign(Gtk.Align.CENTER)

    button_yes = Gtk.Button(label=_("Ok"))
    button_yes.set_size_request(150, -1)
    button_yes.connect("clicked", lambda x: dialog.response(Gtk.ResponseType.YES))

    content_area = dialog.get_content_area()
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

    dialog.show_all()
    dialog.run()
    dialog.destroy()

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

def extract_ico_simple(exe_path, output_path):
    tmp_dir = tempfile.mkdtemp()
    try:
        ensure_parent_dir(output_path)
        temp_ico = os.path.join(tmp_dir, "icon.ico")

        result = subprocess.run(
            ['icoextract', exe_path, temp_ico],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            if "NoIconsAvailableError" in result.stderr or "PEFormatError" in result.stderr:
                print("The file does not contain icons.")
                return "no_icons"
            print(f"Error extracting icon: {result.stderr}")
            return "error"

        magick = shutil.which("magick") or shutil.which("convert")
        if not magick:
            return "error"

        subprocess.run(
            [magick, temp_ico, "-resize", "256x256!", output_path], check=True
        )
        return "ok"

    except Exception as e:
        print(f"An error occurred: {e}")
        return "error"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def extract_ico_frames(exe_path, output_path):
    tmp_dir = tempfile.mkdtemp()
    try:
        ensure_parent_dir(output_path)
        temp_ico = os.path.join(tmp_dir, "icon.ico")

        result = subprocess.run(
            ['icoextract', exe_path, temp_ico],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            if "NoIconsAvailableError" in result.stderr or "PEFormatError" in result.stderr:
                print("The file does not contain icons.")
                return "no_icons"
            print(f"Error extracting icon: {result.stderr}")
            return "error"

        magick = shutil.which("magick") or shutil.which("convert")
        if not magick:
            return "error"

        subprocess.run(
            [magick, temp_ico, os.path.join(tmp_dir, "frame_%d.png")],
            capture_output=True
        )

        if os.path.isfile(temp_ico):
            os.remove(temp_ico)

        def get_index(filepath):
            match = re.search(r'frame_(\d+)\.png', filepath.name)
            return int(match.group(1)) if match else 999

        png_files = sorted(Path(tmp_dir).glob("frame_*.png"), key=get_index)
        if not png_files:
            return "error"

        best, size = None, 0
        for f in png_files:
            r = subprocess.run(
                [magick, "identify", "-format", "%wx%h", str(f)],
                capture_output=True, text=True
            )
            if r.returncode == 0 and r.stdout:
                w, h = map(int, r.stdout.strip().split("x"))
                current_size = w * h
                if current_size > size:
                    best, size = str(f), current_size

        if best:
            subprocess.run(
                [magick, best, "-resize", "256x256!", output_path], check=True
            )
            return "ok"

        return "error"

    except Exception as e:
        print(f"An error occurred: {e}")
        return "error"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

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

def version_key(v):
    cleaned = re.sub(r'^[^\d]+', '', v)
    parts = re.split(r'(\d+)', cleaned)
    return [int(p) if p.isdigit() else p for p in parts]

def populate_combobox_with_runners(combobox):
    combobox.append_text("Proton-CachyOS Latest (default)")
    combobox.append_text("GE-Proton Latest")
    combobox.append_text("Proton-EM Latest")
    combobox.append_text("DW-Proton Latest")
    combobox.append_text("UMU-Proton Latest")

    if os.path.exists(proton_cachyos):
        combobox.append_text("Proton-CachyOS (System)")

    try:
        if os.path.exists(compatibility_dir):
            versions = []
            for entry in os.listdir(compatibility_dir):
                entry_path = os.path.join(compatibility_dir, entry)
                if (
                    os.path.isdir(entry_path)
                    and entry not in ("UMU-Latest", "LegacyRuntime")
                    and not entry.startswith("Proton-GE Latest")
                    and not entry.startswith("Proton-EM Latest")
                    and not entry.startswith("DW-Proton Latest")
                    and not entry.startswith("Proton-CachyOS Latest")
                ):
                    versions.append(entry)

            versions.sort(key=version_key, reverse=True)

            for version in versions:
                combobox.append_text(version)
    except Exception as e:
        print(f"Error accessing the directory: {e}")

    combobox.set_active(0)
    cell_renderer = combobox.get_cells()[0]
    cell_renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
    cell_renderer.set_property("max-width-chars", 20)

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
