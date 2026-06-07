import os
import re
import subprocess
from faugus.path_manager import PathManager, IS_FLATPAK
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
