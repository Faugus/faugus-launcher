import os
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from faugus.path_manager import PathManager, IS_FLATPAK, games_json, compatibility_dir, proton_cachyos, mangohud_dir, gamemoderun
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
        is_dark_theme = False
        try:
            desktop_env = Gio.Settings.new("org.gnome.desktop.interface")
            try:
                is_dark_theme = desktop_env.get_string("color-scheme") == "prefer-dark"
            except Exception:
                is_dark_theme = "-dark" in desktop_env.get_string("gtk-theme")
        except Exception:
            pass
        if is_dark_theme:
            settings = Gtk.Settings.get_default()
            if settings:
                settings.set_property("gtk-application-prefer-dark-theme", True)

class HiDpiMixin:
    def new_surface_from_image(self: Gtk.Window, path, width=None, height=None, keep_aspect_ratio=False):
        scale = self.get_scale_factor()
        w = int(width * scale) if width else None
        h = int(height * scale) if height else None

        pixbuf = safe_load_pixbuf(path, w, h, keep_aspect_ratio)

        surface = Gdk.cairo_surface_create_from_pixbuf(pixbuf, scale, None)
        return surface

def safe_load_pixbuf(path, w=None, h=None, keep_aspect_ratio=False):
    try:
        if w and h:
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(path, w, h, keep_aspect_ratio)
        return GdkPixbuf.Pixbuf.new_from_file(path)
    except GLib.GError as e:
        if "Compressed icons" not in str(e):
            raise e

        with open(path, 'rb') as f:
            data = f.read()

        start = data.find(b'\x89PNG\r\n\x1a\n')
        if start == -1:
            raise e

        loader = GdkPixbuf.PixbufLoader.new_with_type("png")
        loader.write(data[start:])
        loader.close()
        pixbuf = loader.get_pixbuf()

        if w and h:
            pixbuf = pixbuf.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)

        return pixbuf

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
        pixbuf = safe_load_pixbuf(file_path)
        return pixbuf is not None
    except Exception:
        return False

def show_invalid_image_dialog():
    dialog = Gtk.Dialog(title="Faugus Launcher")
    dialog.set_modal(True)
    dialog.set_resizable(False)
    play_notification_sound()

    label = Gtk.Label(label=_("The selected file is not a valid image."))
    label.set_halign(Gtk.Align.CENTER)

    label2 = Gtk.Label(label=_("Please choose another one."))
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

def disable_mangohud_gamemode_if_missing(obj):
    obj.mangohud_enabled = os.path.exists(mangohud_dir)
    if not obj.mangohud_enabled:
        obj.checkbox_mangohud.set_sensitive(False)
        obj.checkbox_mangohud.set_active(False)
        obj.checkbox_mangohud.set_tooltip_text(
            _("Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more. NOT INSTALLED."))

    obj.gamemode_enabled = os.path.exists(gamemoderun) or os.path.exists("/usr/games/gamemoderun")
    if not obj.gamemode_enabled:
        obj.checkbox_gamemode.set_sensitive(False)
        obj.checkbox_gamemode.set_active(False)
        obj.checkbox_gamemode.set_tooltip_text(_("Tweaks your system to improve performance. NOT INSTALLED."))

def create_mangohud_gamemode_checkboxes(obj):
    obj.checkbox_mangohud = Gtk.CheckButton(label="MangoHud")
    obj.checkbox_mangohud.set_tooltip_text(
        _("Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more."))
    obj.checkbox_gamemode = Gtk.CheckButton(label="GameMode")
    obj.checkbox_gamemode.set_tooltip_text(_("Tweaks your system to improve performance."))

def choose_shortcut_icon(obj):
    filechooser = Gtk.FileChooserNative.new(
        _("Select an icon for the shortcut"),
        obj,
        Gtk.FileChooserAction.OPEN,
        _("Open"),
        _("Cancel")
    )

    add_image_file_filters(filechooser)

    filechooser.set_current_folder(obj.icon_directory)

    response = filechooser.run()
    if response == Gtk.ResponseType.ACCEPT:
        file_path = filechooser.get_filename()
        if not file_path or not is_valid_image(file_path):
            show_invalid_image_dialog()
        else:
            shutil.copyfile(file_path, obj.icon_temp)
            surface = obj.new_surface_from_image(obj.icon_temp, 50, 50)
            image = Gtk.Image.new_from_surface(surface)
            obj.button_shortcut_icon.set_image(image)

    filechooser.destroy()

    if os.path.isdir(obj.icon_directory):
        shutil.rmtree(obj.icon_directory)

def load_red_entry_css():
    css_provider = Gtk.CssProvider()
    css = """
    .entry {
        border-color: Red;
    }
    """
    css_provider.load_from_data(css.encode('utf-8'))
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css_provider,
                                             Gtk.STYLE_PROVIDER_PRIORITY_USER)

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

def make_donate_buttons():
    button_kofi = Gtk.Button(label="Ko-fi")
    button_kofi.connect("clicked", on_button_kofi_clicked)
    button_kofi.get_style_context().add_class("kofi")

    button_paypal = Gtk.Button(label="PayPal")
    button_paypal.connect("clicked", on_button_paypal_clicked)
    button_paypal.get_style_context().add_class("paypal")

    return button_kofi, button_paypal

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
            new_icon_path = os.path.join(icons_dir, f"{game_id}.png")
            old_icon_path = os.path.join(icons_dir, f"{game_id}.ico")

            # One-time migration: convert existing .ico to .png
            if os.path.exists(old_icon_path) and not os.path.exists(new_icon_path):
                magick = shutil.which("magick") or shutil.which("convert")
                if magick:
                    tmp_dir = tempfile.mkdtemp()
                    try:
                        # Split ICO into separate frames
                        subprocess.run(
                            [magick, old_icon_path, os.path.join(tmp_dir, "frame_%d.png")],
                            capture_output=True
                        )

                        # Find the largest frame
                        best, size = None, 0
                        for f in Path(tmp_dir).glob("frame_*.png"):
                            r = subprocess.run(
                                [magick, "identify", "-format", "%wx%h", str(f)],
                                capture_output=True, text=True
                            )
                            if r.returncode == 0 and r.stdout:
                                w, h = map(int, r.stdout.strip().split("x"))
                                current_size = w * h
                                if current_size > size:
                                    best, size = str(f), current_size

                        # Save the best frame as the new .png and remove old .ico
                        if best:
                            subprocess.run(
                                [magick, best, "-resize", "256x256!", new_icon_path],
                                check=True
                            )
                            os.remove(old_icon_path)

                            # Update existing .desktop files to point to the new .png
                            desktop_paths = [
                                os.path.expanduser(f"~/.local/share/applications/{game_id}.desktop"),
                                os.path.expanduser(f"~/Desktop/{game_id}.desktop")
                            ]
                            for d_path in desktop_paths:
                                if os.path.exists(d_path):
                                    try:
                                        with open(d_path, 'r') as f:
                                            content = f.read()
                                        if old_icon_path in content:
                                            content = content.replace(old_icon_path, new_icon_path)
                                            with open(d_path, 'w') as f:
                                                f.write(content)
                                    except Exception:
                                        pass
                    except Exception:
                        pass
                    finally:
                        shutil.rmtree(tmp_dir, ignore_errors=True)

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

def init_addon_defaults(obj):
    obj.addapp_enabled = False
    obj.addapp = ""
    obj.addapp_delay = ""
    obj.addapp_first = False
    obj.launch_arguments = ""
    obj.lossless_enabled = False
    obj.lossless_multiplier = 1
    obj.lossless_flow = 100
    obj.lossless_performance = False
    obj.lossless_hdr = False
    obj.lossless_present = False

def show_launch_arguments_dialog(parent, presets_file, current_launch_arguments):
    dialog = Gtk.Dialog(title=_("Launch Arguments"), parent=parent, flags=0)
    dialog.set_resizable(False)
    dialog.set_modal(True)
    dialog.set_default_size(650, 400)

    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    hbox.set_margin_start(10)
    hbox.set_margin_end(10)
    hbox.set_margin_top(10)
    hbox.set_margin_bottom(10)

    store_presets = Gtk.ListStore(str)

    if os.path.exists(presets_file):
        try:
            with open(presets_file, "r") as f:
                for item in json.load(f):
                    store_presets.append([item])
        except Exception:
            pass
    store_presets.append([""])

    tree_presets = Gtk.TreeView(model=store_presets)
    tree_presets.set_hexpand(True)
    tree_presets.set_vexpand(True)
    renderer_presets = Gtk.CellRendererText()
    renderer_presets.set_property("editable", True)

    def on_preset_edited(renderer, path, new_text):
        store_presets[path][0] = new_text
        if path == str(len(store_presets) - 1) and new_text.strip() != "":
            store_presets.append([""])

    def on_preset_key_press(widget, event):
        if event.keyval == Gdk.KEY_Delete:
            selection = widget.get_selection()
            model, treeiter = selection.get_selected()
            if treeiter is not None:
                if model[treeiter][0] != "" or len(model) > 1:
                    model.remove(treeiter)
                if len(model) == 0 or model[-1][0] != "":
                    model.append([""])
            return True
        return False

    renderer_presets.connect("edited", on_preset_edited)
    tree_presets.connect("key-press-event", on_preset_key_press)
    column_presets = Gtk.TreeViewColumn(_("Presets"), renderer_presets, text=0)
    tree_presets.append_column(column_presets)
    scroll_presets = Gtk.ScrolledWindow()
    scroll_presets.add(tree_presets)

    btn_copy = Gtk.Button()
    btn_copy.set_size_request(50, 50)
    btn_copy.set_valign(Gtk.Align.CENTER)

    img = Gtk.Image.new_from_icon_name("faugus-play-symbolic", Gtk.IconSize.BUTTON)

    def flip_image(w, cr):
        cr.translate(w.get_allocated_width(), 0)
        cr.scale(-1, 1)
        return False

    img.connect("draw", flip_image)
    btn_copy.set_image(img)

    store_args = Gtk.ListStore(str)
    current_args = current_launch_arguments.split("\n")
    for arg in current_args:
        if arg.strip():
            store_args.append([arg])
    store_args.append([""])

    tree_args = Gtk.TreeView(model=store_args)
    tree_args.set_hexpand(True)
    tree_args.set_vexpand(True)
    renderer_args = Gtk.CellRendererText()
    renderer_args.set_property("editable", True)

    def on_arg_edited(renderer, path, new_text):
        store_args[path][0] = new_text
        if path == str(len(store_args) - 1) and new_text.strip() != "":
            store_args.append([""])

    def on_arg_key_press(widget, event):
        if event.keyval == Gdk.KEY_Delete:
            selection = widget.get_selection()
            model, treeiter = selection.get_selected()
            if treeiter is not None:
                if model[treeiter][0] != "" or len(model) > 1:
                    model.remove(treeiter)
                if len(model) == 0 or model[-1][0] != "":
                    model.append([""])
            return True
        return False

    renderer_args.connect("edited", on_arg_edited)
    tree_args.connect("key-press-event", on_arg_key_press)
    column_args = Gtk.TreeViewColumn(_("Launch Arguments"), renderer_args, text=0)
    tree_args.append_column(column_args)
    scroll_args = Gtk.ScrolledWindow()
    scroll_args.add(tree_args)

    sel_presets = tree_presets.get_selection()
    sel_args = tree_args.get_selection()

    def on_presets_selection_changed(sel):
        if sel.count_selected_rows() > 0:
            sel_args.unselect_all()

    def on_args_selection_changed(sel):
        if sel.count_selected_rows() > 0:
            sel_presets.unselect_all()

    sel_presets.connect("changed", on_presets_selection_changed)
    sel_args.connect("changed", on_args_selection_changed)

    def on_copy_clicked(btn):
        selection = tree_presets.get_selection()
        model, treeiter = selection.get_selected()
        if treeiter is not None:
            val = model[treeiter][0].strip()
            if val:
                store_args.insert(len(store_args) - 1, [val])

    btn_copy.connect("clicked", on_copy_clicked)

    hbox.pack_start(scroll_args, True, True, 0)
    hbox.pack_start(btn_copy, False, False, 0)
    hbox.pack_start(scroll_presets, True, True, 0)

    content_area = dialog.get_content_area()
    content_area.pack_start(hbox, True, True, 0)

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

    content_area.pack_start(bottom_box, False, False, 0)

    dialog.show_all()
    response = dialog.run()

    result = current_launch_arguments
    if response == Gtk.ResponseType.OK:
        presets_to_save = [row[0] for row in store_presets if row[0].strip()]
        with open(presets_file, "w") as f:
            json.dump(presets_to_save, f)

        args_to_save = [row[0] for row in store_args if row[0].strip()]
        result = "\n".join(args_to_save)

    dialog.destroy()
    return result

def show_addapp_dialog(parent, addapp_enabled, addapp, addapp_delay, addapp_first):
    dialog = Gtk.Dialog(title=_("Additional Application"), parent=parent, flags=0)
    dialog.set_modal(True)
    dialog.set_resizable(False)

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

    enabled = val if (val := addapp_enabled) != "" else False
    cur_path = val if (val := addapp) != "" else ""
    cur_delay = val if (val := addapp_delay) != "" else ""
    cur_first = val if (val := addapp_first) != "" else False

    checkbox_enable = Gtk.CheckButton(label=_("Enable"))
    checkbox_enable.set_active(enabled)
    checkbox_enable.set_halign(Gtk.Align.START)

    label_path = Gtk.Label(label=_("Path"))
    label_path.set_halign(Gtk.Align.START)

    entry_addapp = Gtk.Entry()
    entry_addapp.set_text(cur_path)
    entry_addapp.set_tooltip_text(_("/path/to/the/app"))
    entry_addapp.set_has_tooltip(True)
    entry_addapp.connect("query-tooltip", on_entry_query_tooltip)
    entry_addapp.set_hexpand(True)

    button_search_addapp = Gtk.Button()
    button_search_addapp.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
    button_search_addapp.set_size_request(50, -1)

    def on_search_clicked(w):
        filechooser = Gtk.FileChooserNative(
            title=_("Select an additional application"),
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Open"),
            cancel_label=_("Cancel"),
        )
        add_windows_file_filters(filechooser)
        resp = filechooser.run()
        if resp == Gtk.ResponseType.ACCEPT:
            selected_file = filechooser.get_filename()
            if selected_file:
                entry_addapp.set_text(selected_file)
        filechooser.destroy()

    button_search_addapp.connect("clicked", on_search_clicked)

    label_delay = Gtk.Label(label=_("Delay (seconds)"))
    label_delay.set_halign(Gtk.Align.START)

    adjustment = Gtk.Adjustment(
        value=int(cur_delay) if cur_delay else 0,
        lower=0, upper=60, step_increment=1, page_increment=10, page_size=0
    )

    entry_delay = Gtk.SpinButton()
    entry_delay.set_adjustment(adjustment)
    entry_delay.set_numeric(True)
    entry_delay.set_hexpand(True)

    checkbox_addapp_first = Gtk.CheckButton(label=_("Run the application first"))
    checkbox_addapp_first.set_active(cur_first)
    checkbox_addapp_first.set_halign(Gtk.Align.START)

    def on_enable_toggled(cb):
        active = cb.get_active()
        label_path.set_sensitive(active)
        entry_addapp.set_sensitive(active)
        button_search_addapp.set_sensitive(active)
        label_delay.set_sensitive(active)
        entry_delay.set_sensitive(active)
        checkbox_addapp_first.set_sensitive(active)

    checkbox_enable.connect("toggled", on_enable_toggled)
    on_enable_toggled(checkbox_enable)

    grid.attach(checkbox_enable,        0, 0, 1, 1)
    grid.attach(label_path,             0, 1, 1, 1)
    grid.attach(entry_addapp,           0, 2, 3, 1)
    grid.attach(button_search_addapp,   3, 2, 1, 1)
    grid.attach(label_delay,            0, 3, 1, 1)
    grid.attach(entry_delay,            0, 4, 4, 1)
    grid.attach(checkbox_addapp_first,  0, 5, 1, 1)

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

    result = (addapp_enabled, addapp, addapp_delay, addapp_first)
    if response == Gtk.ResponseType.OK:
        result = (
            checkbox_enable.get_active(),
            entry_addapp.get_text(),
            entry_delay.get_text(),
            checkbox_addapp_first.get_active(),
        )

    dialog.destroy()
    return result

def show_lossless_dialog(parent, lossless_enabled, lossless_multiplier, lossless_flow,
                         lossless_performance, lossless_hdr, lossless_present):
    dialog = Gtk.Dialog(title=_("Lossless Scaling Frame Generation"), parent=parent, flags=0)
    dialog.set_modal(True)
    dialog.set_resizable(False)

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

    enabled = val if (val := lossless_enabled) != "" else False
    multiplier = val if (val := lossless_multiplier) != "" else 1
    flow = val if (val := lossless_flow) != "" else 100
    performance = val if (val := lossless_performance) != "" else False
    hdr = val if (val := lossless_hdr) != "" else False
    present = val if (val := lossless_present) != "" else "VSync/FIFO (default)"

    checkbox_enable = Gtk.CheckButton(label=_("Enable"))
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

    result = (lossless_enabled, lossless_multiplier, lossless_flow,
              lossless_performance, lossless_hdr, lossless_present)
    if response == Gtk.ResponseType.OK:
        present_text = combobox_present.get_active_text()
        present_mapping = {
            "VSync/FIFO (default)": "fifo",
            "Mailbox": "mailbox",
            "Immediate": "immediate",
        }
        result = (
            checkbox_enable.get_active(),
            spin_multiplier.get_value_as_int(),
            scale_flow.get_value(),
            checkbox_performance.get_active(),
            checkbox_hdr.get_active(),
            present_mapping.get(present_text, "fifo"),
        )

    dialog.destroy()
    return result
