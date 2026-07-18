import os
import json
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from faugus.path_manager import PathManager, GAMES_JSON, PRESETS_FILE, COMPATIBILITY_DIR, PROTON_CACHYOS, MANGOHUD_DIR, GAMEMODERUN, ICONS_DIR, COVERS_DIR, FAUGUS_NOTIFICATION, FILECHOOSER_FOLDERS_FILE, IS_FLATPAK
from gi.repository import Gtk, Gdk, Gio, GLib, GdkPixbuf, Pango, GObject, Adw


def _log_writer_filter(log_level, fields, n_fields, user_data):
    import ctypes
    for f in fields:
        if f.key == "MESSAGE":
            try:
                if f.length == -1:
                    message = ctypes.cast(f.value, ctypes.c_char_p).value.decode("utf-8", "replace")
                else:
                    message = ctypes.string_at(f.value, f.length).decode("utf-8", "replace")
            except Exception:
                message = ""
            if "GtkGizmo" in message and "reported min" in message:
                return GLib.LogWriterOutput.HANDLED
            if "gtk_css_node_insert_after" in message:
                return GLib.LogWriterOutput.HANDLED
            if "mapped without a transient parent" in message:
                return GLib.LogWriterOutput.HANDLED
            if "swapchain" in message:
                return GLib.LogWriterOutput.HANDLED
            break
    return GLib.log_writer_default(log_level, fields, user_data)


GLib.log_set_writer_func(_log_writer_filter, None)


_background_executor = ThreadPoolExecutor(max_workers=32, thread_name_prefix="faugus-worker")


def run_in_background(fn, *args, **kwargs):
    return _background_executor.submit(fn, *args, **kwargs)


def kill_by_faugusid(gameid):
    if not gameid:
        return

    script = r'''
MARKER="FAUGUSID=$1"
for d in /proc/[0-9]*; do
    pid=${d#/proc/}
    if tr "\0" "\n" < "$d/environ" 2>/dev/null | grep -qxF "$MARKER"; then
        kill -9 "$pid" 2>/dev/null
    fi
done
'''
    cmd = ["flatpak-spawn", "--host", "sh", "-c", script, "_", gameid] if IS_FLATPAK else ["sh", "-c", script, "_", gameid]
    try:
        subprocess.run(cmd, capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass


HIDPI_SCALE = 2


class HiDpiPaintable(GObject.GObject, Gdk.Paintable):
    def __init__(self, texture, width, height):
        super().__init__()
        self._texture = texture
        self._width = width
        self._height = height

    def do_get_intrinsic_width(self):
        return self._width

    def do_get_intrinsic_height(self):
        return self._height

    def do_snapshot(self, snapshot, width, height):
        self._texture.snapshot(snapshot, width, height)


class HiDpiMixin:
    def new_texture_from_image(self: Gtk.Widget, path, width=None, height=None, keep_aspect_ratio=False):
        w = width * HIDPI_SCALE if width else None
        h = height * HIDPI_SCALE if height else None

        pixbuf = safe_load_pixbuf(path, w, h, keep_aspect_ratio)
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)

        if width and height:
            return HiDpiPaintable(texture, width, height)
        return texture


def normalize_icon_bytes(data):
    if not data or data[:4] != b"\x00\x00\x01\x00":
        return data

    from PIL import Image
    import io

    try:
        with Image.open(io.BytesIO(data)) as icon:
            frame = icon.convert("RGBA")
            buf = io.BytesIO()
            frame.save(buf, "PNG")
            return buf.getvalue()
    except Exception:
        return data


def resize_icon_bytes(data, size=256):
    if not data:
        return data

    from PIL import Image
    import io

    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.size == (size, size):
                return data
            img = img.convert("RGBA").resize((size, size), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "PNG")
            return buf.getvalue()
    except Exception:
        return data


def resize_image_file(src_path, dst_path, width, height):
    from PIL import Image

    with Image.open(src_path) as img:
        img.convert("RGBA").resize((width, height), Image.LANCZOS).save(dst_path, "PNG")


def is_valid_image_bytes(data):
    if not data:
        return False
    try:
        loader = GdkPixbuf.PixbufLoader()
        loader.write(data)
        loader.close()
        return loader.get_pixbuf() is not None
    except GLib.GError:
        return False


def verified_content(response):
    import requests

    content = response.content
    expected_length = response.headers.get("Content-Length")
    if expected_length is not None and len(content) != int(expected_length):
        raise requests.RequestException(
            f"Truncated download: expected {expected_length} bytes, got {len(content)}"
        )
    return content


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


def new_icon_image(icon_filename, size=16):
    path = PathManager.get_icon(icon_filename)
    icon = Gio.FileIcon.new(Gio.File.new_for_path(path))
    image = Gtk.Image.new_from_gicon(icon)
    image.set_pixel_size(size)
    return image


def widget_children(widget):
    children = []
    child = widget.get_first_child()
    while child:
        children.append(child)
        child = child.get_next_sibling()
    return children


def new_picture(paintable=None):
    picture = Gtk.Picture.new_for_paintable(paintable) if paintable else Gtk.Picture()
    picture.set_halign(Gtk.Align.CENTER)
    picture.set_valign(Gtk.Align.CENTER)
    picture.set_can_shrink(False)
    picture.set_content_fit(Gtk.ContentFit.SCALE_DOWN)
    return picture


def wrap_with_spinner(widget, dim_shape="none"):
    dim = Gtk.Box()
    dim.add_css_class("spinner-dim-overlay")
    if dim_shape != "none":
        dim.add_css_class(f"spinner-dim-overlay-{dim_shape}")
        dim.set_overflow(Gtk.Overflow.HIDDEN)
    dim.set_visible(False)
    dim.set_can_target(False)
    dim.set_hexpand(True)
    dim.set_vexpand(True)
    dim.set_margin_top(widget.get_margin_top())
    dim.set_margin_bottom(widget.get_margin_bottom())
    dim.set_margin_start(widget.get_margin_start())
    dim.set_margin_end(widget.get_margin_end())

    spinner = Gtk.Spinner()
    spinner.set_size_request(32, 32)
    spinner.set_halign(Gtk.Align.CENTER)
    spinner.set_valign(Gtk.Align.CENTER)
    spinner.set_visible(False)
    spinner.set_can_target(False)
    spinner.dim_overlay = dim

    overlay = Gtk.Overlay()
    overlay.set_hexpand(widget.get_hexpand())
    overlay.set_vexpand(widget.get_vexpand())
    overlay.set_halign(widget.get_halign())
    overlay.set_valign(widget.get_valign())
    overlay.set_child(widget)
    overlay.add_overlay(dim)
    overlay.add_overlay(spinner)
    return overlay, spinner


def add_focus_tint(overlay, size=None, square=False):
    tint = Gtk.Box()
    tint.add_css_class("steamgriddb-focus-tint")
    if square:
        tint.add_css_class("steamgriddb-focus-tint-square")
    tint.set_can_target(False)
    if size:
        width, height = size
        tint.set_size_request(width, height)
        tint.set_halign(Gtk.Align.CENTER)
        tint.set_valign(Gtk.Align.CENTER)
    else:
        tint.set_hexpand(True)
        tint.set_vexpand(True)
    overlay.add_overlay(tint)
    overlay.set_measure_overlay(tint, False)
    overlay.add_css_class("steamgriddb-artwork-picker-overlay")
    return tint


def create_accent_placeholder_paintable(width, height, alpha=0.4):
    dummy = Gtk.Box()
    found, rgba = dummy.get_style_context().lookup_color("accent_bg_color")
    if not found:
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = 0.5, 0.5, 0.5, 1.0

    w = width * HIDPI_SCALE
    h = height * HIDPI_SCALE
    pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, w, h)
    r = int(rgba.red * 255)
    g = int(rgba.green * 255)
    b = int(rgba.blue * 255)
    a = int(alpha * 255)
    pixbuf.fill((r << 24) | (g << 16) | (b << 8) | a)
    texture = Gdk.Texture.new_for_pixbuf(pixbuf)
    return HiDpiPaintable(texture, width, height)


def wrap_with_replaceable_placeholder(picture, width, height):
    margin_top = picture.get_margin_top()
    margin_bottom = picture.get_margin_bottom()
    margin_start = picture.get_margin_start()
    margin_end = picture.get_margin_end()
    picture.set_margin_top(0)
    picture.set_margin_bottom(0)
    picture.set_margin_start(0)
    picture.set_margin_end(0)

    placeholder = Gtk.Box()
    placeholder.add_css_class("cover-placeholder")
    placeholder.set_size_request(width, height)

    stack = Gtk.Stack()
    stack.set_hhomogeneous(False)
    stack.set_vhomogeneous(False)
    stack.set_transition_type(Gtk.StackTransitionType.NONE)
    stack.set_hexpand(picture.get_hexpand())
    stack.set_vexpand(picture.get_vexpand())
    stack.set_halign(picture.get_halign())
    stack.set_valign(picture.get_valign())
    stack.set_margin_top(margin_top)
    stack.set_margin_bottom(margin_bottom)
    stack.set_margin_start(margin_start)
    stack.set_margin_end(margin_end)
    stack.add_named(placeholder, "placeholder")
    stack.add_named(picture, "picture")
    stack.set_visible_child_name("placeholder")
    return stack


def set_spinner_loading(spinners, loading):
    for spinner in spinners:
        spinner.set_visible(loading)
        if loading:
            spinner.start()
        else:
            spinner.stop()
        dim = getattr(spinner, 'dim_overlay', None)
        if dim is not None:
            dim.set_visible(loading)


class IdComboBox(Gtk.DropDown):
    __gsignals__ = {
        'changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__()
        self._ids = []
        self._short_label_map = {}
        self._suppress = False
        self._ellipsize = False
        self._max_width_chars = 20
        self._store = Gtk.StringList()
        self.set_model(self._store)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_factory_setup)
        factory.connect("bind", self._on_factory_bind)
        self.set_factory(factory)
        list_factory = Gtk.SignalListItemFactory()
        list_factory.connect("setup", self._on_factory_setup)
        list_factory.connect("bind", self._on_full_text_list_factory_bind)
        self.set_list_factory(list_factory)
        self._list_factory_bind_func = self._on_full_text_list_factory_bind
        self.connect("notify::selected", self._on_notify_selected)

    def _on_factory_setup(self, factory, list_item):
        label = Gtk.Label(xalign=0)
        list_item.set_child(label)

    def _on_factory_bind(self, factory, list_item):
        label = list_item.get_child()
        item = list_item.get_item()
        text = item.get_string() if item else ""
        text = self._short_label_map.get(text, text)
        label.set_text(text)
        if self._ellipsize:
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_max_width_chars(self._max_width_chars)

    def _on_full_text_list_factory_bind(self, factory, list_item):
        label = list_item.get_child()
        item = list_item.get_item()
        label.set_text(item.get_string() if item else "")
        if self._ellipsize:
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_max_width_chars(self._max_width_chars)

    def _on_notify_selected(self, *args):
        if not self._suppress:
            self.emit("changed")

    def release(self):
        factory = self.get_factory()
        if factory:
            factory.disconnect_by_func(self._on_factory_setup)
            factory.disconnect_by_func(self._on_factory_bind)
        list_factory = self.get_list_factory()
        if list_factory:
            list_factory.disconnect_by_func(self._on_factory_setup)
            list_factory.disconnect_by_func(self._list_factory_bind_func)
        self.disconnect_by_func(self._on_notify_selected)

    def configure_ellipsize(self, max_width_chars=20):
        self._ellipsize = True
        self._max_width_chars = max_width_chars

    def _on_list_factory_bind(self, factory, list_item):
        self._on_factory_bind(factory, list_item)
        label = list_item.get_child()
        row_widget = label.get_parent()
        is_first = list_item.get_position() == 0
        list_item.set_selectable(not is_first)
        list_item.set_activatable(not is_first)
        label.set_visible(not is_first)
        if row_widget:
            if is_first:
                row_widget.add_css_class("hidden-combo-row")
            else:
                row_widget.remove_css_class("hidden-combo-row")

    def disable_first_item_selection(self):
        add_css_once(
            "hidden_combo_row",
            "row.hidden-combo-row { min-height: 0px; padding: 0px; margin: 0px; border: none; }",
        )
        list_factory = Gtk.SignalListItemFactory()
        list_factory.connect("setup", self._on_factory_setup)
        list_factory.connect("bind", self._on_list_factory_bind)
        self.set_list_factory(list_factory)
        self._list_factory_bind_func = self._on_list_factory_bind

    def append(self, id_, text, short_text=None):
        self._ids.append(id_)
        if short_text:
            self._short_label_map[text] = short_text
        self._suppress = True
        self._store.append(text)
        self._suppress = False

    def append_text(self, text):
        self.append(None, text)

    def remove_all(self):
        n = self._store.get_n_items()
        if n:
            self._suppress = True
            self._store.splice(0, n, [])
            self._suppress = False
        self._ids = []
        self._short_label_map = {}

    def get_active(self):
        sel = self.get_selected()
        return sel if sel != Gtk.INVALID_LIST_POSITION else -1

    def set_active(self, index):
        if index is None or index < 0:
            self.set_selected(Gtk.INVALID_LIST_POSITION)
        else:
            self.set_selected(index)

    def get_active_text(self):
        item = self.get_selected_item()
        return item.get_string() if item else None

    def get_active_id(self):
        idx = self.get_active()
        if idx < 0 or idx >= len(self._ids):
            return None
        return self._ids[idx]

    def set_active_id(self, id_):
        try:
            idx = self._ids.index(id_)
        except ValueError:
            return False
        self.set_active(idx)
        return True

    def set_active_id_silent(self, id_):
        self._suppress = True
        result = self.set_active_id(id_)
        self._suppress = False
        return result

    def set_active_silent(self, index):
        self._suppress = True
        self.set_active(index)
        self._suppress = False

    def get_texts(self):
        return [self._store.get_string(i) for i in range(self._store.get_n_items())]


def hide_dialog_action_area(dialog):
    outer = dialog.get_first_child()
    if not outer:
        return
    content_box = outer.get_first_child()
    if not content_box:
        return
    action_box = content_box.get_next_sibling()
    if action_box:
        action_box.set_visible(False)


def build_grid(margin_top=True, margin_bottom=True, column_homogeneous=False):
    grid = Gtk.Grid()
    grid.set_row_spacing(10)
    grid.set_column_spacing(10)
    if column_homogeneous:
        grid.set_column_homogeneous(True)
    grid.set_margin_start(10)
    grid.set_margin_end(10)
    if margin_top:
        grid.set_margin_top(10)
    if margin_bottom:
        grid.set_margin_bottom(10)
    return grid


def build_bottom_button_box(button_cancel, button_ok):
    bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    bottom_box.set_homogeneous(True)
    bottom_box.set_margin_start(10)
    bottom_box.set_margin_end(10)
    bottom_box.set_margin_bottom(10)
    bottom_box.append(button_cancel)
    bottom_box.append(button_ok)
    return bottom_box


def build_dialog_ok_cancel_box(dialog):
    button_cancel = Gtk.Button(label=_("Cancel"))
    button_cancel.set_hexpand(True)
    button_cancel.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.CANCEL))

    button_ok = Gtk.Button(label=_("Ok"))
    button_ok.set_hexpand(True)
    button_ok.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.OK))

    return build_bottom_button_box(button_cancel, button_ok)


def _release_combo_boxes(widget):
    if isinstance(widget, IdComboBox):
        widget.release()
    child = widget.get_first_child()
    while child:
        nxt = child.get_next_sibling()
        _release_combo_boxes(child)
        child = nxt
    if isinstance(widget, Gtk.Popover):
        widget.popdown()
        widget.unparent()


def destroy_and_release(widget):
    if isinstance(widget, Gtk.Window):
        widget.set_focus(None)

    _release_combo_boxes(widget)

    if isinstance(widget, Gtk.Dialog):
        content = widget.get_content_area()
        child = content.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            content.remove(child)
            child = nxt
    elif hasattr(widget, "set_child"):
        widget.set_child(None)

    widget.destroy()
    widget.__dict__.clear()


def ensure_parent_dir(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def atomic_write(filepath, write_func):
    ensure_parent_dir(filepath)
    dir_name = os.path.dirname(filepath) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            write_func(f)
        os.replace(tmp_path, filepath)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def load_json_file(filepath, default=None):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []


def save_json_file(data, filepath, indent=4):
    atomic_write(filepath, lambda f: json.dump(data, f, indent=indent, ensure_ascii=False))


def format_title(title):
    title = title.strip().lower()
    title = re.sub(r"[^\w\s-]", "", title)
    title = re.sub(r"\s+", "-", title)
    return title


def new_file_chooser(parent, title, action, accept_label=None, cancel_label=None):
    dialog = Gtk.FileChooserDialog(
        title=title,
        transient_for=parent,
        modal=True,
        action=action,
    )
    dialog.add_button(cancel_label or _("Cancel"), Gtk.ResponseType.CANCEL)
    dialog.add_button(accept_label or _("Open"), Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.ACCEPT)
    return dialog


_last_filechooser_folder = load_json_file(FILECHOOSER_FOLDERS_FILE, default={})


def set_file_chooser_start_folder(filechooser, key, preferred_path=None):
    folder = None
    if preferred_path:
        candidate = preferred_path if os.path.isdir(preferred_path) else os.path.dirname(preferred_path)
        if candidate and os.path.isdir(candidate):
            folder = candidate
    if not folder:
        folder = _last_filechooser_folder.get(key)
    if not folder or not os.path.isdir(folder):
        folder = os.path.expanduser("~")

    filechooser.set_current_folder(Gio.File.new_for_path(folder))

    def remember_folder(fc, response):
        current = fc.get_current_folder()
        path = current.get_path() if current else None
        if path and _last_filechooser_folder.get(key) != path:
            _last_filechooser_folder[key] = path
            save_json_file(_last_filechooser_folder, FILECHOOSER_FOLDERS_FILE)

    filechooser.connect("response", remember_folder)


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


_active_media_streams = []


def play_notification_sound():
    media = Gtk.MediaFile.new_for_filename(FAUGUS_NOTIFICATION)
    _active_media_streams.append(media)

    def on_notify_ended(stream, _pspec):
        if stream.get_ended() and stream in _active_media_streams:
            _active_media_streams.remove(stream)

    media.connect("notify::ended", on_notify_ended)
    media.play()


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
    bat_path = expand_path(bat_path)
    exe_path = expand_path(exe_path)
    addapp = expand_path(addapp)
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


def show_message_dialog(text1, text2="", parent=None, confirm_label=None, cancel_label=None, callback=None, modal=True):
    dialog = Gtk.Dialog(title="Faugus", transient_for=parent)
    hide_dialog_action_area(dialog)
    dialog.set_modal(modal)
    dialog.set_resizable(False)
    play_notification_sound()

    content_area = dialog.get_content_area()
    content_area.set_halign(Gtk.Align.CENTER)
    content_area.set_valign(Gtk.Align.CENTER)
    content_area.set_vexpand(True)
    content_area.set_hexpand(True)

    box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box_top.set_margin_start(20)
    box_top.set_margin_end(20)
    box_top.set_margin_top(20)
    box_top.set_margin_bottom(20)

    label1 = Gtk.Label(label=text1)
    label1.set_halign(Gtk.Align.CENTER)
    box_top.append(label1)

    if text2:
        label2 = Gtk.Label(label=text2)
        label2.set_halign(Gtk.Align.CENTER)
        box_top.append(label2)

    box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    box_bottom.set_homogeneous(True)
    box_bottom.set_margin_start(10)
    box_bottom.set_margin_end(10)
    box_bottom.set_margin_bottom(10)

    if cancel_label:
        button_cancel = Gtk.Button(label=cancel_label)
        button_cancel.set_hexpand(True)
        button_cancel.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.CANCEL))
        box_bottom.append(button_cancel)

    button_confirm = Gtk.Button(label=confirm_label or _("Ok"))
    button_confirm.set_hexpand(True)
    button_confirm.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))
    box_bottom.append(button_confirm)

    content_area.append(box_top)
    content_area.append(box_bottom)

    def on_response(d, response_id):
        confirmed = response_id == Gtk.ResponseType.OK
        destroy_and_release(d)
        if callback:
            callback(confirmed)

    dialog.connect("response", on_response)
    dialog.present()
    return dialog


def show_invalid_image_dialog(parent=None):
    show_message_dialog(
        _("The selected file is not a valid image."),
        _("Please choose another one."),
        parent=parent,
    )


def on_entry_changed(widget):
    if widget.get_text():
        widget.remove_css_class("entry")


def on_entry_query_tooltip(widget, x, y, keyboard_mode, tooltip):
    current_text = widget.get_text()
    if current_text.strip():
        text_width = widget.create_pango_layout(current_text).get_pixel_size()[0]
        if text_width <= widget.get_width() - 16:
            return False
        tooltip.set_text(current_text)
        return True

    static_tooltip = widget.get_tooltip_text()
    if not static_tooltip:
        return False
    tooltip.set_text(static_tooltip)
    return True


def disable_mangohud_gamemode_if_missing(obj):
    obj.mangohud_enabled = os.path.exists(MANGOHUD_DIR)
    if not obj.mangohud_enabled:
        obj.checkbox_mangohud.set_sensitive(False)
        obj.checkbox_mangohud.set_active(False)
        obj.checkbox_mangohud.set_tooltip_text(
            _("Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more\nMangoHud not found"))

    obj.gamemode_enabled = os.path.exists(GAMEMODERUN) or os.path.exists("/usr/games/gamemoderun")
    if not obj.gamemode_enabled:
        obj.checkbox_gamemode.set_sensitive(False)
        obj.checkbox_gamemode.set_active(False)
        obj.checkbox_gamemode.set_tooltip_text(_("Tweaks your system to improve performance\nGameMode not found"))


def create_mangohud_gamemode_checkboxes(obj):
    obj.checkbox_mangohud = Gtk.CheckButton(label="MangoHud")
    obj.checkbox_mangohud.set_tooltip_text(
        _("Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more"))
    obj.checkbox_gamemode = Gtk.CheckButton(label="GameMode")
    obj.checkbox_gamemode.set_tooltip_text(_("Tweaks your system to improve performance"))


def choose_shortcut_icon(obj):
    filechooser = new_file_chooser(
        obj,
        _("Select an icon for the shortcut"),
        Gtk.FileChooserAction.OPEN,
    )

    add_image_file_filters(filechooser)

    filechooser.set_current_folder(Gio.File.new_for_path(obj.icon_directory))

    def on_response(dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            file_path = dialog.get_file().get_path()
            if not file_path or not is_valid_image(file_path):
                show_invalid_image_dialog(obj)
            else:
                shutil.copyfile(file_path, obj.icon_temp)
                texture = obj.new_texture_from_image(obj.icon_temp, 50, 50)
                image = new_picture(texture)
                obj.button_shortcut_icon.set_child(image)

        destroy_and_release(dialog)

        if os.path.isdir(obj.icon_directory):
            shutil.rmtree(obj.icon_directory)

    filechooser.connect("response", on_response)
    filechooser.present()


_registered_css_keys = set()


def add_css_once(key, css, priority=Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION):
    if key in _registered_css_keys:
        return
    _registered_css_keys.add(key)

    css_provider = Gtk.CssProvider()
    css_provider.load_from_data(css.encode('utf-8') if isinstance(css, str) else css)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css_provider, priority)


def load_red_entry_css():
    add_css_once(
        "red_entry",
        """
        .entry {
            border: 1px solid red;
        }
        """,
        Gtk.STYLE_PROVIDER_PRIORITY_USER,
    )


def load_frame_css():
    add_css_once(
        "frame",
        """
        frame {
            border: 1px solid alpha(@borders, 0.9);
            border-radius: 6px;
        }
        """,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


def extract_ico(exe_path, output_path, best_frame=False):
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

        from PIL import Image

        with Image.open(temp_ico) as icon:
            frame = icon.convert("RGBA").resize((256, 256), Image.LANCZOS)
            frame.save(output_path, "PNG")

        return "ok"

    except Exception as e:
        print(f"An error occurred: {e}")
        return "error"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def make_donate_buttons():
    button_kofi = Gtk.Button(label="Ko-fi")
    button_kofi.connect("clicked", on_button_kofi_clicked)
    button_kofi.add_css_class("kofi")

    button_paypal = Gtk.Button(label="PayPal")
    button_paypal.connect("clicked", on_button_paypal_clicked)
    button_paypal.add_css_class("paypal")

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


def expand_path(value):
    if not value:
        return value
    return os.path.expandvars(os.path.expanduser(value))


def update_games_json():
    games = load_json_file(GAMES_JSON, None)
    if games is None:
        return

    changed = False

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
            ico_path = os.path.join(ICONS_DIR, f"{game_id}.ico")
            png_path = os.path.join(ICONS_DIR, f"{game_id}.png")

            if os.path.exists(ico_path):
                new_icon_path = ico_path
            else:
                new_icon_path = png_path

            if game.get("icon") != new_icon_path:
                game["icon"] = new_icon_path
                changed = True

            if game.get("cover"):
                new_cover_path = os.path.join(COVERS_DIR, f"{game_id}.png")
                if game.get("cover") != new_cover_path:
                    game["cover"] = new_cover_path
                    changed = True

    if changed:
        save_json_file(games, GAMES_JSON)


def resolve_protonpath(runner):
    return PROTON_CACHYOS if runner == "Proton-CachyOS (System)" else runner


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

    if os.path.exists(PROTON_CACHYOS):
        combobox.append_text("Proton-CachyOS (System)")

    try:
        if os.path.exists(COMPATIBILITY_DIR):
            versions = []
            for entry in os.listdir(COMPATIBILITY_DIR):
                entry_path = os.path.join(COMPATIBILITY_DIR, entry)
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
    combobox.configure_ellipsize(20)


GAME_FIELDS = [
    "gameid", "title", "path", "prefix",
    "launch_arguments", "game_arguments",
    "mangohud", "gamemode", "sdl_enabled",
    "protonfix", "runner",
    "addapp_enabled", "addapp", "addapp_bat", "addapp_delay", "addapp_first",
    "cover",
    "lossless_enabled", "lossless_multiplier", "lossless_flow",
    "lossless_performance", "lossless_hdr", "lossless_present",
    "playtime", "hidden", "no_sleep", "category", "icon",
    "steamgriddb_id", "pre_launch", "post_launch",
    "steam_user",
]


def game_to_dict(game):
    return {field: getattr(game, field) for field in GAME_FIELDS}


def game_to_save_dict(game, hidden=None):
    d = {**game_to_dict(game),
         "mangohud": True if game.mangohud else "",
         "gamemode": True if game.gamemode else "",
         "sdl_enabled": True if game.sdl_enabled else "",
         "addapp_enabled": "addapp_enabled" if game.addapp_enabled else ""}
    if hidden is not None:
        d["hidden"] = hidden
    return d


def prepare_game_kwargs(data):
    defaults = {f: "" for f in GAME_FIELDS}
    defaults.update({"playtime": 0, "hidden": False, "no_sleep": False,
                     "category": False, "icon": ""})
    return {f: data.get(f, defaults[f]) for f in GAME_FIELDS}


def init_addon_defaults(obj):
    obj.addapp_enabled = False
    obj.addapp = ""
    obj.addapp_delay = ""
    obj.addapp_first = False
    obj.launch_arguments = ""
    obj.pre_launch = ""
    obj.post_launch = ""
    obj.lossless_enabled = False
    obj.lossless_multiplier = 1
    obj.lossless_flow = 100
    obj.lossless_performance = False
    obj.lossless_hdr = False
    obj.lossless_present = False


def show_launch_arguments_dialog(parent, current_launch_arguments, current_pre_launch, current_post_launch, callback):
    dialog = Gtk.Dialog(title=_("Launch Settings"), transient_for=parent)
    hide_dialog_action_area(dialog)
    dialog.set_resizable(False)
    dialog.set_modal(True)
    dialog.set_default_size(650, 400)

    frame = Gtk.Frame()
    frame.set_margin_start(10)
    frame.set_margin_end(10)
    frame.set_margin_top(10)
    frame.set_margin_bottom(10)

    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    hbox.set_margin_start(10)
    hbox.set_margin_end(10)
    hbox.set_margin_top(10)
    hbox.set_margin_bottom(10)

    store_presets = Gtk.ListStore(str)

    for item in load_json_file(PRESETS_FILE, default=[]):
        store_presets.append([item])
    store_presets.append([""])

    tree_presets = Gtk.TreeView(model=store_presets)
    tree_presets.add_css_class("selected-list")
    tree_presets.set_hexpand(True)
    tree_presets.set_vexpand(True)
    renderer_presets = Gtk.CellRendererText()
    renderer_presets.set_property("editable", True)

    def on_preset_edited(renderer, path, new_text):
        store_presets[path][0] = new_text
        if path == str(len(store_presets) - 1) and new_text.strip() != "":
            store_presets.append([""])

    def on_preset_key_press(controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Delete:
            selection = tree_presets.get_selection()
            model, treeiter = selection.get_selected()
            if treeiter is not None:
                if model[treeiter][0] != "" or len(model) > 1:
                    model.remove(treeiter)
                if len(model) == 0 or model[-1][0] != "":
                    model.append([""])
            return True
        return False

    renderer_presets.connect("edited", on_preset_edited)
    key_controller_presets = Gtk.EventControllerKey()
    key_controller_presets.connect("key-pressed", on_preset_key_press)
    tree_presets.add_controller(key_controller_presets)
    column_presets = Gtk.TreeViewColumn("", renderer_presets, text=0)
    tree_presets.append_column(column_presets)
    tree_presets.set_headers_visible(False)
    scroll_presets = Gtk.ScrolledWindow()
    scroll_presets.set_child(tree_presets)

    label_presets_header = Gtk.Label(label=_("Presets"))
    label_presets_header.set_halign(Gtk.Align.START)

    box_presets = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box_presets.set_hexpand(True)
    box_presets.set_vexpand(True)
    box_presets.append(label_presets_header)
    box_presets.append(scroll_presets)

    btn_copy = Gtk.Button()
    btn_copy.set_size_request(50, 50)
    btn_copy.set_valign(Gtk.Align.CENTER)

    img = new_icon_image("faugus-play-symbolic.svg")
    img.add_css_class("flip-x")
    add_css_once(
        "launch_arguments_flip",
        ".flip-x { transform: scaleX(-1); }"
        ".selected-list:selected { background-color: @theme_selected_bg_color; color: @theme_selected_fg_color; }"
    )
    btn_copy.set_child(img)

    store_args = Gtk.ListStore(str)
    current_args = current_launch_arguments.split("\n")
    for arg in current_args:
        if arg.strip():
            store_args.append([arg])
    store_args.append([""])

    tree_args = Gtk.TreeView(model=store_args)
    tree_args.add_css_class("selected-list")
    tree_args.set_hexpand(True)
    tree_args.set_vexpand(True)
    renderer_args = Gtk.CellRendererText()
    renderer_args.set_property("editable", True)

    def on_arg_edited(renderer, path, new_text):
        store_args[path][0] = new_text
        if path == str(len(store_args) - 1) and new_text.strip() != "":
            store_args.append([""])

    def on_arg_key_press(controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Delete:
            selection = tree_args.get_selection()
            model, treeiter = selection.get_selected()
            if treeiter is not None:
                if model[treeiter][0] != "" or len(model) > 1:
                    model.remove(treeiter)
                if len(model) == 0 or model[-1][0] != "":
                    model.append([""])
            return True
        return False

    renderer_args.connect("edited", on_arg_edited)
    key_controller_args = Gtk.EventControllerKey()
    key_controller_args.connect("key-pressed", on_arg_key_press)
    tree_args.add_controller(key_controller_args)
    column_args = Gtk.TreeViewColumn("", renderer_args, text=0)
    tree_args.append_column(column_args)
    tree_args.set_headers_visible(False)
    scroll_args = Gtk.ScrolledWindow()
    scroll_args.set_child(tree_args)

    label_args_header = Gtk.Label(label=_("Launch Arguments"))
    label_args_header.set_halign(Gtk.Align.START)

    box_args = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box_args.set_hexpand(True)
    box_args.set_vexpand(True)
    box_args.append(label_args_header)
    box_args.append(scroll_args)

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

    size_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
    size_group.add_widget(box_args)
    size_group.add_widget(box_presets)

    hbox.append(box_args)
    hbox.append(btn_copy)
    hbox.append(box_presets)

    def build_hook_command_box(title, current_value, key, tooltip):
        label = Gtk.Label(label=title)
        label.set_halign(Gtk.Align.START)

        entry = Gtk.Entry()
        entry.set_text(current_value)
        entry.set_hexpand(True)
        entry.set_tooltip_text(tooltip)

        button_search = Gtk.Button()
        button_search.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        button_search.set_size_request(50, -1)
        button_search.set_tooltip_text(tooltip)

        def on_search_clicked(widget):
            filechooser = new_file_chooser(dialog, _("Select a command or script"), Gtk.FileChooserAction.OPEN)
            set_file_chooser_start_folder(filechooser, key, entry.get_text() or None)

            def on_response_fc(dialog_fc, response):
                if response == Gtk.ResponseType.ACCEPT:
                    selected_file = dialog_fc.get_file().get_path()
                    if selected_file:
                        entry.set_text(selected_file)
                destroy_and_release(dialog_fc)

            filechooser.connect("response", on_response_fc)
            filechooser.present()

        button_search.connect("clicked", on_search_clicked)

        entry_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        entry_row.append(entry)
        entry_row.append(button_search)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(label)
        box.append(entry_row)
        return box, entry

    box_pre_launch, entry_pre_launch = build_hook_command_box(
        _("Pre-launch"), current_pre_launch, "pre_launch",
        _("Command or script to run before the game"))
    box_post_launch, entry_post_launch = build_hook_command_box(
        _("Post-launch"), current_post_launch, "post_launch",
        _("Command or script to run after the game"))

    hbox_hooks = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    hbox_hooks.set_homogeneous(True)
    hbox_hooks.set_margin_start(10)
    hbox_hooks.set_margin_end(10)
    hbox_hooks.set_margin_bottom(10)
    hbox_hooks.append(box_pre_launch)
    hbox_hooks.append(box_post_launch)

    frame_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    frame_content.append(hbox)
    frame_content.append(hbox_hooks)
    frame.set_child(frame_content)

    content_area = dialog.get_content_area()
    content_area.append(frame)

    bottom_box = build_dialog_ok_cancel_box(dialog)

    content_area.append(bottom_box)

    def on_response(dialog, response):
        result = current_launch_arguments
        pre_launch = current_pre_launch
        post_launch = current_post_launch
        if response == Gtk.ResponseType.OK:
            presets_to_save = [row[0] for row in store_presets if row[0].strip()]
            save_json_file(presets_to_save, PRESETS_FILE)

            args_to_save = [row[0] for row in store_args if row[0].strip()]
            result = "\n".join(args_to_save)
            pre_launch = entry_pre_launch.get_text().strip()
            post_launch = entry_post_launch.get_text().strip()

        destroy_and_release(dialog)
        callback(result, pre_launch, post_launch)

    dialog.connect("response", on_response)
    dialog.present()


def show_addapp_dialog(parent, addapp_enabled, addapp, addapp_delay, addapp_first, callback):
    dialog = Gtk.Dialog(title=_("Additional Application"), transient_for=parent)
    hide_dialog_action_area(dialog)
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
    entry_addapp.set_tooltip_text(_("Path to the application"))
    entry_addapp.set_has_tooltip(True)
    entry_addapp.connect("query-tooltip", on_entry_query_tooltip)
    entry_addapp.set_hexpand(True)

    button_search_addapp = Gtk.Button()
    button_search_addapp.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
    button_search_addapp.set_size_request(50, -1)

    def on_search_clicked(w):
        filechooser = new_file_chooser(
            dialog,
            _("Select an additional application"),
            Gtk.FileChooserAction.OPEN,
        )
        add_windows_file_filters(filechooser)

        def on_search_response(dialog_fc, resp):
            if resp == Gtk.ResponseType.ACCEPT:
                selected_file = dialog_fc.get_file().get_path()
                if selected_file:
                    entry_addapp.set_text(selected_file)
            destroy_and_release(dialog_fc)

        filechooser.connect("response", on_search_response)
        filechooser.present()

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

    frame.set_child(grid)

    bottom_box = build_dialog_ok_cancel_box(dialog)

    content_area = dialog.get_content_area()
    content_area.append(frame)
    content_area.append(bottom_box)

    def on_response(dialog, response):
        result = (addapp_enabled, addapp, addapp_delay, addapp_first)
        if response == Gtk.ResponseType.OK:
            result = (
                checkbox_enable.get_active(),
                entry_addapp.get_text(),
                entry_delay.get_text(),
                checkbox_addapp_first.get_active(),
            )

        destroy_and_release(dialog)
        callback(result)

    dialog.connect("response", on_response)
    dialog.present()


def show_lossless_dialog(parent, lossless_enabled, lossless_multiplier, lossless_flow,
                         lossless_performance, lossless_hdr, lossless_present, callback):
    dialog = Gtk.Dialog(title=_("Lossless Scaling Frame Generation"), transient_for=parent)
    hide_dialog_action_area(dialog)
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

    from faugus.config_manager import ConfigManager
    from faugus.steam_setup import LOSSLESS_DLL

    cfg = ConfigManager()
    current_location = cfg.config.get('lossless-location', '').strip('"')
    if not current_location and LOSSLESS_DLL:
        current_location = str(LOSSLESS_DLL)

    label_location = Gtk.Label(label=_("Lossless Scaling Location"))
    label_location.set_halign(Gtk.Align.START)

    load_red_entry_css()

    entry_location = Gtk.Entry()
    entry_location.set_text(current_location)
    entry_location.set_hexpand(True)
    entry_location.set_tooltip_text(_("Lossless.dll location"))
    entry_location.set_has_tooltip(True)
    entry_location.connect("query-tooltip", on_entry_query_tooltip)
    entry_location.connect("changed", on_entry_changed)

    button_search_location = Gtk.Button()
    button_search_location.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
    button_search_location.set_size_request(50, -1)

    def on_search_location_clicked(widget):
        filechooser = new_file_chooser(
            dialog,
            _("Select the Lossless.dll file"),
            Gtk.FileChooserAction.OPEN,
        )
        entry_value = entry_location.get_text()
        preferred_path = expand_path(entry_value) if entry_value else None
        set_file_chooser_start_folder(filechooser, "settings_lossless", preferred_path)

        filter_dll = Gtk.FileFilter()
        filter_dll.set_name("Lossless.dll")
        filter_dll.add_pattern("Lossless.dll")
        filechooser.add_filter(filter_dll)
        filechooser.set_filter(filter_dll)

        def on_response_fc(dialog_fc, response):
            if response == Gtk.ResponseType.ACCEPT:
                selected_file = dialog_fc.get_file().get_path()
                if selected_file and os.path.basename(selected_file) == "Lossless.dll":
                    entry_location.set_text(selected_file)
            destroy_and_release(dialog_fc)

        filechooser.connect("response", on_response_fc)
        filechooser.present()

    button_search_location.connect("clicked", on_search_location_clicked)

    box_location = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    box_location.append(entry_location)
    box_location.append(button_search_location)

    checkbox_enable = Gtk.CheckButton(label=_("Enable"))
    checkbox_enable.set_active(enabled)
    checkbox_enable.set_halign(Gtk.Align.START)

    label_multiplier = Gtk.Label(label=_("Multiplier"))
    label_multiplier.set_halign(Gtk.Align.START)
    spin_multiplier = Gtk.SpinButton()
    spin_multiplier.set_adjustment(Gtk.Adjustment(value=multiplier, lower=1, upper=20, step_increment=1))
    spin_multiplier.set_numeric(True)
    spin_multiplier.set_tooltip_text(_("Multiply the FPS"))

    label_flow = Gtk.Label(label=_("Flow Scale"))
    label_flow.set_halign(Gtk.Align.START)
    adjustment = Gtk.Adjustment(value=flow, lower=25, upper=100, step_increment=1)
    scale_flow = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
    scale_flow.set_digits(0)
    scale_flow.set_hexpand(True)
    scale_flow.set_value_pos(Gtk.PositionType.RIGHT)
    scale_flow.set_tooltip_text(_("Lower the internal motion estimation resolution"))

    checkbox_performance = Gtk.CheckButton(label=_("Performance Mode"))
    checkbox_performance.set_tooltip_text(_("Massively improve performance at the cost of quality"))
    checkbox_performance.set_active(performance)

    checkbox_hdr = Gtk.CheckButton(label=_("HDR Mode"))
    checkbox_hdr.set_tooltip_text(_("Enable special HDR-only behavior"))
    checkbox_hdr.set_active(hdr)

    label_present = Gtk.Label(label=_("Present Mode (Experimental)"))
    label_present.set_halign(Gtk.Align.START)

    combobox_present = IdComboBox()
    combobox_present.set_tooltip_text(_("Override the present mode"))

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
        label_location.set_sensitive(active)
        entry_location.set_sensitive(active)
        button_search_location.set_sensitive(active)
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
    grid.attach(label_location,         0, 1, 1, 1)
    grid.attach(box_location,           0, 2, 1, 1)
    grid.attach(label_multiplier,       0, 3, 1, 1)
    grid.attach(spin_multiplier,        0, 4, 1, 1)
    grid.attach(label_flow,             0, 5, 1, 1)
    grid.attach(scale_flow,             0, 6, 1, 1)
    grid.attach(checkbox_performance,   0, 7, 1, 1)
    grid.attach(checkbox_hdr,           0, 8, 1, 1)
    grid.attach(label_present,          0, 9, 1, 1)
    grid.attach(combobox_present,       0, 10, 1, 1)

    frame.set_child(grid)

    bottom_box = build_dialog_ok_cancel_box(dialog)

    content_area = dialog.get_content_area()
    content_area.append(frame)
    content_area.append(bottom_box)

    def on_response(dialog, response):
        result = (lossless_enabled, lossless_multiplier, lossless_flow,
                  lossless_performance, lossless_hdr, lossless_present)
        if response == Gtk.ResponseType.OK:
            if checkbox_enable.get_active() and not entry_location.get_text():
                entry_location.add_css_class("entry")
                return

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
            cfg.set_value("lossless-location", entry_location.get_text())
            cfg.save_config()

        destroy_and_release(dialog)
        callback(result)

    dialog.connect("response", on_response)
    dialog.present()


def suppress_adwaita_theme_warning():
    def handler(domain, level, message, user_data):
        if "gtk-application-prefer-dark-theme" in message:
            return
        GLib.log_default_handler(domain, level, message, user_data)

    GLib.log_set_handler(
        "Adwaita",
        GLib.LogLevelFlags.LEVEL_WARNING | GLib.LogLevelFlags.FLAG_FATAL | GLib.LogLevelFlags.FLAG_RECURSION,
        handler,
        None,
    )


_OVERRIDE_PRIORITY = Gtk.STYLE_PROVIDER_PRIORITY_USER + 1

_accent_css_provider = None


def apply_interface_customization(interface_theme, accent_color):
    style_manager = Adw.StyleManager.get_default()
    scheme_map = {
        "light": Adw.ColorScheme.FORCE_LIGHT,
        "dark": Adw.ColorScheme.FORCE_DARK,
    }
    style_manager.set_color_scheme(scheme_map.get(interface_theme, Adw.ColorScheme.DEFAULT))

    display = Gdk.Display.get_default()
    global _accent_css_provider
    if _accent_css_provider:
        Gtk.StyleContext.remove_provider_for_display(display, _accent_css_provider)
        _accent_css_provider = None

    if accent_color and accent_color != "system":
        fg_color = _contrasting_fg_color(accent_color)
        provider = Gtk.CssProvider()
        css = f"""
        @define-color accent_color {accent_color};
        @define-color accent_bg_color {accent_color};
        @define-color accent_fg_color {fg_color};
        @define-color theme_selected_bg_color {accent_color};
        @define-color theme_selected_fg_color {fg_color};
        """
        provider.load_from_data(css.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(display, provider, _OVERRIDE_PRIORITY)
        _accent_css_provider = provider


def _contrasting_fg_color(rgb_color):
    match = re.match(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', rgb_color)
    if not match:
        return "#ffffff"
    r, g, b = (int(v) / 255 for v in match.groups())
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#000000" if luminance > 0.55 else "#ffffff"


_steamgriddb_session = None


def get_steamgriddb_session():
    global _steamgriddb_session
    if _steamgriddb_session is None:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _steamgriddb_session = session
    return _steamgriddb_session


def fetch_steamgriddb_autocomplete(api_key, term, limit=10):
    import requests
    from urllib.parse import quote

    session = get_steamgriddb_session()
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = session.get(
            f"https://www.steamgriddb.com/api/v2/search/autocomplete/{quote(term)}",
            headers=headers, timeout=10,
        )
        response.raise_for_status()
        results = response.json().get("data") or []
        return [{"id": item["id"], "name": item["name"]} for item in results[:limit] if item.get("name")]
    except requests.RequestException:
        return []


def fetch_steamgriddb_candidates(api_key, game_name, limit=12, game_id=None, steam_appid=None):
    import requests
    from urllib.parse import quote

    session = get_steamgriddb_session()
    headers = {"Authorization": f"Bearer {api_key}"}
    result = {"game_id": None, "grids": [], "heroes": [], "icons": []}

    try:
        if steam_appid is not None:
            id_type, lookup_id = "steam", steam_appid
        else:
            if game_id is None:
                search = session.get(
                    f"https://www.steamgriddb.com/api/v2/search/autocomplete/{quote(game_name)}",
                    headers=headers, timeout=10,
                )
                search.raise_for_status()
                results = search.json().get("data") or []
                if not results:
                    return result
                game_id = results[0]["id"]
            id_type, lookup_id = "game", game_id
            result["game_id"] = game_id

        endpoints = {
            "grids": (f"https://www.steamgriddb.com/api/v2/grids/{id_type}/{lookup_id}", {"dimensions": "600x900"}),
            "heroes": (f"https://www.steamgriddb.com/api/v2/heroes/{id_type}/{lookup_id}", {}),
            "icons": (f"https://www.steamgriddb.com/api/v2/icons/{id_type}/{lookup_id}", {}),
        }

        def fetch_one(key):
            url, params = endpoints[key]
            try:
                response = session.get(url, headers=headers, params=params, timeout=10)
                if response.ok:
                    data = response.json().get("data") or []
                    return key, [
                        {"url": item["url"], "thumb": item.get("thumb") or item["url"]}
                        for item in data[:limit] if item.get("url")
                    ]
            except requests.RequestException:
                pass
            return key, []

        with ThreadPoolExecutor(max_workers=3) as pool:
            for key, items in pool.map(fetch_one, endpoints.keys()):
                result[key] = items

        return result
    except requests.RequestException:
        return result


def show_steamgriddb_picker(obj, category):
    from faugus.config_manager import ConfigManager

    cfg = ConfigManager()
    api_key = cfg.config.get('steamgriddb-api-key', '').strip('"')
    game_name = obj.entry_title.get_text().strip()
    game_id = getattr(obj, '_steamgriddb_suggestion_id', None)
    steam_appid = getattr(obj, '_steamgriddb_steam_appid', None)

    if not api_key:
        show_message_dialog(
            _("No SteamGridDB API key configured."),
            _("Add your API key in Settings first."),
            parent=obj,
        )
        return

    if not game_name:
        load_red_entry_css()
        obj.entry_title.add_css_class("entry")
        if hasattr(obj, "notebook"):
            obj.notebook.set_current_page(0)
        return

    titles = {
        "cover": _("Choose a cover"),
        "banner": _("Choose a banner"),
        "icon": _("Choose an icon"),
    }
    ratios = {"cover": 600 / 900, "banner": 1920 / 620, "icon": 1.0}
    keys = {"cover": "grids", "banner": "heroes", "icon": "icons"}

    dialog = Gtk.Dialog(title=titles.get(category), transient_for=obj)
    hide_dialog_action_area(dialog)
    dialog.set_modal(True)
    dialog.set_default_size(720, 480)

    closed_state = [False]

    def on_close_request(*_a):
        closed_state[0] = True
        return False
    dialog.connect("close-request", on_close_request)

    spinner = Gtk.Spinner()
    spinner.set_size_request(32, 32)
    spinner.start()
    spinner_box = Gtk.Box(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
    spinner_box.set_vexpand(True)
    spinner_box.set_hexpand(True)
    spinner_box.append(spinner)

    is_list = category == "banner"

    items_container = Gtk.FlowBox()
    items_container.set_selection_mode(Gtk.SelectionMode.NONE)
    items_container.set_row_spacing(8)
    items_container.set_column_spacing(8)
    items_container.set_margin_start(10)
    items_container.set_margin_end(10)
    items_container.set_margin_top(10)
    items_container.set_margin_bottom(10)

    if is_list:
        items_container.set_halign(Gtk.Align.FILL)
        items_container.set_valign(Gtk.Align.START)
        items_container.set_min_children_per_line(1)
        items_container.set_max_children_per_line(1)
        items_container.set_homogeneous(True)
    else:
        items_container.set_halign(Gtk.Align.CENTER)
        items_container.set_valign(Gtk.Align.CENTER)
        items_container.set_min_children_per_line(2)
        items_container.set_max_children_per_line(20)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_vexpand(True)
    scrolled.set_hexpand(True)
    scrolled.set_child(items_container)

    stack = Gtk.Stack()
    stack.add_named(spinner_box, "loading")
    stack.add_named(scrolled, "content")
    stack.set_visible_child_name("loading")

    dialog.get_content_area().append(stack)

    thumb_w = 660 if is_list else 160
    thumb_h = int(thumb_w / ratios.get(category, 1.0))

    loading_setter = {
        "cover": obj.set_cover_loading,
        "banner": obj.set_banner_loading,
        "icon": obj.set_icon_loading,
    }[category]

    def apply_selection(url):
        GLib.idle_add(loading_setter, True)

        def fetch_full():
            import requests
            try:
                content = verified_content(get_steamgriddb_session().get(url, timeout=15))
            except requests.RequestException as e:
                print(f"Error fetching selected {category}: {e}")
                GLib.idle_add(loading_setter, False)
                return

            if closed_state[0]:
                return

            def apply_ui():
                if closed_state[0]:
                    return False
                obj.apply_downloaded_artwork(category, content)
                loading_setter(False)
                destroy_and_release(dialog)
                return False
            GLib.idle_add(apply_ui)
        run_in_background(fetch_full)

    def populate(items):
        if closed_state[0]:
            return False
        if not items:
            empty_label = Gtk.Label(label=_("No results found."))
            empty_label.set_margin_top(20)
            items_container.append(empty_label)
        for item, pixbuf in items:
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            paintable = HiDpiPaintable(texture, thumb_w, thumb_h)
            picture = new_picture(paintable)
            picture.set_cursor(Gdk.Cursor.new_from_name("pointer"))

            picture_overlay = Gtk.Overlay()
            picture_overlay.set_child(picture)
            tint = Gtk.Box()
            tint.add_css_class("steamgriddb-focus-tint")
            tint.set_can_target(False)
            tint.set_hexpand(True)
            tint.set_vexpand(True)
            picture_overlay.add_overlay(tint)
            picture_overlay.set_measure_overlay(tint, False)

            child = Gtk.FlowBoxChild()
            if is_list:
                child.set_size_request(thumb_w, -1)
                child.set_halign(Gtk.Align.FILL)
                child.set_valign(Gtk.Align.START)
            else:
                child.set_hexpand(True)
                child.set_vexpand(True)
                child.set_halign(Gtk.Align.FILL)
                child.set_valign(Gtk.Align.FILL)
            child.set_child(picture_overlay)
            child.add_css_class("steamgriddb-candidate")
            child.gamepad_activate = lambda u=item["url"]: apply_selection(u)

            click = Gtk.GestureClick()
            click.set_button(Gdk.BUTTON_PRIMARY)
            click.connect("pressed", lambda g, n, x, y, u=item["url"]: apply_selection(u))
            picture.add_controller(click)

            items_container.append(child)
        stack.set_visible_child_name("content")
        return False

    def fetch_candidates():
        import requests

        candidates = fetch_steamgriddb_candidates(
            api_key, game_name, limit=24, game_id=game_id, steam_appid=steam_appid
        )
        items = candidates.get(keys.get(category), [])

        session = get_steamgriddb_session()

        def download_thumb(item):
            try:
                data = verified_content(session.get(item["thumb"], timeout=15))
                loader = GdkPixbuf.PixbufLoader()
                loader.write(data)
                loader.close()
                return (item, loader.get_pixbuf())
            except Exception as e:
                print(f"Error fetching thumbnail: {e}")
                return None

        results = []
        if items:
            with ThreadPoolExecutor(max_workers=8) as pool:
                downloaded = list(pool.map(download_thumb, items))
            results = [d for d in downloaded if d]

        if not closed_state[0]:
            GLib.idle_add(populate, results)

    run_in_background(fetch_candidates)

    dialog.present()


def get_average_color(image_path):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
    small = pixbuf.scale_simple(32, 32, GdkPixbuf.InterpType.BILINEAR)

    width = small.get_width()
    height = small.get_height()
    rowstride = small.get_rowstride()
    n_channels = small.get_n_channels()
    pixels = small.get_pixels()

    r_total = g_total = b_total = 0
    count = width * height

    for y in range(height):
        row_offset = y * rowstride
        for x in range(width):
            offset = row_offset + x * n_channels
            r_total += pixels[offset]
            g_total += pixels[offset + 1]
            b_total += pixels[offset + 2]

    return r_total // count, g_total // count, b_total // count


def get_dominant_color(image_path):
    import colorsys

    pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
    small = pixbuf.scale_simple(64, 64, GdkPixbuf.InterpType.BILINEAR)

    width = small.get_width()
    height = small.get_height()
    rowstride = small.get_rowstride()
    n_channels = small.get_n_channels()
    pixels = small.get_pixels()

    num_bins = 24
    hue_bins = {}

    for y in range(height):
        row_offset = y * rowstride
        for x in range(width):
            offset = row_offset + x * n_channels
            r, g, b = pixels[offset], pixels[offset + 1], pixels[offset + 2]

            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)

            if v < 0.15 or v > 0.95 or s < 0.25:
                continue

            bin_idx = int(h * num_bins) % num_bins
            bucket = hue_bins.setdefault(bin_idx, [0.0, 0.0, 0.0, 0.0])
            bucket[0] += r * s
            bucket[1] += g * s
            bucket[2] += b * s
            bucket[3] += s

    if not hue_bins:
        return get_average_color(image_path)

    r_total, g_total, b_total, weight = max(hue_bins.values(), key=lambda bucket: bucket[3])
    return int(r_total / weight), int(g_total / weight), int(b_total / weight)
