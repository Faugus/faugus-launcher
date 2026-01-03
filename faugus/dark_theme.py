import os
from gi.repository import Gtk, Gio, GLib
IS_FLATPAK = 'FLATPAK_ID' in os.environ or os.path.exists('/.flatpak-info')

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