import json
import os
import signal
import subprocess
import sys

import gi
from gi.repository import Gio, GLib

from faugus.path_manager import APP_ID, CONFIG_FILE_DIR, RUNNING_GAMES, TRAY_BUS_NAME, TRAY_INTERFACE, TRAY_OBJECT_PATH, subprocess_env
from faugus.tray_sni import TrayIcon

TRAY_CONTROL_XML = f"""
<node>
  <interface name="{TRAY_INTERFACE}">
    <method name="Quit"/>
    <method name="Restart">
      <arg type="b" name="launch_ui" direction="in"/>
    </method>
    <method name="Shutdown"/>
    <method name="RefreshMenu"/>
    <method name="Open"/>
  </interface>
</node>
"""


def load_config():
    try:
        with open(CONFIG_FILE_DIR, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load_running_ids():
    try:
        with open(RUNNING_GAMES, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def spawn(module_args):
    proc = subprocess.Popen(
        [sys.executable, "-m"] + module_args,
        env=subprocess_env(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    GLib.child_watch_add(proc.pid, lambda pid, status: None)


def spawn_ui(console_mode=False):
    args = ["faugus.launcher", "--ui-child"]
    if console_mode:
        args.append("--console")
    spawn(args)


def run_tray_entrypoint(launch_ui, console_mode=False):
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    result = connection.call_sync(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "RequestName",
        GLib.Variant("(su)", (TRAY_BUS_NAME, 0x4)),  # DBUS_NAME_FLAG_DO_NOT_QUEUE
        GLib.VariantType.new("(u)"),
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    if result.unpack()[0] != 1:  # not DBUS_REQUEST_NAME_REPLY_PRIMARY_OWNER
        if launch_ui:
            try:
                connection.call_sync(
                    TRAY_BUS_NAME, TRAY_OBJECT_PATH, TRAY_INTERFACE, "Open",
                    None, None, Gio.DBusCallFlags.NONE, -1, None,
                )
            except GLib.Error:
                pass
        return

    config = load_config()
    mono_icon = config.get("mono-icon", "False") == "True"

    loop = GLib.MainLoop()

    def on_present():
        spawn_ui(console_mode)

    def on_quit():
        tray_connection = tray.connection
        if tray_connection:
            try:
                action_group = Gio.DBusActionGroup.get(tray_connection, APP_ID, "/io/github/Faugus/faugus_launcher")
                action_group.activate_action("quit", None)
            except GLib.Error:
                pass
        loop.quit()

    def on_launch(gameid):
        if gameid in load_running_ids():
            return
        spawn(["faugus.runner", "--game", gameid])

    tray = TrayIcon(mono_icon=mono_icon, on_present=on_present, on_quit=on_quit, on_launch=on_launch)
    tray.start()

    def do_restart(launch_ui):
        tray.stop()
        argv = [sys.executable, "-m", "faugus.tray_only"]
        if not launch_ui:
            argv.append("--hide")
        os.execv(sys.executable, argv)

    def do_shutdown():
        tray.stop()
        os.execv(sys.executable, [sys.executable, "-m", "faugus.launcher"])

    def on_control_method_call(connection, sender, path, interface, method, params, invocation):
        invocation.return_value(None)
        if method == "Quit":
            on_quit()
        elif method == "Restart":
            launch_ui = params[0]
            GLib.timeout_add(100, lambda: (do_restart(launch_ui), False)[1])
        elif method == "Shutdown":
            GLib.timeout_add(100, lambda: (do_shutdown(), False)[1])
        elif method == "RefreshMenu":
            tray.notify_menu_changed()
        elif method == "Open":
            spawn_ui(console_mode)

    control_info = Gio.DBusNodeInfo.new_for_xml(TRAY_CONTROL_XML).interfaces[0]
    register = getattr(connection, "register_object_with_closures2", connection.register_object)
    register(TRAY_OBJECT_PATH, control_info, on_control_method_call, None, None)

    def on_sigterm():
        loop.quit()
        return GLib.SOURCE_REMOVE

    signal_added = False
    try:
        gi.require_version('GLibUnix', '2.0')
        from gi.repository import GLibUnix
        if hasattr(GLibUnix, 'signal_add'):
            GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, on_sigterm)
            signal_added = True
    except (ValueError, ImportError):
        pass
    if not signal_added:
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, on_sigterm)

    if launch_ui:
        spawn_ui(console_mode)

    loop.run()

    tray.stop()


def bootstrap():
    start_hidden = "--hide" in sys.argv
    console_mode = "--console" in sys.argv
    rest = [a for a in sys.argv[1:] if a not in ("--hide", "--console")]

    if len(rest) == 1:
        os.execv(sys.executable, [sys.executable, "-m", "faugus.launcher"] + sys.argv[1:])
        return

    config = load_config()
    if config.get("system-tray", "False") != "True":
        ui_args = []
        if start_hidden:
            ui_args.append("--hide")
        if console_mode:
            ui_args.append("--console")
        os.execv(sys.executable, [sys.executable, "-m", "faugus.launcher"] + ui_args)
        return

    run_tray_entrypoint(launch_ui=not start_hidden, console_mode=console_mode)


if __name__ == "__main__":
    bootstrap()
