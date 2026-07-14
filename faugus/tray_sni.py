import os
import json

import gi
gi.require_version('GdkPixbuf', '2.0')

from gi.repository import GdkPixbuf, Gio, GLib
from faugus.path_manager import faugus_mono_icon, faugus_png, games_json, latest_games
from faugus.language_config import setup_gettext

_ = setup_gettext('faugus-launcher')

ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"

ITEM_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="i" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconPixmap" type="a(iiay)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <method name="Activate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="SecondaryActivate">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="ContextMenu">
      <arg type="i" name="x" direction="in"/>
      <arg type="i" name="y" direction="in"/>
    </method>
    <method name="Scroll">
      <arg type="i" name="delta" direction="in"/>
      <arg type="s" name="orientation" direction="in"/>
    </method>
    <signal name="NewIcon"/>
    <signal name="NewTitle"/>
    <signal name="NewStatus">
      <arg type="s" name="status"/>
    </signal>
    <signal name="NewToolTip"/>
  </interface>
</node>
"""

MENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg type="i" name="parentId" direction="in"/>
      <arg type="i" name="recursionDepth" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="u" name="revision" direction="out"/>
      <arg type="(ia{sv}av)" name="layout" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" name="ids" direction="in"/>
      <arg type="as" name="propertyNames" direction="in"/>
      <arg type="a(ia{sv})" name="properties" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="name" direction="in"/>
      <arg type="v" name="value" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" name="id" direction="in"/>
      <arg type="s" name="eventId" direction="in"/>
      <arg type="v" name="data" direction="in"/>
      <arg type="u" name="timestamp" direction="in"/>
    </method>
    <method name="AboutToShow">
      <arg type="i" name="id" direction="in"/>
      <arg type="b" name="needUpdate" direction="out"/>
    </method>
    <signal name="ItemsPropertiesUpdated">
      <arg type="a(ia{sv})" name="updatedProps"/>
      <arg type="a(ias)" name="removedProps"/>
    </signal>
    <signal name="LayoutUpdated">
      <arg type="u" name="revision"/>
      <arg type="i" name="parent"/>
    </signal>
  </interface>
</node>
"""


def load_json_file(filepath, default=None):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []


def load_icon_pixmap(svg_path, size=64):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(svg_path, size, size, True)
    if not pixbuf.get_has_alpha():
        pixbuf = pixbuf.add_alpha(False, 0, 0, 0)

    width = pixbuf.get_width()
    height = pixbuf.get_height()
    rowstride = pixbuf.get_rowstride()
    pixels = pixbuf.get_pixels()

    argb = bytearray(width * height * 4)
    for y in range(height):
        row = y * rowstride
        for x in range(width):
            i = row + x * 4
            o = (y * width + x) * 4
            argb[o], argb[o + 1], argb[o + 2], argb[o + 3] = pixels[i + 3], pixels[i], pixels[i + 1], pixels[i + 2]

    return width, height, bytes(argb)


def resolve_icon_path(mono_icon):
    return faugus_mono_icon if mono_icon else faugus_png


class TrayIcon:
    def __init__(self, mono_icon, on_present, on_quit, on_launch):
        self.on_present = on_present
        self.on_quit = on_quit
        self.on_launch = on_launch

        self.icon_pixmap = load_icon_pixmap(resolve_icon_path(mono_icon))

        self.item_info = Gio.DBusNodeInfo.new_for_xml(ITEM_XML).interfaces[0]
        self.menu_info = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]

        self.menu_items = []
        self.menu_revision = 0

        self.connection = None
        self.watch_id = None
        self.item_reg_id = None
        self.menu_reg_id = None

    def start(self):
        address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
        connection = Gio.DBusConnection.new_for_address_sync(
            address,
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None, None,
        )
        self.connection = connection

        register = getattr(connection, "register_object_with_closures2", connection.register_object)
        self.item_reg_id = register(
            ITEM_PATH, self.item_info, self.on_item_method_call, self.on_item_get_property, None)
        self.menu_reg_id = register(
            MENU_PATH, self.menu_info, self.on_menu_method_call, self.on_menu_get_property, None)

        self.watch_id = Gio.bus_watch_name_on_connection(
            connection,
            "org.kde.StatusNotifierWatcher",
            Gio.BusNameWatcherFlags.NONE,
            self.on_watcher_appeared,
            None,
        )

    def stop(self):
        if self.watch_id:
            Gio.bus_unwatch_name(self.watch_id)
        if self.connection:
            if self.item_reg_id:
                self.connection.unregister_object(self.item_reg_id)
            if self.menu_reg_id:
                self.connection.unregister_object(self.menu_reg_id)
            self.connection.close_sync(None)
        self.connection = None
        self.watch_id = None

    def on_watcher_appeared(self, connection, name, owner):
        connection.call(
            "org.kde.StatusNotifierWatcher",
            "/StatusNotifierWatcher",
            "org.kde.StatusNotifierWatcher",
            "RegisterStatusNotifierItem",
            GLib.Variant("(s)", (ITEM_PATH,)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
        )

    def on_item_get_property(self, connection, sender, path, interface, prop_name):
        if prop_name == "Category":
            return GLib.Variant("s", "ApplicationStatus")
        if prop_name == "Id":
            return GLib.Variant("s", "faugus-launcher")
        if prop_name == "Title":
            return GLib.Variant("s", "Faugus Launcher")
        if prop_name == "Status":
            return GLib.Variant("s", "Active")
        if prop_name == "WindowId":
            return GLib.Variant("i", 0)
        if prop_name == "IconName":
            return GLib.Variant("s", "")
        if prop_name == "IconPixmap":
            w, h, data = self.icon_pixmap
            return GLib.Variant("a(iiay)", [(w, h, data)])
        if prop_name == "ItemIsMenu":
            return GLib.Variant("b", False)
        if prop_name == "Menu":
            return GLib.Variant("o", MENU_PATH)
        if prop_name == "ToolTip":
            return GLib.Variant("(sa(iiay)ss)", ("", [], "Faugus Launcher", ""))
        return None

    def on_item_method_call(self, connection, sender, path, interface, method, params, invocation):
        if method == "Activate":
            self.on_present()
        invocation.return_value(None)

    def rebuild_menu(self):
        games_by_id = {}
        for entry in load_json_file(games_json, []):
            gameid = entry.get("gameid")
            if gameid:
                games_by_id[gameid] = entry.get("title", gameid)

        items = []
        item_id = 1

        if os.path.exists(latest_games):
            with open(latest_games) as f:
                for gameid in map(str.strip, f):
                    if len(items) >= 5:
                        break
                    title = games_by_id.get(gameid)
                    if not title:
                        continue
                    items.append({"id": item_id, "label": title, "action": lambda gid=gameid: self.on_launch(gid)})
                    item_id += 1

        if items:
            items.append({"id": item_id, "separator": True})
            item_id += 1

        items.append({"id": item_id, "label": _("Open Faugus"), "action": self.on_present})
        item_id += 1
        items.append({"id": item_id, "label": _("Quit"), "action": self.on_quit})

        self.menu_items = items
        self.menu_revision += 1

    def on_menu_get_property(self, connection, sender, path, interface, prop_name):
        if prop_name == "Version":
            return GLib.Variant("u", 3)
        if prop_name == "TextDirection":
            return GLib.Variant("s", "ltr")
        if prop_name == "Status":
            return GLib.Variant("s", "normal")
        if prop_name == "IconThemePath":
            return GLib.Variant("as", [])
        return None

    def build_item_properties(self, item):
        if item.get("separator"):
            return {"type": GLib.Variant("s", "separator")}
        return {
            "label": GLib.Variant("s", item["label"]),
            "enabled": GLib.Variant("b", True),
            "visible": GLib.Variant("b", True),
        }

    def on_menu_method_call(self, connection, sender, path, interface, method, params, invocation):
        if method == "AboutToShow":
            self.rebuild_menu()
            invocation.return_value(GLib.Variant("(b)", (True,)))

        elif method == "GetLayout":
            parent_id = params[0]
            if parent_id != 0:
                invocation.return_value(GLib.Variant("(u(ia{sv}av))", (self.menu_revision, (parent_id, {}, []))))
                return

            children = [
                GLib.Variant("(ia{sv}av)", (item["id"], self.build_item_properties(item), []))
                for item in self.menu_items
            ]
            layout = (0, {}, children)
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (self.menu_revision, layout)))

        elif method == "GetGroupProperties":
            ids = params[0]
            result = [(item["id"], self.build_item_properties(item)) for item in self.menu_items if item["id"] in ids]
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (result,)))

        elif method == "GetProperty":
            item_id, name = params[0], params[1]
            item = next((i for i in self.menu_items if i["id"] == item_id), None)
            props = self.build_item_properties(item) if item else {}
            value = props.get(name, GLib.Variant("s", ""))
            invocation.return_value(GLib.Variant("(v)", (value,)))

        elif method == "Event":
            item_id, event_id = params[0], params[1]
            if event_id == "clicked":
                item = next((i for i in self.menu_items if i["id"] == item_id), None)
                if item and item.get("action"):
                    item["action"]()
            invocation.return_value(None)

        else:
            invocation.return_value(None)
