import bisect
import codecs
import ctypes
import math
import os
import functools
import json
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from faugus.path_manager import PathManager, GAMES_JSON, PRESETS_FILE, COMPATIBILITY_DIRS, FAUGUS_LAUNCHER_STATE_DIR, PROTON_CACHYOS, MANGOHUD_DIR, GAMEMODERUN, ICONS_DIR, COVERS_DIR, FILECHOOSER_FOLDERS_FILE, CONFIG_FILE_DIR
from gi.repository import Gtk, Gdk, Gio, GLib, GdkPixbuf, Pango, GObject, Adw

os.environ.setdefault("VK_LOADER_LAYERS_DISABLE", "VK_LAYER_LSFGVK_frame_generation")

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
            if ("GtkGizmo" in message and "reported min" in message) or any(
                s in message for s in ("gtk_css_node_insert_after", "mapped without a transient parent", "swapchain", "gdk_frame_timings_presented")
            ):
                return GLib.LogWriterOutput.HANDLED
            break
    return GLib.log_writer_default(log_level, fields, user_data)


GLib.log_set_writer_func(_log_writer_filter, None)


_background_executor = ThreadPoolExecutor(max_workers=32, thread_name_prefix="faugus-worker")


def run_in_background(fn, *args, **kwargs):
    return _background_executor.submit(fn, *args, **kwargs)


def idle_add_while_open(closed_event, fn, *args):
    def run():
        if not closed_event.is_set():
            fn(*args)
        return False
    GLib.idle_add(run)


def stop_request_path(gameid):
    return os.path.join(FAUGUS_LAUNCHER_STATE_DIR, f"stop-{gameid}")


def request_game_stop(gameid):
    if not gameid:
        return
    try:
        open(stop_request_path(gameid), "w").close()
    except OSError:
        pass


def kill_by_faugusid(gameid):
    if not gameid:
        return

    marker = f"FAUGUSID={gameid}".encode()
    own_pid = os.getpid()

    for entry in os.scandir("/proc"):
        if not entry.name.isdigit() or int(entry.name) == own_pid:
            continue
        try:
            with open(f"/proc/{entry.name}/environ", "rb") as f:
                environ = f.read()
        except OSError:
            continue
        if marker in environ.split(b"\0"):
            try:
                os.kill(int(entry.name), signal.SIGKILL)
            except OSError:
                pass


class HiDpiPaintable(GObject.GObject, Gdk.Paintable):
    def __init__(self, texture, width, height, loader=None, scale=1):
        super().__init__()
        self._texture = texture
        self._width = width
        self._height = height
        self._loader = loader
        self._scale = scale

    def do_get_intrinsic_width(self):
        return self._width

    def do_get_intrinsic_height(self):
        return self._height

    def do_snapshot(self, snapshot, width, height):
        self._texture.snapshot(snapshot, width, height)

    def set_texture(self, texture):
        self._texture = texture
        self.invalidate_contents()

    def set_scale(self, scale):
        if self._loader is None or scale == self._scale:
            return
        self._scale = scale
        self.set_texture(self._loader(scale))


class HiDpiMixin:
    def device_scale(self: Gtk.Widget):
        return max(1, self.get_scale_factor())

    def new_texture_from_image(self: Gtk.Widget, path, width=None, height=None, keep_aspect_ratio=False):
        if not (width and height):
            return Gdk.Texture.new_for_pixbuf(safe_load_pixbuf(path, None, None, keep_aspect_ratio))

        def build(scale):
            return texture_from_pixbuf(load_resized_pixbuf(path, int(width * scale), int(height * scale)), True)

        scale = self.device_scale() if isinstance(self, Gtk.Widget) else 1
        return HiDpiPaintable(build(scale), width, height, build, scale)


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


def load_resized_pixbuf(path, width, height):
    from PIL import Image
    try:
        with Image.open(path) as image:
            data = image.convert("RGBA").resize((width, height), Image.LANCZOS).tobytes()
    except OSError:
        return safe_load_pixbuf(path, width, height, False)
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(data), GdkPixbuf.Colorspace.RGB, True, 8, width, height, width * 4)


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


def make_descendants_untargetable(widget):
    child = widget.get_first_child()
    while child is not None:
        child.set_can_target(False)
        make_descendants_untargetable(child)
        child = child.get_next_sibling()


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


def new_icon(paintable):
    image = Gtk.Image.new_from_paintable(paintable)
    image.set_pixel_size(paintable.get_intrinsic_width())
    if isinstance(paintable, HiDpiPaintable):
        def sync_scale(widget, *_):
            paintable.set_scale(max(1, widget.get_scale_factor()))

        image.connect("map", sync_scale)
        image.connect("notify::scale-factor", sync_scale)
    return image


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


def create_accent_placeholder_paintable(width, height, scale, alpha=0.4, rgb=None):
    r, g, b = rgb if rgb is not None else get_effective_accent_rgb()

    pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, int(width * scale), int(height * scale))
    a = int(alpha * 255)
    pixbuf.fill((r << 24) | (g << 16) | (b << 8) | a)
    texture = Gdk.Texture.new_for_pixbuf(pixbuf)
    return HiDpiPaintable(texture, width, height)


texture_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="faugus-cover")


def modified_time(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def cover_key(path, installed, max_width, max_height):
    return (path, modified_time(path), installed, max_width, max_height)


def icon_key(path, installed, width, height):
    return (path, modified_time(path), installed, width, height)


def cover_identity(key):
    return key[0]


def icon_identity(key):
    return (key[0], key[3:5])


def texture_from_pixbuf(pixbuf, installed):
    if not installed:
        pixbuf.saturate_and_pixelate(pixbuf, 0.0, False)
    return Gdk.Texture.new_for_pixbuf(pixbuf)


def load_fitted_pixbuf(path, max_width, max_height):
    from PIL import Image
    try:
        with Image.open(path) as image:
            width, height = image.size
            if width > max_width or height > max_height:
                ratio = min(max_width / width, max_height / height)
                width, height = max(1, int(width * ratio)), max(1, int(height * ratio))
                image = image.resize((width, height), Image.LANCZOS)
            data = image.convert("RGBA").tobytes()
    except OSError:
        pixbuf = safe_load_pixbuf(path)
        if pixbuf.get_width() > max_width or pixbuf.get_height() > max_height:
            ratio = min(max_width / pixbuf.get_width(), max_height / pixbuf.get_height())
            pixbuf = pixbuf.scale_simple(
                max(1, int(pixbuf.get_width() * ratio)), max(1, int(pixbuf.get_height() * ratio)), GdkPixbuf.InterpType.BILINEAR)
        return pixbuf
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(data), GdkPixbuf.Colorspace.RGB, True, 8, width, height, width * 4)


def build_cover_texture(key):
    path, _, installed, max_width, max_height = key
    return texture_from_pixbuf(load_fitted_pixbuf(path, max_width, max_height), installed)


def load_full_texture(path):
    return Gdk.Texture.new_for_pixbuf(safe_load_pixbuf(path))


def release_unused_memory():
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def build_icon_texture(key):
    path, _, installed, width, height = key
    return texture_from_pixbuf(load_resized_pixbuf(path, width, height), installed)


class TextureCache:
    def __init__(self, build, identity):
        self.build = build
        self.identity = identity
        self.textures = {}
        self.pending = {}

    def get(self, key):
        texture = self.textures.get(key)
        if texture is None:
            texture = self.build(key)
            self.store(key, texture)
        return texture

    def store(self, key, texture):
        identity = self.identity(key)
        for stale in [other for other in self.textures if self.identity(other) == identity]:
            del self.textures[stale]
        self.textures[key] = texture

    def load(self, key, callback, loaded=None):
        texture = self.textures.get(key)
        if texture is not None:
            callback(texture)
            return

        waiting = self.pending.get(key)
        if waiting is not None:
            waiting.append(callback)
            return
        self.pending[key] = [callback]

        def finish(texture):
            callbacks = self.pending.pop(key, [])
            if texture is not None:
                self.store(key, texture)
                for waiting_callback in callbacks:
                    waiting_callback(texture)
                if loaded is not None:
                    loaded()
            return False

        def work():
            try:
                texture = self.build(key)
            except GLib.Error:
                texture = None
            GLib.idle_add(finish, texture)

        texture_executor.submit(work)

    def trim(self, keep_paths, limit):
        for key in [key for key in self.textures if key[0] not in keep_paths]:
            if len(self.textures) <= limit:
                break
            del self.textures[key]


LAZY_MODES = ("Covers", "Grid", "List")
SETTLE_SECONDS = 5
REFRESH_DELAY_MS = 100
MAX_WAIT_US = 400000


class LazyImages:
    def __init__(self, window):
        self.window = window
        self.loaded = set()
        self.near = set()
        self.geometry = None
        self.source = None
        self.settle_source = None
        self.started = 0

    def watch(self, scroll_box):
        for adjustment in (scroll_box.get_vadjustment(), scroll_box.get_hadjustment()):
            adjustment.connect("value-changed", lambda adjustment: self.schedule())
            adjustment.connect("notify::page-size", lambda adjustment, pspec: self.layout_changed())
            adjustment.connect("notify::upper", lambda adjustment, pspec: self.layout_changed())

    def layout_changed(self):
        self.geometry = None
        self.schedule()

    def schedule(self, restart=True):
        now = GLib.get_monotonic_time()
        if self.source is not None:
            if not restart or now - self.started > MAX_WAIT_US:
                return
            GLib.source_remove(self.source)
        else:
            self.started = now
        self.source = GLib.timeout_add(REFRESH_DELAY_MS, self.refresh)

    def mark_loaded(self, child):
        self.loaded.add(child)

    def unload(self, child):
        self.loaded.discard(child)
        self.window.unload_child_image(child)

    def reset(self):
        for child in list(self.loaded):
            self.unload(child)
        self.schedule()

    def build_geometry(self, scroll_box, horizontal):
        flowbox = self.window.flowbox
        entries = []
        for child in flowbox:
            if not child.get_child_visible() or child.get_height() <= 0:
                continue
            ok, bounds = child.compute_bounds(flowbox)
            if not ok:
                continue
            start, size = (bounds.origin.x, bounds.size.width) if horizontal else (bounds.origin.y, bounds.size.height)
            entries.append((start, start + size, child))
        entries.sort(key=lambda entry: entry[0])
        starts = [entry[0] for entry in entries]
        longest = max((end - start for start, end, _ in entries), default=0)
        self.geometry = (entries, starts, longest, horizontal, scroll_box.get_width(), scroll_box.get_height())

    def children_near(self, scroll_box, horizontal, view):
        geometry = self.geometry
        if geometry is None or geometry[3:] != (horizontal, scroll_box.get_width(), scroll_box.get_height()):
            self.build_geometry(scroll_box, horizontal)
            geometry = self.geometry

        entries, starts, longest = geometry[:3]
        ok, origin = self.window.flowbox.compute_bounds(scroll_box)
        if not ok:
            return set()
        offset = origin.origin.x if horizontal else origin.origin.y
        low = -view - offset
        high = 2 * view - offset
        first = bisect.bisect_left(starts, low - longest)
        last = bisect.bisect_right(starts, high)
        return {child for start, end, child in entries[first:last] if end >= low and start <= high}

    def refresh(self):
        self.source = None
        window = self.window
        scroll_box = getattr(window, "scroll_box", None)
        if window.interface_mode not in LAZY_MODES or scroll_box is None or not window.get_realized():
            return False

        horizontal = scroll_box.get_policy()[1] == Gtk.PolicyType.NEVER
        view = scroll_box.get_width() if horizontal else scroll_box.get_height()
        if view <= 0:
            return False

        near = self.children_near(scroll_box, horizontal, view)
        for child in near - self.loaded:
            self.loaded.add(child)
            window.load_child_image(child)
        for child in [child for child in self.loaded if child not in near or child.get_parent() is None]:
            self.unload(child)
        window.trim_image_caches(near)
        self.near = near
        if self.settle_source is not None:
            GLib.source_remove(self.settle_source)
        self.settle_source = GLib.timeout_add_seconds(SETTLE_SECONDS, self.settle)
        return False

    def settle(self):
        self.settle_source = None
        self.window.trim_image_caches(self.near, tight=True)
        release_unused_memory()
        return False


SMOOTHING = 18
MIN_PADDING = 10
EDGE_TOLERANCE = 20
SETTLE_THRESHOLD = 0.5


class SmoothScroll:
    def __init__(self, window, scroll_box, flowbox):
        self.scroll_box = scroll_box
        self.flowbox = flowbox
        self.adjustment = None
        self.target = 0.0
        self.last = 0.0
        self.time = 0
        self.tick = None

        window.connect("notify::focus-widget", self.on_focus_changed)
        controller = Gtk.EventControllerScroll()
        controller.set_flags(Gtk.EventControllerScrollFlags.BOTH_AXES)
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("scroll", self.on_wheel)
        scroll_box.add_controller(controller)

    @property
    def horizontal(self):
        return self.scroll_box.get_policy()[1] == Gtk.PolicyType.NEVER

    def main_adjustment(self):
        return self.scroll_box.get_hadjustment() if self.horizontal else self.scroll_box.get_vadjustment()

    def current_target(self, adjustment):
        return self.target if self.adjustment is adjustment else adjustment.get_value()

    def stop(self):
        if self.tick is not None:
            self.scroll_box.remove_tick_callback(self.tick)
            self.tick = None
        self.adjustment = None

    def on_tick(self, widget, clock):
        current = self.adjustment.get_value()
        if abs(current - self.last) > SETTLE_THRESHOLD:
            self.stop()
            return GLib.SOURCE_REMOVE

        now = clock.get_frame_time()
        elapsed = (now - self.time) / 1000000
        self.time = now
        value = current + (self.target - current) * (1 - math.exp(-elapsed * SMOOTHING))
        if abs(self.target - value) < SETTLE_THRESHOLD:
            value = self.target
        self.adjustment.set_value(value)
        self.last = self.adjustment.get_value()
        if value == self.target:
            self.stop()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def animate_to(self, adjustment, target):
        target = max(adjustment.get_lower(), min(target, adjustment.get_upper() - adjustment.get_page_size()))
        frame_clock = self.scroll_box.get_frame_clock()
        if frame_clock is None:
            adjustment.set_value(target)
            return
        self.target = target
        self.adjustment = adjustment
        self.last = adjustment.get_value()
        if self.tick is None:
            self.time = frame_clock.get_frame_time()
            self.tick = self.scroll_box.add_tick_callback(self.on_tick)

    def on_wheel(self, controller, dx, dy):
        if controller.get_unit() != Gdk.ScrollUnit.WHEEL:
            return False
        adjustment = self.main_adjustment()
        if adjustment.get_upper() <= adjustment.get_page_size():
            return False

        delta = dx + dy if self.horizontal else dy
        step = adjustment.get_page_size() ** (2 / 3)
        self.animate_to(adjustment, self.current_target(adjustment) + delta * step)
        return True

    def on_focus_changed(self, window, pspec):
        focused = window.get_focus()
        if isinstance(focused, Gtk.FlowBoxChild) and focused.get_parent() is self.flowbox:
            self.show_child(focused)

    def show_child(self, child):
        horizontal = self.horizontal
        adjustment = self.main_adjustment()
        ok, bounds = child.compute_bounds(self.scroll_box)
        if not ok:
            return
        if horizontal:
            start, size, view = bounds.origin.x, bounds.size.width, self.scroll_box.get_width()
        else:
            start, size, view = bounds.origin.y, bounds.size.height, self.scroll_box.get_height()
        padding = max(self.flowbox.get_margin_top(), MIN_PADDING)

        base = self.current_target(adjustment)
        start -= base - adjustment.get_value()
        target = base

        ok, in_flowbox = child.compute_bounds(self.flowbox)
        at_start = at_end = False
        if ok and not horizontal:
            at_start = in_flowbox.origin.y < EDGE_TOLERANCE
            at_end = self.flowbox.get_height() - (in_flowbox.origin.y + in_flowbox.size.height) < EDGE_TOLERANCE

        if at_end:
            target = adjustment.get_upper()
        elif at_start:
            target = adjustment.get_lower()
        elif start + size > view - padding:
            target = base + start + size - (view - padding)
        elif start < padding:
            target = base - (padding - start)
        if target != base:
            self.animate_to(adjustment, target)


REVEAL_DURATION_MS = 150
HIDE_DURATION_MS = 400
HOT_ZONE_PX = 24


class AutoHideBar:
    def __init__(self, revealer, edge):
        self.revealer = revealer
        self.edge = edge
        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.widget.append(revealer)
        self.motion = Gtk.EventControllerMotion()
        self.widget.add_controller(self.motion)
        self.pointer_inside = False


class AutoHide:
    def __init__(self, window):
        self.window = window
        self.bars = []
        self.pinned = set()
        self.held = set()
        self.pointer_y = None

        window.connect("notify::focus-widget", lambda window, pspec: window.auto_hide_enabled and self.apply())
        window_motion = Gtk.EventControllerMotion()
        window_motion.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        window_motion.connect("motion", lambda controller, x, y: self.on_pointer(y))
        window_motion.connect("leave", lambda controller: self.on_pointer(None))
        window.add_controller(window_motion)

    def wrap(self, content, edge):
        revealer = Gtk.Revealer()
        revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_UP if edge == "bottom" else Gtk.RevealerTransitionType.SLIDE_DOWN
        )
        revealer.set_reveal_child(True)
        revealer.set_child(content)

        bar = AutoHideBar(revealer, edge)
        bar.motion.connect("notify::contains-pointer", lambda controller, pspec: self.refresh(bar))
        self.bars = [other for other in self.bars if other.widget.get_parent() is not None]
        self.bars.append(bar)
        self.refresh(bar)
        return bar.widget

    def on_pointer(self, y):
        if not self.window.auto_hide_enabled:
            return
        self.pointer_y = y
        if y is None:
            self.held = {bar.edge for bar in self.bars if bar.pointer_inside}
            return
        self.held = set()
        for bar in self.bars:
            bar.pointer_inside = bar.motion.props.contains_pointer or self.in_hot_zone(bar)
        self.apply()

    def in_hot_zone(self, bar):
        if self.pointer_y is None:
            return False
        ok, bounds = bar.widget.compute_bounds(self.window)
        if not ok:
            return False
        if bar.edge == "bottom":
            return self.pointer_y >= bounds.origin.y + bounds.size.height - HOT_ZONE_PX
        return self.pointer_y <= bounds.origin.y + HOT_ZONE_PX

    def refresh(self, bar):
        focused = self.window.get_focus()
        focus_inside = focused is not None and focused.is_ancestor(bar.widget)
        pointer_near = bar.motion.props.contains_pointer or self.in_hot_zone(bar) or bar.edge in self.held
        hidden = self.window.auto_hide_enabled and not pointer_near and not focus_inside and bar.edge not in self.pinned
        bar.revealer.set_transition_duration(HIDE_DURATION_MS if hidden else REVEAL_DURATION_MS)
        bar.revealer.set_reveal_child(not hidden)

    def apply(self):
        for bar in self.bars:
            self.refresh(bar)

    def reveal(self, edge):
        self.pinned.add(edge)
        was_hidden = False
        for bar in self.bars:
            if bar.edge != edge or bar.widget.get_parent() is None:
                continue
            was_hidden = was_hidden or not bar.revealer.get_reveal_child()
            bar.revealer.set_transition_duration(REVEAL_DURATION_MS)
            bar.revealer.set_reveal_child(True)
        return was_hidden

    def unpin(self, edge):
        self.pinned.discard(edge)
        self.apply()

    def keep_bottom_anchored(self, adjustment):
        previous = [adjustment.get_page_size()]

        def on_page_size_changed(adjustment, pspec):
            page_size = adjustment.get_page_size()
            delta = previous[0] - page_size
            previous[0] = page_size
            if not delta or not self.window.auto_hide_enabled:
                return
            animating = {
                bar.edge for bar in self.bars
                if bar.revealer.get_reveal_child() != bar.revealer.get_child_revealed()
            }
            if animating == {"bottom"}:
                adjustment.set_value(adjustment.get_value() + delta)

        adjustment.connect("notify::page-size", on_page_size_changed)


def set_spinner_loading(spinners, loading):
    for spinner in spinners:
        spinner.set_visible(loading)
        spinner.set_spinning(loading)
        spinner.dim_overlay.set_visible(loading)


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
        factory.connect("bind", self._on_button_factory_bind)
        self.set_factory(factory)
        list_factory = Gtk.SignalListItemFactory()
        list_factory.connect("setup", self._on_factory_setup)
        list_factory.connect("bind", self._on_full_text_list_factory_bind)
        self.set_list_factory(list_factory)
        self._list_factory_bind_func = self._on_full_text_list_factory_bind
        self.connect("notify::selected", self._on_notify_selected)
        self.get_first_child().connect("toggled", play_navigate_if_window_active)

    def _on_factory_setup(self, factory, list_item):
        label = Gtk.Label(xalign=0)
        list_item.set_child(label)

    def _bind_label(self, label, text):
        label.set_text(text)
        if self._ellipsize:
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_max_width_chars(self._max_width_chars)

    def _on_factory_bind(self, factory, list_item):
        item = list_item.get_item()
        text = item.get_string() if item else ""
        self._bind_label(list_item.get_child(), self._short_label_map.get(text, text))

    def _on_button_factory_bind(self, factory, list_item):
        self._on_factory_bind(factory, list_item)
        label = list_item.get_child()
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(self._max_width_chars)

    def _on_full_text_list_factory_bind(self, factory, list_item):
        item = list_item.get_item()
        self._bind_label(list_item.get_child(), item.get_string() if item else "")

    def _on_notify_selected(self, *args):
        if not self._suppress:
            self.emit("changed")

    def release(self):
        factory = self.get_factory()
        if factory:
            try:
                factory.disconnect_by_func(self._on_factory_setup)
                factory.disconnect_by_func(self._on_button_factory_bind)
            except TypeError:
                pass
        list_factory = self.get_list_factory()
        if list_factory:
            try:
                list_factory.disconnect_by_func(self._on_factory_setup)
                list_factory.disconnect_by_func(self._list_factory_bind_func)
            except TypeError:
                pass
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

    def get_ids(self):
        return list(self._ids)


def apply_titlebar_preference(window):
    from faugus.config_manager import ConfigManager
    if ConfigManager().config.get('header-bar', 'False') == 'True':
        window.set_titlebar(Gtk.HeaderBar())
        add_css_once(
            "headerbar_title_size",
            """
            headerbar .title {
                font-size: 1em;
                font-weight: bold;
            }
            """,
        )


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


def track_cell_editing(renderer):
    state = {"editable": None}

    def on_editing_started(r, editable, path):
        state["editable"] = editable
        editable.connect("remove-widget", lambda e: state.update(editable=None))

    renderer.connect("editing-started", on_editing_started)
    return lambda: state["editable"] and state["editable"].editing_done()


def build_bottom_button_box(button_cancel, button_ok, *middle_buttons):
    bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    bottom_box.set_homogeneous(True)
    bottom_box.set_margin_start(10)
    bottom_box.set_margin_end(10)
    bottom_box.set_margin_bottom(10)
    bottom_box.append(button_cancel)
    for button in middle_buttons:
        bottom_box.append(button)
    bottom_box.append(button_ok)
    return bottom_box


def build_dialog_ok_cancel_box(dialog):
    button_cancel = Gtk.Button(label=_("Cancel"))
    button_cancel.set_hexpand(True)
    button_cancel.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.CANCEL))

    button_ok = Gtk.Button(label=_("Ok"))
    button_ok.set_hexpand(True)
    button_ok.set_focus_on_click(False)
    button_ok.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.OK))

    return build_bottom_button_box(button_cancel, button_ok)


def _release_widgets(widget):
    if isinstance(widget, IdComboBox):
        widget.release()
    if isinstance(widget, Gtk.Picture):
        widget.set_paintable(None)
    elif isinstance(widget, Gtk.Image):
        widget.clear()
    for child in widget_children(widget):
        _release_widgets(child)
    if isinstance(widget, Gtk.Popover):
        widget.popdown()
        widget.unparent()


def destroy_and_release(widget):
    if isinstance(widget, Gtk.NativeDialog):
        widget.destroy()
        widget.__dict__.clear()
        return

    if isinstance(widget, Gtk.Window):
        widget.set_focus(None)

    _release_widgets(widget)

    if isinstance(widget, Gtk.Dialog):
        content = widget.get_content_area()
        for child in widget_children(content):
            content.remove(child)
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


LOG_CHUNK_BYTES = 128 * 1024
LOG_SLICE_US = 4000


def load_text_progressively(path, text_view, is_open, on_loaded):
    log_file = open(path, "rb")
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    text_buffer = Gtk.TextBuffer()

    def step():
        deadline = GLib.get_monotonic_time() + LOG_SLICE_US
        while is_open():
            data = log_file.read(LOG_CHUNK_BYTES)
            text = decoder.decode(data, final=not data)
            if text:
                text_buffer.insert(text_buffer.get_end_iter(), text)
            if not data:
                text_view.set_buffer(text_buffer)
                on_loaded(text_buffer)
                break
            if GLib.get_monotonic_time() >= deadline:
                return GLib.SOURCE_CONTINUE
        log_file.close()
        return GLib.SOURCE_REMOVE

    GLib.idle_add(step)


def load_json_file(filepath, default=None):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []


def load_json_file_or_none(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as e:
        print(f"Faugus Launcher: refusing to touch {filepath}, failed to read it ({e})")
        return None


def save_json_file(data, filepath, indent=4):
    atomic_write(filepath, lambda f: json.dump(data, f, indent=indent, ensure_ascii=False))


def format_title(title):
    title = title.strip().lower()
    title = re.sub(r"[^\w\s-]", "", title)
    title = re.sub(r"\s+", "-", title)
    return title


def unique_gameid(base, existing_ids):
    if not base or base not in existing_ids:
        return base
    n = 2
    while f"{base}-{n}" in existing_ids:
        n += 1
    return f"{base}-{n}"


def new_file_chooser(parent, title, action, accept_label=None, cancel_label=None):
    config = load_json_file(CONFIG_FILE_DIR, default={})
    gamepad_navigation = config.get('gamepad-navigation', 'False') == 'True'

    if not gamepad_navigation:
        dialog = Gtk.FileChooserNative(
            title=title,
            transient_for=parent,
            modal=True,
            action=action,
            accept_label=accept_label or _("Open"),
            cancel_label=cancel_label or _("Cancel"),
        )
        dialog.present = dialog.show
        return dialog

    dialog = Gtk.FileChooserDialog(
        title=title,
        transient_for=parent,
        modal=True,
        action=action,
    )
    dialog.add_button(cancel_label or _("Cancel"), Gtk.ResponseType.CANCEL)
    dialog.add_button(accept_label or _("Open"), Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.ACCEPT)
    add_css_once(
        "filechooser_grid_selection",
        """
        filechooser gridview > child:selected,
        filechooser gridview > child:selected:hover {
            background-color: @theme_selected_bg_color;
            color: @theme_selected_fg_color;
        }
        """,
    )
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
        if response != Gtk.ResponseType.ACCEPT:
            return

        selected = fc.get_file()
        path = selected.get_path() if selected else None
        if not path:
            return

        folder = path if os.path.isdir(path) else os.path.dirname(path)
        if folder and _last_filechooser_folder.get(key) != folder:
            _last_filechooser_folder[key] = folder
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


def list_prefix_shortcuts(prefix):
    roots = (
        os.path.join(prefix, "drive_c", "users"),
        os.path.join(prefix, "drive_c", "ProgramData"),
    )
    found = set()
    for root in roots:
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                if filename.lower().endswith(".lnk"):
                    found.add(os.path.join(dirpath, filename))
    return found


def parse_lnk_target_path(lnk_path):
    try:
        with open(lnk_path, "rb") as f:
            data = f.read()
    except OSError:
        return None

    if len(data) < 76 or data[:4] != b"\x4c\x00\x00\x00":
        return None

    link_flags = int.from_bytes(data[20:24], "little")
    has_link_target_id_list = 0x01
    has_link_info = 0x02

    offset = 76
    if link_flags & has_link_target_id_list:
        if offset + 2 > len(data):
            return None
        id_list_size = int.from_bytes(data[offset:offset + 2], "little")
        offset += 2 + id_list_size

    if not (link_flags & has_link_info) or offset + 8 > len(data):
        return None

    link_info_start = offset
    link_info_header_size = int.from_bytes(data[link_info_start + 4:link_info_start + 8], "little")
    link_info_flags = int.from_bytes(data[link_info_start + 8:link_info_start + 12], "little")

    volume_id_and_local_base_path = 0x01
    if not (link_info_flags & volume_id_and_local_base_path):
        return None

    local_base_path_offset = int.from_bytes(data[link_info_start + 16:link_info_start + 20], "little")
    local_base_path_offset_unicode = 0
    if link_info_header_size >= 0x24 and link_info_start + 32 <= len(data):
        local_base_path_offset_unicode = int.from_bytes(
            data[link_info_start + 28:link_info_start + 32], "little"
        )

    if local_base_path_offset_unicode:
        start = link_info_start + local_base_path_offset_unicode
        end = data.find(b"\x00\x00", start)
        if end == -1:
            return None
        if (end - start) % 2 != 0:
            end += 1
        try:
            return data[start:end].decode("utf-16-le")
        except UnicodeDecodeError:
            return None

    if local_base_path_offset:
        start = link_info_start + local_base_path_offset
        end = data.find(b"\x00", start)
        if end == -1:
            return None
        try:
            return data[start:end].decode("cp1252", errors="replace")
        except UnicodeDecodeError:
            return None

    return None


def windows_path_to_prefix_path(win_path, prefix):
    win_path = win_path.strip().strip('"')
    if len(win_path) < 2 or win_path[1] != ":":
        return None
    drive_letter = win_path[0].lower()
    rest = re.sub(r'\\+', '/', win_path[2:]).lstrip("/")
    if drive_letter == "c":
        return os.path.join(prefix, "drive_c", rest)
    dosdevice = os.path.join(prefix, "dosdevices", f"{drive_letter}:")
    if os.path.islink(dosdevice):
        return os.path.join(os.path.realpath(dosdevice), rest)
    return None


def resolve_case_insensitive_path(path):
    if os.path.isfile(path):
        return path

    directory = os.path.dirname(path)
    target_name = os.path.basename(path)
    if not os.path.isdir(directory):
        return None

    try:
        for entry in os.listdir(directory):
            if entry.lower() == target_name.lower() and os.path.isfile(os.path.join(directory, entry)):
                return os.path.join(directory, entry)
    except OSError:
        pass

    return None


_SHORTCUT_UTILITY_KEYWORDS = ("uninstall", "setup", "config", "readme")


def is_utility_shortcut(*names):
    combined = " ".join(n for n in names if n).lower()
    return any(keyword in combined for keyword in _SHORTCUT_UTILITY_KEYWORDS)


def resolve_new_shortcuts(prefix, shortcut_paths):
    by_name = {}
    for path in shortcut_paths:
        by_name.setdefault(os.path.basename(path).lower(), []).append(path)

    results = []
    for paths in by_name.values():
        name = os.path.splitext(os.path.basename(paths[0]))[0].strip()
        if not name or is_utility_shortcut(os.path.basename(paths[0]), name):
            continue

        target = None
        for lnk_path in paths:
            target_win = parse_lnk_target_path(lnk_path)
            if not target_win:
                continue
            candidate = windows_path_to_prefix_path(target_win, prefix)
            resolved = resolve_case_insensitive_path(candidate) if candidate else None
            if resolved and resolved.lower().endswith(".exe"):
                target = resolved
                break

        if not target:
            continue

        dirs = [os.path.dirname(p).replace(os.sep, "/") for p in paths]
        results.append({
            "name": name,
            "target": target,
            "on_desktop": any("/Desktop" in d for d in dirs),
            "on_appmenu": any("/Start Menu" in d for d in dirs),
            "shortcut_path": paths[0],
        })

    return results


def pick_best_shortcut(resolved):
    if not resolved:
        return None
    return min(resolved, key=lambda r: r["name"].lower())


def detect_installed_executable(prefix, existing_shortcuts):
    new_shortcuts = list_prefix_shortcuts(prefix) - existing_shortcuts
    resolved = resolve_new_shortcuts(prefix, new_shortcuts)
    best = pick_best_shortcut(resolved)
    return best["target"] if best else None


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


UI_SOUND_KINDS = ("navigate", "confirm", "cancel", "warning")
UI_SOUND_CONFIG_KEYS = (
    "interface-sounds-enabled",
    "interface-sounds-theme",
    "interface-sounds-volume",
    *(f"interface-sounds-custom-{kind}" for kind in UI_SOUND_KINDS),
)


def get_ui_sound_path(theme, kind, custom_path=""):
    if theme == "custom":
        return expand_path(custom_path)
    return PathManager.get_asset(os.path.join("sounds", f"{theme}-{kind}.ogg"))


def play_sound_file(path, volume=1.0):
    if not path or not os.path.isfile(path):
        return
    media = Gtk.MediaFile.new_for_filename(path)
    media.set_volume(0)
    media.set_volume(volume ** (1 / 3))
    _active_media_streams.append(media)

    def on_notify_ended(stream, _pspec):
        if stream.get_ended() and stream in _active_media_streams:
            _active_media_streams.remove(stream)

    media.connect("notify::ended", on_notify_ended)
    media.play()


_ui_sound_config = None
_queued_ui_sound = None
_last_navigate_sound = 0
_warm_up_media = None
_ui_sound_requests = 0


def reload_ui_sound_config():
    global _ui_sound_config
    _ui_sound_config = None


def _get_ui_sound_config():
    global _ui_sound_config
    if _ui_sound_config is None:
        _ui_sound_config = load_json_file(CONFIG_FILE_DIR, default={})
    return _ui_sound_config


def preview_ui_sound_config(values):
    global _ui_sound_config
    _ui_sound_config = {**_get_ui_sound_config(), **values}


def ui_sounds_enabled():
    return _get_ui_sound_config().get("interface-sounds-enabled", "False") == "True"


def play_ui_sound(kind):
    global _queued_ui_sound, _ui_sound_requests
    _ui_sound_requests += 1
    if _queued_ui_sound is None:
        GLib.idle_add(_flush_ui_sound)
    if _queued_ui_sound is None or UI_SOUND_KINDS.index(kind) > UI_SOUND_KINDS.index(_queued_ui_sound):
        _queued_ui_sound = kind


def clear_queued_ui_sound():
    global _queued_ui_sound
    _queued_ui_sound = None


def _flush_ui_sound():
    global _queued_ui_sound, _last_navigate_sound
    kind, _queued_ui_sound = _queued_ui_sound, None
    if kind == "navigate":
        now = GLib.get_monotonic_time()
        if now - _last_navigate_sound < 50000:
            return False
        _last_navigate_sound = now
    if kind and ui_sounds_enabled():
        config = _get_ui_sound_config()
        path = get_ui_sound_path(
            config.get("interface-sounds-theme", "cloud"),
            kind,
            config.get(f"interface-sounds-custom-{kind}", ""),
        )
        play_sound_file(path, int(config.get("interface-sounds-volume", 50)) / 100)
    return False


def _on_window_focus_changed(window, _pspec):
    focus = window.get_focus()
    popover = focus.get_ancestor(Gtk.Popover) if focus else None
    had_focus = getattr(window, "_ui_sound_had_focus", False)
    same_popover = getattr(window, "_ui_sound_popover", None) is popover
    window._ui_sound_had_focus = focus is not None
    window._ui_sound_popover = popover
    if not (had_focus and focus is not None and same_popover):
        return
    if getattr(window, "_ui_sound_pointer_press", False):
        window._ui_sound_pointer_focus = True
    else:
        GLib.idle_add(_play_navigate_if_focus_visible, window, priority=GLib.PRIORITY_HIGH_IDLE)


def _play_navigate_if_focus_visible(window):
    if window.get_focus_visible() and window.is_active():
        play_ui_sound("navigate")
    return False


def _on_pointer_pressed(gesture, _n_press, x, y):
    window = gesture.get_widget()
    target = window.pick(x, y, Gtk.PickFlags.DEFAULT)
    window._ui_sound_pointer_press = True
    window._ui_sound_pointer_focus = False
    window._ui_sound_press_requests = _ui_sound_requests
    window._ui_sound_press_on_button = target is not None and any(target.get_ancestor(gtype) for gtype in (Gtk.Button, Gtk.CheckButton))


def _on_pointer_end(gesture, *_args):
    window = gesture.get_widget()
    window._ui_sound_pointer_press = False
    if getattr(window, "_ui_sound_pointer_focus", False):
        window._ui_sound_pointer_focus = False
        if window._ui_sound_press_requests == _ui_sound_requests and not window._ui_sound_press_on_button:
            play_ui_sound("navigate")


def _on_toplevels_changed(_toplevels, _position, _removed, added):
    if added:
        GLib.idle_add(_setup_new_toplevels, priority=GLib.PRIORITY_HIGH_IDLE)


def _setup_new_toplevels():
    toplevels = Gtk.Window.get_toplevels()
    windows = [toplevels.get_item(i) for i in range(toplevels.get_n_items())]
    new_windows = [window for window in windows if not getattr(window, "_ui_sound_ready", False)]
    for window in new_windows:
        window._ui_sound_ready = True
        focus = window.get_focus()
        window._ui_sound_had_focus = focus is not None
        window._ui_sound_popover = focus.get_ancestor(Gtk.Popover) if focus else None
        window.connect("notify::focus-widget", _on_window_focus_changed)
        window.connect("notify::visible", _on_window_visible_changed)
        pointer_press = Gtk.GestureClick(button=0, propagation_phase=Gtk.PropagationPhase.CAPTURE)
        pointer_press.connect("pressed", _on_pointer_pressed)
        pointer_press.connect("end", _on_pointer_end)
        window.add_controller(pointer_press)
    if any(window.get_visible() for window in new_windows) and any(window.get_visible() for window in windows if window not in new_windows):
        play_ui_sound("confirm")
    return False


def _on_window_visible_changed(window, _pspec):
    toplevels = Gtk.Window.get_toplevels()
    others = (toplevels.get_item(i) for i in range(toplevels.get_n_items()))
    if window.get_visible() and any(other is not window and other.get_visible() for other in others):
        play_ui_sound("confirm")


def _on_button_clicked(button):
    if not button.get_ancestor(Gtk.SpinButton):
        play_ui_sound("navigate")
    return True


def _on_toggled(button):
    play_navigate_if_window_active(button)
    return True


def play_navigate_if_window_active(widget, *_args):
    root = widget.get_root()
    if isinstance(root, Gtk.Window) and root.is_active():
        play_ui_sound("navigate")


def _on_activated(*_args):
    play_ui_sound("navigate")
    return True


def _on_dialog_response(dialog, response_id):
    if response_id in (Gtk.ResponseType.OK, Gtk.ResponseType.ACCEPT, Gtk.ResponseType.YES, Gtk.ResponseType.APPLY):
        play_ui_sound("confirm")
    elif response_id in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT, Gtk.ResponseType.CLOSE, Gtk.ResponseType.NO):
        play_ui_sound("cancel")
    return True


def mark_invalid_widget(widget, css_class="entry"):
    widget.add_css_class(css_class)
    play_ui_sound("warning")


def warm_up_sound_playback():
    global _warm_up_media
    if ui_sounds_enabled():
        _warm_up_media = Gtk.MediaFile.new_for_filename(get_ui_sound_path("cloud", "navigate"))
    return False


def install_ui_sound_hooks():
    Gtk.Window.get_toplevels().connect("items-changed", _on_toplevels_changed)
    GLib.idle_add(warm_up_sound_playback)
    for gtype in (Gtk.Button, Gtk.CheckButton, Gtk.CellRendererToggle, Gtk.ListBox, Gtk.ListView, Gtk.ColumnView, Gtk.GridView, Gio.SimpleAction, Gtk.Dialog):
        GObject.type_class_ref(gtype)
    GObject.add_emission_hook(Gtk.Button, "clicked", _on_button_clicked)
    GObject.add_emission_hook(Gtk.CheckButton, "toggled", _on_toggled)
    GObject.add_emission_hook(Gtk.CellRendererToggle, "toggled", _on_activated)
    GObject.add_emission_hook(Gtk.ListBox, "row-activated", _on_activated)
    GObject.add_emission_hook(Gtk.ListView, "activate", _on_activated)
    GObject.add_emission_hook(Gtk.ColumnView, "activate", _on_activated)
    GObject.add_emission_hook(Gtk.GridView, "activate", _on_activated)
    GObject.add_emission_hook(Gio.SimpleAction, "activate", _on_activated)
    GObject.add_emission_hook(Gtk.Dialog, "response", _on_dialog_response)


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
    parts.append(f"LSFG_PERFORMANCE_MODE={1 if lossless_performance else 0}")
    parts.append(f"LSFGVK_PERFORMANCE_MODE={1 if lossless_performance else 0}")
    parts.append(f"LSFG_HDR_MODE={1 if lossless_hdr else 0}")
    if lossless_present:
        parts.append(f"LSFG_EXPERIMENTAL_PRESENT_MODE={lossless_present}")
    return parts


def write_addapp_bat(bat_path, exe_path, addapp, addapp_delay, addapp_first, game_arguments):
    bat_path = expand_path(bat_path)
    exe_path = expand_path(exe_path)
    addapp = expand_path(addapp)
    game_line = f'start "" "z:{exe_path}" {game_arguments}\n' if game_arguments else f'start "" "z:{exe_path}"\n'
    addapp_line = f'start "" "z:{addapp}"\n'
    first, second = (addapp_line, game_line) if addapp_first else (game_line, addapp_line)
    with open(bat_path, "w") as f:
        f.write('@echo off\n')
        f.write(first)
        if addapp_delay:
            f.write(f'ping -n {addapp_delay} 127.0.0.1 >nul\n')
        f.write(second)


def is_valid_image(file_path):
    try:
        pixbuf = safe_load_pixbuf(file_path)
        return pixbuf is not None
    except Exception:
        return False


def show_message_dialog(text1, text2="", parent=None, confirm_label=None, cancel_label=None, callback=None, modal=True):
    dialog = Gtk.Dialog(title="Faugus", transient_for=parent)
    apply_titlebar_preference(dialog)
    hide_dialog_action_area(dialog)
    dialog.set_modal(modal)
    dialog.set_resizable(False)
    play_ui_sound("warning")

    content_area = dialog.get_content_area()
    content_area.set_halign(Gtk.Align.CENTER)
    content_area.set_valign(Gtk.Align.CENTER)
    content_area.set_vexpand(True)
    content_area.set_hexpand(True)

    frame = Gtk.Frame()
    frame.set_margin_start(10)
    frame.set_margin_end(10)
    frame.set_margin_top(10)
    frame.set_margin_bottom(10)

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

    frame.set_child(box_top)

    content_area.append(frame)
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


def on_treeview_query_tooltip(widget, x, y, keyboard_mode, tooltip, store):
    result = widget.get_path_at_pos(x, y)
    if result is not None:
        value = store[result[0]][0]
        if value.strip():
            tooltip.set_text(value)
            return True
    return False


def disable_mangohud_gamemode_if_missing(obj):
    obj.mangohud_enabled = os.path.exists(MANGOHUD_DIR)
    if not obj.mangohud_enabled:
        obj.checkbox_mangohud.set_sensitive(False)
        obj.checkbox_mangohud.set_active(False)
        obj.checkbox_mangohud.set_tooltip_text(
            _("Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more")
            + "\n" + _("MangoHud not found"))

    obj.gamemode_enabled = os.path.exists(GAMEMODERUN) or os.path.exists("/usr/games/gamemoderun")
    if not obj.gamemode_enabled:
        obj.checkbox_gamemode.set_sensitive(False)
        obj.checkbox_gamemode.set_active(False)
        obj.checkbox_gamemode.set_tooltip_text(
            _("Tweaks your system to improve performance") + "\n" + _("GameMode not found"))


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


BANNER_RATIO = 1920 / 620
COVER_RATIO = 2 / 3


def keep_banner_ratio(source, target, ratio=BANNER_RATIO, min_width=-1):
    state = {"width": -1}

    def on_tick(widget, frame_clock):
        width = widget.get_width()
        if width > 0 and width != state["width"]:
            state["width"] = width
            target.set_size_request(min_width, math.ceil(width / ratio))
        return True

    source.add_tick_callback(on_tick)


_css_providers = {}
_css_data = {}


def add_css_once(key, css, priority=Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION):
    css_provider = _css_providers.get(key)
    if css_provider is None:
        css_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css_provider, priority)
        _css_providers[key] = css_provider

    data = css.encode('utf-8') if isinstance(css, str) else css
    if _css_data.get(key) == data:
        return
    _css_data[key] = data
    css_provider.load_from_data(data)


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


def load_compact_time_spin_css():
    add_css_once(
        "compact_time_spin",
        """
        spinbutton.compact-time-spin {
            padding: 0;
        }
        spinbutton.compact-time-spin text {
            padding: 0 2px;
        }
        """,
        Gtk.STYLE_PROVIDER_PRIORITY_USER,
    )


def extract_ico(exe_path, output_path):
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

        from PIL import Image, ImageFile

        ImageFile.LOAD_TRUNCATED_IMAGES = True

        with Image.open(temp_ico) as icon:
            sizes = sorted(set(icon.info.get("sizes", [icon.size])), reverse=True)

            frame = None
            for size in sizes:
                try:
                    icon.size = size
                    frame = icon.convert("RGBA").resize((256, 256), Image.LANCZOS)
                    break
                except Exception:
                    continue

            if frame is None:
                print("An error occurred: no usable icon frame found.")
                return "error"

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


def open_uri(widget, uri):
    def on_launched(launcher, result):
        try:
            launcher.launch_finish(result)
        except GLib.Error as e:
            print(e.message)

    Gtk.UriLauncher.new(uri).launch(widget.get_root(), None, on_launched)


def on_button_kofi_clicked(widget):
    play_ui_sound("confirm")
    open_uri(widget, "https://ko-fi.com/K3K210EMDU")


def on_button_paypal_clicked(widget):
    play_ui_sound("confirm")
    open_uri(widget, "https://www.paypal.com/donate/?business=57PP9DVD3VWAN&no_recurring=0&currency_code=USD")


def expand_path(value):
    if not value:
        return value
    return os.path.expandvars(os.path.expanduser(value))


def latest_installed_umu_proton():
    names = set()
    for compat_dir in COMPATIBILITY_DIRS:
        if not os.path.isdir(compat_dir):
            continue
        for entry in os.listdir(compat_dir):
            if entry.startswith("UMU-Proton-") and os.path.isdir(os.path.join(compat_dir, entry)):
                names.add(entry)
    return max(names, key=version_key) if names else None


def update_games_json():
    games = load_json_file_or_none(GAMES_JSON)
    if not games:
        return

    changed = False

    for game in games:
        if game.get("runner") == "Proton-CachyOS":
            game["runner"] = "Proton-CachyOS (System)"
            changed = True

        if game.get("runner") == "":
            game["runner"] = latest_installed_umu_proton() or "Default"
            changed = True

        if game.get("disable_umu") and game.get("runtime") != "disable-runtime":
            game["runtime"] = "disable-runtime"
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

            if os.path.exists(png_path):
                new_icon_path = png_path
            elif os.path.exists(ico_path):
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


def resolve_game_runner(runner):
    if runner != "Default":
        return runner
    from faugus.config_manager import ConfigManager
    return ConfigManager().config.get('default-runner', '').strip('"')


def version_key(v):
    cleaned = re.sub(r'^[^\d]+', '', v)
    parts = re.split(r'(\d+)', cleaned)
    return [int(p) if p.isdigit() else p for p in parts]


_gpus_cache = None


def get_gpus():
    global _gpus_cache
    if _gpus_cache is None:
        _gpus_cache = scan_gpus()
    return [dict(gpu) for gpu in _gpus_cache]


def scan_gpus():
    gpus = []
    drm = "/sys/class/drm"
    try:
        cards = sorted(c for c in os.listdir(drm) if re.fullmatch(r"card\d+", c))
    except OSError:
        return gpus

    for card in cards:
        device = os.path.join(drm, card, "device")
        try:
            with open(os.path.join(device, "uevent")) as f:
                slot = next(l.split("=", 1)[1].strip() for l in f if l.startswith("PCI_SLOT_NAME="))
            with open(os.path.join(device, "vendor")) as f:
                vendor = f.read().strip()[2:]
            with open(os.path.join(device, "device")) as f:
                device_id = f.read().strip()[2:]
        except (OSError, StopIteration):
            continue

        name = slot
        try:
            out = subprocess.check_output(["lspci", "-s", slot, "-mm"], text=True, timeout=5)
            parts = shlex.split(out.strip())
            vendor_name = {"10de": "NVIDIA", "1002": "AMD", "8086": "Intel"}.get(vendor, parts[2])
            model = re.search(r"\[(.+)\]", parts[3])
            name = "{} {}".format(vendor_name, model.group(1) if model else parts[3])
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            pass

        gpus.append({"slot": slot, "vendor": vendor, "device": device_id, "name": name})
    return gpus


def populate_combobox_with_runners(combobox):
    combobox.append("Proton-CachyOS Latest", "Proton-CachyOS {} ({})".format(_("Latest"), _("Default")), "Proton-CachyOS {}".format(_("Latest")))
    combobox.append("Proton-GE Latest", "GE-Proton {}".format(_("Latest")))
    combobox.append("DW-Proton Latest", "DW-Proton {}".format(_("Latest")))
    combobox.append("Proton-Wineland Latest", "Proton-Wineland {}".format(_("Latest")))

    if os.path.exists(PROTON_CACHYOS):
        combobox.append("Proton-CachyOS (System)", "Proton-CachyOS ({})".format(_("System")))

    reserved_names = (
        "UMU-Latest", "LegacyRuntime",
        "Proton-GE Latest",
        "DW-Proton Latest", "Proton-CachyOS Latest",
        "Proton-Wineland Latest",
    )

    try:
        flatpak_dir = COMPATIBILITY_DIRS[-1] if len(COMPATIBILITY_DIRS) > 1 else None
        versions = {}
        for compat_dir in COMPATIBILITY_DIRS:
            if not os.path.exists(compat_dir):
                continue
            for entry in os.listdir(compat_dir):
                entry_path = os.path.join(compat_dir, entry)
                if not os.path.isdir(entry_path):
                    continue
                if entry in reserved_names:
                    if compat_dir == flatpak_dir:
                        combobox.append(entry_path, f"{entry} ({_('Flatpak')})")
                    continue
                if entry not in versions:
                    versions[entry] = compat_dir

        for version in sorted(versions, key=version_key, reverse=True):
            label = f"{version} ({_('Flatpak')})" if versions[version] == flatpak_dir else version
            combobox.append(version, label)
    except Exception as e:
        print(f"Error accessing the directory: {e}")

    combobox.set_active(0)
    combobox.configure_ellipsize(20)


GAME_FIELDS = [
    "gameid", "title", "path", "prefix",
    "launch_arguments", "game_arguments",
    "mangohud", "gamemode", "sdl_enabled",
    "runner",
    "addapp_enabled", "addapp", "addapp_bat", "addapp_delay", "addapp_first",
    "cover",
    "lossless_enabled", "lossless_multiplier", "lossless_flow",
    "lossless_performance", "lossless_hdr", "lossless_present",
    "playtime", "hidden", "no_sleep", "category", "icon",
    "steamgriddb_id", "pre_launch", "post_launch",
    "steam_user", "disable_umu", "runtime", "last_played",
]


def game_to_dict(game):
    return {field: getattr(game, field) for field in GAME_FIELDS}


def game_to_save_dict(game, hidden=None):
    d = {**game_to_dict(game),
         "mangohud": True if game.mangohud else "",
         "gamemode": True if game.gamemode else "",
         "sdl_enabled": True if game.sdl_enabled else "",
         "addapp_enabled": "addapp_enabled" if game.addapp_enabled else "",
         "disable_umu": True if game.disable_umu else ""}
    if hidden is not None:
        d["hidden"] = hidden
    return d


def prepare_game_kwargs(data):
    defaults = {f: "" for f in GAME_FIELDS}
    defaults.update({"playtime": 0, "hidden": False, "no_sleep": False,
                     "category": False})
    return {f: data.get(f, defaults[f]) for f in GAME_FIELDS}


def build_hook_command_grid(parent, title, key, tooltip):
    label = Gtk.Label(label=title)
    label.set_halign(Gtk.Align.START)

    entry = Gtk.Entry()
    entry.set_hexpand(True)
    entry.set_tooltip_text(tooltip)

    button_search = Gtk.Button()
    button_search.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
    button_search.set_size_request(50, -1)
    button_search.set_tooltip_text(tooltip)

    def on_search_clicked(widget):
        filechooser = new_file_chooser(parent, _("Select a command or script"), Gtk.FileChooserAction.OPEN)
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

    grid = build_grid(margin_bottom=False)
    grid.attach(label, 0, 0, 4, 1)
    grid.attach(entry, 0, 1, 3, 1)
    grid.attach(button_search, 3, 1, 1, 1)
    return grid, entry


class HookEntriesMixin:
    pre_launch = property(
        lambda self: self.entry_pre_launch.get_text().strip(),
        lambda self, value: self.entry_pre_launch.set_text(value))
    post_launch = property(
        lambda self: self.entry_post_launch.get_text().strip(),
        lambda self, value: self.entry_post_launch.set_text(value))


class LaunchArgumentsEditor:
    def __init__(self, current_launch_arguments=""):
        self.store_presets = Gtk.ListStore(str)
        for item in load_json_file(PRESETS_FILE, default=[]):
            self.store_presets.append([item])
        self.store_presets.append([""])

        self.store_args = Gtk.ListStore(str)
        self.set_arguments(current_launch_arguments)

        add_css_once(
            "launch_arguments_selected",
            ".selected-list:selected { background-color: @theme_selected_bg_color; color: @theme_selected_fg_color; }"
        )

        self.drag_origin = None

        self.tree_presets, box_presets, self.commit_presets_edit = self.build_editable_list(
            self.store_presets, _("Presets"))
        self.tree_args, box_args, self.commit_args_edit = self.build_editable_list(
            self.store_args, _("Launch Arguments"))
        self.tree_presets.gamepad_copy = self.copy_selected_preset

        sel_presets = self.tree_presets.get_selection()
        sel_args = self.tree_args.get_selection()
        sel_presets.connect("changed", lambda sel: sel_args.unselect_all() if sel.count_selected_rows() > 0 else None)
        sel_args.connect("changed", lambda sel: sel_presets.unselect_all() if sel.count_selected_rows() > 0 else None)

        self.widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.widget.set_margin_start(10)
        self.widget.set_margin_end(10)
        self.widget.set_margin_top(10)
        self.widget.set_margin_bottom(10)
        self.widget.set_vexpand(True)
        self.widget.append(box_args)
        self.widget.append(box_presets)

    def build_editable_list(self, store, header):
        tree = Gtk.TreeView(model=store)
        tree.connect("cursor-changed", play_navigate_if_window_active)
        tree.add_css_class("selected-list")
        tree.set_hexpand(True)
        tree.set_vexpand(True)
        renderer = Gtk.CellRendererText()
        renderer.set_property("editable", False)
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END)

        def on_edited(r, path, new_text):
            store[path][0] = new_text
            if path == str(len(store) - 1) and new_text.strip() != "":
                store.append([""])

        def on_key_press(controller, keyval, keycode, state):
            if keyval == Gdk.KEY_Delete:
                selection = tree.get_selection()
                model, treeiter = selection.get_selected()
                if treeiter is not None:
                    if model[treeiter][0] != "" or len(model) > 1:
                        model.remove(treeiter)
                    if len(model) == 0 or model[-1][0] != "":
                        model.append([""])
                return True
            return False

        commit_edit = track_cell_editing(renderer)

        renderer.connect("edited", on_edited)
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", on_key_press)
        tree.add_controller(key_controller)
        tree.keyboard_editable = True
        column = Gtk.TreeViewColumn("", renderer, text=0)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_expand(True)
        tree.append_column(column)

        def on_row_activated(tv, path, col):
            renderer.set_property("editable", True)
            tv.set_cursor(path, col, True)
            renderer.set_property("editable", False)

        tree.connect("row-activated", on_row_activated)
        tree.set_headers_visible(False)
        tree.set_has_tooltip(True)
        tree.connect("query-tooltip", on_treeview_query_tooltip, store)

        self.attach_drag_and_drop(tree)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(150)
        scroll.set_child(tree)

        label_header = Gtk.Label(label=header)
        label_header.set_halign(Gtk.Align.START)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_hexpand(True)
        box.set_vexpand(True)
        box.append(label_header)
        box.append(scroll)
        return tree, box, commit_edit

    def copy_selected_preset(self):
        path, _column = self.tree_presets.get_cursor()
        if path is None:
            return
        value = self.store_presets[path][0].strip()
        if value:
            self.store_args.insert(len(self.store_args) - 1, [value])

    def row_index_at(self, tree, x, y):
        bx, by = tree.convert_widget_to_bin_window_coords(x, y)
        info = tree.get_path_at_pos(int(bx), int(by))
        return info[0].get_indices()[0] if info else None

    def attach_drag_and_drop(self, tree):
        def on_prepare(source, x, y):
            index = self.row_index_at(tree, x, y)
            if index is None or not tree.get_model()[index][0].strip():
                return None
            self.drag_origin = (tree, index)
            return Gdk.ContentProvider.new_for_value(tree.get_model()[index][0])

        def on_drag_begin(source, drag):
            tree_origin, index = self.drag_origin
            Gtk.DragIcon.get_for_drag(drag).set_child(Gtk.Label(label=tree_origin.get_model()[index][0]))

        def on_drop(target, value, x, y):
            if self.drag_origin is None:
                return False
            tree_origin, src_index = self.drag_origin
            self.drag_origin = None
            store = tree.get_model()
            last = len(store) - 1
            dst_index = self.row_index_at(tree, x, y)
            if tree_origin is tree:
                dst_index = last - 1 if dst_index is None else min(dst_index, last - 1)
                if dst_index == src_index:
                    return False
                src_iter = store.get_iter((src_index,))
                dst_iter = store.get_iter((dst_index,))
                if dst_index > src_index:
                    store.move_after(src_iter, dst_iter)
                else:
                    store.move_before(src_iter, dst_iter)
                return True
            if tree is self.tree_args and tree_origin is self.tree_presets:
                dst_index = last if dst_index is None else min(dst_index, last)
                store.insert(dst_index, [value])
                return True
            return False

        source = Gtk.DragSource()
        source.set_actions(Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        source.connect("prepare", on_prepare)
        source.connect("drag-begin", on_drag_begin)
        tree.add_controller(source)

        target = Gtk.DropTarget.new(str, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        target.connect("drop", on_drop)
        tree.add_controller(target)

    def set_arguments(self, text):
        self.store_args.clear()
        for arg in text.split("\n"):
            if arg.strip():
                self.store_args.append([arg])
        self.store_args.append([""])

    def get_arguments(self):
        self.commit_args_edit()
        return "\n".join(row[0] for row in self.store_args if row[0].strip())

    def save_presets(self):
        self.commit_presets_edit()
        save_json_file([row[0] for row in self.store_presets if row[0].strip()], PRESETS_FILE)


class LaunchArgumentsMixin:
    launch_arguments = property(
        lambda self: self.launch_arguments_editor.get_arguments(),
        lambda self, value: self.launch_arguments_editor.set_arguments(value))


class AddAppPanel:
    def __init__(self, parent, enabled=False, path="", delay="", first=False):
        self.checkbox_enable = Gtk.CheckButton(label=_("Enable"))
        self.checkbox_enable.set_halign(Gtk.Align.START)

        self.label_path = Gtk.Label(label=_("Path"))
        self.label_path.set_halign(Gtk.Align.START)

        self.entry_path = Gtk.Entry()
        self.entry_path.set_tooltip_text(_("Path to the application"))
        self.entry_path.set_has_tooltip(True)
        self.entry_path.connect("query-tooltip", on_entry_query_tooltip)
        self.entry_path.set_hexpand(True)

        self.button_search = Gtk.Button()
        self.button_search.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        self.button_search.set_size_request(50, -1)

        def on_search_clicked(w):
            filechooser = new_file_chooser(
                parent,
                _("Select an additional application"),
                Gtk.FileChooserAction.OPEN,
            )
            set_file_chooser_start_folder(filechooser, "addapp", self.entry_path.get_text() or None)
            add_windows_file_filters(filechooser)

            def on_search_response(dialog_fc, resp):
                if resp == Gtk.ResponseType.ACCEPT:
                    selected_file = dialog_fc.get_file().get_path()
                    if selected_file:
                        self.entry_path.set_text(selected_file)
                destroy_and_release(dialog_fc)

            filechooser.connect("response", on_search_response)
            filechooser.present()

        self.button_search.connect("clicked", on_search_clicked)

        self.label_delay = Gtk.Label(label=_("Delay (seconds)"))
        self.label_delay.set_halign(Gtk.Align.START)

        self.spin_delay = Gtk.SpinButton()
        self.spin_delay.set_adjustment(Gtk.Adjustment(
            value=0, lower=0, upper=60, step_increment=1, page_increment=10, page_size=0))
        self.spin_delay.set_numeric(True)
        self.spin_delay.connect("value-changed", play_navigate_if_window_active)
        self.spin_delay.set_hexpand(True)

        self.checkbox_first = Gtk.CheckButton(label=_("Run the application first"))
        self.checkbox_first.set_halign(Gtk.Align.START)

        self.checkbox_enable.connect("toggled", self.on_enable_toggled)

        self.widget = build_grid()
        self.widget.attach(self.checkbox_enable, 0, 0, 1, 1)
        self.widget.attach(self.label_path, 0, 1, 1, 1)
        self.widget.attach(self.entry_path, 0, 2, 3, 1)
        self.widget.attach(self.button_search, 3, 2, 1, 1)
        self.widget.attach(self.label_delay, 0, 3, 1, 1)
        self.widget.attach(self.spin_delay, 0, 4, 4, 1)
        self.widget.attach(self.checkbox_first, 0, 5, 1, 1)

        self.set_values(enabled, path, delay, first)

    def on_enable_toggled(self, checkbox):
        active = checkbox.get_active()
        for widget in (self.label_path, self.entry_path, self.button_search, self.label_delay, self.spin_delay, self.checkbox_first):
            widget.set_sensitive(active)

    def set_values(self, enabled, path, delay, first):
        self.checkbox_enable.set_active(bool(enabled))
        self.entry_path.set_text(path)
        self.spin_delay.set_value(int(delay) if delay else 0)
        self.checkbox_first.set_active(bool(first))
        self.on_enable_toggled(self.checkbox_enable)

    def get_values(self):
        return (
            self.checkbox_enable.get_active(),
            self.entry_path.get_text(),
            self.spin_delay.get_text(),
            self.checkbox_first.get_active(),
        )


class AddAppMixin:
    addapp_enabled = property(
        lambda self: self.addapp_panel.checkbox_enable.get_active(),
        lambda self, value: self.addapp_panel.checkbox_enable.set_active(bool(value)))
    addapp = property(
        lambda self: self.addapp_panel.entry_path.get_text(),
        lambda self, value: self.addapp_panel.entry_path.set_text(value))
    addapp_delay = property(
        lambda self: self.addapp_panel.spin_delay.get_text(),
        lambda self, value: self.addapp_panel.spin_delay.set_value(int(value) if value else 0))
    addapp_first = property(
        lambda self: self.addapp_panel.checkbox_first.get_active(),
        lambda self, value: self.addapp_panel.checkbox_first.set_active(bool(value)))


class LosslessPanel:
    def __init__(self, parent):
        from faugus.config_manager import ConfigManager
        from faugus.steam_setup import LOSSLESS_DLL

        self.cfg = ConfigManager()
        current_location = self.cfg.config.get('lossless-location', '').strip('"')
        if not current_location and LOSSLESS_DLL:
            current_location = str(LOSSLESS_DLL)

        self.label_location = Gtk.Label(label=_("Lossless Scaling Location"))
        self.label_location.set_halign(Gtk.Align.START)

        load_red_entry_css()

        self.entry_location = Gtk.Entry()
        self.entry_location.set_text(current_location)
        self.entry_location.set_hexpand(True)
        self.entry_location.set_tooltip_text(_("Lossless.dll location"))
        self.entry_location.set_has_tooltip(True)
        self.entry_location.connect("query-tooltip", on_entry_query_tooltip)
        self.entry_location.connect("changed", on_entry_changed)

        self.button_search_location = Gtk.Button()
        self.button_search_location.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        self.button_search_location.set_size_request(50, -1)

        def on_search_location_clicked(widget):
            filechooser = new_file_chooser(
                parent,
                _("Select the Lossless.dll file"),
                Gtk.FileChooserAction.OPEN,
            )
            entry_value = self.entry_location.get_text()
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
                        self.entry_location.set_text(selected_file)
                destroy_and_release(dialog_fc)

            filechooser.connect("response", on_response_fc)
            filechooser.present()

        self.button_search_location.connect("clicked", on_search_location_clicked)

        self.checkbox_enable = Gtk.CheckButton(label=_("Enable"))
        self.checkbox_enable.set_halign(Gtk.Align.START)

        self.label_multiplier = Gtk.Label(label=_("Multiplier"))
        self.label_multiplier.set_halign(Gtk.Align.START)
        self.spin_multiplier = Gtk.SpinButton()
        self.spin_multiplier.set_adjustment(Gtk.Adjustment(value=1, lower=1, upper=20, step_increment=1))
        self.spin_multiplier.set_numeric(True)
        self.spin_multiplier.connect("value-changed", play_navigate_if_window_active)
        self.spin_multiplier.set_tooltip_text(_("Multiply the FPS"))

        self.label_flow = Gtk.Label(label=_("Flow Scale"))
        self.label_flow.set_halign(Gtk.Align.START)
        self.scale_flow = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL,
            adjustment=Gtk.Adjustment(value=100, lower=25, upper=100, step_increment=1))
        self.scale_flow.set_digits(0)
        self.scale_flow.set_hexpand(True)
        self.scale_flow.set_value_pos(Gtk.PositionType.RIGHT)
        self.scale_flow.set_tooltip_text(_("Lower the internal motion estimation resolution"))

        self.checkbox_performance = Gtk.CheckButton(label=_("Performance Mode"))
        self.checkbox_performance.set_tooltip_text(_("Massively improve performance at the cost of quality"))

        self.checkbox_hdr = Gtk.CheckButton(label=_("HDR Mode"))
        self.checkbox_hdr.set_tooltip_text(_("Enable special HDR-only behavior"))

        self.label_present = Gtk.Label(label=_("Present Mode (Experimental)"))
        self.label_present.set_halign(Gtk.Align.START)

        self.combobox_present = IdComboBox()
        self.combobox_present.set_tooltip_text(_("Override the present mode"))
        self.combobox_present.append("fifo", "VSync/FIFO ({})".format(_("Default")), "VSync/FIFO")
        self.combobox_present.append("mailbox", "Mailbox")
        self.combobox_present.append("immediate", "Immediate")

        self.checkbox_enable.connect("toggled", self.on_enable_toggled)

        box_location = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_location.append(self.entry_location)
        box_location.append(self.button_search_location)

        self.widget = build_grid()
        self.widget.attach(self.checkbox_enable, 0, 0, 1, 1)
        self.widget.attach(self.label_location, 0, 1, 1, 1)
        self.widget.attach(box_location, 0, 2, 1, 1)
        self.widget.attach(self.label_multiplier, 0, 3, 1, 1)
        self.widget.attach(self.spin_multiplier, 0, 4, 1, 1)
        self.widget.attach(self.label_flow, 0, 5, 1, 1)
        self.widget.attach(self.scale_flow, 0, 6, 1, 1)
        self.widget.attach(self.checkbox_performance, 0, 7, 1, 1)
        self.widget.attach(self.checkbox_hdr, 0, 8, 1, 1)
        self.widget.attach(self.label_present, 0, 9, 1, 1)
        self.widget.attach(self.combobox_present, 0, 10, 1, 1)

        self.set_values("", "", "", "", "", "")

    def on_enable_toggled(self, checkbox):
        active = checkbox.get_active()
        for widget in (self.label_location, self.entry_location, self.button_search_location, self.label_multiplier,
                       self.spin_multiplier, self.label_flow, self.scale_flow, self.checkbox_performance,
                       self.checkbox_hdr, self.label_present, self.combobox_present):
            widget.set_sensitive(active)

    def set_values(self, enabled, multiplier, flow, performance, hdr, present):
        self.checkbox_enable.set_active(bool(enabled))
        self.spin_multiplier.set_value(multiplier if multiplier != "" else 1)
        self.scale_flow.set_value(flow if flow != "" else 100)
        self.checkbox_performance.set_active(bool(performance))
        self.checkbox_hdr.set_active(bool(hdr))
        if not self.combobox_present.set_active_id(present):
            self.combobox_present.set_active(0)
        self.on_enable_toggled(self.checkbox_enable)

    def get_values(self):
        return (
            self.checkbox_enable.get_active(),
            self.spin_multiplier.get_value_as_int(),
            self.scale_flow.get_value(),
            self.checkbox_performance.get_active(),
            self.checkbox_hdr.get_active(),
            self.combobox_present.get_active_id(),
        )

    def validate(self):
        if self.checkbox_enable.get_active() and not self.entry_location.get_text():
            mark_invalid_widget(self.entry_location)
            return False
        return True

    def save_location(self):
        location = self.entry_location.get_text()
        if location != self.cfg.config.get('lossless-location', '').strip('"'):
            self.cfg.set_value("lossless-location", location)
            self.cfg.save_config()


class LosslessMixin:
    lossless_enabled = property(
        lambda self: self.lossless_panel.checkbox_enable.get_active(),
        lambda self, value: self.lossless_panel.checkbox_enable.set_active(bool(value)))
    lossless_multiplier = property(
        lambda self: self.lossless_panel.spin_multiplier.get_value_as_int(),
        lambda self, value: self.lossless_panel.spin_multiplier.set_value(value if value != "" else 1))
    lossless_flow = property(
        lambda self: self.lossless_panel.scale_flow.get_value(),
        lambda self, value: self.lossless_panel.scale_flow.set_value(value if value != "" else 100))
    lossless_performance = property(
        lambda self: self.lossless_panel.checkbox_performance.get_active(),
        lambda self, value: self.lossless_panel.checkbox_performance.set_active(bool(value)))
    lossless_hdr = property(
        lambda self: self.lossless_panel.checkbox_hdr.get_active(),
        lambda self, value: self.lossless_panel.checkbox_hdr.set_active(bool(value)))
    lossless_present = property(
        lambda self: self.lossless_panel.combobox_present.get_active_id(),
        lambda self, value: self.lossless_panel.combobox_present.set_active_id(value) or self.lossless_panel.combobox_present.set_active(0))


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


_EXCLUDED_THEME_NAMES = {"Adwaita", "Adwaita-dark", "Adwaita-empty", "Default", "Empty", "HighContrast", "HighContrastInverse"}


def list_gtk4_themes():
    search_dirs = [
        os.path.expanduser("~/.themes"),
        PathManager.user_data("themes"),
    ]
    for data_dir in os.getenv("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":"):
        search_dirs.append(os.path.join(data_dir, "themes"))

    names = set()
    for themes_dir in search_dirs:
        if not os.path.isdir(themes_dir):
            continue
        for entry in os.listdir(themes_dir):
            if entry in _EXCLUDED_THEME_NAMES:
                continue
            if os.path.isdir(os.path.join(themes_dir, entry, "gtk-4.0")):
                names.add(entry)

    return sorted(names)


def _read_appearance_setting(key):
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    result = bus.call_sync(
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Settings",
        "Read",
        GLib.Variant("(ss)", ("org.freedesktop.appearance", key)),
        None,
        Gio.DBusCallFlags.NONE,
        500,
        None,
    )
    return result.unpack()[0]


def get_system_accent_rgb():
    try:
        r, g, b = _read_appearance_setting("accent-color")
    except GLib.Error:
        return None
    return int(r * 255), int(g * 255), int(b * 255)


def get_system_prefers_dark():
    try:
        value = _read_appearance_setting("color-scheme")
    except GLib.Error:
        return None
    return {1: True, 2: False}.get(value)


def get_effective_accent_rgb():
    from faugus.config_manager import ConfigManager
    cfg = ConfigManager()
    theme_engine = cfg.config.get('theme-engine', 'adwaita').strip('"')
    accent_color = cfg.get_accent_color()

    color_name = "theme_selected_bg_color"
    if theme_engine == "adwaita":
        if accent_color and accent_color != "system":
            match = re.match(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', accent_color)
            if match:
                return tuple(int(v) for v in match.groups())
        color_name = "accent_bg_color"
    elif theme_engine == "system":
        system_accent = get_system_accent_rgb()
        if system_accent:
            return system_accent

    found, rgba = Gtk.Box().get_style_context().lookup_color(color_name)
    if found:
        return int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255)
    return (30, 30, 34)


_theme_engine_lock_handler = None


def apply_theme_engine(theme_engine):
    settings = Gtk.Settings.get_default()

    global _theme_engine_lock_handler
    if _theme_engine_lock_handler is not None:
        settings.disconnect(_theme_engine_lock_handler)
        _theme_engine_lock_handler = None

    if theme_engine == "adwaita":
        Adw.StyleManager.get_default()
        settings.set_property("gtk-theme-name", "Adwaita-empty")

        def _force_adwaita(obj, pspec):
            if obj.get_property("gtk-theme-name") != "Adwaita-empty":
                obj.set_property("gtk-theme-name", "Adwaita-empty")

        _theme_engine_lock_handler = settings.connect("notify::gtk-theme-name", _force_adwaita)
    elif theme_engine == "system":
        prefers_dark = get_system_prefers_dark()
        if prefers_dark is not None:
            settings.set_property("gtk-application-prefer-dark-theme", prefers_dark)
    elif theme_engine:
        settings.set_property("gtk-theme-name", theme_engine)


def apply_interface_customization(interface_theme, accent_color, theme_engine="adwaita"):
    if theme_engine == "adwaita":
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

    if theme_engine == "adwaita" and accent_color and accent_color != "system":
        fg_color = _contrasting_fg_color(accent_color)
        provider = Gtk.CssProvider()
        css = f"""
        @define-color accent_color {accent_color};
        @define-color accent_bg_color {accent_color};
        @define-color accent_fg_color {fg_color};
        @define-color theme_selected_bg_color {accent_color};
        @define-color theme_selected_fg_color {fg_color};
        :root {{
            --accent-color: {accent_color};
            --accent-bg-color: {accent_color};
            --accent-fg-color: {fg_color};
        }}
        link {{
            color: {accent_color};
        }}
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


@functools.cache
def get_steamgriddb_session():
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
    return session


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
        mark_invalid_widget(obj.entry_title)
        if hasattr(obj, "tab_button_widgets") and hasattr(obj, "tab_names"):
            obj.tab_button_widgets[obj.tab_names.index("page1")].set_active(True)
        return

    titles = {
        "cover": _("Choose a cover"),
        "banner": _("Choose a banner"),
        "icon": _("Choose an icon"),
    }
    ratios = {"cover": 600 / 900, "banner": BANNER_RATIO, "icon": 1.0}
    keys = {"cover": "grids", "banner": "heroes", "icon": "icons"}

    dialog = Gtk.Dialog(title=titles.get(category), transient_for=obj)
    apply_titlebar_preference(dialog)
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

    accent_r, accent_g, accent_b = get_effective_accent_rgb()
    add_css_once(
        "steamgriddb_picker_candidate",
        f"""
        .steamgriddb-candidate {{
            border: none;
            background: none;
            background-color: transparent;
            background-image: none;
            outline: none;
            box-shadow: none;
            padding: 0px;
            min-width: 0;
            min-height: 0;
        }}
        .steamgriddb-candidate:focus-visible {{
            outline: 2px solid rgba({accent_r}, {accent_g}, {accent_b}, 0.8);
            outline-offset: -2px;
        }}
        """,
        _OVERRIDE_PRIORITY,
    )

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

    search_entry = Gtk.SearchEntry()
    search_entry.set_text(game_name)
    search_entry.set_margin_start(10)
    search_entry.set_margin_end(10)
    search_entry.set_margin_top(10)

    content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    content_box.set_vexpand(True)
    content_box.set_hexpand(True)
    content_box.append(search_entry)
    content_box.append(stack)

    dialog.get_content_area().append(content_box)

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

    search_token = [0]

    def populate(items, token):
        if closed_state[0] or token != search_token[0]:
            return False
        items_container.remove_all()
        if not items:
            empty_label = Gtk.Label(label=_("No results found"))
            empty_label.set_margin_top(20)
            items_container.append(empty_label)
        for item, pixbuf in items:
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            paintable = HiDpiPaintable(texture, thumb_w, thumb_h)
            picture = new_picture(paintable)
            picture.set_cursor(Gdk.Cursor.new_from_name("pointer"))

            child = Gtk.FlowBoxChild()
            child.set_size_request(thumb_w, thumb_h)
            child.set_halign(Gtk.Align.CENTER)
            child.set_valign(Gtk.Align.START if is_list else Gtk.Align.CENTER)
            child.set_overflow(Gtk.Overflow.HIDDEN)
            child.set_child(picture)
            child.add_css_class("steamgriddb-candidate")
            child.gamepad_activate = lambda u=item["url"]: apply_selection(u)

            click = Gtk.GestureClick()
            click.set_button(Gdk.BUTTON_PRIMARY)
            click.connect("pressed", lambda g, n, x, y, u=item["url"]: apply_selection(u))
            picture.add_controller(click)

            items_container.append(child)
        stack.set_visible_child_name("content")
        return False

    def fetch_candidates(term, term_game_id, term_steam_appid, token):
        candidates = fetch_steamgriddb_candidates(
            api_key, term, limit=24, game_id=term_game_id, steam_appid=term_steam_appid
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

        if not closed_state[0] and token == search_token[0]:
            GLib.idle_add(populate, results, token)

    def start_search(term, term_game_id=None, term_steam_appid=None):
        if closed_state[0] or not term:
            return
        search_token[0] += 1
        token = search_token[0]
        stack.set_visible_child_name("loading")
        run_in_background(fetch_candidates, term, term_game_id, term_steam_appid, token)

    def on_search_activate(entry):
        start_search(entry.get_text().strip())

    search_entry.connect("activate", on_search_activate)

    start_search(game_name, game_id, steam_appid)

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


_dominant_color_cache = {}


def get_dominant_color(image_path):
    try:
        key = (image_path, os.path.getmtime(image_path))
    except OSError:
        return compute_dominant_color(image_path)
    rgb = _dominant_color_cache.get(key)
    if rgb is None:
        rgb = compute_dominant_color(image_path)
        _dominant_color_cache[key] = rgb
    return rgb


def compute_dominant_color(image_path):
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
